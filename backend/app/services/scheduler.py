"""APScheduler-backed execution of enabled cron jobs.

Jobs are stored in SQLite; this module keeps the in-process scheduler in sync so
entries created, paused, or deleted through the API take effect immediately and
are also restored on service start.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.db.models import CronJob
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_scheduler: Any = None


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
