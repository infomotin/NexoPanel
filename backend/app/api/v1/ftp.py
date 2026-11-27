"""FTP Account Management API router (Pure-FTPd / vsftpd virtual users)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.security import hash_password
from app.core.validators import canonicalize_safe_path, validate_linux_username
from app.db.models import FtpAccount, User
from app.db.session import get_db

router = APIRouter(prefix="/ftp", tags=["FTP Management"])


class FtpAccountCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    home_directory: str
    quota_mb: int = Field(default=0, ge=0, le=1048576)

    @field_validator("username")
    @classmethod
    def check_user(cls, v: str) -> str:
        return validate_linux_username(v)


class FtpPasswordUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=128)


@router.get("")
async def list_ftp_accounts(
    _: User = Depends(require_permission("ftp:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    accounts = (await db.execute(select(FtpAccount).order_by(FtpAccount.id.desc()))).scalars().all()
    return [
        {
            "id": a.id,
            "username": a.username,
            "home_directory": a.home_directory,
            "quota_mb": a.quota_mb,
            "is_active": a.is_active,
            "created_at": a.created_at.isoformat(),
        }
        for a in accounts
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ftp_account(
    body: FtpAccountCreate,
    request: Request,
    actor: User = Depends(require_permission("ftp:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        safe_home = str(canonicalize_safe_path(body.home_directory, settings.ALLOWED_FILE_ROOTS))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = (await db.execute(select(FtpAccount).where(FtpAccount.username == body.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="FTP username already exists")

    acct = FtpAccount(
        username=body.username,
        password_hash=hash_password(body.password),
        home_directory=safe_home,
        quota_mb=body.quota_mb,
    )
    db.add(acct)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="ftp:write", action="create_ftp_account", target_resource=f"ftp:{acct.username}"
    )
    await db.commit()
    return {"id": acct.id, "username": acct.username, "home_directory": acct.home_directory}


@router.post("/{ftp_id}/password")
async def update_ftp_password(
    ftp_id: int,
    body: FtpPasswordUpdate,
    request: Request,
    actor: User = Depends(require_permission("ftp:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    acct = (await db.execute(select(FtpAccount).where(FtpAccount.id == ftp_id))).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="FTP account not found")
    acct.password_hash = hash_password(body.password)
    await record_audit_event(
        db, actor=actor, request=request, permission="ftp:write", action="rotate_ftp_password", target_resource=f"ftp:{acct.username}"
    )
    await db.commit()
    return {"updated": True}


@router.post("/{ftp_id}/toggle")
async def toggle_ftp_account(
    ftp_id: int,
    request: Request,
    actor: User = Depends(require_permission("ftp:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    acct = (await db.execute(select(FtpAccount).where(FtpAccount.id == ftp_id))).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="FTP account not found")
    acct.is_active = not acct.is_active
    await record_audit_event(
        db, actor=actor, request=request, permission="ftp:write", action="toggle_ftp_account", target_resource=f"ftp:{acct.username}"
    )
    await db.commit()
    return {"id": acct.id, "is_active": acct.is_active}


@router.delete("/{ftp_id}")
async def delete_ftp_account(
    ftp_id: int,
    request: Request,
    actor: User = Depends(require_permission("ftp:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    acct = (await db.execute(select(FtpAccount).where(FtpAccount.id == ftp_id))).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="FTP account not found")
    username = acct.username
    await db.delete(acct)
    await record_audit_event(
        db, actor=actor, request=request, permission="ftp:delete", action="delete_ftp_account", target_resource=f"ftp:{username}"
    )
    await db.commit()
    return {"deleted": True}
