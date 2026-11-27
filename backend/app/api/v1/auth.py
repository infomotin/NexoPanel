"""Authentication, TOTP 2FA, CSRF, and rate-limited login endpoints."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import get_current_user
from app.core.security import (
    auth_rate_limiter,
    build_totp_provisioning_uri,
    create_access_token,
    create_partial_2fa_token,
    decode_token,
    generate_recovery_codes,
    generate_totp_qr_base64,
    generate_totp_secret,
    secret_manager,
    verify_password,
    verify_recovery_code,
    verify_totp_code,
)
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TotpVerifyRequest(BaseModel):
    partial_token: str
    code: str = Field(min_length=6, max_length=32)


class TotpConfirmRequest(BaseModel):
    secret: str
    code: str = Field(min_length=6, max_length=12)


@router.get("/csrf")
async def get_csrf_token(response: Response) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        samesite="strict",
        secure=False,
    )
    return {"csrf_token": token}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"{client_ip}:{body.username}"
    locked, retry_after = auth_rate_limiter.is_locked(rate_key)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Locked for {retry_after}s.",
        )

    stmt = select(User).where(User.username == body.username)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        now_locked, lock_sec = auth_rate_limiter.record_failure(rate_key)
        await record_audit_event(
            db,
            actor=user,
            request=request,
            permission="auth:login",
            action="login_failed",
            target_resource=f"user:{body.username}",
            status="locked" if now_locked else "failed",
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    auth_rate_limiter.record_success(rate_key)

    if user.totp_enabled:
        partial = create_partial_2fa_token(user.username, user.id)
        return {"requires_2fa": True, "partial_token": partial}

    user.last_login_at = datetime.now(timezone.utc)
    access_token = create_access_token(
        subject=user.username,
        user_id=user.id,
        role_name=user.role.name,
        permissions=user.role.permissions,
    )
    csrf_token = secrets.token_urlsafe(32)
    cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(key="access_token", value=access_token, max_age=cookie_max_age, httponly=True, samesite="strict")
    response.set_cookie(key=settings.CSRF_COOKIE_NAME, value=csrf_token, max_age=cookie_max_age, httponly=False, samesite="strict")

    await record_audit_event(
        db,
        actor=user,
        request=request,
        permission="auth:login",
        action="login_success",
        target_resource=f"user:{user.username}",
    )
    await db.commit()

    return {
        "requires_2fa": False,
        "access_token": access_token,
        "token_type": "bearer",
        "csrf_token": csrf_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.name,
            "permissions": user.role.permissions,
            "totp_enabled": user.totp_enabled,
        },
    }


@router.post("/2fa/verify")
async def verify_2fa_login(
    body: TotpVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        payload = decode_token(body.partial_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA session") from exc

    if payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = (await db.execute(select(User).where(User.id == payload["uid"]))).scalar_one_or_none()
    if not user or not user.totp_secret_encrypted:
        raise HTTPException(status_code=401, detail="User 2FA not configured")

    rate_key = f"2fa:{user.id}"
    locked, retry_after = auth_rate_limiter.is_locked(rate_key)
    if locked:
        raise HTTPException(status_code=429, detail=f"2FA locked for {retry_after}s")

    secret = secret_manager.decrypt(user.totp_secret_encrypted)
    verified = verify_totp_code(secret, body.code)
    if not verified:
        ok, remaining = verify_recovery_code(body.code, list(user.recovery_codes_hashed or []))
        if ok:
            user.recovery_codes_hashed = remaining
            verified = True

    if not verified:
        auth_rate_limiter.record_failure(rate_key)
        raise HTTPException(status_code=401, detail="Invalid 2FA or recovery code")

    auth_rate_limiter.record_success(rate_key)
    user.last_login_at = datetime.now(timezone.utc)
    access_token = create_access_token(user.username, user.id, user.role.name, user.role.permissions)
    csrf_token = secrets.token_urlsafe(32)
    cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(key="access_token", value=access_token, max_age=cookie_max_age, httponly=True, samesite="strict")
    response.set_cookie(key=settings.CSRF_COOKIE_NAME, value=csrf_token, max_age=cookie_max_age, httponly=False, samesite="strict")
    await record_audit_event(
        db, actor=user, request=request, permission="auth:login", action="login_2fa_success", target_resource=f"user:{user.username}"
    )
    await db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "csrf_token": csrf_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.name,
            "permissions": user.role.permissions,
            "totp_enabled": user.totp_enabled,
        },
    }


@router.get("/me")
async def get_me(response: Response, current_user: User = Depends(get_current_user)) -> dict:
    cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    new_token = create_access_token(
        subject=current_user.username,
        user_id=current_user.id,
        role_name=current_user.role.name,
        permissions=current_user.role.permissions or [],
    )
    response.set_cookie(key="access_token", value=new_token, max_age=cookie_max_age, httponly=True, samesite="strict")
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.name,
        "permissions": current_user.role.permissions,
        "totp_enabled": current_user.totp_enabled,
        "access_token": new_token,
    }


@router.post("/2fa/setup")
async def setup_2fa(current_user: User = Depends(get_current_user)) -> dict:
    secret = generate_totp_secret()
    uri = build_totp_provisioning_uri(secret, current_user.username)
    qr = generate_totp_qr_base64(uri)
    return {"secret": secret, "provisioning_uri": uri, "qr_data_url": qr}


@router.post("/2fa/enable")
async def enable_2fa(
    body: TotpConfirmRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_totp_code(body.secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP verification code")
    plain_codes, hashed_codes = generate_recovery_codes()
    current_user.totp_secret_encrypted = secret_manager.encrypt(body.secret)
    current_user.recovery_codes_hashed = hashed_codes
    current_user.totp_enabled = True
    await record_audit_event(
        db, actor=current_user, request=request, permission="security:write", action="enable_2fa", target_resource=f"user:{current_user.username}"
    )
    await db.commit()
    return {"enabled": True, "recovery_codes": plain_codes}


@router.post("/2fa/disable")
async def disable_2fa(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.totp_enabled = False
    current_user.totp_secret_encrypted = None
    current_user.recovery_codes_hashed = []
    await record_audit_event(
        db, actor=current_user, request=request, permission="security:write", action="disable_2fa", target_resource=f"user:{current_user.username}"
    )
    await db.commit()
    return {"enabled": False}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token")
    return {"status": "logged_out"}
