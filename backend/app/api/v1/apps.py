"""One-Click Web Applications deployment router (WordPress, Laravel, Static/SPA, Node.js, Python)."""
from __future__ import annotations

import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.validators import validate_domain
from app.db.models import InstalledApp, ManagedDatabase, User, Website
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.drivers.webserver import NginxProvider, VhostConfig
from app.services.databases import provision_database, record_database_password
from app.services.executor import get_node_executor

router = APIRouter(prefix="/apps", tags=["One-Click Apps"])

APP_CATALOG = [
    {
        "slug": "wordpress",
        "name": "WordPress",
        "category": "CMS",
        "runtime": "php",
        "description": "Latest WordPress with automated MariaDB database, wp-config.php injection, and Nginx PHP-FPM vhost.",
        "requires_db": True,
    },
    {
        "slug": "laravel",
        "name": "Laravel",
        "category": "PHP Framework",
        "runtime": "php",
        "description": "Production Laravel skeleton with public/ root, .env generation, and MariaDB/PostgreSQL binding.",
        "requires_db": True,
    },
    {
        "slug": "static",
        "name": "Static / SPA",
        "category": "Frontend",
        "runtime": "static",
        "description": "High-performance static & Single-Page Application hosting with history fallback.",
        "requires_db": False,
    },
    {
        "slug": "nodejs",
        "name": "Node.js App",
        "category": "Backend",
        "runtime": "proxy",
        "description": "Reverse-proxied Node.js runtime (Express/Fastify/NestJS) with systemd unit & WebSocket upgrade headers.",
        "requires_db": False,
    },
    {
        "slug": "python",
        "name": "Python ASGI/WSGI",
        "category": "Backend",
        "runtime": "proxy",
        "description": "Reverse-proxied FastAPI/Django application with isolated venv and Uvicorn upstream.",
        "requires_db": False,
    },
]


class AppDeployRequest(BaseModel):
    app_slug: str = Field(pattern="^(wordpress|laravel|static|nodejs|python)$")
    domain: str
    proxy_port: int = Field(default=3000, ge=1024, le=65535)
    php_version: str = "8.2"
    db_engine: str = Field(default="mariadb", pattern="^(mariadb|postgresql)$")

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v)


@router.get("/catalog")
async def get_catalog(_: User = Depends(require_permission("apps:read"))) -> list[dict]:
    return APP_CATALOG


@router.get("/installed")
async def list_installed_apps(
    _: User = Depends(require_permission("apps:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    apps = (await db.execute(select(InstalledApp).order_by(InstalledApp.id.desc()))).scalars().all()
    return [
        {
            "id": a.id,
            "app_slug": a.app_slug,
            "domain": a.domain,
            "install_path": a.install_path,
            "db_name": a.db_name,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in apps
    ]


@router.post("/deploy", status_code=status.HTTP_201_CREATED)
async def deploy_app(
    body: AppDeployRequest,
    request: Request,
    actor: User = Depends(require_permission("apps:deploy")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(select(Website).where(Website.domain == body.domain))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Domain {body.domain} is already provisioned")

    catalog_item = next(c for c in APP_CATALOG if c["slug"] == body.app_slug)
    install_path = str(settings.WEB_ROOT_BASE / body.domain)
    doc_root = f"{install_path}/public" if body.app_slug in {"laravel", "static"} else install_path

    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor()
    await executor.ensure_directory(doc_root, owner=distro.paths.www_user, group=distro.paths.www_group)

    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    if catalog_item["requires_db"]:
        safe_prefix = body.domain.replace(".", "_").replace("-", "_")[:24]
        db_name = f"np_{safe_prefix}"
        db_user = f"u_{safe_prefix[:16]}"
        db_password = secrets.token_urlsafe(16)
        provision = await provision_database(
            executor,
            engine=body.db_engine,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
        )
        if not provision.ok:
            raise HTTPException(
                status_code=500,
                detail=f"Database provisioning failed: {provision.stderr or provision.stdout}",
            )
        db.add(ManagedDatabase(engine=body.db_engine, db_name=db_name, db_user=db_user))
        await record_database_password(
            db, engine=body.db_engine, db_name=db_name, password=db_password, note=body.domain
        )
        env_content = (
            f"APP_URL=https://{body.domain}\n"
            f"DB_CONNECTION={body.db_engine}\n"
            f"DB_DATABASE={db_name}\n"
            f"DB_USERNAME={db_user}\n"
            f"DB_PASSWORD={db_password}\n"
        )
        await executor.write_privileged_file(f"{install_path}/.env", env_content, mode=0o640)

    proxy_upstream = f"http://127.0.0.1:{body.proxy_port}" if catalog_item["runtime"] == "proxy" else None
    vhost_cfg = VhostConfig(
        domain=body.domain,
        aliases=[],
        document_root=doc_root,
        runtime_type=catalog_item["runtime"],
        php_version=body.php_version,
        proxy_upstream=proxy_upstream,
    )
    conf_path = provider.vhost_config_path(body.domain)
    await executor.write_privileged_file(conf_path, provider.render_vhost(vhost_cfg), mode=0o644)
    await executor.create_symlink(conf_path, provider.vhost_enabled_path(body.domain))
    await executor.run_command(provider.test_config_command())
    await executor.run_command(provider.reload_command())

    site = Website(
        domain=body.domain,
        aliases=[],
        document_root=doc_root,
        runtime_type=catalog_item["runtime"],
        php_version=body.php_version,
        proxy_upstream=proxy_upstream,
        app_type=body.app_slug,
    )
    db.add(site)

    installed = InstalledApp(
        app_slug=body.app_slug,
        domain=body.domain,
        install_path=install_path,
        db_name=db_name,
        metadata_json={"runtime": catalog_item["runtime"], "proxy_upstream": proxy_upstream},
    )
    db.add(installed)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="apps:deploy",
        action="deploy_app",
        target_resource=f"app:{body.app_slug}:{body.domain}",
        after_state={"domain": body.domain, "db_name": db_name},
    )
    await db.commit()
    return {
        "id": installed.id,
        "app_slug": body.app_slug,
        "domain": body.domain,
        "install_path": install_path,
        "db_name": db_name,
        "db_user": db_user,
    }
