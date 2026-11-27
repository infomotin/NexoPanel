"""Execution engine for cron jobs, shared by manual runs and the scheduler."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validators import validate_outbound_url
from app.db.models import BackupManifest, CronJob, ManagedDatabase
from app.services.backups import create_backup_archive, store_backup_archive
from app.services.executor import get_node_executor

SHELL_TIMEOUT_SECONDS = 300


async def _run_shell(command: str) -> tuple[str, str]:
    """Run a shell job as the unprivileged panel user (never the root daemon)."""
    if sys.platform == "win32":
        return "failed", "Shell cron jobs require a POSIX host"
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_SECONDS)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return "failed", "Shell command timed out"
    output = (out_b + err_b).decode("utf-8", errors="replace").strip()
    status = "success" if proc.returncode == 0 else "failed"
    return status, output[:1000]


async def _run_backup_job(db: AsyncSession, job: CronJob) -> tuple[str, str]:
    target_type = "website" if job.job_type == "backup_site" else "database"
    engine = "mariadb"
    if target_type == "database":
        record = (
            await db.execute(select(ManagedDatabase).where(ManagedDatabase.db_name == job.command_or_target))
        ).scalar_one_or_none()
        if record:
            engine = record.engine

    try:
        staging_path = await create_backup_archive(
            target_type, job.command_or_target, engine=engine
        )
        stored_uri, size_bytes, checksum = await store_backup_archive(staging_path)
    except (RuntimeError, ValueError) as exc:
        return "failed", str(exc)

    db.add(
        BackupManifest(
            job_id=None,
            target_type=target_type,
            target_identifier=job.command_or_target,
            storage_backend="local",
            artifact_path=stored_uri,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            status="completed",
        )
    )
    return "success", f"Backup stored at {stored_uri} ({size_bytes} bytes)"


async def execute_cron_job(db: AsyncSession, job: CronJob) -> tuple[str, str]:
    """Execute one cron job, update its run state, and return (status, output).

    The caller owns the transaction and must commit the session afterwards.
    """
    status = "success"
    output = ""

    if job.job_type == "url":
        try:
            # SSRF guard: a scheduled URL job must not be usable to reach
            # loopback, link-local (cloud metadata) or private addresses.
            target_url = validate_outbound_url(job.command_or_target)
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.get(target_url)
            output = f"HTTP {response.status_code}: {response.text[:500]}"
            if not response.is_success:
                status = "failed"
        except Exception as exc:
            output = str(exc)
            status = "failed"
    elif job.job_type == "log_rotate":
        executor = get_node_executor()
        res = await executor.run_command(["/usr/sbin/nginx", "-s", "reopen"])
        output = res.stdout or res.stderr or "Rotated nginx logs"
        status = "success" if res.ok else "failed"
    elif job.job_type in {"backup_site", "backup_db"}:
        status, output = await _run_backup_job(db, job)
    elif job.job_type == "shell":
        status, output = await _run_shell(job.command_or_target)
    else:
        status = "failed"
        output = f"Unsupported cron job type: {job.job_type}"

    job.last_run_at = datetime.now(timezone.utc)
    job.last_status = status
    job.last_output = output
    return status, output
