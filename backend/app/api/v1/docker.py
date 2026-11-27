"""Docker Container, Image, Volume, Network, and Template Management API router."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.drivers.distro import get_distro_driver
from app.core.rbac import require_permission
from app.db.models import User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/docker", tags=["Docker Manager"])

CONTAINER_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{2,128}$")
IMAGE_REF_RE = re.compile(r"^[a-zA-Z0-9._/:@-]{2,255}$")
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")
PORT_SPEC_RE = re.compile(r"^(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}:)?([0-9]{1,5}):([0-9]{1,5})(?:/(?:tcp|udp))?$")

# Curated App Stack Templates
TEMPLATES_CATALOG = [
    {
        "id": "redis",
        "name": "Redis In-Memory Cache",
        "category": "Cache & Queue",
        "description": "Blazing fast in-memory key-value store, cache, and message broker.",
        "icon": "lightning",
        "image": "redis:7-alpine",
        "default_name": "redis-server",
        "default_ports": ["6379:6379"],
        "default_env": {},
        "default_volumes": ["redis_data:/data"],
        "command": "redis-server --appendonly yes",
    },
    {
        "id": "postgres",
        "name": "PostgreSQL 16 Database",
        "category": "Databases",
        "description": "Enterprise-grade open-source relational database with JSON support.",
        "icon": "database",
        "image": "postgres:16-alpine",
        "default_name": "postgres-db",
        "default_ports": ["5432:5432"],
        "default_env": {
            "POSTGRES_DB": "nexopanel",
            "POSTGRES_USER": "nexo_user",
            "POSTGRES_PASSWORD": "ChangeThisSecurePassword123!",
        },
        "default_volumes": ["pg_data:/var/lib/postgresql/data"],
        "command": "",
    },
    {
        "id": "mariadb",
        "name": "MariaDB 10.11 (MySQL)",
        "category": "Databases",
        "description": "High performance community-developed MySQL drop-in relational database.",
        "icon": "database",
        "image": "mariadb:10.11",
        "default_name": "mariadb-server",
        "default_ports": ["3306:3306"],
        "default_env": {
            "MARIADB_ROOT_PASSWORD": "ChangeThisRootPassword123!",
            "MARIADB_DATABASE": "app_db",
            "MARIADB_USER": "dbuser",
            "MARIADB_PASSWORD": "ChangeThisUserPassword123!",
        },
        "default_volumes": ["mariadb_data:/var/lib/mysql"],
        "command": "",
    },
    {
        "id": "nginx",
        "name": "Nginx Web & Reverse Proxy",
        "category": "Web Servers",
        "description": "High-performance HTTP server, reverse proxy, and static file server.",
        "icon": "globe",
        "image": "nginx:alpine",
        "default_name": "nginx-web",
        "default_ports": ["8088:80"],
        "default_env": {},
        "default_volumes": ["nginx_html:/usr/share/nginx/html"],
        "command": "",
    },
    {
        "id": "portainer",
        "name": "Portainer CE",
        "category": "Management",
        "description": "Powerful container management web GUI for managing Docker environments.",
        "icon": "cube",
        "image": "portainer/portainer-ce:latest",
        "default_name": "portainer-ce",
        "default_ports": ["9000:9000", "9443:9443"],
        "default_env": {},
        "default_volumes": [
            "/var/run/docker.sock:/var/run/docker.sock",
            "portainer_data:/data",
        ],
        "command": "",
    },
    {
        "id": "adminer",
        "name": "Adminer DB Management",
        "category": "Tools",
        "description": "Lightweight single-file database management tool in a single container.",
        "icon": "table",
        "image": "adminer:latest",
        "default_name": "adminer-web",
        "default_ports": ["8081:8080"],
        "default_env": {},
        "default_volumes": [],
        "command": "",
    },
    {
        "id": "uptime-kuma",
        "name": "Uptime Kuma Monitoring",
        "category": "Monitoring",
        "description": "Self-hosted monitoring tool for HTTP, TCP, Ping, DNS, and SSL certificates.",
        "icon": "chart",
        "image": "louislam/uptime-kuma:1",
        "default_name": "uptime-kuma",
        "default_ports": ["3001:3001"],
        "default_env": {},
        "default_volumes": ["uptime_kuma_data:/app/data"],
        "command": "",
    },
    {
        "id": "node",
        "name": "Node.js 20 LTS Runtime",
        "category": "Development",
        "description": "Node.js JavaScript runtime environment with npm and yarn on Alpine Linux.",
        "icon": "code",
        "image": "node:20-alpine",
        "default_name": "node-app",
        "default_ports": ["3000:3000"],
        "default_env": {"NODE_ENV": "production"},
        "default_volumes": ["node_app_data:/app"],
        "command": "node -e 'console.log(\"Node.js container ready\")'",
    },
    {
        "id": "python",
        "name": "Python 3.11 Runtime",
        "category": "Development",
        "description": "Lightweight Python environment for running web APIs and background workers.",
        "icon": "code",
        "image": "python:3.11-slim",
        "default_name": "python-app",
        "default_ports": ["8000:8000"],
        "default_env": {"PYTHONUNBUFFERED": "1"},
        "default_volumes": ["python_app_data:/app"],
        "command": "python -c 'print(\"Python container ready\")'",
    },
    {
        "id": "vaultwarden",
        "name": "Vaultwarden Password Vault",
        "category": "Security",
        "description": "Lightweight self-hosted Bitwarden server implementation written in Rust.",
        "icon": "shield",
        "image": "vaultwarden/server:latest",
        "default_name": "vaultwarden",
        "default_ports": ["8085:80"],
        "default_env": {"SIGNUPS_ALLOWED": "true"},
        "default_volumes": ["vaultwarden_data:/data"],
        "command": "",
    },
    {
        "id": "rabbitmq",
        "name": "RabbitMQ Message Broker",
        "category": "Cache & Queue",
        "description": "Robust message broker with AMQP messaging and web administration console.",
        "icon": "mail",
        "image": "rabbitmq:3-management-alpine",
        "default_name": "rabbitmq-server",
        "default_ports": ["5672:5672", "15672:15672"],
        "default_env": {
            "RABBITMQ_DEFAULT_USER": "admin",
            "RABBITMQ_DEFAULT_PASS": "ChangeThisRabbitMQPassword123!",
        },
        "default_volumes": ["rabbitmq_data:/var/lib/rabbitmq"],
        "command": "",
    },
]


# Schemas
class ImagePullRequest(BaseModel):
    image: str = Field(min_length=2, max_length=255)


class ContainerRunRequest(BaseModel):
    name: str = Field(default="", max_length=64)
    image: str = Field(min_length=2, max_length=255)
    ports: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)
    restart_policy: str = Field(default="unless-stopped")
    memory_limit: str = Field(default="")
    network: str = Field(default="")
    command: str = Field(default="")


class ContainerExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=512)


class VolumeCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    driver: str = Field(default="local", max_length=32)


class NetworkCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    driver: str = Field(default="bridge", max_length=32)


class PruneRequest(BaseModel):
    all: bool = Field(default=False)
    volumes: bool = Field(default=False)


class TemplateDeployRequest(BaseModel):
    template_id: str = Field(min_length=2, max_length=64)
    name: str = Field(default="", max_length=64)
    ports: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)


class ComposeDeployRequest(BaseModel):
    project_name: str = Field(min_length=2, max_length=64)
    compose_yaml: str = Field(min_length=10, max_length=65536)


# Helpers
def _parse_container_ports(ports_str: str | None) -> list[dict[str, str]]:
    """Parse Docker port string like '0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp' into structured items."""
    if not ports_str:
        return []
    items: list[dict[str, str]] = []
    for part in ports_str.split(","):
        p = part.strip()
        if not p:
            continue
        # Format often: 0.0.0.0:8080->80/tcp or 80/tcp
        if "->" in p:
            host, container = p.split("->", 1)
            host_port = host.split(":")[-1] if ":" in host else host
            proto = container.split("/")[-1] if "/" in container else "tcp"
            cont_port = container.split("/")[0]
            items.append({
                "host_port": host_port,
                "container_port": cont_port,
                "protocol": proto,
                "full": p,
            })
        else:
            items.append({
                "host_port": "",
                "container_port": p.split("/")[0],
                "protocol": p.split("/")[-1] if "/" in p else "tcp",
                "full": p,
            })
    return items


# Routes
@router.get("/status")
async def get_docker_status(_: User = Depends(require_permission("docker:read"))) -> dict[str, Any]:
    """Retrieve Docker daemon status, version information, system resource counts, and disk usage."""
    executor = get_node_executor()
    distro = get_distro_driver()

    # In mock mode, return rich mock data
    if getattr(executor, "use_mock", False):
        return {
            "installed": True,
            "active": True,
            "service_status": "active",
            "version": {
                "Client": {"Version": "26.1.3", "ApiVersion": "1.45"},
                "Server": {"Version": "26.1.3", "ApiVersion": "1.45", "Os": "linux", "Arch": "amd64"},
            },
            "info": {
                "Containers": 3,
                "ContainersRunning": 2,
                "ContainersPaused": 0,
                "ContainersStopped": 1,
                "Images": 4,
                "Driver": "overlay2",
                "OperatingSystem": "Ubuntu 22.04.4 LTS",
                "NCPU": 4,
                "MemTotal": 8589934592,
                "DockerRootDir": "/var/lib/docker",
            },
            "disk_usage": {
                "Images": {"TotalCount": 4, "ActiveCount": 2, "Size": 1420000000},
                "Containers": {"TotalCount": 3, "ActiveCount": 2, "Size": 45000000},
                "Volumes": {"TotalCount": 3, "ActiveCount": 2, "Size": 120000000},
                "BuildCache": {"TotalCount": 0, "ActiveCount": 0, "Size": 0},
            },
            "error": "",
        }

    # Check system service status
    svc_res = await executor.run_command(distro.build_service_control_cmd("docker", "is-active"))
    service_status = svc_res.stdout.strip() if svc_res.ok else "inactive"
    is_active = service_status == "active"

    # Check docker version
    ver_res = await executor.run_command(["/usr/bin/docker", "version", "--format", "{{json .}}"])
    installed = ver_res.returncode != 127 and "Executable not found" not in ver_res.stderr

    version_data: dict[str, Any] = {}
    if ver_res.ok and ver_res.stdout.strip():
        try:
            version_data = json.loads(ver_res.stdout.strip())
        except json.JSONDecodeError:
            version_data = {"raw": ver_res.stdout.strip()}

    info_data: dict[str, Any] = {}
    if is_active:
        inf_res = await executor.run_command(["/usr/bin/docker", "info", "--format", "{{json .}}"])
        if inf_res.ok and inf_res.stdout.strip():
            try:
                info_data = json.loads(inf_res.stdout.strip())
            except json.JSONDecodeError:
                pass

    disk_usage: dict[str, Any] = {}
    if is_active:
        df_res = await executor.run_command(["/usr/bin/docker", "system", "df", "--format", "{{json .}}"])
        if df_res.ok and df_res.stdout.strip():
            df_rows: list[dict[str, Any]] = []
            for line in df_res.stdout.splitlines():
                try:
                    df_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            disk_usage = {"rows": df_rows}

    err_msg = ""
    if not installed:
        err_msg = "Docker is not installed on this server."
    elif not is_active:
        err_msg = f"Docker daemon is not running (service is {service_status})."

    return {
        "installed": installed,
        "active": is_active,
        "service_status": service_status,
        "version": version_data,
        "info": info_data,
        "disk_usage": disk_usage,
        "error": err_msg,
    }


@router.post("/install")
async def install_docker(
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Install Docker Engine and Docker Compose via distro package manager and start service."""
    executor = get_node_executor()
    distro = get_distro_driver()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="install_docker", target_resource="docker"
        )
        await db.commit()
        return {"ok": True, "message": "Docker Engine installed and started successfully (mock)."}

    # Update package index and install docker.io and docker-compose-v2
    update_cmd = distro.build_update_pkg_cache_cmd()
    await executor.run_command(update_cmd, timeout=300)

    install_cmd = distro.build_install_package_cmd(["docker.io", "docker-compose-v2"])
    res = await executor.run_command(install_cmd, timeout=600)
    if not res.ok:
        # Fallback to docker.io alone if compose v2 package name is different
        res = await executor.run_command(distro.build_install_package_cmd(["docker.io"]), timeout=600)

    # Enable and start docker service
    await executor.run_command(distro.build_service_control_cmd("docker", "enable"))
    start_res = await executor.run_command(distro.build_service_control_cmd("docker", "start"))

    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="install_docker", target_resource="docker"
    )
    await db.commit()

    return {
        "ok": start_res.ok or res.ok,
        "stdout": res.stdout + "\n" + start_res.stdout,
        "stderr": res.stderr + "\n" + start_res.stderr,
        "message": "Docker installation finished." if (res.ok and start_res.ok) else "Docker installation encountered warnings.",
    }


@router.post("/service/{action}")
async def control_docker_service(
    action: str,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Control the Docker system service (start, stop, restart)."""
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=400, detail="Invalid service action")
    executor = get_node_executor()
    distro = get_distro_driver()

    if getattr(executor, "use_mock", False):
        return {"ok": True, "action": action, "status": "active" if action != "stop" else "inactive"}

    cmd = distro.build_service_control_cmd("docker", action)
    res = await executor.run_command(cmd)

    status_cmd = distro.build_service_control_cmd("docker", "is-active")
    stat_res = await executor.run_command(status_cmd)
    current_status = stat_res.stdout.strip() if stat_res.ok else "inactive"

    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action=f"docker_service_{action}", target_resource="docker"
    )
    await db.commit()
    return {"ok": res.ok, "status": current_status, "stderr": res.stderr}


@router.get("/containers")
async def list_containers(
    status: str = Query(default="all", pattern=r"^(all|running|stopped|paused)$"),
    _: User = Depends(require_permission("docker:read")),
) -> dict[str, Any]:
    """List Docker containers with parsed port mappings and live resource statistics."""
    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        mock_containers = [
            {
                "ID": "1a2b3c4d5e6f",
                "Names": "nexopanel-redis",
                "Image": "redis:7-alpine",
                "State": "running",
                "Status": "Up 3 hours",
                "Created": "3 hours ago",
                "Ports": "0.0.0.0:6379->6379/tcp",
                "parsed_ports": [{"host_port": "6379", "container_port": "6379", "protocol": "tcp", "full": "0.0.0.0:6379->6379/tcp"}],
                "cpu_perc": "0.15%",
                "mem_usage": "14.2MiB / 1GiB",
                "mem_perc": "1.38%",
                "net_io": "2.4MB / 1.8MB",
            },
            {
                "ID": "2b3c4d5e6f7a",
                "Names": "nexopanel-nginx",
                "Image": "nginx:alpine",
                "State": "running",
                "Status": "Up 5 hours",
                "Ports": "0.0.0.0:8088->80/tcp",
                "parsed_ports": [{"host_port": "8088", "container_port": "80", "protocol": "tcp", "full": "0.0.0.0:8088->80/tcp"}],
                "cpu_perc": "0.08%",
                "mem_usage": "8.5MiB / 1GiB",
                "mem_perc": "0.83%",
                "net_io": "5.4MB / 12.1MB",
            },
            {
                "ID": "3c4d5e6f7a8b",
                "Names": "app-postgres",
                "Image": "postgres:16-alpine",
                "State": "exited",
                "Status": "Exited (0) 1 hour ago",
                "Created": "2 days ago",
                "Ports": "5432/tcp",
                "parsed_ports": [{"host_port": "", "container_port": "5432", "protocol": "tcp", "full": "5432/tcp"}],
                "cpu_perc": "0%",
                "mem_usage": "0B / 0B",
                "mem_perc": "0%",
                "net_io": "0B / 0B",
            },
        ]
        if status != "all":
            mock_containers = [c for c in mock_containers if c["State"].lower() == status]
        return {"available": True, "containers": mock_containers, "error": ""}

    res = await executor.run_command(["/usr/bin/docker", "ps", "-a", "--format", "{{json .}}"])
    containers: list[dict[str, Any]] = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                item = json.loads(line)
                item["parsed_ports"] = _parse_container_ports(item.get("Ports"))
                # Default empty stats
                item["cpu_perc"] = "0%"
                item["mem_usage"] = "0B"
                item["mem_perc"] = "0%"
                item["net_io"] = "0B"
                containers.append(item)
            except json.JSONDecodeError:
                continue

    # Attempt to fetch live stats for running containers
    if containers:
        stats_res = await executor.run_command(["/usr/bin/docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=10)
        if stats_res.ok and stats_res.stdout.strip():
            stats_map: dict[str, dict[str, str]] = {}
            for line in stats_res.stdout.splitlines():
                try:
                    s = json.loads(line)
                    c_id = s.get("ID", "")
                    c_name = s.get("Name", "")
                    stats_map[c_id] = s
                    if c_name:
                        stats_map[c_name] = s
                except json.JSONDecodeError:
                    continue
            for c in containers:
                cid = c.get("ID", "")
                cname = c.get("Names", "")
                matched = stats_map.get(cid) or stats_map.get(cname)
                if matched:
                    c["cpu_perc"] = matched.get("CPUPerc", "0%")
                    c["mem_usage"] = matched.get("MemUsage", "0B")
                    c["mem_perc"] = matched.get("MemPerc", "0%")
                    c["net_io"] = matched.get("NetIO", "0B")

    if status != "all":
        containers = [c for c in containers if c.get("State", "").lower() == status]

    return {"available": res.ok, "containers": containers, "error": res.stderr if not res.ok else ""}


@router.post("/containers/run")
async def run_container(
    body: ContainerRunRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deploy and start a new Docker container with port mappings, environment variables, and volume mounts."""
    if not IMAGE_REF_RE.match(body.image):
        raise HTTPException(status_code=400, detail="Invalid Docker image reference")
    if body.name and not NAME_RE.match(body.name):
        raise HTTPException(status_code=400, detail="Invalid container name (use letters, numbers, dash, underscore)")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_run", target_resource=body.name or body.image
        )
        await db.commit()
        return {"ok": True, "container_id": "mock_new_c12345", "stdout": "mock_new_c12345", "stderr": ""}

    args: list[str] = ["/usr/bin/docker", "run", "-d"]
    if body.name:
        args.extend(["--name", body.name])
    if body.restart_policy in {"no", "always", "unless-stopped", "on-failure"}:
        args.extend(["--restart", body.restart_policy])
    if body.memory_limit and re.match(r"^\d+[bkmgBKMG]$", body.memory_limit):
        args.extend(["--memory", body.memory_limit.lower()])
    if body.network and re.match(r"^[a-zA-Z0-9_-]+$", body.network):
        args.extend(["--network", body.network])

    for p in body.ports:
        p_clean = p.strip()
        if p_clean and (PORT_SPEC_RE.match(p_clean) or re.match(r"^\d+:\d+$", p_clean)):
            args.extend(["-p", p_clean])

    for k, v in body.env.items():
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
            args.extend(["-e", f"{k}={v}"])

    for v in body.volumes:
        v_clean = v.strip()
        if v_clean and ":" in v_clean:
            args.extend(["-v", v_clean])

    args.append(body.image)

    if body.command.strip():
        # Append safe command tokens
        import shlex
        args.extend(shlex.split(body.command.strip()))

    res = await executor.run_command(args, timeout=120)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_run", target_resource=body.name or body.image
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or "Failed to start container")

    return {"ok": True, "container_id": res.stdout.strip(), "stdout": res.stdout, "stderr": res.stderr}


@router.get("/containers/{container_id}/logs")
async def get_container_logs(
    container_id: str,
    tail: int = Query(default=100, ge=10, le=2000),
    timestamps: bool = Query(default=False),
    _: User = Depends(require_permission("docker:read")),
) -> dict[str, Any]:
    """Retrieve tail logs for a specific container."""
    if not CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container ID or name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        mock_log_lines = [
            f"[2026-11-28 00:00:{i:02d}] Container {container_id} healthy and serving connections"
            for i in range(1, 20)
        ]
        return {"container_id": container_id, "logs": "\n".join(mock_log_lines)}

    cmd = ["/usr/bin/docker", "logs", "--tail", str(tail)]
    if timestamps:
        cmd.append("-t")
    cmd.append(container_id)

    res = await executor.run_command(cmd, timeout=30)
    logs_output = res.stdout + ("\n" + res.stderr if res.stderr else "")
    return {"container_id": container_id, "logs": logs_output, "ok": res.ok}


@router.get("/containers/{container_id}/inspect")
async def inspect_container(
    container_id: str,
    _: User = Depends(require_permission("docker:read")),
) -> dict[str, Any]:
    """Retrieve detailed low-level JSON configuration for a container."""
    if not CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container ID or name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        return {
            "Id": container_id,
            "Name": f"/{container_id}",
            "State": {"Status": "running", "Running": True, "StartedAt": "2026-11-28T00:00:00Z"},
            "Config": {"Image": "redis:7-alpine", "Env": ["PATH=/usr/local/bin:/usr/bin"]},
            "NetworkSettings": {"IPAddress": "172.17.0.2", "Ports": {"6379/tcp": [{"HostPort": "6379"}]}},
        }

    res = await executor.run_command(["/usr/bin/docker", "inspect", container_id])
    if not res.ok:
        raise HTTPException(status_code=404, detail=res.stderr or "Container not found")
    try:
        data = json.loads(res.stdout)
        return data[0] if isinstance(data, list) and data else data
    except json.JSONDecodeError:
        return {"raw": res.stdout}


@router.post("/containers/{container_id}/exec")
async def exec_in_container(
    container_id: str,
    body: ContainerExecRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute a single diagnostic or management command inside a running container."""
    if not CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container ID or name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        return {"ok": True, "stdout": f"[mock-exec] Ran '{body.command}' in {container_id}\nAll systems operational.", "stderr": ""}

    import shlex
    cmd_tokens = shlex.split(body.command.strip())
    args = ["/usr/bin/docker", "exec", container_id] + cmd_tokens

    res = await executor.run_command(args, timeout=60)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_exec", target_resource=container_id
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}


@router.post("/containers/{container_id}/action/{action}")
@router.post("/containers/{container_id}/{action}")
async def control_container(
    container_id: str,
    action: str,
    request: Request,
    force: bool = Query(default=False),
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Control a Docker container (start, stop, restart, pause, unpause, kill, rm)."""
    if not CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container ID or name")
    valid_actions = {"start", "stop", "restart", "pause", "unpause", "kill", "rm"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid docker action. Choose from {valid_actions}")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action=f"docker_{action}", target_resource=container_id
        )
        await db.commit()
        return {"ok": True, "stdout": f"Container {container_id} {action}ed (mock)", "stderr": ""}

    cmd = ["/usr/bin/docker", action]
    if action == "rm" and force:
        cmd.append("-f")
    cmd.append(container_id)

    res = await executor.run_command(cmd, timeout=60)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action=f"docker_{action}", target_resource=container_id
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to {action} container {container_id}")

    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


# Images
@router.get("/images")
async def list_images(_: User = Depends(require_permission("docker:read"))) -> dict[str, Any]:
    """List local Docker images with repository, tag, size, and creation timestamp."""
    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        return {
            "images": [
                {"ID": "sha256:redis7", "Repository": "redis", "Tag": "7-alpine", "Size": "36.2MB", "CreatedAt": "2 weeks ago"},
                {"ID": "sha256:nginx1", "Repository": "nginx", "Tag": "alpine", "Size": "23.5MB", "CreatedAt": "3 weeks ago"},
                {"ID": "sha256:pg16", "Repository": "postgres", "Tag": "16-alpine", "Size": "98.4MB", "CreatedAt": "1 month ago"},
                {"ID": "sha256:node20", "Repository": "node", "Tag": "20-alpine", "Size": "142.1MB", "CreatedAt": "2 months ago"},
            ]
        }

    res = await executor.run_command(["/usr/bin/docker", "images", "--format", "{{json .}}"])
    images: list[dict[str, Any]] = []
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
) -> dict[str, Any]:
    """Pull an image from Docker Hub or a remote container registry."""
    if not IMAGE_REF_RE.match(body.image):
        raise HTTPException(status_code=400, detail="Invalid Docker image reference")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_pull", target_resource=body.image
        )
        await db.commit()
        return {"ok": True, "stdout": f"Status: Downloaded newer image for {body.image} (mock)", "stderr": ""}

    res = await executor.run_command(["/usr/bin/docker", "pull", body.image], timeout=600)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_pull", target_resource=body.image
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to pull image {body.image}")

    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.delete("/images/{image_id}")
async def remove_image(
    image_id: str,
    request: Request,
    force: bool = Query(default=False),
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove a local Docker image."""
    if not IMAGE_REF_RE.match(image_id):
        raise HTTPException(status_code=400, detail="Invalid Docker image ID or reference")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_rmi", target_resource=image_id
        )
        await db.commit()
        return {"ok": True, "stdout": f"Untagged: {image_id} (mock)", "stderr": ""}

    cmd = ["/usr/bin/docker", "rmi"]
    if force:
        cmd.append("-f")
    cmd.append(image_id)

    res = await executor.run_command(cmd, timeout=60)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_rmi", target_resource=image_id
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to delete image {image_id}")

    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


# Volumes
@router.get("/volumes")
async def list_volumes(_: User = Depends(require_permission("docker:read"))) -> dict[str, Any]:
    """List Docker storage volumes."""
    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        return {
            "volumes": [
                {"Name": "redis_data", "Driver": "local", "Scope": "local", "Mountpoint": "/var/lib/docker/volumes/redis_data/_data"},
                {"Name": "pg_data", "Driver": "local", "Scope": "local", "Mountpoint": "/var/lib/docker/volumes/pg_data/_data"},
                {"Name": "nginx_html", "Driver": "local", "Scope": "local", "Mountpoint": "/var/lib/docker/volumes/nginx_html/_data"},
            ]
        }

    res = await executor.run_command(["/usr/bin/docker", "volume", "ls", "--format", "{{json .}}"])
    volumes: list[dict[str, Any]] = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                volumes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"volumes": volumes}


@router.post("/volumes")
async def create_volume(
    body: VolumeCreateRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a persistent Docker storage volume."""
    if not NAME_RE.match(body.name):
        raise HTTPException(status_code=400, detail="Invalid volume name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_volume_create", target_resource=body.name
        )
        await db.commit()
        return {"ok": True, "volume": body.name}

    cmd = ["/usr/bin/docker", "volume", "create", "-d", body.driver, body.name]
    res = await executor.run_command(cmd)

    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_volume_create", target_resource=body.name
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to create volume {body.name}")

    return {"ok": res.ok, "volume": res.stdout.strip()}


@router.delete("/volumes/{name}")
async def remove_volume(
    name: str,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove a Docker storage volume."""
    if not NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid volume name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_volume_rm", target_resource=name
        )
        await db.commit()
        return {"ok": True}

    res = await executor.run_command(["/usr/bin/docker", "volume", "rm", name])
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_volume_rm", target_resource=name
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to remove volume {name}")

    return {"ok": res.ok, "stdout": res.stdout}


# Networks
@router.get("/networks")
async def list_networks(_: User = Depends(require_permission("docker:read"))) -> dict[str, Any]:
    """List Docker virtual networks."""
    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        return {
            "networks": [
                {"ID": "bridge1", "Name": "bridge", "Driver": "bridge", "Scope": "local"},
                {"ID": "host1", "Name": "host", "Driver": "host", "Scope": "local"},
                {"ID": "none1", "Name": "none", "Driver": "null", "Scope": "local"},
                {"ID": "nexo1", "Name": "nexopanel-net", "Driver": "bridge", "Scope": "local"},
            ]
        }

    res = await executor.run_command(["/usr/bin/docker", "network", "ls", "--format", "{{json .}}"])
    networks: list[dict[str, Any]] = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                networks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"networks": networks}


@router.post("/networks")
async def create_network(
    body: NetworkCreateRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a Docker virtual network."""
    if not NAME_RE.match(body.name):
        raise HTTPException(status_code=400, detail="Invalid network name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_network_create", target_resource=body.name
        )
        await db.commit()
        return {"ok": True, "network": body.name}

    cmd = ["/usr/bin/docker", "network", "create", "-d", body.driver, body.name]
    res = await executor.run_command(cmd)

    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_network_create", target_resource=body.name
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to create network {body.name}")

    return {"ok": res.ok, "network": res.stdout.strip()}


@router.delete("/networks/{name}")
async def remove_network(
    name: str,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove a Docker virtual network."""
    if not NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid network name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_network_rm", target_resource=name
        )
        await db.commit()
        return {"ok": True}

    res = await executor.run_command(["/usr/bin/docker", "network", "rm", name])
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_network_rm", target_resource=name
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or f"Failed to remove network {name}")

    return {"ok": res.ok, "stdout": res.stdout}


# System Prune
@router.post("/prune")
async def prune_system(
    body: PruneRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Prune unused Docker resources (stopped containers, dangling images, unused networks, and optional volumes)."""
    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_prune", target_resource="system"
        )
        await db.commit()
        return {"ok": True, "output": "Deleted Containers: 1\nTotal reclaimed space: 1.25GB (mock)"}

    cmd = ["/usr/bin/docker", "system", "prune", "-f"]
    if body.all:
        cmd.append("-a")
    if body.volumes:
        cmd.append("--volumes")

    res = await executor.run_command(cmd, timeout=180)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_prune", target_resource="system"
    )
    await db.commit()

    return {"ok": res.ok, "output": res.stdout + ("\n" + res.stderr if res.stderr else "")}


# 1-Click App Templates
@router.get("/templates")
async def list_templates(_: User = Depends(require_permission("docker:read"))) -> list[dict[str, Any]]:
    """Retrieve catalog of curated ready-to-run 1-click Docker application templates."""
    return TEMPLATES_CATALOG


@router.post("/templates/deploy")
async def deploy_template(
    body: TemplateDeployRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deploy a curated 1-click template container with customizable ports, environment variables, and persistent volumes."""
    tmpl = next((t for t in TEMPLATES_CATALOG if t["id"] == body.template_id), None)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    container_name = body.name.strip() or tmpl["default_name"]
    ports = body.ports or tmpl["default_ports"]
    env = {**tmpl["default_env"], **body.env}
    volumes = body.volumes or tmpl["default_volumes"]

    run_req = ContainerRunRequest(
        name=container_name,
        image=tmpl["image"],
        ports=ports,
        env=env,
        volumes=volumes,
        restart_policy="unless-stopped",
        command=tmpl.get("command", ""),
    )
    return await run_container(run_req, request=request, actor=actor, db=db)


# Docker Compose / Stack Deployer
@router.post("/compose/deploy")
async def deploy_compose_stack(
    body: ComposeDeployRequest,
    request: Request,
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deploy or update a multi-container Docker Compose stack from raw YAML configuration."""
    if not NAME_RE.match(body.project_name):
        raise HTTPException(status_code=400, detail="Invalid project name (use letters, numbers, dash, underscore)")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_compose_deploy", target_resource=body.project_name
        )
        await db.commit()
        return {"ok": True, "output": f"Creating network and starting stack for {body.project_name} (mock)", "project": body.project_name}

    stack_dir = Path(f"/var/www/compose/{body.project_name}")
    await executor.ensure_directory(str(stack_dir), owner="root", group="root", mode=0o755)

    compose_file = str(stack_dir / "docker-compose.yml")
    write_res = await executor.write_privileged_file(compose_file, body.compose_yaml, mode=0o644)
    if not write_res.ok:
        raise HTTPException(status_code=500, detail="Failed to write docker-compose.yml configuration")

    cmd = ["/usr/bin/docker", "compose", "-p", body.project_name, "-f", compose_file, "up", "-d"]
    res = await executor.run_command(cmd, timeout=300)

    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_compose_deploy", target_resource=body.project_name
    )
    await db.commit()

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.stderr or "Failed to deploy Docker Compose stack")

    return {"ok": res.ok, "output": res.stdout + ("\n" + res.stderr if res.stderr else ""), "project": body.project_name}


@router.post("/compose/down")
async def teardown_compose_stack(
    body: ComposeDeployRequest,
    request: Request,
    remove_volumes: bool = Query(default=False),
    actor: User = Depends(require_permission("docker:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tear down and stop a Docker Compose stack."""
    if not NAME_RE.match(body.project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    executor = get_node_executor()

    if getattr(executor, "use_mock", False):
        await record_audit_event(
            db, actor=actor, request=request, permission="docker:write", action="docker_compose_down", target_resource=body.project_name
        )
        await db.commit()
        return {"ok": True, "output": f"Stopping and removing stack {body.project_name} (mock)"}

    compose_file = f"/var/www/compose/{body.project_name}/docker-compose.yml"
    cmd = ["/usr/bin/docker", "compose", "-p", body.project_name, "-f", compose_file, "down"]
    if remove_volumes:
        cmd.append("--volumes")

    res = await executor.run_command(cmd, timeout=180)
    await record_audit_event(
        db, actor=actor, request=request, permission="docker:write", action="docker_compose_down", target_resource=body.project_name
    )
    await db.commit()

    return {"ok": res.ok, "output": res.stdout + ("\n" + res.stderr if res.stderr else "")}
