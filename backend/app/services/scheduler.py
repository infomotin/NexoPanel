"""APScheduler-backed execution of enabled cron jobs.

Jobs are stored in SQLite; this module keeps the in-process scheduler in sync so
entries created, paused, or deleted through the API take effect immediately and
are also restored on service start.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.db.models import CronJob, PanelSetting
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_scheduler: Any = None

AUTO_BACKUP_KEY_PREFIX = "db_auto_backup:"
DEFAULT_AUTO_BACKUP_SCHEDULE = "0 3 * * *"


def _job_id(job_id: int) -> str:
    return f"cron-{job_id}"


async def _run_scheduled_job(job_id: int) -> None:
    # Imported lazily so importing app.main never requires APScheduler.
    from app.services.cron import execute_cron_job

    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(CronJob).where(CronJob.id == job_id))).scalar_one_or_none()
        if job is None or not job.is_enabled:
            return
        try:
            await execute_cron_job(db, job)
        except Exception:
            logger.exception("Scheduled cron job %s failed", job_id)
        await db.commit()


def _trigger_for(expression: str) -> Any:
    from apscheduler.triggers.cron import CronTrigger

    return CronTrigger.from_crontab(expression)


def validate_cron_expression(expression: str) -> bool:
    """True when *expression* is a valid five-field cron expression."""
    try:
        _trigger_for(expression)
        return True
    except Exception:
        return False


def _auto_backup_job_id(engine: str) -> str:
    return f"db-auto-backup-{engine}"


async def _run_db_auto_backup(engine: str) -> None:
    from app.services.backups import backup_all_databases

    try:
        count = await backup_all_databases(engine)
        logger.info("Automatic database backup for %s completed (%d database(s))", engine, count)
    except Exception:
        logger.exception("Automatic database backup for %s failed", engine)


def schedule_db_auto_backup(engine: str, schedule: str) -> bool:
    """(Re)register the per-engine automatic database backup job."""
    if _scheduler is None:
        return False
    try:
        trigger = _trigger_for(schedule)
    except Exception:
        logger.warning("Invalid auto-backup schedule for %s: %r", engine, schedule)
        return False
    _scheduler.add_job(
        _run_db_auto_backup,
        trigger,
        args=[engine],
        id=_auto_backup_job_id(engine),
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )
    return True


def unschedule_db_auto_backup(engine: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_auto_backup_job_id(engine))
    except Exception:
        pass


async def _load_db_auto_backup_schedules(scheduler: Any) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(PanelSetting).where(
                    PanelSetting.key.like(f"{AUTO_BACKUP_KEY_PREFIX}%")
                )
            )
        ).scalars().all()
    for row in rows:
        try:
            config = json.loads(row.value)
        except Exception:
            continue
        if not config.get("enabled"):
            continue
        engine = row.key[len(AUTO_BACKUP_KEY_PREFIX):]
        schedule = config.get("schedule") or DEFAULT_AUTO_BACKUP_SCHEDULE
        try:
            trigger = _trigger_for(schedule)
        except Exception:
            logger.warning("Skipping invalid auto-backup schedule for %s: %r", engine, schedule)
            continue
        scheduler.add_job(
            _run_db_auto_backup,
            trigger,
            args=[engine],
            id=_auto_backup_job_id(engine),
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )


def schedule_job(job: CronJob) -> None:
    """Add or replace a single enabled job in the running scheduler."""
    if _scheduler is None or not job.is_enabled:
        return
    try:
        trigger = _trigger_for(job.schedule)
    except ValueError:
        logger.warning("Invalid cron expression for job %s: %r", job.id, job.schedule)
        return
    _scheduler.add_job(
        _run_scheduled_job,
        trigger,
        args=[job.id],
        id=_job_id(job.id),
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )


def unschedule_job(job_id: int) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(job_id))
    except Exception:
        # The job may never have been scheduled (invalid expression / paused).
        pass


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None or settings.ENVIRONMENT == "testing":
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("APScheduler is not installed; cron jobs will not run automatically")
        return

    scheduler = AsyncIOScheduler(timezone="UTC")
    async with AsyncSessionLocal() as db:
        jobs = (
            (await db.execute(select(CronJob).where(CronJob.is_enabled.is_(True)))).scalars().all()
        )
        for job in jobs:
            try:
                scheduler.add_job(
                    _run_scheduled_job,
                    _trigger_for(job.schedule),
                    args=[job.id],
                    id=_job_id(job.id),
                    replace_existing=True,
                    misfire_grace_time=60,
                    coalesce=True,
                )
            except ValueError:
                logger.warning("Skipping job %s with invalid cron expression", job.id)
    scheduler.start()
    _scheduler = scheduler
    logger.info("Cron scheduler started with %d job(s)", len(scheduler.get_jobs()))


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
