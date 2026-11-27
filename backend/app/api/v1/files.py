"""Web File Manager API router with strict path canonicalization (os.path.realpath)."""
from __future__ import annotations

import errno
import io
import os
import shutil
import tarfile
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

try:
    import pwd
except ImportError:
    pwd = None  # Windows dev fallback

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.validators import canonicalize_safe_path, validate_outbound_url
from app.db.models import AuditLog, FileTrashItem, User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/files", tags=["Web File Manager"])

# Ownership applied to files/directories created through the file manager so
# the web server user can serve and later modify the content.
FILE_OWNER = "www-data"
FILE_GROUP = "www-data"


def _safe_path(path: str) -> Path:
    try:
        return canonicalize_safe_path(path, settings.ALLOWED_FILE_ROOTS)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _is_permission_error(exc: BaseException) -> bool:
    """True when the failure was caused by insufficient filesystem rights.

    ``shutil`` aggregates per-file failures into ``shutil.Error`` (which has no
    errno), so those have to be inspected separately - otherwise a permission
    problem would not escalate to the privileged daemon.
    """
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, shutil.Error):
        entries = exc.args[0] if exc.args and isinstance(exc.args[0], list) else []
        for entry in entries:
            reason = str(entry[2]) if len(entry) > 2 else ""
            if "Permission denied" in reason or "Operation not permitted" in reason:
                return True
        return False
    return isinstance(exc, OSError) and exc.errno in (errno.EACCES, errno.EPERM)


def _best_effort_chown(path: Path) -> None:
    """Give the file to the web-server user when the worker is allowed to."""
    try:
        import grp

        uid = pwd.getpwnam(FILE_OWNER).pw_uid  # type: ignore[union-attr]
        gid = grp.getgrnam(FILE_GROUP).gr_gid
        os.chown(path, uid, gid)
    except (KeyError, OSError, AttributeError):
        pass


def _daemon_error(action: str, stderr: str) -> HTTPException:
    detail = (stderr or "the operation could not be completed").strip()
    return HTTPException(status_code=500, detail=f"{action} failed: {detail}")


async def _write_file_bytes(target: Path, data: bytes, mode: int = 0o644, *, append: bool = False) -> None:
    """Write *data* to *target*, escalating to the privileged daemon if needed."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("ab" if append else "wb") as fh:
            fh.write(data)
        os.chmod(target, mode)
        _best_effort_chown(target)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Write failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().write_bytes(
        str(target), data, mode, append=append, owner=FILE_OWNER, group=FILE_GROUP
    )
    if not res.ok:
        raise _daemon_error("Write", res.stderr)


async def _ensure_directory(target: Path, mode: int = 0o755) -> None:
    """Create a directory, escalating to the privileged daemon if needed."""
    try:
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, mode)
        _best_effort_chown(target)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Create directory failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().ensure_directory(
        str(target), owner=FILE_OWNER, group=FILE_GROUP, mode=mode, scope="file_manager"
    )
    if not res.ok:
        raise _daemon_error("Create directory", res.stderr)


async def _move_item(src: Path, dst: Path) -> None:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        _best_effort_chown(dst)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Move failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().move_item(str(src), str(dst), owner=FILE_OWNER, group=FILE_GROUP)
    if not res.ok:
        raise _daemon_error("Move", res.stderr)


async def _copy_item(src: Path, dst: Path) -> None:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(src, dst)
        _best_effort_chown(dst)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Copy failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().copy_item(str(src), str(dst), owner=FILE_OWNER, group=FILE_GROUP)
    if not res.ok:
        raise _daemon_error("Copy", res.stderr)


async def _chmod_item(target: Path, mode: int) -> None:
    try:
        os.chmod(target, mode)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"chmod failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().chmod_item(str(target), mode)
    if not res.ok:
        raise _daemon_error("chmod", res.stderr)


async def _remove_item(target: Path) -> None:
    try:
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Delete failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().remove_item(str(target))
    if not res.ok:
        raise _daemon_error("Delete", res.stderr)


async def _install_file(source: Path, destination: Path, mode: int = 0o644) -> None:
    """Move a file produced by the worker into a panel-owned root."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(destination))
        os.chmod(destination, mode)
        _best_effort_chown(destination)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Store failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().install_file(
        str(source), str(destination), mode, owner=FILE_OWNER, group=FILE_GROUP
    )
    if not res.ok:
        raise _daemon_error("Store", res.stderr)


async def _install_tree(source: Path, destination: Path) -> None:
    """Move a directory tree produced by the worker into a panel-owned root."""
    try:
        destination.mkdir(parents=True, exist_ok=True)
        # Copy the contents (not the source directory itself) and keep the
        # destination's own mode intact.
        for entry in sorted(source.iterdir()):
            target = destination / entry.name
            if entry.is_symlink():
                continue
            if entry.is_dir():
                shutil.copytree(entry, target, dirs_exist_ok=True, symlinks=False)
            else:
                shutil.copy2(entry, target, follow_symlinks=False)
        _best_effort_chown(destination)
        return
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Extract failed: {exc.strerror or exc}") from exc
    res = await get_node_executor().install_tree(
        str(source), str(destination), owner=FILE_OWNER, group=FILE_GROUP
    )
    if not res.ok:
        raise _daemon_error("Extract", res.stderr)


async def _read_file_bytes(path: Path, max_bytes: int = 512 * 1024 * 1024) -> bytes:
    """Read a file, escalating to the privileged daemon when it is not readable."""
    try:
        return path.read_bytes()
    except OSError as exc:
        if not _is_permission_error(exc):
            raise HTTPException(status_code=500, detail=f"Read failed: {exc.strerror or exc}") from exc
    try:
        return await get_node_executor().read_bytes(str(path), max_bytes)
    except RuntimeError as daemon_exc:
        raise HTTPException(status_code=500, detail=str(daemon_exc)) from daemon_exc


def _archive_members(src: Path) -> list[tuple[Path, str]]:
    """Collect (path, archive name) pairs for a file or a directory tree."""
    if src.is_symlink():
        return []
    if src.is_file():
        return [(src, src.name)]
    if not src.is_dir():
        return []
    members: list[tuple[Path, str]] = []
    try:
        for p in sorted(src.rglob("*")):
            try:
                if p.is_symlink() or not p.is_file():
                    continue
            except OSError:
                continue
            members.append((p, str(p.relative_to(src.parent))))
    except OSError:
        pass
    return members


def _staging_dir(prefix: str) -> Path:
    """Create a private staging directory shared with the privileged daemon.

    The daemon only installs content that lives inside this directory, so a
    root-only file (e.g. /etc/shadow) can never be copied into the web root.
    """
    base = settings.DAEMON_TEMP_DIR
    try:
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(base, 0o700)
    except OSError:
        base = Path(tempfile.gettempdir())
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))


def _archive_member_path(dest: Path, name: str) -> Path:
    """Validate an archive member name and return its safe destination path."""
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise HTTPException(status_code=400, detail=f"Unsafe archive member: {name!r}")
    member = dest / name
    resolved = Path(os.path.realpath(member))
    if resolved != dest and dest not in resolved.parents:
        raise HTTPException(status_code=400, detail=f"Unsafe archive member: {name!r}")
    return member


class FileWriteRequest(BaseModel):
    path: str
    content: str


class FileActionRequest(BaseModel):
    source: str
    destination: str | None = None


class ChmodRequest(BaseModel):
    path: str
    mode: str  # e.g. "0755" or "644"


class ArchiveRequest(BaseModel):
    paths: list[str]
    output_path: str
    format: str = "tar.gz"  # tar.gz | zip


class ExtractRequest(BaseModel):
    archive_path: str
    destination_dir: str


@router.get("/roots")
async def get_permitted_roots(_: User = Depends(require_permission("files:read"))) -> dict:
    return {"roots": settings.ALLOWED_FILE_ROOTS}


@router.get("/list")
async def list_directory(
    path: str = Query(default="/var/www"),
    _: User = Depends(require_permission("files:read")),
) -> dict:
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        st = item.stat()
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name if pwd else str(st.st_uid)
        except Exception:
            owner = str(st.st_uid)
        mode_octal = oct(st.st_mode & 0o777).replace("0o", "").zfill(3)
        entries.append(
            {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": st.st_size,
                "mode": oct(st.st_mode & 0o777),
                "mode_short": mode_octal,
                "owner": owner,
                "modified_at": st.st_mtime,
            }
        )
    return {"path": str(target), "entries": entries}


@router.get("/read")
async def read_file_content(
    path: str = Query(...),
    _: User = Depends(require_permission("files:read")),
) -> dict:
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a regular file")
    if target.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large for inline editor (>5MB)")
    raw = await _read_file_bytes(target, 5 * 1024 * 1024)
    return {"path": str(target), "content": raw.decode("utf-8", errors="replace")}


@router.post("/write")
async def write_file_content(
    body: FileWriteRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(body.path)
    await _write_file_bytes(target, body.content.encode("utf-8"))
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="write_file", target_resource=str(target)
    )
    await db.commit()
    return {"saved": True, "path": str(target)}


@router.post("/upload")
async def upload_chunk(
    request: Request,
    path: str = Form(...),
    file: UploadFile = File(...),
    chunk_index: int = Form(0),
    total_chunks: int = Form(1),
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    dest_dir = _safe_path(path)
    await _ensure_directory(dest_dir)
    safe_name = Path(file.filename or "upload.bin").name
    target = _safe_path(str(dest_dir / safe_name))
    data = await file.read()
    await _write_file_bytes(target, data, append=chunk_index > 0)
    if chunk_index + 1 >= total_chunks:
        await record_audit_event(
            db, actor=actor, request=request, permission="files:write", action="upload_file", target_resource=str(target)
        )
        await db.commit()
    return {"uploaded": True, "path": str(target), "chunk": chunk_index + 1, "total_chunks": total_chunks}


@router.get("/download")
async def download_file(
    path: str = Query(...),
    _: User = Depends(require_permission("files:read")),
):
    target = _safe_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if os.access(target, os.R_OK):
        # Stream it directly (no memory copy).
        return FileResponse(path=str(target), filename=target.name)
    # Not readable by the unprivileged worker: fetch it through the daemon.
    try:
        data = await get_node_executor().read_bytes(str(target))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )


@router.post("/mkdir")
async def make_directory(
    body: FileActionRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(body.source)
    await _ensure_directory(target)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="mkdir", target_resource=str(target)
    )
    await db.commit()
    return {"created": True, "path": str(target)}


@router.post("/rename")
async def rename_or_move(
    body: FileActionRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.destination:
        raise HTTPException(status_code=400, detail="destination required")
    src = _safe_path(body.source)
    dst = _safe_path(body.destination)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    await _move_item(src, dst)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="move_file", target_resource=f"{src} -> {dst}"
    )
    await db.commit()
    return {"moved": True, "path": str(dst)}


@router.post("/copy")
async def copy_item(
    body: FileActionRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.destination:
        raise HTTPException(status_code=400, detail="destination required")
    src = _safe_path(body.source)
    dst = _safe_path(body.destination)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    await _copy_item(src, dst)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="copy_file", target_resource=f"{src} -> {dst}"
    )
    await db.commit()
    return {"copied": True, "path": str(dst)}


@router.post("/chmod")
async def chmod_item(
    body: ChmodRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(body.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    try:
        mode_val = int(body.mode, 8)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid mode") from exc
    if mode_val & 0o7000:
        raise HTTPException(status_code=400, detail="setuid/setgid bits are not permitted")
    await _chmod_item(target, mode_val)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="chmod", target_resource=f"{target}:{body.mode}"
    )
    await db.commit()
    return {"updated": True, "mode": body.mode}


@router.post("/archive")
async def create_archive(
    body: ArchiveRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = _safe_path(body.output_path)
    sources = [_safe_path(p) for p in body.paths]
    if not sources:
        raise HTTPException(status_code=400, detail="No files selected for archiving")
    # The archive is built in a private staging directory (the worker may not
    # be able to write the target directory) and then installed into the root.
    tmp_dir = _staging_dir("nexopanel-archive-")
    try:
        tmp_out = tmp_dir / "archive.bin"
        if body.format == "zip":
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zf:
                for src in sources:
                    for file_path, arcname in _archive_members(src):
                        data = await _read_file_bytes(file_path)
                        st = file_path.stat()
                        info = zipfile.ZipInfo(arcname, date_time=time.localtime(st.st_mtime)[:6])
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = (st.st_mode & 0xFFFF) << 16
                        zf.writestr(info, data)
        else:
            with tarfile.open(tmp_out, "w:gz") as tf:
                for src in sources:
                    for file_path, arcname in _archive_members(src):
                        data = await _read_file_bytes(file_path)
                        st = file_path.stat()
                        info = tarfile.TarInfo(arcname)
                        info.size = len(data)
                        info.mtime = st.st_mtime
                        info.mode = st.st_mode & 0o777
                        tf.addfile(info, io.BytesIO(data))
        await _install_file(tmp_out, out, 0o644)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="archive_files", target_resource=str(out)
    )
    await db.commit()
    return {"archived": True, "output_path": str(out)}


@router.post("/extract")
async def extract_archive(
    body: ExtractRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    arch = _safe_path(body.archive_path)
    dest = _safe_path(body.destination_dir)
    if not arch.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")
    # Extract into a private staging directory first: the archive may contain
    # symlinks or traversal entries, and the worker must never write outside
    # the staging directory.
    tmp_dir = _staging_dir("nexopanel-extract-")
    try:
        raw = await _read_file_bytes(arch)
        buf = io.BytesIO(raw)
        if arch.suffix.lower() == ".zip":
            with zipfile.ZipFile(buf) as zf:
                for member in zf.infolist():
                    _archive_member_path(tmp_dir, member.filename)
                    if member.is_dir():
                        continue
                    mode = (member.external_attr >> 16) & 0o170000
                    if mode == 0o120000:  # symlink
                        raise HTTPException(status_code=400, detail=f"Archive contains a symlink: {member.filename}")
                zf.extractall(tmp_dir)
        else:
            with tarfile.open(fileobj=buf, mode="r:*") as tf:
                for member in tf.getmembers():
                    _archive_member_path(tmp_dir, member.name)
                    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                        raise HTTPException(status_code=400, detail=f"Archive contains an unsupported entry: {member.name}")
                tf.extractall(tmp_dir, filter="data")
        await _ensure_directory(dest)
        await _install_tree(tmp_dir, dest)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="extract_archive", target_resource=str(arch)
    )
    await db.commit()
    return {"extracted": True, "destination": str(dest)}


@router.delete("")
async def delete_item(
    path: str = Query(...),
    request: Request = None,
    actor: User = Depends(require_permission("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(path)
    if not target.exists() and not target.is_symlink():
        raise HTTPException(status_code=404, detail="Path not found")
    await _remove_item(target)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:delete", action="delete_file", target_resource=str(target)
    )
    await db.commit()
    return {"deleted": True}


class FetchUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    destination_dir: str
    filename: str | None = None

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        # SSRF guard: only public, routable HTTP(S) targets may be fetched.
        try:
            return validate_outbound_url(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


@router.get("/search")
async def search_files(
    path: str = Query(default="/var/www"),
    query: str = Query(..., min_length=1),
    _: User = Depends(require_permission("files:read")),
) -> dict:
    root = _safe_path(path)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="Search root must be a directory")
    matches = []
    for p in root.rglob("*"):
        if query.lower() in p.name.lower():
            matches.append({"name": p.name, "path": str(p), "is_dir": p.is_dir()})
            if len(matches) >= 100:
                break
    return {"matches": matches}


@router.post("/fetch-url")
async def fetch_remote_url(
    body: FetchUrlRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    dest_dir = _safe_path(body.destination_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(body.filename or body.url.split("/")[-1] or "downloaded.bin").name
    target = _safe_path(str(dest_dir / name))
    # Redirects are followed manually and every hop is re-validated, so a
    # public URL cannot redirect the panel to an internal address.
    max_bytes = 100 * 1024 * 1024
    current_url = body.url
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        for _ in range(5):
            resp = await client.get(current_url)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise HTTPException(status_code=502, detail="Remote fetch failed: invalid redirect")
                current_url = str(httpx.URL(current_url).join(location))
                try:
                    validate_outbound_url(current_url)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"Refusing to follow redirect: {exc}") from exc
                continue
            if not resp.is_success:
                raise HTTPException(status_code=502, detail=f"Remote fetch failed: HTTP {resp.status_code}")
            content = resp.content
            break
        else:
            raise HTTPException(status_code=502, detail="Remote fetch failed: too many redirects")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Remote file exceeds the 100 MB limit")
    await _write_file_bytes(target, content)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="fetch_url", target_resource=str(target)
    )
    await db.commit()
    return {"saved": True, "path": str(target), "size": len(content)}


@router.post("/trash/move")
async def move_to_trash(
    path: str = Query(...),
    request: Request = None,
    actor: User = Depends(require_permission("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    src = _safe_path(path)
    if not src.exists() and not src.is_symlink():
        raise HTTPException(status_code=404, detail="Path not found")
    trash_dir = settings.BACKUP_DIR / ".trash"
    await _ensure_directory(trash_dir, mode=0o700)
    trash_target = trash_dir / f"{uuid.uuid4().hex}_{src.name}"
    size = src.stat().st_size if src.is_file() else 0
    is_dir = src.is_dir()
    await _move_item(src, trash_target)
    item = FileTrashItem(original_path=str(src), trash_path=str(trash_target), is_dir=is_dir, size_bytes=size)
    db.add(item)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="files:delete", action="trash_file", target_resource=str(src)
    )
    await db.commit()
    return {"trashed": True, "id": item.id}


@router.get("/trash")
async def list_trash(
    _: User = Depends(require_permission("files:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    items = (await db.execute(select(FileTrashItem).order_by(FileTrashItem.id.desc()))).scalars().all()
    return [
        {
            "id": i.id,
            "original_path": i.original_path,
            "is_dir": i.is_dir,
            "size_bytes": i.size_bytes,
            "deleted_at": i.deleted_at.isoformat(),
        }
        for i in items
    ]


@router.post("/trash/{item_id}/restore")
async def restore_from_trash(
    item_id: int,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = (await db.execute(select(FileTrashItem).where(FileTrashItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Trash item not found")
    dest = _safe_path(item.original_path)
    await _ensure_directory(dest.parent)
    trash_path = Path(item.trash_path)
    if trash_path.exists() or trash_path.is_symlink():
        await _move_item(trash_path, dest)
    await db.delete(item)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="restore_trash", target_resource=str(dest)
    )
    await db.commit()
    return {"restored": True, "path": str(dest)}


@router.get("/size")
async def calculate_size(
    path: str = Query(...),
    _: User = Depends(require_permission("files:read")),
) -> dict:
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_file():
        return {"path": str(target), "size": target.stat().st_size}
    total = 0
    for p in target.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return {"path": str(target), "size": total}


@router.get("/search-content")
async def search_file_content(
    path: str = Query(default="/var/www"),
    query: str = Query(..., min_length=1),
    _: User = Depends(require_permission("files:read")),
) -> dict:
    root = _safe_path(path)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="Search root must be a directory")
    matches = []
    q_lower = query.lower()
    for p in root.rglob("*"):
        if not p.is_file() or p.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for idx, line in enumerate(text.splitlines(), start=1):
                if q_lower in line.lower():
                    matches.append({"path": str(p), "name": p.name, "line": idx, "snippet": line.strip()[:160]})
                    break
        except OSError:
            continue
        if len(matches) >= 50:
            break
    return {"matches": matches}


@router.delete("/trash/{item_id}")
async def delete_trash_item(
    item_id: int,
    _: User = Depends(require_permission("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = (await db.execute(select(FileTrashItem).where(FileTrashItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Trash item not found")
    tp = Path(item.trash_path)
    if tp.exists() or tp.is_symlink():
        await _remove_item(tp)
    await db.delete(item)
    await db.commit()
    return {"deleted": True}


@router.delete("/trash")
async def empty_trash(
    _: User = Depends(require_permission("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items = (await db.execute(select(FileTrashItem))).scalars().all()
    for item in items:
        tp = Path(item.trash_path)
        if tp.exists() or tp.is_symlink():
            await _remove_item(tp)
        await db.delete(item)
    await db.commit()
    return {"emptied": True}


@router.get("/logs")
async def get_file_logs(
    _: User = Depends(require_permission("files:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    logs = (
        await db.execute(
            select(AuditLog)
            .where(or_(AuditLog.permission.like("files:%"), AuditLog.action.in_(["write_file", "upload_file", "mkdir", "move_file", "copy_file", "chmod", "archive_files", "extract_archive", "delete_file", "fetch_url", "trash_file", "restore_trash"])))
            .order_by(AuditLog.id.desc())
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": l.id,
            "actor": l.actor_username,
            "action": l.action,
            "target": l.target_resource,
            "status": l.status,
            "created_at": l.timestamp.isoformat(),
        }
        for l in logs
    ]
