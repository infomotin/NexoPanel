"""Database bootstrapper: creates tables and seeds default roles & admin user."""
from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import ALL_PERMISSIONS
from app.core.security import hash_password
from app.db.models import PanelSetting, Role, User
from app.db.session import Base, engine


async def init_db_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_defaults(db: AsyncSession, initial_admin_password: str | None = None) -> str | None:
    """Seed built-in RBAC roles and default admin user if missing. Returns generated password if created."""
    # 1. Administrator role
    admin_role = (await db.execute(select(Role).where(Role.name == "Administrator"))).scalar_one_or_none()
    if not admin_role:
        admin_role = Role(
            name="Administrator",
            description="Full unrestricted access to all NexoPanel modules",
            permissions=["*"] + ALL_PERMISSIONS,
            is_system=True,
        )
        db.add(admin_role)
        await db.flush()

    # 2. Operator role
    op_role = (await db.execute(select(Role).where(Role.name == "Site Operator"))).scalar_one_or_none()
    if not op_role:
        op_role = Role(
            name="Site Operator",
            description="Manage websites, files, SSL, and databases without system/RBAC privileges",
            permissions=[
                "dashboard:read",
                "websites:read",
                "websites:write",
                "subdomains:read",
                "subdomains:write",
                "apps:read",
                "apps:deploy",
                "files:read",
                "files:write",
                "ssl:read",
                "ssl:issue",
                "databases:read",
                "databases:write",
                "telemetry:read",
                "logs:read",
                "backups:read",
                "backups:write",
            ],
            is_system=True,
        )
        db.add(op_role)

    # 3. Read-Only Auditor role
    auditor_role = (await db.execute(select(Role).where(Role.name == "Auditor"))).scalar_one_or_none()
    if not auditor_role:
        auditor_role = Role(
            name="Auditor",
            description="Read-only observability and audit inspection",
            permissions=[p for p in ALL_PERMISSIONS if p.endswith(":read")],
            is_system=True,
        )
        db.add(auditor_role)

    await db.flush()

    # 4. Admin user
    admin_user = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
    generated_pw: str | None = None
    if not admin_user:
        generated_pw = initial_admin_password or secrets.token_urlsafe(16)
        admin_user = User(
            username="admin",
            email="admin@localhost.localdomain",
            password_hash=hash_password(generated_pw),
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(admin_user)

    # 5. Default panel settings
    defaults = {
        "panel_title": "NexoPanel",
        "session_timeout_minutes": "60",
        "acme_email": "admin@localhost.localdomain",
        "acme_directory": "https://acme-v02.api.letsencrypt.org/directory",
    }
    for k, v in defaults.items():
        existing = (await db.execute(select(PanelSetting).where(PanelSetting.key == k))).scalar_one_or_none()
        if not existing:
            db.add(PanelSetting(key=k, value=v, is_secret=False))

    await db.commit()
    return generated_pw
