"""DNS Zone & Record Management API router (Bind9/PowerDNS with named-checkzone validation)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import socket
from typing import Any

import dns.resolver
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.security import secret_manager
from app.core.validators import validate_domain
from app.db.models import (
    AuditLog,
    DnsProviderCredential,
    DnsRecord,
    DnsZone,
    PanelSetting,
    SslCertificate,
    User,
)
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.services.executor import get_node_executor

router = APIRouter(prefix="/dns", tags=["DNS Management"])
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


class DnsZoneCreate(BaseModel):
    domain: str
    primary_ns: str = "ns1.localhost.localdomain"
    secondary_ns: str | None = None
    admin_email: str = "hostmaster.localhost.localdomain"

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v)

    @field_validator("primary_ns")
    @classmethod
    def check_primary_ns(cls, v: str) -> str:
        return validate_domain(v)

    @field_validator("secondary_ns")
    @classmethod
    def check_secondary_ns(cls, v: str | None) -> str | None:
        return validate_domain(v) if v else None

    @field_validator("admin_email")
    @classmethod
    def check_admin_email(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if not clean:
            return "hostmaster.localhost.localdomain"
        if "@" in clean:
            clean = clean.replace("@", ".")
        return clean.rstrip(".")


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


class NameserverUpdate(BaseModel):
    public_ip: str
    ns1: str
    ns2: str

    @field_validator("public_ip")
    @classmethod
    def check_ip(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_address(v.strip()))
        except ValueError as exc:
            raise ValueError(f"Invalid IPv4/IPv6 address: {v!r}") from exc

    @field_validator("ns1", "ns2")
    @classmethod
    def check_ns(cls, v: str) -> str:
        return validate_domain(v)


# --- Nameserver discovery & persistence ---------------------------------

NS_SETTING_KEYS = ("dns_public_ip", "dns_ns1", "dns_ns2")


def _detect_server_ip() -> str:
    """Best-effort primary IP of this host (no packet is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.connect(("1.1.1.1", 80))
            return sock.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.getfqdn())
    except OSError:
        return "127.0.0.1"


def _default_nameservers(hostname: str) -> tuple[str, str]:
    host = (hostname or "").strip().rstrip(".")
    if "." in host and not host.endswith("localdomain") and not host.endswith("localhost"):
        return f"ns1.{host}", f"ns2.{host}"
    return "ns1.localhost.localdomain", "ns2.localhost.localdomain"


async def _get_setting(db: AsyncSession, key: str) -> str | None:
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = (await db.execute(select(PanelSetting).where(PanelSetting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(PanelSetting(key=key, value=value, is_secret=False))


def _normalize_ns(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _safe_resolve(qname: str, rtype: str, nameserver: str | None = None) -> dict[str, Any]:
    """Run a single DNS lookup and never raise (used for health diagnostics)."""
    try:
        resolver = dns.resolver.Resolver()
        if nameserver:
            resolver.nameservers = [nameserver]
        resolver.timeout = settings.DNS_CHECK_TIMEOUT_SECONDS
        resolver.lifetime = settings.DNS_CHECK_TIMEOUT_SECONDS
        answer = resolver.resolve(qname, rtype, raise_on_no_answer=False)
        values = [r.to_text() for r in answer] if answer.rrset is not None else []
        return {"ok": True, "values": values, "error": None}
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash the endpoint
        return {"ok": False, "values": [], "error": str(exc)}


async def _bind_service_status(executor) -> str:
    try:
        distro = get_distro_driver()
        res = await executor.run_command(distro.build_service_control_cmd("bind9", "is-active"))
    except Exception:  # noqa: BLE001 - diagnostics must not crash the endpoint
        return "unknown"
    raw = (res.stdout or "").strip()
    if raw in {"active", "inactive", "failed", "activating", "deactivating", "unknown"}:
        return raw
    return "active" if res.ok else "inactive"


async def _sync_named_conf_local(executor, db: AsyncSession) -> None:
    distro = get_distro_driver()
    zones = (await db.execute(select(DnsZone).order_by(DnsZone.domain))).scalars().all()
    lines = [
        "// Managed by NexoPanel DNS Engine",
        "// Do not edit this file manually",
        "",
    ]
    for z in zones:
        lines.append(f'zone "{z.domain}" {{')
        lines.append('    type master;')
        lines.append(f'    file "{distro.paths.bind_zones_dir}/db.{z.domain}";')
        lines.append('};')
        lines.append('')
    content = "\n".join(lines)
    await executor.write_privileged_file(distro.paths.bind_named_conf_local, content, mode=0o644)


async def _sync_bind_zone(zone: DnsZone, records: list[DnsRecord], db: AsyncSession | None = None) -> None:
    distro = get_distro_driver()
    executor = get_node_executor(zone.node_id)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
    tmpl = env.get_template("bind_zone.db.j2")
    rendered = tmpl.render(
        minimum_ttl=zone.minimum_ttl,
        primary_ns=zone.primary_ns.rstrip("."),
        admin_email=zone.admin_email.rstrip("."),
        serial=zone.serial,
        refresh=zone.refresh,
        retry=zone.retry,
        expire=zone.expire,
        records=records,
    )
    zone_file = f"{distro.paths.bind_zones_dir}/db.{zone.domain}"
    await executor.ensure_directory(distro.paths.bind_zones_dir, owner="bind", group="bind", mode=0o755)
    await executor.write_privileged_file(zone_file, rendered, mode=0o644)

    # Check syntax if named-checkzone is installed
    check = await executor.run_command([distro.paths.bind_checkzone_bin, zone.domain, zone_file])
    if not check.ok:
        # If check binary is missing or not installed (126/127), don't crash
        if check.returncode not in (126, 127) and "not found" not in (check.stderr or "").lower():
            raise HTTPException(status_code=422, detail=f"named-checkzone failed: {check.stderr or check.stdout}")

    if db is not None:
        await _sync_named_conf_local(executor, db)

    # Reload BIND9, or fallback to restart if inactive
    res = await executor.run_command(distro.build_service_control_cmd("bind9", "reload"))
    if not res.ok:
        await executor.run_command(distro.build_service_control_cmd("bind9", "restart"))


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
    p_ns = body.primary_ns.rstrip(".")
    s_ns = body.secondary_ns.rstrip(".") if body.secondary_ns else None
    zone = DnsZone(
        domain=body.domain,
        primary_ns=p_ns,
        admin_email=body.admin_email,
        serial=serial,
    )
    db.add(zone)
    await db.flush()
    default_ns = DnsRecord(zone_id=zone.id, name="@", record_type="NS", value=f"{p_ns}.", ttl=3600)
    db.add(default_ns)
    if s_ns and s_ns != p_ns:
        db.add(DnsRecord(zone_id=zone.id, name="@", record_type="NS", value=f"{s_ns}.", ttl=3600))
    await db.flush()

    zone_records = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    await _sync_bind_zone(zone, list(zone_records), db=db)
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
    await db.flush()
    await _sync_named_conf_local(executor, db)
    res = await executor.run_command(distro.build_service_control_cmd("bind9", "reload"))
    if not res.ok:
        await executor.run_command(distro.build_service_control_cmd("bind9", "restart"))
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
            "created_at": l.timestamp.isoformat(),
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


# --- Nameserver setup & live DNS diagnostics ----------------------------


@router.get("/nameservers")
async def get_nameservers(
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the nameservers this panel advertises plus authoritative-engine status.

    The values are persisted in ``panel_settings`` so the operator can publish
    the exact hostnames registered as glue records at their domain registrar.
    """
    hostname = socket.getfqdn() or socket.gethostname()
    default_ns1, default_ns2 = _default_nameservers(hostname)

    stored_ip = await _get_setting(db, "dns_public_ip")
    stored_ns1 = await _get_setting(db, "dns_ns1")
    stored_ns2 = await _get_setting(db, "dns_ns2")

    # When the host has no FQDN, suggest nameservers under the first managed
    # domain (e.g. ns1.example.com) instead of a useless localhost placeholder.
    first_zone = (await db.execute(select(DnsZone.domain).order_by(DnsZone.id).limit(1))).scalar_one_or_none()
    if first_zone and default_ns1.endswith("localhost.localdomain"):
        default_ns1, default_ns2 = f"ns1.{first_zone}", f"ns2.{first_zone}"

    executor = get_node_executor()
    bind_status = await _bind_service_status(executor)

    zone_count = (await db.execute(select(func.count(DnsZone.id)))).scalar_one()
    record_count = (await db.execute(select(func.count(DnsRecord.id)))).scalar_one()

    return {
        "hostname": hostname,
        "server_ip": stored_ip or _detect_server_ip(),
        "ns1": stored_ns1 or default_ns1,
        "ns2": stored_ns2 or default_ns2,
        "customized": any([stored_ip, stored_ns1, stored_ns2]),
        "bind_status": bind_status,
        "bind_healthy": bind_status in {"active", "activating"},
        "zone_count": zone_count,
        "record_count": record_count,
        "live_check_enabled": settings.DNS_LIVE_CHECK_ENABLED,
    }


@router.put("/nameservers")
async def update_nameservers(
    body: NameserverUpdate,
    request: Request,
    actor: User = Depends(require_permission("dns:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _set_setting(db, "dns_public_ip", body.public_ip)
    await _set_setting(db, "dns_ns1", body.ns1)
    await _set_setting(db, "dns_ns2", body.ns2)
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="dns:write",
        action="update_nameservers",
        target_resource="dns:nameservers",
        after_state={"public_ip": body.public_ip, "ns1": body.ns1, "ns2": body.ns2},
    )
    await db.commit()
    return {"ok": True, "public_ip": body.public_ip, "ns1": body.ns1, "ns2": body.ns2}


def _check(check_id: str, label: str, status: str, detail: str, fix: str | None = None) -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


@router.post("/zones/{zone_id}/check")
async def check_zone(
    zone_id: int,
    _: User = Depends(require_permission("dns:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run end-to-end DNS diagnostics for a zone and return actionable fixes."""
    zone = (await db.execute(select(DnsZone).where(DnsZone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="DNS zone not found")

    records = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    executor = get_node_executor(zone.node_id)
    distro = get_distro_driver()
    checks: list[dict] = []

    # 1. Zone file syntax (named-checkzone)
    zone_file = f"{distro.paths.bind_zones_dir}/db.{zone.domain}"
    try:
        check_res = await executor.run_command([distro.paths.bind_checkzone_bin, zone.domain, zone_file])
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash the endpoint
        check_res = None
        check_error = str(exc)
    else:
        check_error = None
    if check_res is not None and check_res.ok:
        checks.append(_check("zone_file", "Zone file syntax", "pass", f"{zone_file} passes named-checkzone validation."))
    else:
        detail = check_error or (
            (check_res.stderr or check_res.stdout).strip() if check_res else "named-checkzone is unavailable"
        )
        checks.append(
            _check(
                "zone_file",
                "Zone file syntax",
                "fail",
                detail or "named-checkzone rejected the zone file",
                "Correct the record values shown above, then click 'Pull Data' to regenerate the zone file and reload BIND9.",
            )
        )

    # 2. Authoritative engine status
    bind_status = await _bind_service_status(executor)
    if bind_status in {"active", "activating"}:
        checks.append(_check("bind_service", "BIND9 authoritative service", "pass", f"named service is {bind_status}."))
    else:
        checks.append(
            _check(
                "bind_service",
                "BIND9 authoritative service",
                "fail",
                f"named service is {bind_status}.",
                "Start BIND9 (systemctl start named) and confirm it is enabled (systemctl enable named), then re-run the test.",
            )
        )

    # 3. Nameserver records in the zone
    ns_values = [_normalize_ns(r.value) for r in records if r.record_type == "NS"]
    if len(ns_values) >= 2:
        checks.append(_check("ns_records", "NS records", "pass", f"Zone publishes {len(ns_values)} nameserver(s): {', '.join(ns_values)}."))
    elif len(ns_values) == 1:
        checks.append(
            _check(
                "ns_records",
                "NS records",
                "warn",
                f"Only one NS record is configured ({ns_values[0]}).",
                "Add a second NS record (for example ns2) for redundancy; registrars require at least two nameservers.",
            )
        )
    else:
        checks.append(
            _check(
                "ns_records",
                "NS records",
                "fail",
                "The zone has no NS records.",
                "Add an NS record with host '@' pointing to your nameserver hostname (for example ns1.example.com).",
            )
        )

    # 4. Apex address record
    apex = [r for r in records if r.name in {"@", ""} and r.record_type in {"A", "AAAA"}]
    if apex:
        checks.append(_check("apex", "Apex address record", "pass", f"Apex resolves to {', '.join(r.value for r in apex)}."))
    else:
        checks.append(
            _check(
                "apex",
                "Apex address record",
                "warn",
                "No A/AAAA record exists at the zone apex (@).",
                "Add an A record with host '@' pointing to your server IP so the bare domain resolves.",
            )
        )

    # 5. SOA / serial sanity
    if zone.serial > 0:
        checks.append(_check("soa", "SOA serial", "pass", f"Zone serial is {zone.serial}."))
    else:
        checks.append(
            _check("soa", "SOA serial", "fail", "Zone serial is not initialised.", "Click 'Pull Data' to regenerate the SOA record.")
        )

    # 6-8. Live resolution checks (authoritative + public delegation)
    if settings.DNS_LIVE_CHECK_ENABLED:
        local_ns = await asyncio.to_thread(_safe_resolve, zone.domain, "NS", "127.0.0.1")
        if not local_ns["ok"]:
            checks.append(
                _check(
                    "local_resolution",
                    "Local authoritative resolution",
                    "warn",
                    f"Could not query BIND9 on 127.0.0.1:53 ({local_ns['error']}).",
                    "Confirm BIND9 listens on port 53 and that the zone is included from named.conf.local, then reload named.",
                )
            )
        elif not local_ns["values"]:
            checks.append(
                _check(
                    "local_resolution",
                    "Local authoritative resolution",
                    "warn",
                    "BIND9 answered but returned no NS records for the zone.",
                    "Check that the zone file contains NS records and that the zone is loaded (named-checkzone + reload).",
                )
            )
        else:
            checks.append(
                _check("local_resolution", "Local authoritative resolution", "pass", f"BIND9 answered NS: {', '.join(local_ns['values'])}.")
            )

        public_ns = await asyncio.to_thread(_safe_resolve, zone.domain, "NS")
        if not public_ns["ok"]:
            checks.append(
                _check(
                    "public_delegation",
                    "Public delegation",
                    "warn",
                    f"Public NS lookup failed ({public_ns['error']}).",
                    "Set the domain's nameservers at your registrar to the NS1/NS2 hostnames shown in the Nameserver tab, then wait for propagation.",
                )
            )
        elif not public_ns["values"]:
            checks.append(
                _check(
                    "public_delegation",
                    "Public delegation",
                    "warn",
                    "No public NS records were returned for the domain.",
                    "Register the domain's nameservers (NS1/NS2) at your registrar and create matching glue/A records.",
                )
            )
        else:
            observed = {_normalize_ns(v) for v in public_ns["values"]}
            expected = set(ns_values)
            if expected and observed == expected:
                checks.append(
                    _check("public_delegation", "Public delegation", "pass", f"Registrar delegation matches: {', '.join(sorted(observed))}.")
                )
            else:
                checks.append(
                    _check(
                        "public_delegation",
                        "Public delegation",
                        "warn",
                        f"Public NS is {', '.join(sorted(observed))} but the zone publishes {', '.join(sorted(expected)) or 'none'}.",
                        "Update the nameservers at your registrar to match the zone NS records, or add the delegated nameservers as NS records.",
                    )
                )

        apex_a = next((r for r in apex if r.record_type == "A"), None)
        if apex_a:
            public_a = await asyncio.to_thread(_safe_resolve, zone.domain, "A")
            if public_a["ok"] and public_a["values"]:
                if apex_a.value in public_a["values"]:
                    checks.append(_check("propagation", "Public propagation", "pass", f"{zone.domain} resolves to {apex_a.value}."))
                else:
                    checks.append(
                        _check(
                            "propagation",
                            "Public propagation",
                            "warn",
                            f"{zone.domain} resolves to {', '.join(public_a['values'])} but the zone expects {apex_a.value}.",
                            "Allow up to the record TTL for propagation, or correct the A record and pull the zone again.",
                        )
                    )
            else:
                checks.append(
                    _check(
                        "propagation",
                        "Public propagation",
                        "warn",
                        f"{zone.domain} did not resolve publicly ({public_a['error'] or 'no answer'}).",
                        "Ensure the domain is delegated to this server and the apex A record points to the server's public IP.",
                    )
                )
    else:
        checks.append(_check("live_checks", "Live resolution checks", "info", "Live lookups are disabled in this environment."))

    summary = {
        "pass": sum(1 for c in checks if c["status"] == "pass"),
        "warn": sum(1 for c in checks if c["status"] == "warn"),
        "fail": sum(1 for c in checks if c["status"] == "fail"),
    }
    overall = "fail" if summary["fail"] else ("warn" if summary["warn"] else "pass")

    return {
        "zone": zone.domain,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "summary": summary,
        "checks": checks,
    }
