"""Web File Manager API router with strict path canonicalization (os.path.realpath)."""
from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.validators import canonicalize_safe_path
from app.db.models import User
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
        entries.append(
            {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": st.st_size,
                "mode": oct(st.st_mode & 0o777),
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
