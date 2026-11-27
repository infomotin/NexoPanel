"""Process Task Manager & Listening Network Ports API router."""
from __future__ import annotations

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/processes", tags=["Task & Process Manager"])


@router.get("")
async def list_processes(
    limit: int = Query(default=50, ge=10, le=200),
    _: User = Depends(require_permission("processes:read")),
) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "username": info.get("username") or "-",
                    "cpu_percent": round(info.get("cpu_percent") or 0.0, 2),
                    "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                    "status": info.get("status") or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: (x["cpu_percent"], x["memory_percent"]), reverse=True)
    return procs[:limit]


@router.get("/ports")
async def list_listening_ports(_: User = Depends(require_permission("processes:read"))) -> list[dict]:
    ports = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN":
                ports.append(
                    {
                        "ip": conn.laddr.ip,
                        "port": conn.laddr.port,
                        "pid": conn.pid,
                        "family": "IPv6" if conn.family.name == "AF_INET6" else "IPv4",
                    }
                )
    except psutil.AccessDenied:
        pass
    return sorted(ports, key=lambda x: x["port"])


@router.post("/{pid}/kill")
async def kill_process(
    pid: int,
    request: Request,
    actor: User = Depends(require_permission("processes:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if pid <= 1:
        raise HTTPException(status_code=400, detail="Refusing to terminate PID <= 1")
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
    except psutil.NoSuchProcess as exc:
        raise HTTPException(status_code=404, detail="Process not found") from exc
    except psutil.AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Permission denied terminating process") from exc

    await record_audit_event(
        db, actor=actor, request=request, permission="processes:write", action="kill_process", target_resource=f"pid:{pid}:{name}"
    )
    await db.commit()
    return {"terminated": True, "pid": pid, "name": name}
