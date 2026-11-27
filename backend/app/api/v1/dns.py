"""DNS Zone & Record Management API router (Bind9/PowerDNS with named-checkzone validation)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.validators import validate_domain
from app.db.models import DnsRecord, DnsZone, User
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
    return [
        {
            "id": z.id,
            "domain": z.domain,
            "primary_ns": z.primary_ns,
            "admin_email": z.admin_email,
            "serial": z.serial,
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
