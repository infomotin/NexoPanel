"""Immutable, append-only audit log writer with secret scrubbing."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AuditLog, User

SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "private_key", "relay_password", "totp_secret"}


def scrub_secrets(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    cleaned: dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            cleaned[k] = "********"
        elif isinstance(v, dict):
            cleaned[k] = scrub_secrets(v)
        else:
            cleaned[k] = v
    return cleaned


async def record_audit_event(
    db: AsyncSession,
    *,
    actor: User | None,
    request: Request | None,
    permission: str,
    action: str,
    target_resource: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    status: str = "success",
    node_id: str | None = None,
) -> AuditLog:
    source_ip = "127.0.0.1"
    if request and request.client:
        source_ip = request.client.host

    entry = AuditLog(
        node_id=node_id or settings.LOCAL_NODE_ID,
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else "system",
        source_ip=source_ip,
        permission=permission,
        action=action,
        target_resource=target_resource,
        before_state=scrub_secrets(before_state),
        after_state=scrub_secrets(after_state),
        status=status,
    )
    db.add(entry)
    await db.flush()
    return entry
