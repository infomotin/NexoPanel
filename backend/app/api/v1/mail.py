"""Mail Server Administration, DNS Readiness Inspector, Postfix Queue & OutboundMailRouter."""
from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any

import dns.resolver
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.rbac import require_permission
from app.core.security import hash_dovecot_sha512_crypt, secret_manager
from app.core.validators import QUEUE_ID_RE, validate_domain
from app.db.models import DnsRecord, DnsZone, MailAlias, Mailbox, MailDomain, User
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.drivers.mail import OutboundMailRouter, OutboundRouteConfig, generate_dkim_keypair
from app.services.executor import get_node_executor

SERVICE_STATES = {"active", "inactive", "failed", "activating", "deactivating", "unknown"}

router = APIRouter(prefix="/mail", tags=["Mail Server & Routing"])


class MailDomainCreate(BaseModel):
    domain: str
    dkim_selector: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]{1,63}$")

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v)


class MailboxCreate(BaseModel):
    mail_domain_id: int
    local_part: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._+-]+$")
    password: str = Field(min_length=8, max_length=128)
    quota_mb: int = Field(default=1024, ge=50, le=102400)


class MailboxUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    quota_mb: int | None = Field(default=None, ge=50, le=102400)
    is_active: bool | None = None


class AliasCreate(BaseModel):
    mail_domain_id: int
    source_email: EmailStr
    destination_email: EmailStr


class MailServerConfigUpdate(BaseModel):
    max_message_size_mb: int | None = Field(default=None, ge=5, le=200)
    webmail_url: str | None = Field(default=None, max_length=255)
    tls_security_level: str | None = Field(default=None, pattern=r"^(may|encrypt|mandatory)$")


class TestEmailRequest(BaseModel):
    sender: EmailStr
    recipient: EmailStr
    subject: str = Field(default="NexoPanel Mail Delivery Test", max_length=200)
    body: str = Field(
        default="This is a test email sent from NexoPanel to verify SMTP configuration and delivery.",
        max_length=5000,
    )


class OutboundRouteUpdate(BaseModel):
    outbound_mode: str = Field(pattern="^(direct|relay)$")
    relay_host: str | None = None
    relay_port: int = Field(default=587, ge=1, le=65535)
    relay_username: str | None = None
    relay_password: str | None = None

    @field_validator("relay_host")
    @classmethod
    def check_relay_host(cls, v: str | None) -> str | None:
        # The relay host is rendered into Postfix map files: a newline would
        # let the caller append arbitrary map entries (relay/redirect for
        # domains they do not own).
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if any(ch in cleaned for ch in ("\x00", "\r", "\n", " ", "\t", "[", "]", ",")):
            raise ValueError(f"Invalid relay host: {v!r}")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,255}", cleaned):
            raise ValueError(f"Invalid relay host: {v!r}")
        return cleaned

    @field_validator("relay_username", "relay_password")
    @classmethod
    def check_relay_credentials(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if any(ch in v for ch in ("\x00", "\r", "\n")):
            raise ValueError("Relay credentials must not contain newlines")
        return v


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


def _mail_hostname() -> str:
    host = (socket.getfqdn() or "").strip().rstrip(".")
    if "." in host and not host.endswith("localdomain") and not host.endswith("localhost"):
        return host
    return ""


def _maildir_base(domain: str, local_part: str) -> Path:
    return settings.MAIL_DIR_BASE / domain / local_part


def _get_mailbox_usage_mb(domain: str, local_part: str) -> float:
    try:
        path = _maildir_base(domain, local_part)
        if not path.exists():
            return 0.0
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total / (1024 * 1024), 2)
    except Exception:
        return 0.0


async def _ensure_maildir(domain: str, local_part: str) -> None:
    """Create the Dovecot Maildir skeleton for a mailbox (idempotent)."""
    distro = get_distro_driver()
    executor = get_node_executor()
    base = _maildir_base(domain, local_part)
    for path in (base, base / "Maildir", base / "Maildir" / "cur", base / "Maildir" / "new", base / "Maildir" / "tmp"):
        await executor.ensure_directory(
            str(path), owner=distro.paths.mail_user, group=distro.paths.mail_group, mode=0o700
        )


def _render_lines(lines: list[str]) -> str:
    return "\n".join(sorted(lines)) + "\n" if lines else ""


async def _sync_mail_maps(db: AsyncSession) -> None:
    distro = get_distro_driver()
    executor = get_node_executor()
    domains = (await db.execute(select(MailDomain))).scalars().all()
    mailboxes = (await db.execute(select(Mailbox))).scalars().all()
    aliases = (await db.execute(select(MailAlias))).scalars().all()

    domain_lines = _render_lines([f"{d.domain} OK" for d in domains])
    await executor.write_privileged_file(distro.paths.postfix_virtual_mailbox_domains, domain_lines)

    mbox_lines = _render_lines(
        [f"{m.email} {m.email.split('@')[1]}/{m.email.split('@')[0]}/" for m in mailboxes]
    )
    await executor.write_privileged_file(distro.paths.postfix_virtual_mailbox_maps, mbox_lines)

    alias_lines = [f"{a.source_email} {a.destination_email}" for a in aliases]
    for d in domains:
        if d.catchall_address:
            alias_lines.append(f"@{d.domain} {d.catchall_address}")
    await executor.write_privileged_file(distro.paths.postfix_virtual_alias_maps, _render_lines(alias_lines))

    dovecot_lines = _render_lines(
        [
            f"{m.email}:{m.password_crypt}:5000:5000::{_maildir_base(m.email.split('@')[1], m.email.split('@')[0])}::userdb_quota_rule=*:storage={m.quota_mb}M"
            for m in mailboxes
            if m.is_active
        ]
    )
    await executor.write_privileged_file(distro.paths.dovecot_passwd_file, dovecot_lines, mode=0o640)

    routes: list[OutboundRouteConfig] = []
    for d in domains:
        pw = secret_manager.decrypt(d.relay_password_encrypted) if d.relay_password_encrypted else None
        routes.append(
            OutboundRouteConfig(
                domain=d.domain,
                mode=d.outbound_mode,  # type: ignore[arg-type]
                relay_host=d.relay_host,
                relay_port=d.relay_port or 587,
                relay_username=d.relay_username,
                relay_password=pw,
            )
        )
    await executor.write_privileged_file(
        distro.paths.postfix_sender_relay_maps, OutboundMailRouter.render_sender_relay_maps(routes)
    )
    await executor.write_privileged_file(
        distro.paths.postfix_sasl_passwd, OutboundMailRouter.render_sasl_passwd(routes), mode=0o600
    )
    await executor.run_command(["/usr/sbin/postmap", distro.paths.postfix_virtual_mailbox_maps])
    await executor.run_command(["/usr/sbin/postmap", distro.paths.postfix_virtual_alias_maps])
    await executor.run_command(["/usr/sbin/postmap", distro.paths.postfix_sender_relay_maps])
    await executor.run_command(["/usr/sbin/postmap", distro.paths.postfix_sasl_passwd])


@router.get("/status")
async def mail_server_status(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    distro = get_distro_driver()
    services: dict[str, str] = {}
    for service in ("postfix", "dovecot", "opendkim", "rspamd"):
        try:
            res = await executor.run_command(distro.build_service_control_cmd(service, "is-active"))
        except Exception:  # noqa: BLE001 - diagnostics must not crash the endpoint
            services[service] = "unknown"
            continue
        raw = (res.stdout or "").strip()
        services[service] = raw if raw in SERVICE_STATES else ("active" if res.ok else "inactive")

    domain_count = (await db.execute(select(func.count()).select_from(MailDomain))).scalar_one()
    mailbox_count = (await db.execute(select(func.count()).select_from(Mailbox))).scalar_one()
    active_mailbox_count = (
        await db.execute(select(func.count()).select_from(Mailbox).where(Mailbox.is_active.is_(True)))
    ).scalar_one()
    alias_count = (await db.execute(select(func.count()).select_from(MailAlias))).scalar_one()

    return {
        "hostname": socket.getfqdn(),
        "public_ip": _detect_server_ip(),
        "services": services,
        "counts": {
            "domains": domain_count,
            "mailboxes": mailbox_count,
            "active_mailboxes": active_mailbox_count,
            "aliases": alias_count,
        },
    }


@router.get("/domains")
async def list_mail_domains(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    domains = (await db.execute(select(MailDomain).order_by(MailDomain.domain))).scalars().all()
    mailbox_counts = dict(
        (await db.execute(select(Mailbox.mail_domain_id, func.count()).group_by(Mailbox.mail_domain_id))).all()
    )
    alias_counts = dict(
        (await db.execute(select(MailAlias.mail_domain_id, func.count()).group_by(MailAlias.mail_domain_id))).all()
    )
    return [
        {
            "id": d.id,
            "domain": d.domain,
            "dkim_selector": d.dkim_selector,
            "dkim_public_key": d.dkim_public_key,
            "outbound_mode": d.outbound_mode,
            "relay_host": d.relay_host,
            "relay_port": d.relay_port,
            "relay_username": d.relay_username,
            "relay_password": secret_manager.mask(d.relay_password_encrypted),
            "catchall_address": d.catchall_address,
            "mailbox_count": mailbox_counts.get(d.id, 0),
            "alias_count": alias_counts.get(d.id, 0),
        }
        for d in domains
    ]


@router.post("/domains", status_code=status.HTTP_201_CREATED)
async def create_mail_domain(
    body: MailDomainCreate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = (await db.execute(select(MailDomain).where(MailDomain.domain == body.domain))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Mail domain already exists")

    priv_pem, dns_pub = generate_dkim_keypair(2048)
    md = MailDomain(
        domain=body.domain,
        dkim_selector=body.dkim_selector,
        dkim_public_key=dns_pub,
        dkim_private_key_encrypted=secret_manager.encrypt(priv_pem),
    )
    db.add(md)
    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action="create_mail_domain", target_resource=f"mail:{md.domain}"
    )
    await db.commit()
    return {"id": md.id, "domain": md.domain, "dkim_selector": md.dkim_selector, "dkim_public_key": md.dkim_public_key}


def _dns_lookup(qname: str, rtype: str) -> dict[str, Any]:
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = settings.DNS_CHECK_TIMEOUT_SECONDS
        resolver.lifetime = settings.DNS_CHECK_TIMEOUT_SECONDS
        answer = resolver.resolve(qname, rtype, raise_on_no_answer=False)
        values = [r.to_text() for r in answer] if answer.rrset is not None else []
        return {"propagated": bool(values), "observed": values, "error": None}
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash the endpoint
        return {"propagated": False, "observed": [], "error": str(exc)}


@router.get("/domains/{domain_id}/dns-readiness")
async def inspect_dns_readiness(
    domain_id: int,
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")

    public_ip = _detect_server_ip()
    mail_host = _mail_hostname() or f"mail.{md.domain}"
    spf_value = (
        f"v=spf1 a mx ip4:{public_ip} ~all"
        if public_ip and public_ip != "127.0.0.1"
        else "v=spf1 a mx ~all"
    )
    dkim_name = f"{md.dkim_selector}._domainkey"
    dmarc_value = f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{md.domain}"

    required_records = [
        {
            "type": "MX",
            "name": "@",
            "priority": 10,
            "value": f"{mail_host}.",
            "purpose": "Inbound mail routing",
            "fix": f"Add an MX record for @ pointing to {mail_host} with priority 10.",
        },
        {
            "type": "A",
            "name": mail_host.split(".")[0] if mail_host.endswith(f".{md.domain}") else mail_host,
            "value": public_ip,
            "purpose": "Mail host address",
            "fix": f"Add an A record for {mail_host} pointing to {public_ip}.",
        },
        {
            "type": "TXT",
            "name": "@",
            "value": spf_value,
            "purpose": "SPF sender policy",
            "fix": "Publish a single SPF TXT record at @ that authorises this server to send mail.",
        },
        {
            "type": "TXT",
            "name": dkim_name,
            "value": md.dkim_public_key,
            "purpose": "2048-bit RSA DKIM signature key",
            "fix": f"Publish the DKIM public key at {dkim_name} as a TXT record.",
        },
        {
            "type": "TXT",
            "name": "_dmarc",
            "value": dmarc_value,
            "purpose": "DMARC alignment & reporting",
            "fix": "Publish a DMARC TXT record at _dmarc (start with p=none if unsure).",
        },
    ]

    live_checks: dict[str, dict] = {}
    if settings.DNS_LIVE_CHECK_ENABLED:
        mx = _dns_lookup(md.domain, "MX")
        a = _dns_lookup(mail_host, "A")
        spf = _dns_lookup(md.domain, "TXT")
        spf["observed"] = [v for v in spf["observed"] if "v=spf1" in v.lower()]
        spf["propagated"] = bool(spf["observed"])
        live_checks = {
            "mx": mx,
            "a": a,
            "spf": spf,
            "dkim": _dns_lookup(f"{dkim_name}.{md.domain}", "TXT"),
            "dmarc": _dns_lookup(f"_dmarc.{md.domain}", "TXT"),
        }

    return {
        "domain": md.domain,
        "mail_host": mail_host,
        "public_ip": public_ip,
        "dkim_selector": md.dkim_selector,
        "required_records": required_records,
        "live_checks_enabled": settings.DNS_LIVE_CHECK_ENABLED,
        "live_propagation": live_checks,
    }


@router.delete("/domains/{domain_id}")
async def delete_mail_domain(
    domain_id: int,
    request: Request,
    actor: User = Depends(require_permission("mail:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")
    domain = md.domain
    await db.delete(md)
    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:delete", action="delete_mail_domain", target_resource=f"mail:{domain}"
    )
    await db.commit()
    return {"deleted": True, "domain": domain}


@router.put("/domains/{domain_id}/outbound-route")
async def update_outbound_route(
    domain_id: int,
    body: OutboundRouteUpdate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")

    md.outbound_mode = body.outbound_mode
    md.relay_host = body.relay_host
    md.relay_port = body.relay_port
    md.relay_username = body.relay_username
    if body.relay_password is not None:
        md.relay_password_encrypted = secret_manager.encrypt(body.relay_password)

    await _sync_mail_maps(db)
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action="update_outbound_route",
        target_resource=f"mail:{md.domain}",
        after_state={"mode": md.outbound_mode, "relay_host": md.relay_host},
    )
    await db.commit()
    return {"updated": True, "outbound_mode": md.outbound_mode}


@router.get("/diagnostics/egress")
async def check_direct_egress_diagnostics(_: User = Depends(require_permission("mail:read"))) -> dict:
    hostname = socket.getfqdn()
    public_ip = _detect_server_ip()
    port25_open = False
    try:
        with socket.create_connection(("gmail-smtp-in.l.google.com", 25), timeout=3):
            port25_open = True
    except OSError:
        port25_open = False

    ptr_records: list[str] = []
    try:
        rev = dns.reversename.from_address(public_ip)
        ptr_records = [str(r).rstrip(".") for r in dns.resolver.resolve(rev, "PTR")]
    except Exception:
        pass

    host = hostname.rstrip(".")
    ptr_matches = any(rec == host for rec in ptr_records)
    recommendations: list[str] = []
    if not port25_open:
        recommendations.append(
            "Outbound port 25 is blocked by your provider. Use an SMTP relay under Domains → Outbound route."
        )
    if not ptr_matches:
        recommendations.append(
            f"Set a PTR (reverse DNS) record for {public_ip} to {host or 'this mail hostname'} to improve deliverability."
        )
    if not recommendations:
        recommendations.append("Direct egress looks healthy: port 25 is reachable and PTR matches the hostname.")

    return {
        "hostname": hostname,
        "public_ip": public_ip,
        "port_25_egress_reachable": port25_open,
        "ptr_records": ptr_records,
        "ptr_matches_hostname": ptr_matches,
        "recommendations": recommendations,
    }


@router.get("/mailboxes")
async def list_mailboxes(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    mboxes = (await db.execute(select(Mailbox).order_by(Mailbox.email))).scalars().all()
    res = []
    for m in mboxes:
        parts = m.email.split("@")
        domain = parts[1] if len(parts) > 1 else ""
        local_part = parts[0]
        res.append(
            {
                "id": m.id,
                "mail_domain_id": m.mail_domain_id,
                "email": m.email,
                "quota_mb": m.quota_mb,
                "used_mb": _get_mailbox_usage_mb(domain, local_part),
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return res


@router.post("/mailboxes", status_code=status.HTTP_201_CREATED)
async def create_mailbox(
    body: MailboxCreate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == body.mail_domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")

    email = f"{body.local_part.lower()}@{md.domain}"
    existing = (await db.execute(select(Mailbox).where(Mailbox.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Mailbox already exists")

    mbox = Mailbox(
        mail_domain_id=md.id,
        email=email,
        password_crypt=hash_dovecot_sha512_crypt(body.password),
        quota_mb=body.quota_mb,
    )
    db.add(mbox)
    await db.flush()
    await _ensure_maildir(md.domain, body.local_part.lower())
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action="create_mailbox", target_resource=f"mailbox:{email}"
    )
    await db.commit()
    return {"id": mbox.id, "email": mbox.email, "quota_mb": mbox.quota_mb}


@router.put("/mailboxes/{mailbox_id}")
async def update_mailbox(
    mailbox_id: int,
    body: MailboxUpdate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    mbox = (await db.execute(select(Mailbox).where(Mailbox.id == mailbox_id))).scalar_one_or_none()
    if not mbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    if body.password is not None:
        mbox.password_crypt = hash_dovecot_sha512_crypt(body.password)
    if body.quota_mb is not None:
        mbox.quota_mb = body.quota_mb
    if body.is_active is not None:
        mbox.is_active = body.is_active

    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action="update_mailbox",
        target_resource=f"mailbox:{mbox.email}",
        after_state={"quota_mb": mbox.quota_mb, "is_active": mbox.is_active, "password_rotated": body.password is not None},
    )
    await db.commit()
    return {
        "id": mbox.id,
        "email": mbox.email,
        "quota_mb": mbox.quota_mb,
        "is_active": mbox.is_active,
    }


@router.delete("/mailboxes/{mailbox_id}")
async def delete_mailbox(
    mailbox_id: int,
    request: Request,
    actor: User = Depends(require_permission("mail:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    mbox = (await db.execute(select(Mailbox).where(Mailbox.id == mailbox_id))).scalar_one_or_none()
    if not mbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    email = mbox.email
    await db.delete(mbox)
    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:delete", action="delete_mailbox", target_resource=f"mailbox:{email}"
    )
    await db.commit()
    return {"deleted": True}


@router.get("/aliases")
async def list_aliases(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    aliases = (await db.execute(select(MailAlias))).scalars().all()
    return [
        {"id": a.id, "mail_domain_id": a.mail_domain_id, "source_email": a.source_email, "destination_email": a.destination_email}
        for a in aliases
    ]


@router.post("/aliases", status_code=status.HTTP_201_CREATED)
async def create_alias(
    body: AliasCreate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alias = MailAlias(
        mail_domain_id=body.mail_domain_id,
        source_email=body.source_email.lower(),
        destination_email=body.destination_email.lower(),
    )
    db.add(alias)
    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action="create_mail_alias", target_resource=body.source_email
    )
    await db.commit()
    return {"id": alias.id, "source_email": alias.source_email, "destination_email": alias.destination_email}


@router.delete("/aliases/{alias_id}")
async def delete_alias(
    alias_id: int,
    request: Request,
    actor: User = Depends(require_permission("mail:delete")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alias = (await db.execute(select(MailAlias).where(MailAlias.id == alias_id))).scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")
    source_email = alias.source_email
    await db.delete(alias)
    await db.flush()
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:delete", action="delete_mail_alias", target_resource=source_email
    )
    await db.commit()
    return {"deleted": True}


@router.get("/queue")
async def get_postfix_queue(_: User = Depends(require_permission("mail:read"))) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/sbin/postqueue", "-j"])
    items = []
    if res.ok and res.stdout.strip():
        for line in res.stdout.splitlines():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"queue": items, "count": len(items), "raw_error": res.stderr if not res.ok else ""}


@router.post("/queue/{action}")
async def manage_postfix_queue(
    action: str,
    queue_id: str | None = Query(default=None),
    request: Request = None,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    if action == "flush":
        res = await executor.run_command(["/usr/sbin/postqueue", "-f"])
    elif action == "requeue":
        if queue_id == "ALL":
            res = await executor.run_command(["/usr/sbin/postsuper", "-r", "ALL"])
        elif queue_id and QUEUE_ID_RE.match(queue_id):
            res = await executor.run_command(["/usr/sbin/postsuper", "-r", queue_id])
        else:
            raise HTTPException(status_code=400, detail="Valid Postfix queue_id or 'ALL' required")
    elif action == "release":
        if not queue_id or not QUEUE_ID_RE.match(queue_id):
            raise HTTPException(status_code=400, detail="Valid Postfix queue_id required")
        res = await executor.run_command(["/usr/sbin/postsuper", "-H", queue_id])
    elif action == "hold":
        if not queue_id or not QUEUE_ID_RE.match(queue_id):
            raise HTTPException(status_code=400, detail="Valid Postfix queue_id required")
        res = await executor.run_command(["/usr/sbin/postsuper", "-h", queue_id])
    elif action == "delete":
        if queue_id == "ALL_DEFERRED":
            res = await executor.run_command(["/usr/sbin/postsuper", "-d", "ALL", "deferred"])
        elif queue_id and QUEUE_ID_RE.match(queue_id):
            res = await executor.run_command(["/usr/sbin/postsuper", "-d", queue_id])
        else:
            raise HTTPException(status_code=400, detail="Valid Postfix queue_id or 'ALL_DEFERRED' required")
    else:
        raise HTTPException(status_code=400, detail="Unsupported queue action")

    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action=f"postfix_queue_{action}", target_resource=queue_id or "all"
    )
    await db.commit()
    return {"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr}


@router.get("/logs")
async def read_mail_logs(
    lines: int = Query(default=100, ge=10, le=1000),
    _: User = Depends(require_permission("mail:read")),
) -> dict:
    for candidate in (Path("/var/log/mail.log"), Path("/var/log/maillog")):
        if not candidate.exists():
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return {"lines": [], "source": str(candidate), "error": str(exc)}
        return {"lines": content[-lines:], "source": str(candidate), "error": None}
    return {"lines": [], "source": None, "error": "No mail log found at /var/log/mail.log or /var/log/maillog"}


class CatchallUpdate(BaseModel):
    catchall_address: str | None = None

    @field_validator("catchall_address")
    @classmethod
    def check_catchall(cls, v: str | None) -> str | None:
        # The catch-all address is rendered into the Postfix virtual alias map;
        # newlines would allow injecting extra map entries.
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if any(ch in cleaned for ch in ("\x00", "\r", "\n", " ", "\t")):
            raise ValueError(f"Invalid catch-all address: {v!r}")
        if not re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}", cleaned):
            raise ValueError(f"Invalid catch-all address: {v!r}")
        return cleaned


@router.put("/domains/{domain_id}/catchall")
async def update_catchall(
    domain_id: int,
    body: CatchallUpdate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")
    md.catchall_address = body.catchall_address
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action="update_catchall", target_resource=f"mail:{md.domain}"
    )
    await db.commit()
    return {"updated": True, "catchall_address": md.catchall_address}


@router.post("/domains/{domain_id}/sync-dns")
async def sync_mail_domain_dns(
    domain_id: int,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")

    zone = (await db.execute(select(DnsZone).where(DnsZone.domain == md.domain))).scalar_one_or_none()
    if not zone:
        return {
            "synced": False,
            "message": f"No DNS zone found for '{md.domain}' in NexoPanel. Please create the DNS zone first in DNS Manager.",
        }

    public_ip = _detect_server_ip()
    mail_host = _mail_hostname() or f"mail.{md.domain}"
    spf_value = f"v=spf1 a mx ip4:{public_ip} ~all" if public_ip and public_ip != "127.0.0.1" else "v=spf1 a mx ~all"
    dkim_name = f"{md.dkim_selector}._domainkey"
    dmarc_value = f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{md.domain}"

    targets = [
        {"name": "@", "record_type": "MX", "value": f"{mail_host}.", "priority": 10, "ttl": 300},
        {"name": mail_host.split(".")[0] if mail_host.endswith(f".{md.domain}") else "mail", "record_type": "A", "value": public_ip, "priority": None, "ttl": 300},
        {"name": "@", "record_type": "TXT", "value": spf_value, "priority": None, "ttl": 300},
        {"name": dkim_name, "record_type": "TXT", "value": md.dkim_public_key, "priority": None, "ttl": 300},
        {"name": "_dmarc", "record_type": "TXT", "value": dmarc_value, "priority": None, "ttl": 300},
    ]

    existing_records = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()
    created_count = 0
    updated_count = 0

    for t in targets:
        match = next((r for r in existing_records if r.name == t["name"] and r.record_type == t["record_type"]), None)
        if match:
            if match.value != t["value"] or match.priority != t["priority"]:
                match.value = t["value"]
                match.priority = t["priority"]
                updated_count += 1
        else:
            rec = DnsRecord(
                zone_id=zone.id,
                name=t["name"],
                record_type=t["record_type"],
                value=t["value"],
                priority=t["priority"],
                ttl=t["ttl"],
            )
            db.add(rec)
            created_count += 1

    await db.flush()
    all_recs = (await db.execute(select(DnsRecord).where(DnsRecord.zone_id == zone.id))).scalars().all()

    try:
        from app.api.v1.dns import _sync_bind_zone
        await _sync_bind_zone(zone, list(all_recs))
    except Exception:
        pass

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action="sync_mail_domain_dns",
        target_resource=f"mail:{md.domain}->zone:{zone.domain}",
    )
    await db.commit()
    return {
        "synced": True,
        "zone": zone.domain,
        "created_records": created_count,
        "updated_records": updated_count,
        "message": f"Successfully synced DNS records into NexoPanel zone {zone.domain} ({created_count} created, {updated_count} updated).",
    }


@router.get("/client-config")
async def get_client_config(
    email: EmailStr = Query(...),
    _: User = Depends(require_permission("mail:read")),
) -> dict:
    domain_part = email.split("@")[-1]
    mail_host = _mail_hostname() or f"mail.{domain_part}"
    pub_ip = _detect_server_ip()
    return {
        "email": email,
        "username": email,
        "mail_host": mail_host,
        "server_ip": pub_ip,
        "webmail_url": "/webmail",
        "protocols": {
            "imap": {
                "host": mail_host,
                "port_ssl": 993,
                "security_ssl": "SSL/TLS",
                "port_starttls": 143,
                "security_starttls": "STARTTLS",
                "auth": "Normal password",
            },
            "pop3": {
                "host": mail_host,
                "port_ssl": 995,
                "security_ssl": "SSL/TLS",
                "port_starttls": 110,
                "security_starttls": "STARTTLS",
                "auth": "Normal password",
            },
            "smtp": {
                "host": mail_host,
                "port_tls": 587,
                "security_tls": "STARTTLS",
                "port_ssl": 465,
                "security_ssl": "SSL/TLS",
                "auth": "Normal password (authentication required)",
            },
        },
    }


@router.get("/client-config/mobileconfig")
async def get_apple_mobileconfig(
    email: EmailStr = Query(...),
    _: User = Depends(require_permission("mail:read")),
) -> Response:
    import uuid

    domain_part = email.split("@")[-1]
    local_part = email.split("@")[0]
    mail_host = _mail_hostname() or f"mail.{domain_part}"

    payload_uuid = str(uuid.uuid4()).upper()
    mail_uuid = str(uuid.uuid4()).upper()

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadDisplayName</key>
    <string>{email} Mail Account</string>
    <key>PayloadIdentifier</key>
    <string>com.nexopanel.mail.{domain_part}.{local_part}</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{payload_uuid}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.mail.managed</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.nexopanel.mail.{domain_part}.{local_part}.account</string>
            <key>PayloadUUID</key>
            <string>{mail_uuid}</string>
            <key>PayloadDisplayName</key>
            <string>{email}</string>
            <key>EmailAccountDescription</key>
            <string>{email}</string>
            <key>EmailAccountType</key>
            <string>EmailTypeIMAP</string>
            <key>EmailAddress</key>
            <string>{email}</string>
            <key>IncomingMailServerAuthentication</key>
            <string>EmailAuthPassword</string>
            <key>IncomingMailServerHostName</key>
            <string>{mail_host}</string>
            <key>IncomingMailServerPortNumber</key>
            <integer>993</integer>
            <key>IncomingMailServerUseSSL</key>
            <true/>
            <key>IncomingMailServerUsername</key>
            <string>{email}</string>
            <key>OutgoingMailServerAuthentication</key>
            <string>EmailAuthPassword</string>
            <key>OutgoingMailServerHostName</key>
            <string>{mail_host}</string>
            <key>OutgoingMailServerPortNumber</key>
            <integer>587</integer>
            <key>OutgoingMailServerUseSSL</key>
            <true/>
            <key>OutgoingMailServerUsername</key>
            <string>{email}</string>
            <key>OutgoingPasswordSameAsIncomingPassword</key>
            <true/>
        </dict>
    </array>
</dict>
</plist>"""
    return Response(
        content=xml,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": f'attachment; filename="{email}.mobileconfig"'},
    )


@router.post("/services/{service}/{action}")
async def control_mail_service(
    service: str,
    action: str,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if service not in {"postfix", "dovecot", "opendkim", "rspamd"}:
        raise HTTPException(status_code=400, detail=f"Unsupported service: {service}")
    if action not in {"restart", "reload", "start", "stop"}:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    distro = get_distro_driver()
    executor = get_node_executor()
    cmd = distro.build_service_control_cmd(service, action)
    res = await executor.run_command(cmd)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action=f"mail_service_{action}",
        target_resource=service,
        after_state={"ok": res.ok, "stdout": res.stdout, "stderr": res.stderr},
    )
    await db.commit()
    return {"ok": res.ok, "service": service, "action": action, "output": (res.stdout or res.stderr).strip()}


@router.get("/config")
async def get_mail_server_config(
    _: User = Depends(require_permission("mail:read")),
) -> dict:
    executor = get_node_executor()
    max_mb = 25
    tls_level = "may"
    try:
        res = await executor.run_command(["/usr/sbin/postconf", "-h", "message_size_limit"])
        if res.ok and res.stdout.strip().isdigit():
            max_mb = max(5, int(res.stdout.strip()) // (1024 * 1024))
    except Exception:
        pass

    try:
        res_tls = await executor.run_command(["/usr/sbin/postconf", "-h", "smtpd_tls_security_level"])
        if res_tls.ok and res_tls.stdout.strip():
            tls_level = res_tls.stdout.strip()
    except Exception:
        pass

    return {
        "hostname": socket.getfqdn(),
        "public_ip": _detect_server_ip(),
        "mail_dir_base": str(settings.MAIL_DIR_BASE),
        "max_message_size_mb": max_mb,
        "tls_security_level": tls_level,
        "webmail_url": "/webmail",
    }


@router.put("/config")
async def update_mail_server_config(
    body: MailServerConfigUpdate,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    changes = []
    if body.max_message_size_mb is not None:
        bytes_val = body.max_message_size_mb * 1024 * 1024
        await executor.run_command(["/usr/sbin/postconf", "-e", f"message_size_limit={bytes_val}"])
        changes.append(f"message_size_limit={bytes_val}")

    if body.tls_security_level is not None:
        await executor.run_command(["/usr/sbin/postconf", "-e", f"smtpd_tls_security_level={body.tls_security_level}"])
        changes.append(f"smtpd_tls_security_level={body.tls_security_level}")

    if changes:
        distro = get_distro_driver()
        await executor.run_command(distro.build_service_control_cmd("postfix", "reload"))

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action="update_mail_server_config",
        target_resource="mail_config",
        after_state={"changes": changes, "webmail_url": body.webmail_url},
    )
    await db.commit()
    return {"updated": True, "applied": changes, "webmail_url": body.webmail_url or "/webmail"}


@router.post("/test-email")
async def send_test_email(
    body: TestEmailRequest,
    request: Request,
    actor: User = Depends(require_permission("mail:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    import email.utils
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = body.sender
    msg["To"] = body.recipient
    msg["Subject"] = body.subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=body.sender.split("@")[-1])
    msg["X-Mailer"] = "NexoPanel Mail Console"
    msg.set_content(body.body)

    raw_text = msg.as_string()
    cmd = ["/usr/sbin/sendmail", "-t", "-i", "-f", body.sender]
    res = await executor.run_command(cmd, stdin=raw_text)

    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="mail:write",
        action="send_test_email",
        target_resource=f"{body.sender}->{body.recipient}",
    )
    await db.commit()

    if not res.ok:
        return {
            "success": False,
            "error": res.stderr or res.stdout or "Failed to deliver message to local MTA",
            "sender": body.sender,
            "recipient": body.recipient,
        }
    return {
        "success": True,
        "message": f"Test email handed over to Postfix MTA for {body.recipient}.",
        "sender": body.sender,
        "recipient": body.recipient,
    }
