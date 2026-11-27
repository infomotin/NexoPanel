"""Backup orchestration shared by the backups API and the cron scheduler.

Every backup is a gzip-compressed tar archive stored through the pluggable
``BackupStorageBackend``.  Restores validate each archive member before
extraction so a tampered backup cannot write outside its target root (tar
path-traversal / link-escape).
"""
from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.drivers.storage import LocalDiskStorageBackend
from app.services.databases import dump_database, import_sql
from app.services.executor import get_node_executor


class UnsafeBackupArchive(ValueError):
    """Raised when an archive member would escape the restore destination."""


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            member_path = (destination / member.name).resolve()
            if member_path != destination and destination not in member_path.parents:
                raise UnsafeBackupArchive(
                    f"Refusing archive member outside destination: {member.name}"
                )
            if member.issym() or member.islnk():
                raise UnsafeBackupArchive(f"Refusing archive link member: {member.name}")
        try:
            # Python 3.12+ can enforce its own data filter as a second layer.
            tf.extractall(destination, filter="data")
        except TypeError:  # pragma: no cover - older Python without the filter kwarg
            tf.extractall(destination)


def build_backup_filename(target_type: str, target_identifier: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_target = target_identifier.replace("/", "_")
    return f"{target_type}_{safe_target}_{ts}.tar.gz"


async def create_backup_archive(
    target_type: str, target_identifier: str, *, engine: str = "mariadb"
) -> Path:
    """Create a local backup archive and return its staging path."""
    filename = build_backup_filename(target_type, target_identifier)
    staging_path = settings.BACKUP_DIR / filename
    staging_path.parent.mkdir(parents=True, exist_ok=True)

    if target_type == "website":
        src_dir = settings.WEB_ROOT_BASE / target_identifier
        with tarfile.open(staging_path, "w:gz") as tf:
            if src_dir.exists():
                tf.add(src_dir, arcname=target_identifier)
        return staging_path

    if target_type == "mail":
        src_dir = settings.MAIL_DIR_BASE / target_identifier
        with tarfile.open(staging_path, "w:gz") as tf:
            if src_dir.exists():
                tf.add(src_dir, arcname=target_identifier)
        return staging_path

    if target_type == "database":
        executor = get_node_executor()
        dump = await dump_database(executor, engine=engine, db_name=target_identifier)
        if not dump.ok:
            raise RuntimeError(dump.stderr or f"Database dump failed for {target_identifier}")
        dump_file = settings.BACKUP_DIR / f"{target_identifier}_{filename.removesuffix('.tar.gz')}.sql"
        dump_file.write_text(dump.stdout, encoding="utf-8")
        try:
            with tarfile.open(staging_path, "w:gz") as tf:
                tf.add(dump_file, arcname=dump_file.name)
        finally:
            dump_file.unlink(missing_ok=True)
        return staging_path

    raise ValueError(f"Unsupported backup target type: {target_type}")


async def store_backup_archive(staging_path: Path) -> tuple[str, int, str]:
    backend = LocalDiskStorageBackend(settings.BACKUP_DIR)
    return await backend.store(staging_path, staging_path.name)


def _read_sql_member(archive: Path) -> str:
    with tarfile.open(archive, "r:gz") as tf:
        member = next(
            (m for m in tf.getmembers() if m.isfile() and m.name.endswith(".sql")), None
        )
        if member is None:
            raise ValueError("Backup archive does not contain a .sql dump")
        extracted = tf.extractfile(member)
        if extracted is None:
            raise ValueError("Unable to read the .sql dump from the backup archive")
        return extracted.read().decode("utf-8", errors="replace")


async def restore_backup_archive(
    *, target_type: str, target_identifier: str, artifact_path: str, engine: str = "mariadb"
) -> str:
    """Restore a stored backup and return a short human-readable summary."""
    backend = LocalDiskStorageBackend(settings.BACKUP_DIR)
    tmp_archive = settings.BACKUP_DIR / f"restore_{Path(artifact_path).name}"
    await backend.retrieve(artifact_path, tmp_archive)
    try:
        if target_type == "website":
            _safe_extract(tmp_archive, settings.WEB_ROOT_BASE)
            return f"Website files for {target_identifier} restored"
        if target_type == "mail":
            _safe_extract(tmp_archive, settings.MAIL_DIR_BASE)
            return f"Mail directory for {target_identifier} restored"
        if target_type == "database":
            sql_text = _read_sql_member(tmp_archive)
            executor = get_node_executor()
            res = await import_sql(
                executor, engine=engine, db_name=target_identifier, sql_content=sql_text
            )
            if not res.ok:
                raise RuntimeError(res.stderr or f"Database restore failed for {target_identifier}")
            return f"Database {target_identifier} restored from dump"
        raise ValueError(f"Unsupported backup target type: {target_type}")
    finally:
        tmp_archive.unlink(missing_ok=True)
