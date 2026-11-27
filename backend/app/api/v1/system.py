"""Telemetry, Log Observability, Service Control, System Package Manager, Audit Logs & Settings."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import time
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.security import decode_token
from app.core.validators import validate_package_name
from app.db.models import AuditLog, PanelSetting, User
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.services.executor import get_node_executor

router = APIRouter(prefix="/system", tags=["Telemetry, Packages, Logs & Settings"])


class ServiceControlRequest(BaseModel):
    service: str
    action: str = Field(pattern="^(start|stop|restart|reload)$")


class PackageActionRequest(BaseModel):
    packages: list[str] = Field(min_length=1)


class SettingUpdateRequest(BaseModel):
    value: str


def _collect_telemetry() -> dict:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "cpu_cores": psutil.cpu_count(logical=True),
        "load_average": [round(x, 2) for x in load_avg],
        "memory": {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent,
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
    }


@router.get("/telemetry")
async def get_telemetry(_: User = Depends(require_permission("telemetry:read"))) -> dict:
    return _collect_telemetry()


@router.websocket("/telemetry/ws")
async def telemetry_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            await websocket.send_json(_collect_telemetry())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass


@router.get("/services")
async def get_service_statuses(_: User = Depends(require_permission("telemetry:read"))) -> list[dict]:
    distro = get_distro_driver()
    executor = get_node_executor()
    services = ["nginx", "mariadb", "postgresql", "postfix", "dovecot", "bind9"]
    results = []
    for svc in services:
        res = await executor.run_command(distro.build_service_control_cmd(svc, "is-active"))
        status_str = res.stdout.strip() or ("active" if res.ok else "inactive")
        results.append({"name": svc, "status": status_str})
    return results


@router.post("/services/control")
async def control_service(
    body: ServiceControlRequest,
    request: Request,
    actor: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    distro = get_distro_driver()
    executor = get_node_executor()
    try:
        cmd = distro.build_service_control_cmd(body.service, body.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    res = await executor.run_command(cmd)
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="settings:write",
        action=f"service_{body.action}",
        target_resource=f"service:{body.service}",
        status="success" if res.ok else "failed",
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


# --- System Package Manager (apt) ---

@router.get("/packages")
async def list_installed_packages(
    search: str = Query(default=""),
    _: User = Depends(require_permission("packages:read")),
) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(
        ["/usr/bin/dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"]
    )
    packages = []
    if res.ok:
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                if search and search.lower() not in parts[0].lower():
                    continue
                packages.append({"name": parts[0], "version": parts[1], "status": parts[2] if len(parts) > 2 else "installed"})
    return {"packages": packages[:200]}


@router.post("/packages/{action}")
async def manage_packages(
    action: str,
    body: PackageActionRequest,
    request: Request,
    actor: User = Depends(require_permission("packages:write")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    validated = [validate_package_name(p) for p in body.packages]
    distro = get_distro_driver()
    if action == "install":
        cmd = distro.build_install_package_cmd(validated)
    elif action == "remove":
        cmd = distro.build_remove_package_cmd(validated)
    elif action == "upgrade":
        cmd = distro.build_upgrade_package_cmd(validated)
    else:
        raise HTTPException(status_code=400, detail="Invalid package action")

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="packages:write",
        action=f"apt_{action}",
        target_resource=",".join(validated),
    )
    await db.commit()

    executor = get_node_executor()

    async def event_stream():
        res = await executor.run_command(cmd, timeout=300)
        for line in (res.stdout + "\n" + res.stderr).splitlines():
            yield f"data: {json.dumps({'line': line})}\n\n"
        yield f"data: {json.dumps({'done': True, 'returncode': res.returncode})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Log Observability ---

LOG_TARGETS: dict[str, Path] = {
    "nginx_access": Path("/var/log/nginx/access.log"),
    "nginx_error": Path("/var/log/nginx/error.log"),
    "syslog": Path("/var/log/syslog"),
    "mail": Path("/var/log/mail.log"),
    "nexopanel": settings.LOG_DIR / "nexopanel.log",
}


@router.get("/logs/{target}")
async def get_system_logs(
    target: str,
    lines: int = Query(default=150, ge=10, le=2000),
    search: str = Query(default=""),
    _: User = Depends(require_permission("logs:read")),
) -> dict:
    if target not in LOG_TARGETS:
        raise HTTPException(status_code=404, detail="Unknown log target")
    path = LOG_TARGETS[target]
    if not path.exists():
        return {"target": target, "path": str(path), "lines": []}
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if search:
        content = [l for l in content if search.lower() in l.lower()]
    return {"target": target, "path": str(path), "lines": content[-lines:]}


# --- Immutable Audit Log ---

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permission("security:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    logs = (await db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": l.id,
            "node_id": l.node_id,
            "timestamp": l.timestamp.isoformat(),
            "actor_username": l.actor_username,
            "source_ip": l.source_ip,
            "permission": l.permission,
            "action": l.action,
            "target_resource": l.target_resource,
            "before_state": l.before_state,
            "after_state": l.after_state,
            "status": l.status,
        }
        for l in logs
    ]


# --- Panel Settings ---

@router.get("/settings")
async def list_settings(
    _: User = Depends(require_permission("settings:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (await db.execute(select(PanelSetting))).scalars().all()
    return [{"key": r.key, "value": "********" if r.is_secret else r.value, "is_secret": r.is_secret} for r in rows]


@router.put("/settings/{key}")
async def update_setting(
    key: str,
    body: SettingUpdateRequest,
    request: Request,
    actor: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    if not row:
        row = PanelSetting(key=key, value=body.value, is_secret=False)
        db.add(row)
    else:
        row.value = body.value
    await record_audit_event(
        db, actor=actor, request=request, permission="settings:write", action="update_setting", target_resource=f"setting:{key}"
    )
    await db.commit()
    return {"key": key, "updated": True}
