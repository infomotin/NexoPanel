"""Backup & Disaster Recovery Engine API router."""
from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.db.models import BackupJob, BackupManifest, User
from app.db.session import get_db
from app.drivers.storage import LocalDiskStorageBackend
from app.services.executor import get_node_executor

router = APIRouter(prefix="/backups", tags=["Backup & Disaster Recovery"])


class BackupJobCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    target_type: str = Field(pattern="^(website|database|mail|full)$")
    target_identifier: str = Field(min_length=1, max_length=255)
    cron_expression: str | None = "0 2 * * *"
    retention_count: int = Field(default=7, ge=1, le=365)


class ManualBackupRequest(BaseModel):
    target_type: str = Field(pattern="^(website|database|mail)$")
    target_identifier: str = Field(min_length=1, max_length=255)
    job_id: int | None = None


@router.get("/jobs")
async def list_backup_jobs(
    _: User = Depends(require_permission("backups:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    jobs = (await db.execute(select(BackupJob).order_by(BackupJob.id.desc()))).scalars().all()
    return [
        {
            "id": j.id,
            "name": j.name,
            "target_type": j.target_type,
            "target_identifier": j.target_identifier,
            "storage_backend": j.storage_backend,
            "cron_expression": j.cron_expression,
            "retention_count": j.retention_count,
            "is_enabled": j.is_enabled,
        }
        for j in jobs
    ]


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_backup_job(
    body: BackupJobCreate,
    request: Request,
    actor: User = Depends(require_permission("backups:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = BackupJob(
        name=body.name,
        target_type=body.target_type,
        target_identifier=body.target_identifier,
        cron_expression=body.cron_expression,
        retention_count=body.retention_count,
    )
    db.add(job)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="backups:write", action="create_backup_job", target_resource=f"backup_job:{job.name}"
    )
    await db.commit()
    return {"id": job.id, "name": job.name}


@router.get("/manifests")
async def list_manifests(
    _: User = Depends(require_permission("backups:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    manifests = (await db.execute(select(BackupManifest).order_by(BackupManifest.id.desc()))).scalars().all()
    return [
        {
            "id": m.id,
            "job_id": m.job_id,
            "target_type": m.target_type,
            "target_identifier": m.target_identifier,
            "storage_backend": m.storage_backend,
            "artifact_path": m.artifact_path,
            "size_bytes": m.size_bytes,
            "checksum_sha256": m.checksum_sha256,
            "status": m.status,
            "created_at": m.created_at.isoformat(),
        }
        for m in manifests
    ]


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_manual_backup(
    body: ManualBackupRequest,
    request: Request,
    actor: User = Depends(require_permission("backups:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    backend = LocalDiskStorageBackend(settings.BACKUP_DIR)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{body.target_type}_{body.target_identifier.replace('/', '_')}_{ts}.tar.gz"
    staging_path = settings.BACKUP_DIR / filename
    staging_path.parent.mkdir(parents=True, exist_ok=True)

    if body.target_type == "website":
        src_dir = settings.WEB_ROOT_BASE / body.target_identifier
        with tarfile.open(staging_path, "w:gz") as tf:
            if src_dir.exists():
                tf.add(src_dir, arcname=body.target_identifier)
    elif body.target_type == "mail":
        src_dir = settings.MAIL_DIR_BASE / body.target_identifier
        with tarfile.open(staging_path, "w:gz") as tf:
            if src_dir.exists():
                tf.add(src_dir, arcname=body.target_identifier)
    else:
        executor = get_node_executor()
        sql_out = await executor.run_command(["/usr/bin/mariadb-dump", body.target_identifier])
        dump_file = settings.BACKUP_DIR / f"{body.target_identifier}_{ts}.sql"
        dump_file.write_text(sql_out.stdout, encoding="utf-8")
        with tarfile.open(staging_path, "w:gz") as tf:
            tf.add(dump_file, arcname=dump_file.name)
        dump_file.unlink(missing_ok=True)

    stored_uri, size_bytes, checksum = await backend.store(staging_path, filename)
    manifest = BackupManifest(
        job_id=body.job_id,
        target_type=body.target_type,
        target_identifier=body.target_identifier,
        storage_backend=backend.backend_name,
        artifact_path=stored_uri,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        status="completed",
    )
    db.add(manifest)
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="backups:write",
        action="run_backup",
        target_resource=f"backup:{body.target_type}:{body.target_identifier}",
    )
    await db.commit()
    return {"id": manifest.id, "artifact_path": stored_uri, "size_bytes": size_bytes, "checksum_sha256": checksum}


@router.post("/manifests/{manifest_id}/restore")
async def restore_backup(
    manifest_id: int,
    request: Request,
    actor: User = Depends(require_permission("backups:restore")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    manifest = (await db.execute(select(BackupManifest).where(BackupManifest.id == manifest_id))).scalar_one_or_none()
    if not manifest:
        raise HTTPException(status_code=404, detail="Backup manifest not found")

    backend = LocalDiskStorageBackend(settings.BACKUP_DIR)
    tmp_archive = settings.BACKUP_DIR / f"restore_{manifest.id}.tar.gz"
    await backend.retrieve(manifest.artifact_path, tmp_archive)
    if manifest.target_type == "website":
        with tarfile.open(tmp_archive, "r:gz") as tf:
            tf.extractall(settings.WEB_ROOT_BASE)
    elif manifest.target_type == "mail":
        with tarfile.open(tmp_archive, "r:gz") as tf:
            tf.extractall(settings.MAIL_DIR_BASE)
    tmp_archive.unlink(missing_ok=True)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="backups:restore",
        action="restore_backup",
        target_resource=f"backup_manifest:{manifest.id}",
    )
    await db.commit()
    return {"restored": True, "manifest_id": manifest.id}
