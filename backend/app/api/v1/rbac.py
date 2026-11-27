"""Granular RBAC & User Management API router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import ALL_PERMISSIONS, require_permission
from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import get_db

router = APIRouter(prefix="/rbac", tags=["RBAC & Users"])


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    description: str | None = None
    permissions: list[str] | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    role_id: int


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


@router.get("/permissions")
async def list_permissions(_: User = Depends(require_permission("rbac:read"))) -> dict:
    return {"permissions": ALL_PERMISSIONS}


@router.get("/roles")
async def list_roles(
    _: User = Depends(require_permission("rbac:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    roles = (await db.execute(select(Role).order_by(Role.id))).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "permissions": r.permissions,
            "is_system": r.is_system,
        }
        for r in roles
    ]


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    request: Request,
    actor: User = Depends(require_permission("rbac:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    invalid = [p for p in body.permissions if p != "*" and p not in ALL_PERMISSIONS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid permissions: {invalid}")
    existing = (await db.execute(select(Role).where(Role.name == body.name))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Role name already exists")
    role = Role(name=body.name, description=body.description, permissions=body.permissions, is_system=False)
    db.add(role)
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="rbac:write",
        action="create_role",
        target_resource=f"role:{role.name}",
        after_state={"permissions": role.permissions},
    )
    await db.commit()
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions}


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdate,
    request: Request,
    actor: User = Depends(require_permission("rbac:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    before = {"description": role.description, "permissions": list(role.permissions)}
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        invalid = [p for p in body.permissions if p != "*" and p not in ALL_PERMISSIONS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid permissions: {invalid}")
        role.permissions = body.permissions
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="rbac:write",
        action="update_role",
        target_resource=f"role:{role.name}",
        before_state=before,
        after_state={"description": role.description, "permissions": role.permissions},
    )
    await db.commit()
    return {"id": role.id, "name": role.name, "description": role.description, "permissions": role.permissions}


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    request: Request,
    actor: User = Depends(require_permission("rbac:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted")
    await db.delete(role)
    await record_audit_event(
        db, actor=actor, request=request, permission="rbac:write", action="delete_role", target_resource=f"role:{role.name}"
    )
    await db.commit()
    return {"deleted": True}


@router.get("/users")
async def list_users(
    _: User = Depends(require_permission("rbac:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role_id": u.role_id,
            "role_name": u.role.name,
            "is_active": u.is_active,
            "totp_enabled": u.totp_enabled,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    actor: User = Depends(require_permission("rbac:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    role = (await db.execute(select(Role).where(Role.id == body.role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    existing = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role_id=body.role_id,
    )
    db.add(user)
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="rbac:write",
        action="create_user",
        target_resource=f"user:{user.username}",
        after_state={"role": role.name, "email": user.email},
    )
    await db.commit()
    return {"id": user.id, "username": user.username, "email": user.email, "role_id": user.role_id}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    actor: User = Depends(require_permission("rbac:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.email is not None:
        user.email = body.email
    if body.role_id is not None:
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
    await record_audit_event(
        db, actor=actor, request=request, permission="rbac:write", action="update_user", target_resource=f"user:{user.username}"
    )
    await db.commit()
    return {"updated": True, "id": user.id}
