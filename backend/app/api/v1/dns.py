"""DNS Zone & Record Management API router (Bind9/PowerDNS with named-checkzone validation)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.security import secret_manager
from app.core.validators import validate_domain
from app.db.models import AuditLog, DnsProviderCredential, DnsRecord, DnsZone, SslCertificate, User
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.services.executor import get_node_executor

router = APIRouter(prefix="/dns", tags=["DNS Management"])
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


class DnsZoneCreate(BaseModel):
    domain: str
    primary_ns: str = "ns1.localhost.localdomain"
    admin_email: str = "hostmaster.localhost.localdomain"

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v)


class DnsRecordCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    record_type: str = Field(pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV|CAA)$")
    value: str = Field(min_length=1, max_length=1024)
    ttl: int = Field(default=300, ge=60, le=86400)
    priority: int | None = Field(default=None, ge=0, le=65535)


class DnsRecordUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    record_type: str | None = Field(default=None, pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV|CAA)$")
    value: str | None = Field(default=None, min_length=1, max_length=1024)
    ttl: int | None = Field(default=None, ge=60, le=86400)
    priority: int | None = Field(default=None, ge=0, le=65535)


class DnsProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    provider_type: str = Field(pattern="^(cloudflare|namecheap|digitalocean|route53|dnspod|aliyun)$")
    api_token: str = Field(min_length=6)


async def _sync_bind_zone(zone: DnsZone, records: list[DnsRecord]) -> None:
    distro = get_distro_driver()
    executor = get_node_executor(zone.node_id)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
    tmpl = env.get_template("bind_zone.db.j2")
    rendered = tmpl.render(
        minimum_ttl=zone.minimum_ttl,
        primary_ns=zone.primary_ns,
        admin_email=zone.admin_email,
        serial=zone.serial,
        refresh=zone.refresh,
        retry=zone.retry,
        expire=zone.expire,
        records=records,
    )
    zone_file = f"{distro.paths.bind_zones_dir}/db.{zone.domain}"
    await executor.ensure_directory(distro.paths.bind_zones_dir, owner="bind", group="bind", mode=0o755)
    await executor.write_privileged_file(zone_file, rendered, mode=0o644)
    check = await executor.run_command([distro.paths.bind_checkzone_bin, zone.domain, zone_file])
    if not check.ok:
        raise HTTPException(status_code=422, detail=f"named-checkzone failed: {check.stderr or check.stdout}")
    await executor.run_command(distro.build_service_control_cmd("bind9", "reload"))


def _next_serial(current: int) -> int:
    today_prefix = int(datetime.now(timezone.utc).strftime("%Y%m%d00"))
    if current >= today_prefix:
        return current + 1
    return today_prefix + 1


@router.get("/zones")
async def list_zones(
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    zones = (await db.execute(select(DnsZone).order_by(DnsZone.domain))).scalars().all()
    counts_rows = (
        await db.execute(select(DnsRecord.zone_id, func.count(DnsRecord.id)).group_by(DnsRecord.zone_id))
    ).all()
    count_map = {row[0]: row[1] for row in counts_rows}
    certs = (await db.execute(select(SslCertificate))).scalars().all()
    cert_map = {c.domain: c for c in certs}
    return [
        {
            "id": z.id,
            "domain": z.domain,
            "primary_ns": z.primary_ns,
            "admin_email": z.admin_email,
            "serial": z.serial,
            "record_count": count_map.get(z.id, 0),
            "ssl_status": cert_map[z.domain].status if z.domain in cert_map else None,
            "ssl_expires_at": (
                cert_map[z.domain].expires_at.isoformat()
                if z.domain in cert_map and cert_map[z.domain].expires_at
                else None
            ),
            "created_at": z.created_at.isoformat(),
        }
        for z in zones
    ]


@router.post("/zones", status_code=status.HTTP_201_CREATED)
async def create_zone(
    body: DnsZoneCreate,
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(select(DnsZone).where(DnsZone.domain == body.domain))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="DNS zone already exists")

    serial = _next_serial(0)
    zone = DnsZone(
        domain=body.domain,
        primary_ns=body.primary_ns,
        admin_email=body.admin_email.replace("@", "."),
        serial=serial,
    )
    db.add(zone)
    await db.flush()
    default_ns = DnsRecord(zone_id=zone.id, name="@", record_type="NS", value=f"{body.primary_ns}.", ttl=3600)
    db.add(default_ns)
    await db.flush()

    await _sync_bind_zone(zone, [default_ns])
    await record_audit_event(
        db, actor=actor, request=request, permission="dns:write", action="create_dns_zone", target_resource=f"dns:{zone.domain}"
    )
    await db.commit()
    return {"id": zone.id, "domain": zone.domain, "serial": zone.serial}


@router.get("/zones/{zone_id}/records")
async def list_records(
    zone_id: int,
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone_id))).scalars().all()
    return [
        {
            "id": r.id,
            "zone_id": r.zone_id,
            "name": r.name,
            "record_type": r.record_type,
            "value": r.value,
            "ttl": r.ttl,
            "priority": r.priority,
        }
        for r in recs
    ]


@router.post("/zones/{zone_id}/records", status_code=status.HTTP_201_CREATED)
async def add_record(
    zone_id: int,
    body: DnsRecordCreate,
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    zone = (await db.execute(select(DnsZone).where(DnsZone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="DNS zone not found")

    rec = DnsRecord(
        zone_id=zone.id,
        name=body.name,
        record_type=body.record_type,
        value=body.value,
        ttl=body.ttl,
        priority=body.priority,
    )
    db.add(rec)
    zone.serial = _next_serial(zone.serial)
    await db.flush()

    recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    await _sync_bind_zone(zone, list(recs))
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="dns:write",
        action="add_dns_record",
        target_resource=f"dns:{zone.domain}",
        after_state={"type": rec.record_type, "name": rec.name, "value": rec.value},
    )
    await db.commit()
    return {"id": rec.id, "serial": zone.serial}


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: int,
    request: Request,
    actor: User = Depends(require_permission("dns:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(DnsRecord).where(DnsRecord.id == record_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="DNS record not found")
    zone = (await db.execute(select(DnsZone).where(DnsZone.id == rec.zone_id))).scalar_one()
    await db.delete(rec)
    zone.serial = _next_serial(zone.serial)
    await db.flush()
    recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    await _sync_bind_zone(zone, list(recs))
    await record_audit_event(
        db, actor=actor, request=request, permission="dns:delete", action="delete_dns_record", target_resource=f"dns:{zone.domain}"
    )
    await db.commit()
    return {"deleted": True, "serial": zone.serial}


@router.delete("/zones/{zone_id}")
async def delete_zone(
    zone_id: int,
    request: Request,
    actor: User = Depends(require_permission("dns:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    zone = (await db.execute(select(DnsZone).where(DnsZone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="DNS zone not found")
    distro = get_distro_driver()
    executor = get_node_executor(zone.node_id)
    await executor.remove_file(f"{distro.paths.bind_zones_dir}/db.{zone.domain}")
    await db.delete(zone)
    await record_audit_event(
        db, actor=actor, request=request, permission="dns:delete", action="delete_dns_zone", target_resource=f"dns:{zone.domain}"
    )
    await db.commit()
    return {"deleted": True}


@router.put("/records/{record_id}")
async def update_record(
    record_id: int,
    body: DnsRecordUpdate,
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = (await db.execute(select(DnsRecord).where(DnsRecord.id == record_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="DNS record not found")
    zone = (await db.execute(select(DnsZone).where(DnsZone.id == rec.zone_id))).scalar_one()

    if body.name is not None:
        rec.name = body.name
    if body.record_type is not None:
        rec.record_type = body.record_type
    if body.value is not None:
        rec.value = body.value
    if body.ttl is not None:
        rec.ttl = body.ttl
    if body.priority is not None:
        rec.priority = body.priority

    zone.serial = _next_serial(zone.serial)
    await db.flush()

    recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    await _sync_bind_zone(zone, list(recs))
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="dns:write",
        action="update_dns_record",
        target_resource=f"dns:{zone.domain}",
        after_state={"type": rec.record_type, "name": rec.name, "value": rec.value, "ttl": rec.ttl},
    )
    await db.commit()
    return {
        "id": rec.id,
        "zone_id": rec.zone_id,
        "name": rec.name,
        "record_type": rec.record_type,
        "value": rec.value,
        "ttl": rec.ttl,
        "priority": rec.priority,
        "serial": zone.serial,
    }


@router.post("/zones/pull")
async def pull_dns_data(
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    zones = (await db.execute(select(DnsZone))).scalars().all()
    synced = 0
    for zone in zones:
        recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
        await _sync_bind_zone(zone, list(recs))
        synced += 1
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="dns:write",
        action="pull_dns_data",
        target_resource="dns:all",
        after_state={"synced_zones": synced},
    )
    await db.commit()
    return {"ok": True, "synced": synced, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/logs")
async def get_dns_logs(
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    logs = (
        await db.execute(
            select(AuditLog)
            .where(or_(AuditLog.target_resource.like("dns:%"), AuditLog.action.like("%dns%")))
            .order_by(AuditLog.id.desc())
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": l.id,
            "actor": l.actor_username,
            "action": l.action,
            "target": l.target_resource,
            "status": l.status,
            "detail": l.after_state or {},
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]


@router.get("/providers")
async def list_providers(
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    creds = (await db.execute(select(DnsProviderCredential).order_by(DnsProviderCredential.id))).scalars().all()
    providers: list[dict] = [
        {
            "id": 0,
            "name": "Local BIND9 (Authoritative)",
            "provider_type": "bind9",
            "api_token": "builtin-systemd",
            "is_builtin": True,
            "status": "active",
            "created_at": None,
        }
    ]
    for c in creds:
        providers.append(
            {
                "id": c.id,
                "name": c.name,
                "provider_type": c.provider_type,
                "api_token": secret_manager.mask(c.credentials_encrypted),
                "is_builtin": False,
                "status": "active",
                "created_at": c.created_at.isoformat(),
            }
        )
    return providers


@router.post("/providers", status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: DnsProviderCreate,
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(select(DnsProviderCredential).where(DnsProviderCredential.name == body.name))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Provider name already exists")
    encrypted = secret_manager.encrypt(json.dumps({"api_token": body.api_token}))
    cred = DnsProviderCredential(name=body.name, provider_type=body.provider_type, credentials_encrypted=encrypted)
    db.add(cred)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="dns:write", action="create_dns_provider", target_resource=f"dns:{cred.name}"
    )
    await db.commit()
    return {"id": cred.id, "name": cred.name, "provider_type": cred.provider_type}


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int,
    request: Request,
    actor: User = Depends(require_permission("dns:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cred = (await db.execute(select(DnsProviderCredential).where(DnsProviderCredential.id == provider_id))).scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(cred)
    await record_audit_event(
        db, actor=actor, request=request, permission="dns:delete", action="delete_dns_provider", target_resource=f"dns:{cred.name}"
    )
    await db.commit()
    return {"deleted": True}
