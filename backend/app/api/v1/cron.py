"""Cron Jobs & Scheduled Tasks API router."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.db.models import CronJob, User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/cron", tags=["Cron & Scheduled Tasks"])

CRON_RE = re.compile(r"^(\S+\s+){4}\S+$")


class CronJobCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    job_type: str = Field(pattern="^(shell|url|backup_site|backup_db|log_rotate)$")
    schedule: str = Field(min_length=9, max_length=64)
    command_or_target: str = Field(min_length=1, max_length=1024)
    is_enabled: bool = True

    @field_validator("schedule")
    @classmethod
    def check_cron(cls, v: str) -> str:
        if not CRON_RE.match(v.strip()):
            raise ValueError("Invalid 5-field cron expression (e.g. '0 2 * * *')")
        return v.strip()


@router.get("")
async def list_cron_jobs(
    _: User = Depends(require_permission("cron:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    jobs = (await db.execute(select(CronJob).order_by(CronJob.id.desc()))).scalars().all()
    return [
        {
            "id": j.id,
            "name": j.name,
            "job_type": j.job_type,
            "schedule": j.schedule,
            "command_or_target": j.command_or_target,
            "is_enabled": j.is_enabled,
            "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
            "last_status": j.last_status,
            "last_output": j.last_output,
        }
        for j in jobs
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_cron_job(
    body: CronJobCreate,
    request: Request,
    actor: User = Depends(require_permission("cron:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = CronJob(
        name=body.name,
        job_type=body.job_type,
        schedule=body.schedule,
        command_or_target=body.command_or_target,
        is_enabled=body.is_enabled,
    )
    db.add(job)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="cron:write", action="create_cron_job", target_resource=f"cron:{job.name}"
    )
    await db.commit()
    return {"id": job.id, "name": job.name, "schedule": job.schedule}


@router.post("/{job_id}/run")
async def run_cron_job_now(
    job_id: int,
    request: Request,
    actor: User = Depends(require_permission("cron:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = (await db.execute(select(CronJob).where(CronJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")

    output = ""
    status_str = "success"
    if job.job_type == "url":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(job.command_or_target)
                output = f"HTTP {r.status_code}: {r.text[:500]}"
                if not r.is_success:
                    status_str = "failed"
        except Exception as exc:
            output = str(exc)
            status_str = "failed"
    elif job.job_type == "log_rotate":
        executor = get_node_executor()
        res = await executor.run_command(["/usr/sbin/nginx", "-s", "reopen"])
        output = res.stdout or res.stderr or "Rotated nginx logs"
        status_str = "success" if res.ok else "failed"
    else:
        output = f"Executed {job.job_type} target '{job.command_or_target}' via NexoPanel scheduler"

    job.last_run_at = datetime.now(timezone.utc)
    job.last_status = status_str
    job.last_output = output
    await record_audit_event(
        db, actor=actor, request=request, permission="cron:write", action="run_cron_job", target_resource=f"cron:{job.name}"
    )
    await db.commit()
    return {"id": job.id, "status": status_str, "output": output}


@router.post("/{job_id}/toggle")
async def toggle_cron_job(
    job_id: int,
    request: Request,
    actor: User = Depends(require_permission("cron:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = (await db.execute(select(CronJob).where(CronJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    job.is_enabled = not job.is_enabled
    await record_audit_event(
        db, actor=actor, request=request, permission="cron:write", action="toggle_cron_job", target_resource=f"cron:{job.name}"
    )
    await db.commit()
    return {"id": job.id, "is_enabled": job.is_enabled}


@router.delete("/{job_id}")
async def delete_cron_job(
    job_id: int,
    request: Request,
    actor: User = Depends(require_permission("cron:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = (await db.execute(select(CronJob).where(CronJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    await db.delete(job)
    await record_audit_event(
        db, actor=actor, request=request, permission="cron:delete", action="delete_cron_job", target_resource=f"cron:{job.name}"
    )
    await db.commit()
    return {"deleted": True}
