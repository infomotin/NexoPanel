"""Telemetry, Log Observability, Service Control, System Package Manager, Audit Logs & Settings."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import time
from pathlib import Path
from typing import Any

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
    core_services = ["nginx", "mariadb", "postgresql", "postfix", "dovecot", "bind9", "pure-ftpd", "redis-server", "docker", "fail2ban"]
    results = []
    for svc in core_services:
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


# --- System Package Manager (apt) & Curated Software Catalog ---

CURATED_STACK_CATALOG: list[dict[str, Any]] = [
    {
        "slug": "nginx",
        "name": "Nginx Web Server",
        "category": "Web Server",
        "description": "High performance asynchronous HTTP server, reverse proxy, and SSL/TLS terminator.",
        "apt_packages": ["nginx"],
        "service": "nginx",
        "icon": "globe",
    },
    {
        "slug": "apache2",
        "name": "Apache HTTP Server",
        "category": "Web Server",
        "description": "Traditional Apache2 web server with .htaccess support and modular architecture.",
        "apt_packages": ["apache2"],
        "service": "apache2",
        "icon": "globe",
    },
    {
        "slug": "php8.4",
        "name": "PHP 8.4 (FPM)",
        "category": "PHP",
        "description": "Latest PHP 8.4 runtime with PHP-FPM and standard extensions (mysql, curl, mbstring, xml, zip, gd, opcache).",
        "apt_packages": ["php8.4-fpm", "php8.4-cli", "php8.4-mysql", "php8.4-curl", "php8.4-mbstring", "php8.4-xml", "php8.4-zip", "php8.4-gd", "php8.4-opcache"],
        "service": "php8.4-fpm",
        "php_version": "8.4",
        "icon": "file-code",
    },
    {
        "slug": "php8.3",
        "name": "PHP 8.3 (FPM)",
        "category": "PHP",
        "description": "Production PHP 8.3 runtime with PHP-FPM and standard web extensions.",
        "apt_packages": ["php8.3-fpm", "php8.3-cli", "php8.3-mysql", "php8.3-curl", "php8.3-mbstring", "php8.3-xml", "php8.3-zip", "php8.3-gd", "php8.3-opcache"],
        "service": "php8.3-fpm",
        "php_version": "8.3",
        "icon": "file-code",
    },
    {
        "slug": "php8.2",
        "name": "PHP 8.2 (FPM)",
        "category": "PHP",
        "description": "Ubuntu LTS default PHP 8.2 runtime with PHP-FPM and standard web extensions.",
        "apt_packages": ["php8.2-fpm", "php8.2-cli", "php8.2-mysql", "php8.2-curl", "php8.2-mbstring", "php8.2-xml", "php8.2-zip", "php8.2-gd"],
        "service": "php8.2-fpm",
        "php_version": "8.2",
        "icon": "file-code",
    },
    {
        "slug": "php8.1",
        "name": "PHP 8.1 (FPM)",
        "category": "PHP",
        "description": "PHP 8.1 runtime for legacy applications and frameworks.",
        "apt_packages": ["php8.1-fpm", "php8.1-cli", "php8.1-mysql", "php8.1-curl", "php8.1-mbstring", "php8.1-xml", "php8.1-zip"],
        "service": "php8.1-fpm",
        "php_version": "8.1",
        "icon": "file-code",
    },
    {
        "slug": "php8.0",
        "name": "PHP 8.0 (FPM)",
        "category": "PHP",
        "description": "PHP 8.0 runtime for legacy web applications.",
        "apt_packages": ["php8.0-fpm", "php8.0-cli", "php8.0-mysql", "php8.0-curl", "php8.0-mbstring", "php8.0-xml", "php8.0-zip"],
        "service": "php8.0-fpm",
        "php_version": "8.0",
        "icon": "file-code",
    },
    {
        "slug": "php7.4",
        "name": "PHP 7.4 (FPM)",
        "category": "PHP",
        "description": "Legacy PHP 7.4 runtime for older WordPress plugins and codebases.",
        "apt_packages": ["php7.4-fpm", "php7.4-cli", "php7.4-mysql", "php7.4-curl", "php7.4-mbstring", "php7.4-xml", "php7.4-zip"],
        "service": "php7.4-fpm",
        "php_version": "7.4",
        "icon": "file-code",
    },
    {
        "slug": "mariadb",
        "name": "MariaDB Server",
        "category": "Database",
        "description": "High-performance drop-in replacement for MySQL relational database server.",
        "apt_packages": ["mariadb-server", "mariadb-client"],
        "service": "mariadb",
        "icon": "database",
    },
    {
        "slug": "mysql",
        "name": "MySQL Server",
        "category": "Database",
        "description": "Oracle MySQL relational database management system.",
        "apt_packages": ["mysql-server"],
        "service": "mysql",
        "icon": "database",
    },
    {
        "slug": "postgresql",
        "name": "PostgreSQL",
        "category": "Database",
        "description": "Advanced open-source object-relational database management system.",
        "apt_packages": ["postgresql", "postgresql-contrib"],
        "service": "postgresql",
        "icon": "database",
    },
    {
        "slug": "redis",
        "name": "Redis In-Memory Cache",
        "category": "Database",
        "description": "In-memory data structure store used as a database, cache, and message broker.",
        "apt_packages": ["redis-server"],
        "service": "redis-server",
        "icon": "database",
    },
    {
        "slug": "memcached",
        "name": "Memcached Object Store",
        "category": "Database",
        "description": "High-performance distributed memory caching system for accelerating dynamic web apps.",
        "apt_packages": ["memcached"],
        "service": "memcached",
        "icon": "database",
    },
    {
        "slug": "pure-ftpd",
        "name": "Pure-FTPd Server",
        "category": "FTP",
        "description": "Secure production-grade FTP daemon with virtual database isolation and TLS encryption.",
        "apt_packages": ["pure-ftpd"],
        "service": "pure-ftpd",
        "icon": "hard-drive",
    },
    {
        "slug": "nodejs",
        "name": "Node.js & NPM",
        "category": "Runtime",
        "description": "Event-driven JavaScript runtime and package manager for SSR and microservices.",
        "apt_packages": ["nodejs", "npm"],
        "service": None,
        "icon": "cpu",
    },
    {
        "slug": "python3",
        "name": "Python 3 & venv",
        "category": "Runtime",
        "description": "Python 3 programming environment with pip package installer and virtual environments.",
        "apt_packages": ["python3", "python3-pip", "python3-venv"],
        "service": None,
        "icon": "cpu",
    },
    {
        "slug": "composer",
        "name": "Composer PHP Manager",
        "category": "Tools",
        "description": "Standard dependency and library manager for PHP projects and frameworks.",
        "apt_packages": ["composer"],
        "service": None,
        "icon": "tool",
    },
    {
        "slug": "supervisor",
        "name": "Supervisor Process Manager",
        "category": "Tools",
        "description": "System for monitoring and controlling background daemon processes and worker queues.",
        "apt_packages": ["supervisor"],
        "service": "supervisor",
        "icon": "cpu",
    },
    {
        "slug": "docker",
        "name": "Docker Engine",
        "category": "Tools",
        "description": "Container runtime platform for running Docker containers and Compose environments.",
        "apt_packages": ["docker.io"],
        "service": "docker",
        "icon": "container",
    },
    {
        "slug": "ufw",
        "name": "UFW Firewall",
        "category": "Security",
        "description": "Host-based packet filtering firewall configuration tool.",
        "apt_packages": ["ufw"],
        "service": "ufw",
        "icon": "flame",
    },
    {
        "slug": "fail2ban",
        "name": "Fail2ban Defense",
        "category": "Security",
        "description": "Automated brute-force intrusion prevention analyzing system and authentication logs.",
        "apt_packages": ["fail2ban"],
        "service": "fail2ban",
        "icon": "shield",
    },
    {
        "slug": "certbot",
        "name": "Certbot (Let's Encrypt)",
        "category": "Security",
        "description": "Automated ACME client for issuing and renewing free SSL/TLS certificates.",
        "apt_packages": ["certbot", "python3-certbot-nginx"],
        "service": None,
        "icon": "key",
    },
    {
        "slug": "git",
        "name": "Git SCM",
        "category": "Tools",
        "description": "Fast and distributed version control system for web deployments.",
        "apt_packages": ["git"],
        "service": None,
        "icon": "tool",
    },
]


@router.get("/packages/catalog")
async def get_curated_packages_catalog(
    category: str = Query(default="ALL"),
    search: str = Query(default=""),
    _: User = Depends(require_permission("packages:read")),
) -> list[dict]:
    executor = get_node_executor()
    distro = get_distro_driver()

    res = await executor.run_command(
        ["/usr/bin/dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"]
    )
    installed_map: dict[str, dict[str, str]] = {}
    if res.ok:
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and "installed" in parts[2]:
                installed_map[parts[0]] = {"version": parts[1], "status": parts[2]}

    results = []
    for item in CURATED_STACK_CATALOG:
        cat_match = category == "ALL" or category == "Installed" or item["category"].lower() == category.lower()
        if not cat_match:
            continue
        if search:
            s = search.lower()
            if s not in item["name"].lower() and s not in item["description"].lower() and s not in item["slug"].lower():
                continue

        primary_pkg = item["apt_packages"][0]
        is_installed = primary_pkg in installed_map
        version = installed_map[primary_pkg]["version"] if is_installed else None

        service_status = "none"
        if is_installed and item.get("service"):
            try:
                svc_cmd = distro.build_service_control_cmd(item["service"], "is-active")
                svc_res = await executor.run_command(svc_cmd)
                service_status = svc_res.stdout.strip() or ("active" if svc_res.ok else "inactive")
            except Exception:
                service_status = "inactive"

        if category == "Installed" and not is_installed:
            continue

        results.append({
            **item,
            "is_installed": is_installed,
            "version": version,
            "service_status": service_status,
        })

    return results


@router.get("/runtimes/php")
async def get_php_runtimes(_: User = Depends(require_permission("websites:read"))) -> list[dict]:
    executor = get_node_executor()
    distro = get_distro_driver()
    versions = ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0", "7.4"]
    results = []

    res = await executor.run_command(
        ["/usr/bin/dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"]
    )
    installed_pkgs = set()
    if res.ok:
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and "installed" in parts[2]:
                installed_pkgs.add(parts[0])

    for v in versions:
        fpm_pkg = f"php{v}-fpm"
        is_installed = fpm_pkg in installed_pkgs
        service_status = "inactive"
        if is_installed:
            try:
                svc_cmd = distro.build_service_control_cmd(fpm_pkg, "is-active")
                svc_res = await executor.run_command(svc_cmd)
                service_status = svc_res.stdout.strip() or ("active" if svc_res.ok else "inactive")
            except Exception:
                service_status = "inactive"

        status_text = "Running" if service_status == "active" else ("Installed" if is_installed else "Not Installed")
        results.append({
            "version": v,
            "is_installed": is_installed,
            "socket": f"/run/php/php{v}-fpm.sock",
            "service_status": service_status,
            "label": f"PHP {v} ({status_text})",
        })

    return results


@router.post("/packages/curated/{slug}/install")
async def install_curated_package(
    slug: str,
    request: Request,
    actor: User = Depends(require_permission("packages:write")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    target = next((item for item in CURATED_STACK_CATALOG if item["slug"] == slug), None)
    if not target:
        raise HTTPException(status_code=404, detail="Curated software package not found")

    distro = get_distro_driver()
    executor = get_node_executor()
    validated = [validate_package_name(p) for p in target["apt_packages"]]
    cmd = distro.build_install_package_cmd(validated)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="packages:write",
        action=f"install_curated_{slug}",
        target_resource=slug,
    )
    await db.commit()

    pkg_name = target["name"]
    cmd_str = " ".join(cmd)

    async def event_stream():
        yield f"data: {json.dumps({'line': f'=== NexoPanel Package Installer: Installing {pkg_name} ==='})}\n\n"
        yield f"data: {json.dumps({'line': f'Running command: {cmd_str}'})}\n\n"
        res = await executor.run_command(cmd, timeout=600)
        for line in (res.stdout + "\n" + res.stderr).splitlines():
            if line.strip():
                yield f"data: {json.dumps({'line': line})}\n\n"

        if res.ok:
            yield f"data: {json.dumps({'line': '✓ APT packages installed successfully.'})}\n\n"
            svc = target.get("service")
            if svc:
                yield f"data: {json.dumps({'line': f'Configuring and starting systemd service: {svc}...'})}\n\n"
                try:
                    enable_cmd = distro.build_service_control_cmd(svc, "enable")
                    start_cmd = distro.build_service_control_cmd(svc, "restart")
                    await executor.run_command(enable_cmd)
                    start_res = await executor.run_command(start_cmd)
                    if start_res.ok:
                        yield f"data: {json.dumps({'line': f'✓ Service {svc} is now active and operational.'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'line': f'! Service restart: {start_res.stderr or start_res.stdout}'})}\n\n"
                except Exception as ex:
                    yield f"data: {json.dumps({'line': f'! Post-install service step: {ex}'})}\n\n"

            yield f"data: {json.dumps({'line': f'🎉 Installation of {pkg_name} complete and integrated with NexoPanel!'})}\n\n"
        else:
            yield f"data: {json.dumps({'line': f'✗ Installation failed with exit code {res.returncode}'})}\n\n"

        yield f"data: {json.dumps({'done': True, 'returncode': res.returncode})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/packages/curated/{slug}/uninstall")
async def uninstall_curated_package(
    slug: str,
    request: Request,
    actor: User = Depends(require_permission("packages:write")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    target = next((item for item in CURATED_STACK_CATALOG if item["slug"] == slug), None)
    if not target:
        raise HTTPException(status_code=404, detail="Curated software package not found")

    distro = get_distro_driver()
    executor = get_node_executor()
    validated = [validate_package_name(p) for p in target["apt_packages"]]
    cmd = distro.build_remove_package_cmd(validated)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="packages:write",
        action=f"uninstall_curated_{slug}",
        target_resource=slug,
    )
    await db.commit()

    pkg_name = target["name"]
    cmd_str = " ".join(cmd)

    async def event_stream():
        yield f"data: {json.dumps({'line': f'=== NexoPanel Package Manager: Removing {pkg_name} ==='})}\n\n"
        svc = target.get("service")
        if svc:
            yield f"data: {json.dumps({'line': f'Stopping service: {svc}...'})}\n\n"
            try:
                stop_cmd = distro.build_service_control_cmd(svc, "stop")
                await executor.run_command(stop_cmd)
            except Exception:
                pass

        yield f"data: {json.dumps({'line': f'Running command: {cmd_str}'})}\n\n"
        res = await executor.run_command(cmd, timeout=300)
        for line in (res.stdout + "\n" + res.stderr).splitlines():
            if line.strip():
                yield f"data: {json.dumps({'line': line})}\n\n"

        if res.ok:
            yield f"data: {json.dumps({'line': f'✓ {pkg_name} was cleanly uninstalled.'})}\n\n"
        else:
            yield f"data: {json.dumps({'line': f'✗ Removal exited with code {res.returncode}'})}\n\n"

        yield f"data: {json.dumps({'done': True, 'returncode': res.returncode})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/packages/curated/{slug}/control")
async def control_curated_package_service(
    slug: str,
    body: ServiceControlRequest,
    request: Request,
    actor: User = Depends(require_permission("packages:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = next((item for item in CURATED_STACK_CATALOG if item["slug"] == slug), None)
    if not target or not target.get("service"):
        raise HTTPException(status_code=400, detail="Package has no associated system service")

    distro = get_distro_driver()
    executor = get_node_executor()
    cmd = distro.build_service_control_cmd(target["service"], body.action)
    res = await executor.run_command(cmd)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="packages:write",
        action=f"package_service_{body.action}",
        target_resource=f"{slug}:{target['service']}",
        status="success" if res.ok else "failed",
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.post("/packages/update-cache")
async def update_package_cache(
    request: Request,
    actor: User = Depends(require_permission("packages:write")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    executor = get_node_executor()
    cmd = ["/usr/bin/apt-get", "update", "-q"]
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="packages:write",
        action="apt_update_cache",
        target_resource="apt-cache",
    )
    await db.commit()

    async def event_stream():
        yield f"data: {json.dumps({'line': '=== Updating APT Package Repository Index (apt-get update) ==='})}\n\n"
        res = await executor.run_command(cmd, timeout=300)
        for line in (res.stdout + "\n" + res.stderr).splitlines():
            if line.strip():
                yield f"data: {json.dumps({'line': line})}\n\n"
        yield f"data: {json.dumps({'line': '✓ Package index update finished.' if res.ok else '✗ Update failed.'})}\n\n"
        yield f"data: {json.dumps({'done': True, 'returncode': res.returncode})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
