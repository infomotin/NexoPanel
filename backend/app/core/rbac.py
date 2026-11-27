"""Granular RBAC permissions catalog and FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

ALL_PERMISSIONS: list[str] = [
    "dashboard:read",
    "websites:read",
    "websites:write",
    "websites:delete",
    "subdomains:read",
    "subdomains:write",
    "subdomains:delete",
    "apps:read",
    "apps:deploy",
    "apps:delete",
    "files:read",
    "files:write",
    "files:delete",
    "packages:read",
    "packages:write",
    "dns:read",
    "dns:write",
    "dns:delete",
    "mail:read",
    "mail:write",
    "mail:delete",
    "ssl:read",
    "ssl:issue",
    "ssl:revoke",
    "databases:read",
    "databases:write",
    "databases:delete",
    "terminal:execute",
    "telemetry:read",
    "logs:read",
    "security:read",
    "security:write",
    "rbac:read",
    "rbac:write",
    "backups:read",
    "backups:write",
    "backups:restore",
    "settings:read",
    "settings:write",
]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token: str | None = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("uid")
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found",
        )
    return user


def require_permission(permission: str):
    """FastAPI dependency enforcing server-side RBAC for a specific permission."""

    async def _permission_checker(current_user: User = Depends(get_current_user)) -> User:
        user_perms = set(current_user.role.permissions or [])
        if "*" in user_perms or permission in user_perms:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
        )

    return _permission_checker
