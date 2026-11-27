"""Web File Manager API router with strict path canonicalization (os.path.realpath)."""
from __future__ import annotations

import os
import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path

try:
    import pwd
except ImportError:
    pwd = None  # Windows dev fallback

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.validators import canonicalize_safe_path
from app.db.models import AuditLog, FileTrashItem, User
from app.db.session import get_db

router = APIRouter(prefix="/files", tags=["Web File Manager"])


def _safe_path(path: str) -> Path:
    try:
        return canonicalize_safe_path(path, settings.ALLOWED_FILE_ROOTS)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large for inline editor (>5MB)")
    return {"path": str(target), "content": target.read_text(encoding="utf-8", errors="replace")}


@router.post("/write")
async def write_file_content(
    body: FileWriteRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
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
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    target = _safe_path(str(dest_dir / safe_name))
    mode = "wb" if chunk_index == 0 else "ab"
    data = await file.read()
    with target.open(mode) as fh:
        fh.write(data)
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
    return FileResponse(path=str(target), filename=target.name)


@router.post("/mkdir")
async def make_directory(
    body: FileActionRequest,
    request: Request,
    actor: User = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = _safe_path(body.source)
    target.mkdir(parents=True, exist_ok=True)
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
    shutil.move(str(src), str(dst))
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
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
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
    mode_val = int(body.mode, 8)
    os.chmod(target, mode_val)
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
    if body.format == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                if src.is_dir():
                    for p in src.rglob("*"):
                        zf.write(p, arcname=p.relative_to(src.parent))
                else:
                    zf.write(src, arcname=src.name)
    else:
        with tarfile.open(out, "w:gz") as tf:
            for src in sources:
                tf.add(src, arcname=src.name)
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
    dest.mkdir(parents=True, exist_ok=True)
    if arch.suffix == ".zip":
        with zipfile.ZipFile(arch, "r") as zf:
            for member in zf.namelist():
                _safe_path(str(dest / member))
            zf.extractall(dest)
    else:
        with tarfile.open(arch, "r:*") as tf:
            for member in tf.getmembers():
                _safe_path(str(dest / member.name))
            tf.extractall(dest)
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
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    await record_audit_event(
        db, actor=actor, request=request, permission="files:delete", action="delete_file", target_resource=str(target)
    )
    await db.commit()
    return {"deleted": True}


class FetchUrlRequest(BaseModel):
    url: str
    destination_dir: str
    filename: str | None = None


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
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(body.url)
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"Remote fetch failed: HTTP {resp.status_code}")
        target.write_bytes(resp.content)
    await record_audit_event(
        db, actor=actor, request=request, permission="files:write", action="fetch_url", target_resource=str(target)
    )
    await db.commit()
    return {"saved": True, "path": str(target), "size": target.stat().st_size}


@router.post("/trash/move")
async def move_to_trash(
    path: str = Query(...),
    request: Request = None,
    actor: User = Depends(require_permission("files:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    src = _safe_path(path)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    trash_dir = settings.BACKUP_DIR / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    trash_target = trash_dir / f"{uuid.uuid4().hex}_{src.name}"
    size = src.stat().st_size if src.is_file() else 0
    is_dir = src.is_dir()
    shutil.move(str(src), str(trash_target))
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(item.trash_path).exists():
        shutil.move(item.trash_path, str(dest))
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
    if tp.exists():
        if tp.is_dir():
            shutil.rmtree(tp)
        else:
            tp.unlink()
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
        if tp.exists():
            if tp.is_dir():
                shutil.rmtree(tp)
            else:
                tp.unlink()
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
