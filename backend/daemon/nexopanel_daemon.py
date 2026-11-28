"""Privilege-separated root helper daemon listening on a 0600 Unix domain socket.

Strict command-schema validation ensures only allowlisted binaries *and* only
arguments matching a per-binary schema can be executed, and only permitted
configuration paths can be mutated by the unprivileged FastAPI worker.

Security notes:
* The allowlist is intentionally minimal: every binary listed here is actually
  used by the control plane, and each one has an argument schema below.  A
  binary on its own is never enough (e.g. ``/usr/bin/cp`` or ``/usr/bin/tar``
  are only usable with paths inside the panel-owned roots).
* File writes use ``O_NOFOLLOW`` and create the target with its final mode, so
  a symlink planted by a less-privileged user cannot redirect a root write and
  secrets are never briefly world-readable.
"""
from __future__ import annotations

import asyncio
import base64
import errno
import grp
import ipaddress
import json
import os
import pwd
import re
import shutil
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SOCKET_PATH = Path(os.environ.get("NEXOPANEL_DAEMON_SOCKET_PATH", "/run/nexopanel/daemon.sock"))

# SQL dumps are streamed to the database client on stdin, so a single request
# line can legitimately be large (up to this cap) rather than the 64 KiB default.
MAX_REQUEST_BYTES = 64 * 1024 * 1024

ALLOWED_BINARIES: set[str] = {
    "/usr/sbin/nginx",
    "/bin/systemctl",
    "/usr/bin/systemctl",
    "/usr/bin/apt-get",
    "/usr/bin/dpkg-query",
    "/usr/sbin/named-checkzone",
    "/usr/sbin/postsuper",
    "/usr/sbin/postqueue",
    "/usr/sbin/postmap",
    "/usr/bin/mariadb",
    "/usr/bin/mariadb-dump",
    "/usr/bin/psql",
    "/usr/bin/pg_dump",
    "/usr/bin/certbot",
    "/usr/sbin/ufw",
    "/usr/bin/fail2ban-client",
    "/usr/bin/docker",
    "/bin/cp",
    "/usr/bin/cp",
}

ALLOWED_WRITE_PREFIXES: tuple[str, ...] = (
    "/etc/nginx/",
    "/etc/bind/",
    "/etc/postfix/",
    "/etc/dovecot/",
    "/etc/opendkim/",
    "/etc/letsencrypt/",
    "/var/www/",
    "/var/mail/vhosts/",
    "/var/backups/nexopanel/",
)

# Root-only scratch directory is no longer needed: the control plane performs
# archive handling in-process (tarfile) and downloads through the API worker.

# Roots the file manager may mutate through the privileged daemon. This is
# intentionally narrower than ALLOWED_WRITE_PREFIXES: the file manager must
# never be able to touch system configuration such as /etc/nginx/nginx.conf.
FILE_MANAGER_PREFIXES: tuple[str, ...] = (
    "/var/www/",
    "/var/backups/nexopanel/",
    "/etc/nginx/sites-available/",
)

# Private staging directory used to hand content (archives, extracted trees)
# from the unprivileged worker over to the privileged daemon. Only files that
# live inside this directory may be installed into the panel-owned roots.
TEMP_BASE = Path(os.environ.get("NEXOPANEL_DAEMON_TEMP_DIR", "/run/nexopanel/tmp"))

# `cp` is only used to migrate FTP home directories, so it is restricted to the
# panel-owned web/backups roots instead of every writable configuration root.
CP_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/var/www/",
    "/var/backups/nexopanel/",
)

SERVICE_UNIT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,63}(\.service)?$")
PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.:-]{0,127}$")
DB_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
ZONE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,253}$")
DOCKER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
DOCKER_IMAGE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,255}$")
DOMAIN_RE = re.compile(r"^(?:\*\.)?(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")
PORT_SPEC_RE = re.compile(r"^(?:\d{1,5})(?::\d{1,5})?/(?:tcp|udp)$")

SYSTEMCTL_ACTIONS = {
    "start",
    "stop",
    "restart",
    "reload",
    "reload-or-restart",
    "force-reload",
    "status",
    "is-active",
    "enable",
    "disable",
    "reopen",
    "reopenlogs",
}

APT_ACTIONS = {"update", "install", "remove", "purge", "upgrade", "--only-upgrade"}
APT_FLAGS = {"-y", "-q", "-qq", "--only-upgrade", "--allow-downgrades", "--allow-remove-essential"}

NGINX_SIGNALS = {"reload", "reopen"}

DB_CLIENT_FLAGS = {
    "-e",
    "--execute",
    "-c",
    "--command",
    "-N",
    "-s",
    "-A",
    "-t",
    "--batch",
    "--skip-column-names",
    "--no-align",
    "-U",
    "--username",
    "-d",
    "--dbname",
    "--tuples-only",
    "-B",
    "-F",
    "--field-separator",
}

DOCKER_ACTIONS = {"ps", "images", "pull", "start", "stop", "restart", "rm", "logs", "inspect"}
DOCKER_FLAGS = {"-a", "--all", "--format", "-q", "--quiet", "--no-trunc", "--tail", "-f", "--follow"}

UFW_ACTIONS = {"status", "allow", "delete", "enable", "disable", "reload", "show"}
CERTBOT_ACTIONS = {"certonly", "renew"}
CERTBOT_VALUE_FLAGS = {"-d", "--domain", "-n", "--cert-name", "-w", "--webroot-path", "-m", "--email"}
CERTBOT_FLAGS = {"--non-interactive", "--agree-tos", "--force-renewal", "--quiet", "-q", "--keep-until-expiring", "--standalone", "--nginx", "--apache", "--webroot"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}$")
FAIL2BAN_ACTIONS = {"status", "set"}
FAIL2BAN_JAIL_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
QUEUE_ID_RE = re.compile(r"^[A-F0-9]{6,20}$")

# Only these upstreams may be contacted by the privileged downloader.
ALLOWED_FETCH_HOSTS = {
    "wordpress.org",
    "www.wordpress.org",
    "github.com",
    "codeload.github.com",
    "api.github.com",
    "raw.githubusercontent.com",
}


def _is_allowed_path(path_str: str, prefixes: tuple[str, ...] = ALLOWED_WRITE_PREFIXES) -> bool:
    """Resolve symlinks and '..' before comparing against the write allowlist."""
    if not path_str or "\x00" in path_str or ".." in Path(path_str).parts:
        return False
    resolved = Path(os.path.realpath(path_str))
    for prefix in prefixes:
        root = Path(os.path.realpath(prefix))
        if resolved == root or root in resolved.parents:
            return True
    return False


def _is_file_manager_path(path_str: str) -> bool:
    """True when the path may be mutated through the file-manager operations."""
    return _is_allowed_path(path_str, FILE_MANAGER_PREFIXES)


def _is_staging_path(path_str: str) -> bool:
    """True when the path lives inside the daemon's private staging directory.

    Only content prepared by the unprivileged worker inside this directory may
    be installed into the panel-owned roots, so the daemon can never be used to
    copy an arbitrary root-only file (e.g. /etc/shadow) somewhere readable.
    """
    if not path_str or "\x00" in path_str:
        return False
    resolved = Path(os.path.realpath(path_str))
    base = Path(os.path.realpath(TEMP_BASE))
    if resolved == base or base not in resolved.parents:
        return False
    parent = resolved.parent
    try:
        info = parent.stat()
    except OSError:
        return False
    if info.st_mode & 0o022:  # group/other writable
        return False
    try:
        panel_uid = pwd.getpwnam("nexopanel").pw_uid
    except KeyError:
        panel_uid = -1
    return info.st_uid in (0, panel_uid)


def _is_flag(arg: str) -> bool:
    return arg.startswith("-")


def _validate_systemctl(args: list[str]) -> str | None:
    if len(args) != 2:
        return "systemctl expects exactly <action> <unit>"
    action, unit = args
    if action not in SYSTEMCTL_ACTIONS:
        return f"Unsupported systemd action: {action}"
    if not SERVICE_UNIT_RE.match(unit):
        return f"Invalid systemd unit: {unit}"
    return None


def _validate_nginx(args: list[str]) -> str | None:
    if args in (["-t"], ["-s", "reopen"], ["-s", "reload"]):
        return None
    if len(args) == 2 and args[0] == "-c" and _is_allowed_path(args[1]):
        return None
    return "Unsupported nginx invocation"


def _validate_apt_get(args: list[str]) -> str | None:
    if not args:
        return "apt-get requires an action"
    action = args[0]
    if action not in APT_ACTIONS:
        return f"Unsupported apt-get action: {action}"
    for arg in args[1:]:
        if arg in APT_FLAGS:
            continue
        if not PACKAGE_NAME_RE.match(arg):
            return f"Invalid package name: {arg}"
    return None


def _validate_dpkg_query(args: list[str]) -> str | None:
    for arg in args:
        if arg == "-W" or arg.startswith("-f="):
            continue
        return f"Unsupported dpkg-query argument: {arg}"
    return None


def _validate_named_checkzone(args: list[str]) -> str | None:
    if len(args) != 2:
        return "named-checkzone expects <zone> <zonefile>"
    zone, zone_file = args
    if not ZONE_NAME_RE.match(zone):
        return f"Invalid zone name: {zone}"
    if not _is_allowed_path(zone_file):
        return f"Zone file not permitted: {zone_file}"
    return None


def _validate_postmap(args: list[str]) -> str | None:
    if len(args) != 1 or not _is_allowed_path(args[0]):
        return "postmap expects a single permitted map file"
    return None


def _validate_postqueue(args: list[str]) -> str | None:
    if len(args) > 1 or (args and args[0] not in {"-j", "-f"}):
        return "Unsupported postqueue invocation"
    return None


def _validate_postsuper(args: list[str]) -> str | None:
    if len(args) != 2:
        return "postsuper expects <flag> <queue-id>"
    flag, queue_id = args
    if flag not in {"-d", "-h", "-H", "-r"}:
        return f"Unsupported postsuper flag: {flag}"
    if not QUEUE_ID_RE.match(queue_id):
        return "Invalid queue id"
    return None


def _validate_db_client(args: list[str], *, allow_sql: bool = True) -> str | None:
    """Validate argv for mariadb/psql/mysqldump/pg_dump style clients.

    Only the SQL text (the argument following -e/--execute/-c/--command) is
    free-form; every other positional argument must be a plain identifier.
    """
    skip_next = False
    value_flag: str | None = None
    for arg in args:
        if skip_next:
            skip_next = False
            if value_flag is not None and not DB_IDENTIFIER_RE.match(arg):
                return f"Invalid database identifier: {arg}"
            continue
        if arg in {"-e", "--execute", "-c", "--command"}:
            if not allow_sql:
                return "SQL execution is not permitted for this command"
            skip_next = True
            value_flag = None
            continue
        if arg in {"-U", "--username", "-d", "--dbname"}:
            skip_next = True
            value_flag = arg
            continue
        if arg in {"-F", "--field-separator"}:
            skip_next = True
            value_flag = "raw"
            continue
        if _is_flag(arg):
            if arg not in DB_CLIENT_FLAGS and arg not in {"-f"} and not arg.startswith("--format="):
                return f"Unsupported database client flag: {arg}"
            continue
        if not DB_IDENTIFIER_RE.match(arg):
            return f"Invalid database identifier: {arg}"
    return None


def _validate_certbot(args: list[str]) -> str | None:
    if not args or args[0] not in CERTBOT_ACTIONS:
        return "Unsupported certbot action"
    pending_flag: str | None = None
    for arg in args[1:]:
        if pending_flag is not None:
            flag, pending_flag = pending_flag, None
            if flag in {"-d", "--domain"}:
                if not DOMAIN_RE.match(arg):
                    return f"Invalid domain: {arg}"
            elif flag in {"-w", "--webroot-path"}:
                if not arg.startswith("/var/www/acme-challenge"):
                    return f"Invalid webroot path: {arg}"
            elif flag in {"-m", "--email"}:
                if not EMAIL_RE.match(arg):
                    return "Invalid email address"
            elif flag in {"-n", "--cert-name"}:
                if not re.match(r"^[A-Za-z0-9._-]{1,64}$", arg):
                    return "Invalid certificate name"
            continue
        if arg in CERTBOT_VALUE_FLAGS:
            pending_flag = arg
            continue
        if arg in CERTBOT_FLAGS:
            continue
        if arg.startswith("-"):
            return f"Unsupported certbot flag: {arg}"
        if not DOMAIN_RE.match(arg):
            return f"Invalid domain: {arg}"
    if pending_flag is not None:
        return f"Missing value for {pending_flag}"
    return None


def _validate_ufw(args: list[str]) -> str | None:
    if not args or args[0] not in UFW_ACTIONS:
        return "Unsupported ufw action"
    for arg in args[1:]:
        if PORT_SPEC_RE.match(arg) or arg in {"any", "default", "verbose", "numbered", "allow", "deny", "reject", "limit"}:
            continue
        if _is_flag(arg):
            return f"Unsupported ufw flag: {arg}"
        return f"Invalid ufw argument: {arg}"
    return None


def _validate_fail2ban(args: list[str]) -> str | None:
    if not args or args[0] not in FAIL2BAN_ACTIONS:
        return "Unsupported fail2ban-client action"
    if args[0] == "status":
        if len(args) == 1:
            return None
        if len(args) == 2 and FAIL2BAN_JAIL_RE.match(args[1]):
            return None
        return "Invalid fail2ban jail"
    # set <jail> unbanip <ip>
    if len(args) == 4 and args[2] == "unbanip" and FAIL2BAN_JAIL_RE.match(args[1]):
        try:
            ipaddress.ip_address(args[3])
        except ValueError:
            return "Invalid IP address"
        return None
    return "Unsupported fail2ban-client invocation"


def _validate_docker(args: list[str]) -> str | None:
    if not args or args[0] not in DOCKER_ACTIONS:
        return "Unsupported docker action"
    value_flags = {"--format", "--tail"}
    expect_value = False
    for arg in args[1:]:
        if expect_value:
            expect_value = False
            continue
        if arg in value_flags:
            expect_value = True
            continue
        if arg in DOCKER_FLAGS:
            continue
        if arg.startswith("--format="):
            continue
        if _is_flag(arg):
            return f"Unsupported docker flag: {arg}"
        if args[0] == "pull":
            if not DOCKER_IMAGE_RE.match(arg):
                return f"Invalid image reference: {arg}"
        elif not DOCKER_NAME_RE.match(arg):
            return f"Invalid container reference: {arg}"
    return None


def _validate_cp(args: list[str]) -> str | None:
    """cp is only used to migrate FTP home directories inside panel-owned roots."""
    paths: list[str] = []
    for arg in args:
        if arg in {"-r", "-p", "-a", "-rp", "-pr", "-aL", "-rL", "--preserve=mode", "--preserve=ownership"}:
            continue
        if _is_flag(arg):
            return f"Unsupported cp flag: {arg}"
        paths.append(arg)
    if len(paths) < 2:
        return "cp requires a source and a destination"
    for path_str in paths:
        if not _is_allowed_path(path_str):
            return f"cp path not permitted: {path_str}"
        resolved = Path(os.path.realpath(path_str))
        if not any(
            resolved == Path(os.path.realpath(prefix)) or Path(os.path.realpath(prefix)) in resolved.parents
            for prefix in CP_ALLOWED_PREFIXES
        ):
            return f"cp path not permitted: {path_str}"
    return None


_EXEC_VALIDATORS = {
    "/bin/systemctl": _validate_systemctl,
    "/usr/bin/systemctl": _validate_systemctl,
    "/usr/sbin/nginx": _validate_nginx,
    "/usr/bin/apt-get": _validate_apt_get,
    "/usr/bin/dpkg-query": _validate_dpkg_query,
    "/usr/sbin/named-checkzone": _validate_named_checkzone,
    "/usr/sbin/postmap": _validate_postmap,
    "/usr/sbin/postqueue": _validate_postqueue,
    "/usr/sbin/postsuper": _validate_postsuper,
    "/usr/bin/mariadb": _validate_db_client,
    "/usr/bin/mariadb-dump": _validate_db_client,
    "/usr/bin/psql": _validate_db_client,
    "/usr/bin/pg_dump": _validate_db_client,
    "/usr/bin/certbot": _validate_certbot,
    "/usr/sbin/ufw": _validate_ufw,
    "/usr/bin/fail2ban-client": _validate_fail2ban,
    "/usr/bin/docker": _validate_docker,
    "/bin/cp": _validate_cp,
    "/usr/bin/cp": _validate_cp,
}


def _validate_exec_args(args: list[str]) -> str | None:
    """Validate the full argv (not just argv[0]) against the per-binary schema."""
    validator = _EXEC_VALIDATORS.get(args[0])
    if validator is None:
        return f"No argument schema for {args[0]}"
    return validator(args[1:])


# Maximum amount of data the daemon will read back for the API worker.
MAX_PRIVILEGED_READ_BYTES = 32 * 1024 * 1024


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of *data* (os.write may write partially)."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _resolve_ids(owner: str | None, group: str | None) -> tuple[int, int] | None:
    """Resolve optional owner/group names to uid/gid, or None if unknown."""
    if not owner and not group:
        return None
    uid = gid = -1
    if owner:
        try:
            uid = pwd.getpwnam(owner).pw_uid
        except KeyError:
            return None
    if group:
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError:
            return None
    return uid, gid


def _chown_path(target: Path, owner: str | None, group: str | None) -> None:
    """Best-effort ownership change; failures are not fatal."""
    ids = _resolve_ids(owner, group)
    if ids is None:
        return
    uid, gid = ids
    try:
        os.chown(target, uid, gid)
    except OSError:
        pass


def _read_regular_file(path: Path, max_bytes: int = MAX_PRIVILEGED_READ_BYTES) -> bytes:
    """Read a regular file without following symlinks."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        if info.st_size > max_bytes:
            raise OSError(errno.EFBIG, "file too large")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _copy_tree_contents(src: Path, dst: Path) -> None:
    """Copy the contents of *src* into *dst* without changing dst's own mode.

    ``shutil.copytree`` would apply the source directory's mode to the
    destination root (via copystat), which can make the destination unusable
    for its new owner.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        target = dst / entry.name
        if entry.is_symlink():
            continue
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(entry, target, follow_symlinks=False)


def _ensure_owner_accessible(root: Path, owner: str | None, group: str | None) -> None:
    """Make the installed tree usable by its owner and give it the right owner.

    Archive entries may carry very restrictive modes (e.g. 0000) which would
    leave the installed files unusable, so the owner always keeps read/write
    access on directories and read/write on files.
    """
    for current, dirs, files in os.walk(root):
        for name in dirs:
            target = Path(current) / name
            try:
                os.chmod(target, (target.stat().st_mode & 0o777) | 0o700)
            except OSError:
                pass
            _chown_path(target, owner, group)
        for name in files:
            target = Path(current) / name
            try:
                os.chmod(target, (target.stat().st_mode & 0o777) | 0o600)
            except OSError:
                pass
            _chown_path(target, owner, group)
    try:
        os.chmod(root, (root.stat().st_mode & 0o777) | 0o700)
    except OSError:
        pass
    _chown_path(root, owner, group)


def _open_regular_file_for_write(target: Path, mode: int) -> int:
    """Open a file for writing without following symlinks.

    Returns a file descriptor opened with the final permissions so the file is
    never briefly readable by other users, and a planted symlink cannot
    redirect the privileged write.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(target, flags, mode)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "target is not a regular file")
        os.fchmod(fd, mode)
    except Exception:
        os.close(fd)
        raise
    return fd


async def handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    op = payload.get("op")

    if op == "exec":
        args = payload.get("args")
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            return {"returncode": 1, "stdout": "", "stderr": "Invalid command argument list"}
        if args[0] not in ALLOWED_BINARIES:
            return {"returncode": 126, "stdout": "", "stderr": f"Binary not allowlisted: {args[0]}"}
        validation_error = _validate_exec_args(args)
        if validation_error:
            return {"returncode": 126, "stdout": "", "stderr": f"Command rejected: {validation_error}"}
        timeout = min(int(payload.get("timeout", 120)), 600)
        stdin_data = payload.get("stdin")
        if stdin_data is not None and not isinstance(stdin_data, str):
            return {"returncode": 1, "stdout": "", "stderr": "Invalid stdin payload"}
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(input=stdin_data.encode("utf-8") if stdin_data is not None else None),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()  # reap the child; otherwise it lingers as a zombie
            return {"returncode": 124, "stdout": "", "stderr": "Command timed out"}
        return {
            "returncode": proc.returncode or 0,
            "stdout": out_b.decode("utf-8", errors="replace"),
            "stderr": err_b.decode("utf-8", errors="replace"),
        }

    if op == "write_file":
        path_str = str(payload.get("path", ""))
        content = str(payload.get("content", ""))
        mode = int(payload.get("mode", 0o644))
        if not _is_allowed_path(path_str):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        target = Path(path_str)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Re-validate the parent after creating it: a symlinked parent must
            # not be able to redirect the privileged write outside the roots.
            if not _is_allowed_path(str(target.parent)):
                return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
            fd = _open_regular_file_for_write(target, mode)
            try:
                os.write(fd, content.encode("utf-8"))
            finally:
                os.close(fd)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Write failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": "written", "stderr": ""}

    if op == "symlink":
        target_str = str(payload.get("target", ""))
        link_str = str(payload.get("link_path", ""))
        if not _is_allowed_path(target_str) or not _is_allowed_path(link_str):
            return {"returncode": 1, "stdout": "", "stderr": "Symlink path not permitted"}
        link = Path(link_str)
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target_str)
        return {"returncode": 0, "stdout": "linked", "stderr": ""}

    if op == "remove_file":
        path_str = str(payload.get("path", ""))
        if not _is_allowed_path(path_str):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        p = Path(path_str)
        if p.exists() or p.is_symlink():
            p.unlink()
        return {"returncode": 0, "stdout": "removed", "stderr": ""}

    if op == "ensure_dir":
        path_str = str(payload.get("path", ""))
        owner = str(payload.get("owner", "www-data"))
        group = str(payload.get("group", "www-data"))
        mode = int(payload.get("mode", 0o755))
        scope = payload.get("scope")
        allowed = _is_file_manager_path(path_str) if scope == "file_manager" else _is_allowed_path(path_str)
        if not allowed:
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        os.chmod(p, mode)
        try:
            uid = pwd.getpwnam(owner).pw_uid
            gid = grp.getgrnam(group).gr_gid
            os.chown(p, uid, gid)
        except KeyError:
            pass
        return {"returncode": 0, "stdout": "created", "stderr": ""}

    # --- File manager operations (the API worker is unprivileged and cannot
    # always write the web roots directly) -------------------------------

    if op == "write_bytes":
        path_str = str(payload.get("path", ""))
        content_b64 = str(payload.get("content_b64", ""))
        mode = int(payload.get("mode", 0o644))
        append = bool(payload.get("append", False))
        owner = payload.get("owner")
        group = payload.get("group")
        if not _is_file_manager_path(path_str):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        if mode & 0o7000:
            return {"returncode": 1, "stdout": "", "stderr": "setuid/setgid bits are not permitted"}
        try:
            data = base64.b64decode(content_b64, validate=True)
        except Exception:
            return {"returncode": 1, "stdout": "", "stderr": "Invalid base64 payload"}
        target = Path(path_str)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Re-validate the parent after creating it: a symlinked parent must
            # not be able to redirect the privileged write outside the roots.
            if not _is_allowed_path(str(target.parent)):
                return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
            if append:
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                fd = os.open(target, flags, mode)
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise OSError(errno.EINVAL, "target is not a regular file")
                    os.fchmod(fd, mode)
                    _write_all(fd, data)
                finally:
                    os.close(fd)
            else:
                fd = _open_regular_file_for_write(target, mode)
                try:
                    _write_all(fd, data)
                finally:
                    os.close(fd)
            _chown_path(target, owner, group)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Write failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": "written", "stderr": ""}

    if op == "read_file":
        path_str = str(payload.get("path", ""))
        if not _is_file_manager_path(path_str):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        try:
            data = _read_regular_file(Path(path_str))
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Read failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": base64.b64encode(data).decode("ascii"), "stderr": ""}

    if op == "move_item":
        source = str(payload.get("source", ""))
        destination = str(payload.get("destination", ""))
        owner = payload.get("owner")
        group = payload.get("group")
        if not _is_file_manager_path(source) or not _is_file_manager_path(destination):
            return {"returncode": 1, "stdout": "", "stderr": "Path not permitted"}
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            return {"returncode": 1, "stdout": "", "stderr": f"Source not found: {source}"}
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Move failed: {exc.strerror or exc}"}
        if owner or group:
            if dst.is_dir():
                for root, dirs, files in os.walk(dst):
                    for name in dirs + files:
                        _chown_path(Path(root) / name, owner, group)
            _chown_path(dst, owner, group)
        return {"returncode": 0, "stdout": "moved", "stderr": ""}

    if op == "copy_item":
        source = str(payload.get("source", ""))
        destination = str(payload.get("destination", ""))
        owner = payload.get("owner")
        group = payload.get("group")
        if not _is_file_manager_path(source) or not _is_file_manager_path(destination):
            return {"returncode": 1, "stdout": "", "stderr": "Path not permitted"}
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            return {"returncode": 1, "stdout": "", "stderr": f"Source not found: {source}"}
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
            else:
                shutil.copy2(src, dst)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Copy failed: {exc.strerror or exc}"}
        if owner or group:
            if dst.is_dir():
                for root, dirs, files in os.walk(dst):
                    for name in dirs + files:
                        _chown_path(Path(root) / name, owner, group)
            _chown_path(dst, owner, group)
        return {"returncode": 0, "stdout": "copied", "stderr": ""}

    if op == "chmod_item":
        path_str = str(payload.get("path", ""))
        mode = int(payload.get("mode", 0o644))
        if not _is_file_manager_path(path_str):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        if mode & 0o7000:
            return {"returncode": 1, "stdout": "", "stderr": "setuid/setgid bits are not permitted"}
        target = Path(path_str)
        if not target.exists():
            return {"returncode": 1, "stdout": "", "stderr": f"Path not found: {path_str}"}
        try:
            os.chmod(target, mode)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"chmod failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": "chmod", "stderr": ""}

    if op == "remove_item":
        path_str = str(payload.get("path", ""))
        target = Path(path_str)
        # The parent must be inside the roots so a symlink (which must not be
        # followed) can still be unlinked, while its target stays untouched.
        if not _is_file_manager_path(path_str) and not _is_file_manager_path(str(target.parent)):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {path_str}"}
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Remove failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": "removed", "stderr": ""}

    if op == "install_file":
        # Copy a single regular file (produced by the unprivileged worker in a
        # private temp directory) into one of the panel-owned roots.
        source = str(payload.get("source", ""))
        destination = str(payload.get("destination", ""))
        mode = int(payload.get("mode", 0o644))
        owner = payload.get("owner")
        group = payload.get("group")
        if not _is_file_manager_path(destination):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {destination}"}
        if not _is_staging_path(source):
            return {"returncode": 1, "stdout": "", "stderr": f"Staging path not permitted: {source}"}
        if mode & 0o7000:
            return {"returncode": 1, "stdout": "", "stderr": "setuid/setgid bits are not permitted"}
        try:
            data = _read_regular_file(Path(source))
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Read failed: {exc.strerror or exc}"}
        dst = Path(destination)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not _is_file_manager_path(str(dst.parent)):
                return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {destination}"}
            fd = _open_regular_file_for_write(dst, mode)
            try:
                _write_all(fd, data)
            finally:
                os.close(fd)
            _chown_path(dst, owner, group)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Install failed: {exc.strerror or exc}"}
        return {"returncode": 0, "stdout": "installed", "stderr": ""}

    if op == "install_tree":
        # Copy a directory tree (produced by the unprivileged worker in a
        # private temp directory) into one of the panel-owned roots.
        source = str(payload.get("source", ""))
        destination = str(payload.get("destination", ""))
        owner = payload.get("owner")
        group = payload.get("group")
        if not _is_file_manager_path(destination):
            return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {destination}"}
        if not _is_staging_path(source):
            return {"returncode": 1, "stdout": "", "stderr": f"Staging path not permitted: {source}"}
        src = Path(source)
        if src.is_symlink() or not src.is_dir():
            return {"returncode": 1, "stdout": "", "stderr": "Source is not a directory"}
        # Never follow symlinks out of the source tree.
        for root, dirs, files in os.walk(src):
            for name in list(dirs) + list(files):
                if (Path(root) / name).is_symlink():
                    return {"returncode": 1, "stdout": "", "stderr": "Refusing to install a tree containing symlinks"}
        dst = Path(destination)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not _is_file_manager_path(str(dst.parent)):
                return {"returncode": 1, "stdout": "", "stderr": f"Path not permitted: {destination}"}
            _copy_tree_contents(src, dst)
        except OSError as exc:
            return {"returncode": 1, "stdout": "", "stderr": f"Install failed: {exc.strerror or exc}"}
        _ensure_owner_accessible(dst, owner, group)
        return {"returncode": 0, "stdout": "installed", "stderr": ""}

    return {"returncode": 1, "stdout": "", "stderr": f"Unknown operation: {op}"}


async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        payload = json.loads(line.decode("utf-8"))
        response = await handle_request(payload)
        writer.write((json.dumps(response) + "\n").encode("utf-8"))
        await writer.drain()
    except Exception:
        writer.write((json.dumps({"returncode": 1, "stdout": "", "stderr": "internal error"}) + "\n").encode("utf-8"))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    # Bind with a restrictive umask so the socket is never briefly world-readable.
    previous_umask = os.umask(0o077)
    try:
        server = await asyncio.start_unix_server(
            client_connected, path=str(SOCKET_PATH), limit=MAX_REQUEST_BYTES
        )
    finally:
        os.umask(previous_umask)
    os.chmod(SOCKET_PATH, 0o600)
    uid: int | None = None
    gid: int | None = None
    try:
        uid = pwd.getpwnam("nexopanel").pw_uid
        gid = grp.getgrnam("nexopanel").gr_gid
        os.chown(SOCKET_PATH, uid, gid)
    except KeyError:
        pass
    # Private staging directory shared with the unprivileged worker: only
    # content placed here may be installed into the panel-owned roots.
    try:
        TEMP_BASE.mkdir(parents=True, exist_ok=True)
        os.chmod(TEMP_BASE, 0o700)
        if uid is not None and gid is not None:
            os.chown(TEMP_BASE, uid, gid)
    except OSError:
        pass
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
