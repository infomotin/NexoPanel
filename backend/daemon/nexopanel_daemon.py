"""Privilege-separated root helper daemon listening on a 0600 Unix domain socket.

Strict command-schema validation ensures only allowlisted binaries and permitted
configuration paths can be mutated by the unprivileged FastAPI worker.
"""
from __future__ import annotations

import asyncio
import json
import os
import pwd
import grp
from pathlib import Path
from typing import Any

SOCKET_PATH = Path(os.environ.get("NEXOPANEL_DAEMON_SOCKET_PATH", "/run/nexopanel/daemon.sock"))

ALLOWED_BINARIES: set[str] = {
    "/usr/sbin/nginx",
    "/bin/systemctl",
    "/usr/bin/systemctl",
    "/usr/bin/apt-get",
    "/usr/bin/dpkg-query",
    "/usr/sbin/named-checkzone",
    "/usr/sbin/rndc",
    "/usr/sbin/postsuper",
    "/usr/sbin/postqueue",
    "/usr/sbin/postmap",
    "/usr/bin/doveadm",
    "/usr/bin/mysql",
    "/usr/bin/mariadb",
    "/usr/bin/mysqldump",
    "/usr/bin/mariadb-dump",
    "/usr/bin/psql",
    "/usr/bin/pg_dump",
    "/usr/bin/certbot",
    "/bin/chown",
    "/bin/chmod",
    "/usr/bin/tar",
}

ALLOWED_WRITE_PREFIXES: tuple[str, ...] = (
    "/etc/nginx/",
    "/etc/bind/",
    "/etc/postfix/",
    "/etc/dovecot/",
    "/etc/opendkim/",
    "/var/www/",
    "/var/mail/vhosts/",
    "/var/backups/nexopanel/",
)


def _is_allowed_path(path_str: str) -> bool:
    if "\x00" in path_str or ".." in Path(path_str).parts:
        return False
    return any(path_str.startswith(prefix) for prefix in ALLOWED_WRITE_PREFIXES)


async def handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    op = payload.get("op")

    if op == "exec":
        args = payload.get("args")
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            return {"returncode": 1, "stdout": "", "stderr": "Invalid command argument list"}
        if args[0] not in ALLOWED_BINARIES:
            return {"returncode": 126, "stdout": "", "stderr": f"Binary not allowlisted: {args[0]}"}
        timeout = min(int(payload.get("timeout", 120)), 600)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
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
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        os.chmod(target, mode)
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
        if not _is_allowed_path(path_str):
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
    except Exception as exc:
        writer.write((json.dumps({"returncode": 1, "stdout": "", "stderr": str(exc)}) + "\n").encode("utf-8"))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    server = await asyncio.start_unix_server(client_connected, path=str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o600)
    try:
        uid = pwd.getpwnam("nexopanel").pw_uid
        gid = grp.getgrnam("nexopanel").gr_gid
        os.chown(SOCKET_PATH, uid, gid)
    except KeyError:
        pass
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
