"""Domain & Website Hosting + Subdomain Management API router."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.validators import validate_domain
from app.db.models import Subdomain, User, Website
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.drivers.webserver import NginxProvider, VhostConfig
from app.services.executor import get_node_executor

router = APIRouter(prefix="/sites", tags=["Websites & Subdomains"])


class WebsiteCreate(BaseModel):
    domain: str
    aliases: list[str] = Field(default_factory=list)
    runtime_type: str = Field(default="static", pattern="^(static|php|proxy)$")
    php_version: str | None = Field(default="8.2")
    proxy_upstream: str | None = None
    custom_directives: str = ""
    node_id: str = settings.LOCAL_NODE_ID

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v)

    @field_validator("aliases")
    @classmethod
    def check_aliases(cls, v: list[str]) -> list[str]:
        return [validate_domain(a) for a in v]


class WebsiteUpdate(BaseModel):
    aliases: list[str] | None = None
    runtime_type: str | None = Field(default=None, pattern="^(static|php|proxy)$")
    php_version: str | None = None
    proxy_upstream: str | None = None
    custom_directives: str | None = None
    force_https: bool | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


class SubdomainCreate(BaseModel):
    website_id: int
    prefix: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$")
    runtime_type: str = Field(default="static", pattern="^(static|php|proxy)$")
    php_version: str | None = "8.2"
    proxy_upstream: str | None = None
    create_dns_record: bool = False


async def _apply_nginx_vhost_with_rollback(
    provider: NginxProvider,
    executor,
    cfg: VhostConfig,
    previous_content: str | None = None,
) -> None:
    conf_path = provider.vhost_config_path(cfg.domain)
    enabled_path = provider.vhost_enabled_path(cfg.domain)
    rendered = provider.render_vhost(cfg)

    await executor.write_privileged_file(conf_path, rendered, mode=0o644)
    await executor.create_symlink(conf_path, enabled_path)

    test_res = await executor.run_command(provider.test_config_command())
    if not test_res.ok:
        if previous_content is not None:
            await executor.write_privileged_file(conf_path, previous_content, mode=0o644)
        else:
            await executor.remove_file(enabled_path)
            await executor.remove_file(conf_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nginx config validation failed (rolled back): {test_res.stderr or test_res.stdout}",
        )

    await executor.run_command(provider.reload_command())


@router.get("")
async def list_websites(
    _: User = Depends(require_permission("websites:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    sites = (await db.execute(select(Website).order_by(Website.id.desc()))).scalars().all()
    return [
        {
            "id": s.id,
            "node_id": s.node_id,
            "domain": s.domain,
            "aliases": s.aliases,
            "document_root": s.document_root,
            "runtime_type": s.runtime_type,
            "php_version": s.php_version,
            "proxy_upstream": s.proxy_upstream,
            "custom_directives": s.custom_directives,
            "ssl_enabled": s.ssl_enabled,
            "force_https": s.force_https,
            "status": s.status,
            "app_type": s.app_type,
            "created_at": s.created_at.isoformat(),
        }
        for s in sites
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_website(
    body: WebsiteCreate,
    request: Request,
    actor: User = Depends(require_permission("websites:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(select(Website).where(Website.domain == body.domain))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Website {body.domain} already exists")

    doc_root = str(settings.WEB_ROOT_BASE / body.domain / "public")
    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor(body.node_id)

    await executor.ensure_directory(doc_root, owner=distro.paths.www_user, group=distro.paths.www_group)
    index_file = Path(doc_root) / "index.html"
    if not index_file.exists():
        await executor.write_privileged_file(
            str(index_file),
            f"<!doctype html><html><head><title>{body.domain}</title></head><body><h1>{body.domain} — Provisioned by NexoPanel</h1></body></html>\n",
        )

    await _apply_nginx_vhost_with_rollback(
        provider,
        executor,
        VhostConfig(
            domain=body.domain,
            aliases=body.aliases,
            document_root=doc_root,
            runtime_type=body.runtime_type,
            php_version=body.php_version,
            proxy_upstream=body.proxy_upstream,
            custom_directives=body.custom_directives,
        ),
    )

    site = Website(
        node_id=body.node_id,
        domain=body.domain,
        aliases=body.aliases,
        document_root=doc_root,
        runtime_type=body.runtime_type,
        php_version=body.php_version,
        proxy_upstream=body.proxy_upstream,
        custom_directives=body.custom_directives,
    )
    db.add(site)
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="websites:write",
        action="create_website",
        target_resource=f"website:{site.domain}",
        after_state={"domain": site.domain, "runtime": site.runtime_type},
    )
    await db.commit()
    return {"id": site.id, "domain": site.domain, "document_root": site.document_root, "status": site.status}


@router.put("/{site_id}")
async def update_website(
    site_id: int,
    body: WebsiteUpdate,
    request: Request,
    actor: User = Depends(require_permission("websites:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    site = (await db.execute(select(Website).where(Website.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Website not found")

    before = {"runtime_type": site.runtime_type, "custom_directives": site.custom_directives, "force_https": site.force_https}
    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor(site.node_id)

    prev_conf = None
    conf_file = Path(provider.vhost_config_path(site.domain))
    if conf_file.exists():
        prev_conf = conf_file.read_text(encoding="utf-8", errors="replace")

    if body.aliases is not None:
        site.aliases = body.aliases
    if body.runtime_type is not None:
        site.runtime_type = body.runtime_type
    if body.php_version is not None:
        site.php_version = body.php_version
    if body.proxy_upstream is not None:
        site.proxy_upstream = body.proxy_upstream
    if body.custom_directives is not None:
        site.custom_directives = body.custom_directives
    if body.force_https is not None:
        site.force_https = body.force_https
    if body.status is not None:
        site.status = body.status

    await _apply_nginx_vhost_with_rollback(
        provider,
        executor,
        VhostConfig(
            domain=site.domain,
            aliases=site.aliases,
            document_root=site.document_root,
            runtime_type=site.runtime_type,
            php_version=site.php_version,
            proxy_upstream=site.proxy_upstream,
            custom_directives=site.custom_directives,
            ssl_enabled=site.ssl_enabled,
            force_https=site.force_https,
        ),
        previous_content=prev_conf,
    )

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="websites:write",
        action="update_website",
        target_resource=f"website:{site.domain}",
        before_state=before,
        after_state={"runtime_type": site.runtime_type, "force_https": site.force_https},
    )
    await db.commit()
    return {"updated": True, "id": site.id}


@router.delete("/{site_id}")
async def delete_website(
    site_id: int,
    request: Request,
    actor: User = Depends(require_permission("websites:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    site = (await db.execute(select(Website).where(Website.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Website not found")

    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor(site.node_id)
    await executor.remove_file(provider.vhost_enabled_path(site.domain))
    await executor.remove_file(provider.vhost_config_path(site.domain))
    await executor.run_command(provider.reload_command())

    await db.delete(site)
    await record_audit_event(
        db, actor=actor, request=request, permission="websites:delete", action="delete_website", target_resource=f"website:{site.domain}"
    )
    await db.commit()
    return {"deleted": True}


# --- Subdomain Management ---

@router.get("/subdomains")
async def list_subdomains(
    _: User = Depends(require_permission("subdomains:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    subs = (await db.execute(select(Subdomain).order_by(Subdomain.id.desc()))).scalars().all()
    return [
        {
            "id": s.id,
            "website_id": s.website_id,
            "fqdn": s.fqdn,
            "document_root": s.document_root,
            "runtime_type": s.runtime_type,
            "php_version": s.php_version,
            "proxy_upstream": s.proxy_upstream,
            "dns_record_created": s.dns_record_created,
            "status": s.status,
        }
        for s in subs
    ]


@router.post("/subdomains", status_code=status.HTTP_201_CREATED)
async def create_subdomain(
    body: SubdomainCreate,
    request: Request,
    actor: User = Depends(require_permission("subdomains:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    parent = (await db.execute(select(Website).where(Website.id == body.website_id))).scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent website not found")

    fqdn = validate_domain(f"{body.prefix}.{parent.domain}")
    existing = (await db.execute(select(Subdomain).where(Subdomain.fqdn == fqdn))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Subdomain {fqdn} already exists")

    doc_root = str(settings.WEB_ROOT_BASE / fqdn / "public")
    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor(parent.node_id)

    await executor.ensure_directory(doc_root, owner=distro.paths.www_user, group=distro.paths.www_group)
    await _apply_nginx_vhost_with_rollback(
        provider,
        executor,
        VhostConfig(
            domain=fqdn,
            aliases=[],
            document_root=doc_root,
            runtime_type=body.runtime_type,
            php_version=body.php_version,
            proxy_upstream=body.proxy_upstream,
        ),
    )

    sub = Subdomain(
        node_id=parent.node_id,
        website_id=parent.id,
        fqdn=fqdn,
        document_root=doc_root,
        runtime_type=body.runtime_type,
        php_version=body.php_version,
        proxy_upstream=body.proxy_upstream,
        dns_record_created=body.create_dns_record,
    )
    db.add(sub)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="subdomains:write", action="create_subdomain", target_resource=f"subdomain:{fqdn}"
    )
    await db.commit()
    return {"id": sub.id, "fqdn": sub.fqdn, "document_root": sub.document_root}


@router.delete("/subdomains/{sub_id}")
async def delete_subdomain(
    sub_id: int,
    request: Request,
    actor: User = Depends(require_permission("subdomains:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sub = (await db.execute(select(Subdomain).where(Subdomain.id == sub_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subdomain not found")

    distro = get_distro_driver()
    provider = NginxProvider(distro)
    executor = get_node_executor(sub.node_id)
    await executor.remove_file(provider.vhost_enabled_path(sub.fqdn))
    await executor.remove_file(provider.vhost_config_path(sub.fqdn))
    await executor.run_command(provider.reload_command())

    await db.delete(sub)
    await record_audit_event(
        db, actor=actor, request=request, permission="subdomains:delete", action="delete_subdomain", target_resource=f"subdomain:{sub.fqdn}"
    )
    await db.commit()
    return {"deleted": True}
