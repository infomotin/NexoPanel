"""Database Engine Administration (MariaDB/MySQL & PostgreSQL) API router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.validators import validate_db_identifier
from app.db.models import ManagedDatabase, User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/databases", tags=["Database Administration"])


class DatabaseCreate(BaseModel):
    engine: str = Field(pattern="^(mariadb|postgresql)$")
    db_name: str
    db_user: str
    db_password: str = Field(min_length=8, max_length=128)
    db_host: str = Field(default="localhost", max_length=64)
    charset: str = Field(default="utf8mb4", max_length=32)

    @field_validator("db_name", "db_user")
    @classmethod
    def check_ident(cls, v: str) -> str:
        return validate_db_identifier(v)


class PasswordRotateRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.get("")
async def list_databases(
    _: User = Depends(require_permission("databases:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    dbs = (await db.execute(select(ManagedDatabase).order_by(ManagedDatabase.id.desc()))).scalars().all()
    return [
        {
            "id": d.id,
            "engine": d.engine,
            "db_name": d.db_name,
            "db_user": d.db_user,
            "db_host": d.db_host,
            "charset": d.charset,
            "created_at": d.created_at.isoformat(),
        }
        for d in dbs
    ]


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
    safe_pw = body.db_password.replace("'", "''")
    if body.engine == "mariadb":
        sql = (
            f"CREATE DATABASE IF NOT EXISTS `{body.db_name}` CHARACTER SET {body.charset}; "
            f"CREATE USER IF NOT EXISTS '{body.db_user}'@'{body.db_host}' IDENTIFIED BY '{safe_pw}'; "
            f"GRANT ALL PRIVILEGES ON `{body.db_name}`.* TO '{body.db_user}'@'{body.db_host}'; "
            "FLUSH PRIVILEGES;"
        )
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        sql = (
            f"DO $$ BEGIN CREATE USER {body.db_user} WITH PASSWORD '{safe_pw}'; "
            f"EXCEPTION WHEN duplicate_object THEN ALTER USER {body.db_user} WITH PASSWORD '{safe_pw}'; END $$; "
            f"CREATE DATABASE {body.db_name} OWNER {body.db_user};"
        )
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", sql])

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
    safe_pw = body.new_password.replace("'", "''")
    if rec.engine == "mariadb":
        sql = f"ALTER USER '{rec.db_user}'@'{rec.db_host}' IDENTIFIED BY '{safe_pw}'; FLUSH PRIVILEGES;"
        res = await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        sql = f"ALTER USER {rec.db_user} WITH PASSWORD '{safe_pw}';"
        res = await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", sql])

    if not res.ok:
        raise HTTPException(status_code=500, detail=f"Password rotation failed: {res.stderr}")

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
    if rec.engine == "mariadb":
        sql = f"DROP DATABASE IF EXISTS `{rec.db_name}`; DROP USER IF EXISTS '{rec.db_user}'@'{rec.db_host}';"
        await executor.run_command(["/usr/bin/mariadb", "-e", sql])
    else:
        await executor.run_command(["/usr/bin/psql", "-U", "postgres", "-c", f"DROP DATABASE IF EXISTS {rec.db_name};"])

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
