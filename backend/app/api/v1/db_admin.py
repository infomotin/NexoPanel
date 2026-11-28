"""Database Engine Administration (MariaDB/MySQL & PostgreSQL) + Built-in phpMyAdmin SQL Explorer API router."""
from __future__ import annotations

import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.security import secret_manager
from app.core.validators import (
    escape_sql_string_literal,
    validate_db_host,
    validate_db_identifier,
    validate_mysql_charset,
)
from app.db.models import BackupManifest, ManagedDatabase, PanelSetting, User
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.services.backups import backup_all_databases
from app.services.databases import (
    drop_database,
    dump_database,
    import_sql as import_sql_stream,
    provision_database,
)
from app.services.executor import get_node_executor
from app.services.scheduler import schedule_db_auto_backup, unschedule_db_auto_backup, validate_cron_expression

router = APIRouter(prefix="/databases", tags=["Database Administration"])

# The database clients run with root/superuser privileges over the local
# socket, so the session's string-escaping semantics are pinned explicitly:
#   * MariaDB/MySQL's default sql_mode treats "\" as an escape character, which
#     would allow a password containing a backslash to break out of the quoted
#     literal and inject SQL into a root-privileged statement.
#   * PostgreSQL's standard_conforming_strings is pinned to "on" so that quote
#     doubling is always the correct (and only) escape.
MARIADB_SESSION_PREFIX = "SET SESSION sql_mode = CONCAT(@@SESSION.sql_mode, ',NO_BACKSLASH_ESCAPES');"
POSTGRES_SESSION_PREFIX = "SET standard_conforming_strings = on;"


def _mariadb_sql(statement: str) -> str:
    return f"{MARIADB_SESSION_PREFIX} {statement}"


def _postgres_sql(statement: str) -> str:
    return f"{POSTGRES_SESSION_PREFIX} {statement}"


async def _get_setting_json(db: AsyncSession, key: str) -> dict:
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    if not row:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


async def _set_setting_json(db: AsyncSession, key: str, updates: dict, *, is_secret: bool = False) -> None:
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    meta = {}
    if row:
        try:
            meta = json.loads(row.value)
        except Exception:
            meta = {}
    meta.update(updates)
    if row:
        row.value = json.dumps(meta)
    else:
        db.add(PanelSetting(key=key, value=json.dumps(meta), is_secret=is_secret))


async def _get_db_meta(db: AsyncSession, engine: str, db_name: str) -> dict:
    key = f"db_meta:{engine}:{db_name}"
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    if not row:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


async def _set_db_meta(db: AsyncSession, engine: str, db_name: str, updates: dict) -> None:
    key = f"db_meta:{engine}:{db_name}"
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    meta = {}
    if row:
        try:
            meta = json.loads(row.value)
        except Exception:
            meta = {}
    meta.update(updates)
    if row:
        row.value = json.dumps(meta)
    else:
        db.add(PanelSetting(key=key, value=json.dumps(meta), is_secret=True))


class DatabaseCreate(BaseModel):
    engine: str = Field(pattern="^(mariadb|postgresql)$")
    db_name: str
    db_user: str
    db_password: str = Field(min_length=6, max_length=128)
    db_host: str = Field(default="localhost", max_length=64)
    charset: str = Field(default="utf8mb4", max_length=32)
    note: str = Field(default="", max_length=255)

    @field_validator("db_name", "db_user")
    @classmethod
    def check_ident(cls, v: str) -> str:
        return validate_db_identifier(v)

    @field_validator("db_host")
    @classmethod
    def check_host(cls, v: str) -> str:
        return validate_db_host(v)

    @field_validator("charset")
    @classmethod
    def check_charset(cls, v: str) -> str:
        return validate_mysql_charset(v)


class PasswordRotateRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class RootPasswordRequest(BaseModel):
    engine: str = Field(default="mariadb", pattern="^(mariadb|postgresql)$")
    password: str = Field(min_length=6, max_length=128)


class PermissionUpdateRequest(BaseModel):
    db_host: str = Field(min_length=1, max_length=64)


class NoteUpdateRequest(BaseModel):
    note: str = Field(default="", max_length=255)


class TableToolActionRequest(BaseModel):
    table_name: str
    action: str = Field(pattern="^(repair|optimize|to_innodb|to_myisam|vacuum)$")

    @field_validator("table_name")
    @classmethod
    def check_tbl(cls, v: str) -> str:
        return validate_db_identifier(v)


class SqlQueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=50000)


@router.get("")
async def list_databases(
    engine: str | None = Query(default=None),
    _: User = Depends(require_permission("databases:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(ManagedDatabase).order_by(ManagedDatabase.id.desc())
    if engine:
        stmt = stmt.where(ManagedDatabase.engine == engine)
    dbs = (await db.execute(stmt)).scalars().all()

    bkp_rows = (
        await db.execute(
            select(BackupManifest.target_identifier, func.count(BackupManifest.id))
            .where(BackupManifest.target_type == "database")
            .group_by(BackupManifest.target_identifier)
        )
    ).all()
    bkp_map = {r[0]: r[1] for r in bkp_rows}

    results = []
    for d in dbs:
        meta = await _get_db_meta(db, d.engine, d.db_name)
        results.append(
            {
                "id": d.id,
                "engine": d.engine,
                "db_name": d.db_name,
                "db_user": d.db_user,
                "db_host": d.db_host,
                "charset": d.charset,
                "backup_count": bkp_map.get(d.db_name, 0),
                "note": meta.get("note") or d.db_name,
                "quota_mb": meta.get("quota_mb", 0),
                "has_password": bool(meta.get("password_enc")),
                "created_at": d.created_at.isoformat(),
            }
        )
    return results


@router.get("/status")
async def get_engine_status(
    engine: str = Query(default="mariadb"),
    _: User = Depends(require_permission("databases:read")),
) -> dict:
    distro = get_distro_driver()
    executor = get_node_executor()
    svc = "mariadb" if engine == "mariadb" else ("postgresql" if engine == "postgresql" else "redis-server")
    try:
        res = await executor.run_command(distro.build_service_control_cmd(svc, "is-active"))
        is_active = (res.stdout.strip() == "active") or res.ok
    except Exception:
        is_active = False

    version = "10.11" if engine == "mariadb" else ("16" if engine == "postgresql" else "7.0")
    if engine == "mariadb":
        ver_res = await executor.run_command(["/usr/bin/mariadb", "-N", "-s", "-e", "SELECT VERSION();"])
        if ver_res.ok and ver_res.stdout.strip() and "[mock" not in ver_res.stdout:
            version = ver_res.stdout.strip().split("-")[0]
    elif engine == "postgresql":
        ver_res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-t", "-A", "-c", "SHOW server_version;"])
        if ver_res.ok and ver_res.stdout.strip() and "[mock" not in ver_res.stdout:
            version = ver_res.stdout.strip().split(" ")[0]

    return {"engine": engine, "service": svc, "active": is_active, "version": version}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_database(
    body: DatabaseCreate,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (
        await db.execute(
            select(ManagedDatabase).where(ManagedDatabase.engine == body.engine, ManagedDatabase.db_name == body.db_name)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Database already exists")

    executor = get_node_executor()
    res = await provision_database(
        executor,
        engine=body.engine,
        db_name=body.db_name,
        db_user=body.db_user,
        db_password=body.db_password,
        db_host=body.db_host,
        charset=body.charset,
    )

    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Database provisioning failed: {res.stderr}")

    record = ManagedDatabase(
        engine=body.engine,
        db_name=body.db_name,
        db_user=body.db_user,
        db_host=body.db_host,
        charset=body.charset,
    )
    db.add(record)
    await _set_db_meta(
        db,
        body.engine,
        body.db_name,
        {
            "password_enc": secret_manager.encrypt(body.db_password),
            "note": body.note or body.db_name,
        },
    )
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:write",
        action="create_database",
        target_resource=f"{body.engine}:{body.db_name}",
    )
    await db.commit()
    return {"id": record.id, "engine": record.engine, "db_name": record.db_name, "db_user": record.db_user}


@router.post("/{db_id}/rotate-password")
async def rotate_database_password(
    db_id: int,
    body: PasswordRotateRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    executor = get_node_executor()
    safe_pw = escape_sql_string_literal(body.new_password)
    if rec.engine == "mariadb":
        sql = _mariadb_sql(f"ALTER USER '{rec.db_user}'@'{rec.db_host}' IDENTIFIED BY '{safe_pw}'; FLUSH PRIVILEGES;")
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        sql = _postgres_sql(f"ALTER USER {rec.db_user} WITH PASSWORD '{safe_pw}';")
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", sql])

    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Password rotation failed: {res.stderr}")

    await _set_db_meta(db, rec.engine, rec.db_name, {"password_enc": secret_manager.encrypt(body.new_password)})
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:write",
        action="rotate_db_password",
        target_resource=f"{rec.engine}:{rec.db_name}",
    )
    await db.commit()
    return {"rotated": True}


@router.delete("/{db_id}")
async def drop_database(
    db_id: int,
    request: Request,
    actor: User = Depends(require_permission("databases:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    executor = get_node_executor()
    res = await drop_database(
        executor,
        engine=rec.engine,
        db_name=rec.db_name,
        db_user=rec.db_user,
        db_host=rec.db_host,
    )

    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Database removal failed: {res.stderr or res.stdout}")

    meta_key = f"db_meta:{rec.engine}:{rec.db_name}"
    meta_row = (await db.execute(select(PanelSetting).where(PanelSetting.key == meta_key))).scalar_one_or_none()
    if meta_row:
        await db.delete(meta_row)
    await db.delete(rec)
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:delete",
        action="drop_database",
        target_resource=f"{rec.engine}:{rec.db_name}",
    )
    await db.commit()
    return {"deleted": True}


class SqlImportRequest(BaseModel):
    sql_content: str = Field(min_length=1, max_length=64 * 1024 * 1024)


@router.post("/{db_id}/import")
async def import_sql(
    db_id: int,
    body: SqlImportRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    executor = get_node_executor()
    res = await import_sql_stream(executor, engine=rec.engine, db_name=rec.db_name, sql_content=body.sql_content)
    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action="import_sql", target_resource=f"{rec.engine}:{rec.db_name}"
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.get("/{db_id}/export")
async def export_sql(
    db_id: int,
    request: Request,
    actor: User = Depends(require_permission("databases:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    executor = get_node_executor()
    res = await dump_database(executor, engine=rec.engine, db_name=rec.db_name)
    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Database export failed: {res.stderr or res.stdout}")
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:read",
        action="export_database",
        target_resource=f"{rec.engine}:{rec.db_name}",
    )
    await db.commit()
    return {"db_name": rec.db_name, "engine": rec.engine, "dump": res.stdout, "ok": res.ok}


@router.post("/root-password")
async def set_root_password(
    body: RootPasswordRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    safe_pw = escape_sql_string_literal(body.password)
    if body.engine == "mariadb":
        sql = _mariadb_sql(f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{safe_pw}'; FLUSH PRIVILEGES;")
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        sql = _postgres_sql(f"ALTER USER postgres WITH PASSWORD '{safe_pw}';")
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", sql])
    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Failed to update root password: {res.stderr}")
    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action="set_db_root_password", target_resource=body.engine
    )
    await db.commit()
    return {"ok": True}


@router.post("/sync-from-server")
async def sync_databases_from_server(
    engine: str = Query(default="mariadb", pattern="^(mariadb|postgresql)$"),
    request: Request = None,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    discovered: list[str] = []
    if engine == "mariadb":
        res = await executor.run_command(["/usr/bin/mariadb", "-N", "-s", "-e", "SHOW DATABASES;"])
        system_dbs = {"information_schema", "performance_schema", "mysql", "sys"}
        if res.ok and "[mock" not in res.stdout:
            discovered = [line.strip() for line in res.stdout.splitlines() if line.strip() and line.strip() not in system_dbs]
    else:
        res = await executor.run_command(
            ["/usr/bin/psql", "-U", "postgres", "-t", "-A", "-c", "SELECT datname FROM pg_database WHERE datistemplate = false;"]
        )
        system_dbs = {"postgres"}
        if res.ok and "[mock" not in res.stdout:
            discovered = [line.strip() for line in res.stdout.splitlines() if line.strip() and line.strip() not in system_dbs]

    validated: list[str] = []
    for name in discovered:
        try:
            validated.append(validate_db_identifier(name))
        except ValueError:
            continue

    added = 0
    for name in validated:
        exists = (
            await db.execute(select(ManagedDatabase).where(ManagedDatabase.engine == engine, ManagedDatabase.db_name == name))
        ).scalar_one_or_none()
        if not exists:
            db.add(ManagedDatabase(engine=engine, db_name=name, db_user=name[:32], db_host="localhost", charset="utf8mb4"))
            added += 1

    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action="sync_dbs_from_server", target_resource=engine
    )
    await db.commit()
    return {"ok": True, "discovered": len(discovered), "added": added}


@router.get("/{db_id}/password/reveal")
async def reveal_database_password(
    db_id: int,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    meta = await _get_db_meta(db, rec.engine, rec.db_name)
    enc = meta.get("password_enc")
    if not enc:
        return {"password": None}
    try:
        password = secret_manager.decrypt(enc)
    except Exception:
        return {"password": None}
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:write",
        action="reveal_db_password",
        target_resource=f"{rec.engine}:{rec.db_name}",
    )
    await db.commit()
    return {"password": password}


@router.put("/{db_id}/permission")
async def update_database_permission(
    db_id: int,
    body: PermissionUpdateRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    new_host = validate_db_host(body.db_host)

    executor = get_node_executor()
    if rec.engine == "mariadb":
        meta = await _get_db_meta(db, rec.engine, rec.db_name)
        pw = ""
        if meta.get("password_enc"):
            try:
                pw = escape_sql_string_literal(secret_manager.decrypt(meta["password_enc"]))
            except Exception:
                pw = ""
        if not pw:
            raise HTTPException(status_code=400, detail="Cannot change host without a stored password; rotate the password first")
        sql = _mariadb_sql(
            f"CREATE USER IF NOT EXISTS '{rec.db_user}'@'{new_host}' IDENTIFIED BY '{pw}'; "
            f"GRANT ALL PRIVILEGES ON `{rec.db_name}`.* TO '{rec.db_user}'@'{new_host}'; "
            "FLUSH PRIVILEGES;"
        )
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
        if not res.ok:
            raise HTTPException(status_code=500, detail=f"Permission update failed: {res.stderr}")
        if new_host != rec.db_host:
            await executor.run_command(["/usr/bin/mariadb", "-e", _mariadb_sql(f"DROP USER IF EXISTS '{rec.db_user}'@'{rec.db_host}'; FLUSH PRIVILEGES;"]))

    else:
        # PostgreSQL has no host-based grants; only record the requested host.
        pass

    rec.db_host = new_host
    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action="update_db_permission", target_resource=f"{rec.db_name}@{new_host}"
    )
    await db.commit()
    return {"ok": True, "db_host": rec.db_host}


@router.put("/{db_id}/note")
async def update_database_note(
    db_id: int,
    body: NoteUpdateRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")
    await _set_db_meta(db, rec.engine, rec.db_name, {"note": body.note})
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:write",
        action="update_db_note",
        target_resource=f"{rec.engine}:{rec.db_name}",
    )
    await db.commit()
    return {"ok": True, "note": body.note}


@router.get("/{db_id}/tools")
async def get_database_toolbox(
    db_id: int,
    _: User = Depends(require_permission("databases:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    executor = get_node_executor()
    tables: list[dict] = []
    total_size = 0

    if rec.engine == "mariadb":
        sql = (
            "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_ROWS, (DATA_LENGTH + INDEX_LENGTH) AS SIZE_BYTES "
            f"FROM information_schema.TABLES WHERE TABLE_SCHEMA = '{rec.db_name}' ORDER BY TABLE_NAME;"
        )
        res = await executor.run_command(["/usr/bin/mariadb", "-N", "-B", "-e", sql])
        if res.ok and "[mock" not in res.stdout:
            for line in res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 5:
                    sz = int(parts[4]) if parts[4].isdigit() else 0
                    total_size += sz
                    tables.append(
                        {
                            "name": parts[0],
                            "engine": parts[1] or "InnoDB",
                            "collation": parts[2] or "utf8mb4_general_ci",
                            "rows": int(parts[3]) if parts[3].isdigit() else 0,
                            "size_bytes": sz,
                        }
                    )
    else:
        sql = (
            "SELECT c.relname, 'PostgreSQL', 'UTF8', COALESCE(s.n_live_tup, 0), pg_total_relation_size(c.oid) "
            "FROM pg_class c LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname;"
        )
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-d", rec.db_name, "-t", "-A", "-F", "\t", "-c", sql])
        if res.ok and "[mock" not in res.stdout:
            for line in res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 5:
                    sz = int(parts[4]) if parts[4].isdigit() else 0
                    total_size += sz
                    tables.append(
                        {
                            "name": parts[0],
                            "engine": parts[1],
                            "collation": parts[2],
                            "rows": int(parts[3]) if parts[3].isdigit() else 0,
                            "size_bytes": sz,
                        }
                    )

    return {"db_name": rec.db_name, "engine": rec.engine, "total_size_bytes": total_size, "tables": tables}


@router.post("/{db_id}/tools/action")
async def run_database_tool_action(
    db_id: int,
    body: TableToolActionRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    executor = get_node_executor()
    tbl = validate_db_identifier(body.table_name)
    if rec.engine == "mariadb":
        if body.action == "repair":
            sql = f"REPAIR TABLE `{rec.db_name}`.`{tbl}`;"
        elif body.action == "optimize":
            sql = f"OPTIMIZE TABLE `{rec.db_name}`.`{tbl}`;"
        elif body.action == "to_innodb":
            sql = f"ALTER TABLE `{rec.db_name}`.`{tbl}` ENGINE=InnoDB;"
        elif body.action == "to_myisam":
            sql = f"ALTER TABLE `{rec.db_name}`.`{tbl}` ENGINE=MyISAM;"
        else:
            sql = f"ANALYZE TABLE `{rec.db_name}`.`{tbl}`;"
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-d", rec.db_name, "-c", f"VACUUM ANALYZE {tbl};"])

    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action=f"db_tool_{body.action}", target_resource=f"{rec.db_name}.{tbl}"
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.get("/{db_id}/tables/{table_name}/rows")
async def browse_table_rows(
    db_id: int,
    table_name: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permission("databases:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tbl = validate_db_identifier(table_name)
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    executor = get_node_executor()
    if rec.engine == "mariadb":
        res = await executor.run_command(["/usr/bin/mariadb", "-B", rec.db_name, "-e", f"SELECT * FROM `{tbl}` LIMIT {limit};"])
    else:
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-d", rec.db_name, "-A", "-F", "\t", "-c", f"SELECT * FROM {tbl} LIMIT {limit};"])

    columns: list[str] = []
    rows: list[list[str]] = []
    if res.ok and res.stdout.strip() and "[mock" not in res.stdout:
        lines = res.stdout.splitlines()
        if lines:
            columns = lines[0].split("\t")
            for line in lines[1:]:
                if rec.engine == "postgresql" and line.startswith("(") and line.endswith(")"):
                    continue
                rows.append(line.split("\t"))
    return {"table": tbl, "columns": columns, "rows": rows, "ok": res.ok, "stderr": res.stderr}


@router.post("/{db_id}/query")
async def execute_sql_query(
    db_id: int,
    body: SqlQueryRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(ManagedDatabase).where(ManagedDatabase.id == db_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Database not found")

    started = time.perf_counter()
    executor = get_node_executor()
    if rec.engine == "mariadb":
        res = await executor.run_command(["/usr/bin/mariadb", "-B", rec.db_name, "-e", body.sql])
    else:
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-d", rec.db_name, "-A", "-F", "\t", "-c", body.sql])
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    columns: list[str] = []
    rows: list[list[str]] = []
    if res.ok and res.stdout.strip() and "[mock" not in res.stdout:
        lines = res.stdout.splitlines()
        if lines:
            columns = lines[0].split("\t")
            for line in lines[1:]:
                rows.append(line.split("\t"))

    await record_audit_event(
        db, actor=actor, request=request, permission="databases:write", action="execute_sql_query", target_resource=f"{rec.engine}:{rec.db_name}"
    )
    await db.commit()
    return {
        "ok": res.ok,
        "columns": columns,
        "rows": rows,
        "raw": res.stdout,
        "stderr": res.stderr,
        "elapsed_ms": elapsed_ms,
    }


# --- Active Database Query Inspector & Processlist Monitoring ---

class KillQueryRequest(BaseModel):
    engine: str = Field(default="mariadb", pattern="^(mariadb|postgresql)$")
    process_id: int = Field(ge=1)


@router.get("/queries/active")
async def get_active_queries(
    engine: str = Query(default="mariadb", pattern="^(mariadb|postgresql)$"),
    _: User = Depends(require_permission("databases:read")),
) -> dict[str, Any]:
    """Retrieve running queries, connection threads, and processlist for the selected database engine."""
    executor = get_node_executor()
    queries: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "threads_running": 0,
        "threads_connected": 0,
        "slow_queries": 0,
        "uptime_seconds": 0,
        "total_queries": 0,
    }

    if engine == "mariadb":
        # 1. Fetch Global Status
        status_res = await executor.run_command([
            "/usr/bin/mariadb", "-B", "-e",
            "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_running', 'Threads_connected', 'Slow_queries', 'Uptime', 'Questions');"
        ])
        if status_res.ok and status_res.stdout.strip():
            for line in status_res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 2:
                    k, v = parts[0].strip(), parts[1].strip()
                    if k == "Threads_running" and v.isdigit():
                        stats["threads_running"] = int(v)
                    elif k == "Threads_connected" and v.isdigit():
                        stats["threads_connected"] = int(v)
                    elif k == "Slow_queries" and v.isdigit():
                        stats["slow_queries"] = int(v)
                    elif k == "Uptime" and v.isdigit():
                        stats["uptime_seconds"] = int(v)
                    elif k == "Questions" and v.isdigit():
                        stats["total_queries"] = int(v)

        # 2. Fetch Processlist
        plist_res = await executor.run_command([
            "/usr/bin/mariadb", "-B", "-e", "SHOW FULL PROCESSLIST;"
        ])
        if plist_res.ok and plist_res.stdout.strip():
            lines = plist_res.stdout.splitlines()
            if len(lines) > 1:
                # header: Id User Host db Command Time State Info
                for line in lines[1:]:
                    cols = line.split("\t")
                    if len(cols) >= 8:
                        pid_str, user, host, db_name, command, time_sec_str, state, info = cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]
                        # Filter out internal sleep threads or self check queries
                        if command == "Binlog Dump":
                            continue
                        t_sec = int(time_sec_str) if time_sec_str.isdigit() else 0
                        queries.append({
                            "id": int(pid_str) if pid_str.isdigit() else 0,
                            "user": user,
                            "host": host,
                            "database": db_name if db_name and db_name != "NULL" else "(none)",
                            "command": command,
                            "time_seconds": t_sec,
                            "state": state if state and state != "NULL" else "",
                            "query": info if info and info != "NULL" else "",
                            "is_slow": t_sec >= 2,
                            "engine": "mariadb",
                        })

    else:
        # PostgreSQL Activity
        pg_res = await executor.run_command([
            "/usr/bin/psql", "-U", "postgres", "-A", "-F", "\t", "-c",
            "SELECT pid, usename, datname, COALESCE(client_addr::text, 'local'), state, COALESCE(EXTRACT(EPOCH FROM (now() - query_start))::int, 0) as duration, query, COALESCE(wait_event, '') FROM pg_stat_activity WHERE state != 'idle' AND pid <> pg_backend_pid();"
        ])
        if pg_res.ok and pg_res.stdout.strip():
            lines = [l for l in pg_res.stdout.splitlines() if not (l.startswith("(") and l.endswith(")"))]
            if len(lines) > 1:
                for line in lines[1:]:
                    cols = line.split("\t")
                    if len(cols) >= 8:
                        pid_str, user, db_name, host, state, dur_str, query_text, wait_evt = cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]
                        t_sec = int(dur_str) if dur_str.isdigit() else 0
                        queries.append({
                            "id": int(pid_str) if pid_str.isdigit() else 0,
                            "user": user,
                            "host": host,
                            "database": db_name,
                            "command": state,
                            "time_seconds": t_sec,
                            "state": wait_evt or state,
                            "query": query_text,
                            "is_slow": t_sec >= 2,
                            "engine": "postgresql",
                        })
        stats["threads_running"] = len(queries)
        stats["threads_connected"] = len(queries)

    # Sort queries so longest-running appears first
    queries.sort(key=lambda q: q["time_seconds"], reverse=True)
    return {
        "engine": engine,
        "stats": stats,
        "total_active": len(queries),
        "queries": queries,
    }


@router.post("/queries/kill")
async def kill_active_query(
    body: KillQueryRequest,
    request: Request,
    actor: User = Depends(require_permission("databases:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Terminate / kill a runaway or blocking query thread."""
    executor = get_node_executor()
    if body.engine == "mariadb":
        res = await executor.run_command(["/usr/bin/mariadb", "-B", "-e", f"KILL {body.process_id};"])
    else:
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-A", "-c", f"SELECT pg_terminate_backend({body.process_id});"])

    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Failed to kill query process: {res.stderr or res.stdout}")

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="databases:write",
        action="kill_database_query",
        target_resource=f"{body.engine}:{body.process_id}",
    )
    await db.commit()
    return {"ok": True, "engine": body.engine, "process_id": body.process_id}


@router.get("/queries/summary")
async def get_queries_summary(
    _: User = Depends(require_permission("databases:read")),
) -> dict[str, Any]:
    """Lightweight aggregated active query counter for real-time dashboard display."""
    executor = get_node_executor()
    mariadb_running = 0
    mariadb_connected = 0
    mariadb_slow = 0

    status_res = await executor.run_command([
        "/usr/bin/mariadb", "-B", "-e",
        "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_running', 'Threads_connected', 'Slow_queries');"
    ])
    if status_res.ok and status_res.stdout.strip():
        for line in status_res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                if k == "Threads_running" and v.isdigit():
                    mariadb_running = int(v)
                elif k == "Threads_connected" and v.isdigit():
                    mariadb_connected = int(v)
                elif k == "Slow_queries" and v.isdigit():
                    mariadb_slow = int(v)

    return {
        "mariadb_running": mariadb_running,
        "mariadb_connected": mariadb_connected,
        "mariadb_slow": mariadb_slow,
        "total_active": mariadb_running,
    }
