"""Backup & Disaster Recovery Engine API router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.db.models import BackupJob, BackupManifest, ManagedDatabase, User
from app.db.session import get_db
from app.services.backups import (
    UnsafeBackupArchive,
    create_backup_archive,
    restore_backup_archive,
    store_backup_archive,
)

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
    engine = "mariadb"
    if body.target_type == "database":
        record = (
            await db.execute(select(ManagedDatabase).where(ManagedDatabase.db_name == body.target_identifier))
        ).scalar_one_or_none()
        if record:
            engine = record.engine

    try:
        staging_path = await create_backup_archive(
            body.target_type, body.target_identifier, engine=engine
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    stored_uri, size_bytes, checksum = await store_backup_archive(staging_path)
    manifest = BackupManifest(
        job_id=body.job_id,
        target_type=body.target_type,
        target_identifier=body.target_identifier,
        storage_backend="local",
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

    engine = "mariadb"
    if manifest.target_type == "database":
        record = (
            await db.execute(select(ManagedDatabase).where(ManagedDatabase.db_name == manifest.target_identifier))
        ).scalar_one_or_none()
        if record:
            engine = record.engine

    try:
        summary = await restore_backup_archive(
            target_type=manifest.target_type,
            target_identifier=manifest.target_identifier,
            artifact_path=manifest.artifact_path,
            engine=engine,
        )
    except UnsafeBackupArchive as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="backups:restore",
        action="restore_backup",
        target_resource=f"backup_manifest:{manifest.id}",
    )
    await db.commit()
    return {"restored": True, "manifest_id": manifest.id, "detail": summary}
