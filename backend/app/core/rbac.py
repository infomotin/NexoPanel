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
    "firewall:read",
    "firewall:write",
    "cron:read",
    "cron:write",
    "cron:delete",
    "processes:read",
    "processes:write",
    "docker:read",
    "docker:write",
    "ftp:read",
    "ftp:write",
    "ftp:delete",
]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    # 1. Gather all candidate token sources in priority order
    candidates: list[str] = []

    # Bearer header from bearer_scheme
    raw_cred = (credentials.credentials or "").strip() if credentials else ""
    if raw_cred and raw_cred.lower() not in {"null", "undefined", "none"}:
        candidates.append(raw_cred)

    # Authorization header fallback if HTTPBearer scheme missed it
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token_from_auth = auth_header[7:].strip()
        if token_from_auth and token_from_auth not in candidates and token_from_auth.lower() not in {"null", "undefined", "none"}:
            candidates.append(token_from_auth)

    # HttpOnly or standard access_token cookie
    cookie_token = (request.cookies.get("access_token") or "").strip()
    if cookie_token and cookie_token not in candidates and cookie_token.lower() not in {"null", "undefined", "none"}:
        candidates.append(cookie_token)

    # Custom x-access-token header
    x_token = (request.headers.get("x-access-token") or "").strip()
    if x_token and x_token not in candidates and x_token.lower() not in {"null", "undefined", "none"}:
        candidates.append(x_token)

    # URL query parameter ?token= or ?access_token= (essential for SSE / EventSource streams)
    query_token = (request.query_params.get("token") or request.query_params.get("access_token") or "").strip()
    if query_token and query_token not in candidates and query_token.lower() not in {"null", "undefined", "none"}:
        candidates.append(query_token)

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # 2. Test candidate tokens in sequence
    for token in candidates:
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                continue

            user_id = payload.get("uid")
            if not user_id:
                continue

            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            if not user or not user.is_active:
                continue

            return user
        except Exception:
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
    )


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
