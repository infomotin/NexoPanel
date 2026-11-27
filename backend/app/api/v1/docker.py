"""Docker Container & Image Management API router."""
from __future__ import annotations

import json
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.db.models import User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/docker", tags=["Docker Manager"])

CONTAINER_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{2,64}$")
IMAGE_REF_RE = re.compile(r"^[a-zA-Z0-9._/:@-]{2,128}$")


class ImagePullRequest(BaseModel):
    image: str = Field(min_length=2, max_length=128)


@router.get("/containers")
async def list_containers(_: User = Depends(require_permission("docker:read"))) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/docker", "ps", "-a", "--format", "{{json .}}"])
    containers = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"available": res.ok, "containers": containers, "error": res.stderr if not res.ok else ""}


@router.post("/containers/{container_id}/{action}")
async def control_container(
    container_id: str,
    action: str,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container ID")
    if action not in {"start", "stop", "restart", "rm"}:
        raise HTTPException(status_code=400, detail="Invalid docker action")
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/docker", action, container_id])
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action=f"docker_{action}", target_resource=container_id
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.get("/images")
async def list_images(_: User = Depends(require_permission("docker:read"))) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/docker", "images", "--format", "{{json .}}"])
    images = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"images": images}


@router.post("/images/pull")
async def pull_image(
    body: ImagePullRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not IMAGE_REF_RE.match(body.image):
        raise HTTPException(status_code=400, detail="Invalid Docker image reference")
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/docker", "pull", body.image], timeout=300)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_pull", target_resource=body.image
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}
