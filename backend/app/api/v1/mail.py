"""Mail Server Administration, DNS Readiness Inspector, Postfix Queue & OutboundMailRouter."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import dns.resolver
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.security import hash_dovecot_sha512_crypt, secret_manager
from app.core.validators import QUEUE_ID_RE, validate_domain
from app.db.models import MailAlias, MailDomain, Mailbox, User
from app.db.session import get_db
from app.drivers.distro import get_distro_driver
from app.drivers.mail import OutboundMailRouter, OutboundRouteConfig, generate_dkim_keypair
from app.services.executor import get_node_executor

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


class AliasCreate(BaseModel):
    mail_domain_id: int
    source_email: EmailStr
    destination_email: EmailStr


class OutboundRouteUpdate(BaseModel):
    outbound_mode: str = Field(pattern="^(direct|relay)$")
    relay_host: str | None = None
    relay_port: int = Field(default=587, ge=1, le=65535)
    relay_username: str | None = None
    relay_password: str | None = None


async def _sync_mail_maps(db: AsyncSession) -> None:
    distro = get_distro_driver()
    executor = get_node_executor()
    domains = (await db.execute(select(MailDomain))).scalars().all()
    mailboxes = (await db.execute(select(Mailbox))).scalars().all()
    aliases = (await db.execute(select(MailAlias))).scalars().all()

    domain_lines = "\n".join(f"{d.domain} OK" for d in domains) + "\n"
    await executor.write_privileged_file(distro.paths.postfix_virtual_mailbox_domains, domain_lines)

    mbox_lines = "\n".join(f"{m.email} {m.email.split('@')[1]}/{m.email.split('@')[0]}/" for m in mailboxes) + "\n"
    await executor.write_privileged_file(distro.paths.postfix_virtual_mailbox_maps, mbox_lines)

    alias_lines = "\n".join(f"{a.source_email} {a.destination_email}" for a in aliases) + "\n"
    await executor.write_privileged_file(distro.paths.postfix_virtual_alias_maps, alias_lines)

    dovecot_lines = "\n".join(
        f"{m.email}:{m.password_crypt}:5000:5000::/var/mail/vhosts/{m.email.split('@')[1]}/{m.email.split('@')[0]}::userdb_quota_rule=*:storage={m.quota_mb}M"
        for m in mailboxes
        if m.is_active
    ) + "\n"
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


@router.get("/domains")
async def list_mail_domains(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    domains = (await db.execute(select(MailDomain).order_by(MailDomain.domain))).scalars().all()
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


@router.get("/domains/{domain_id}/dns-readiness")
async def inspect_dns_readiness(
    domain_id: int,
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    md = (await db.execute(select(MailDomain).where(MailDomain.id == domain_id))).scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail="Mail domain not found")

    hostname = socket.getfqdn()
    required_records = [
        {"type": "MX", "name": "@", "priority": 10, "value": f"mail.{md.domain}.", "purpose": "Inbound mail routing"},
        {"type": "TXT", "name": "@", "value": f"v=spf1 a mx ip4:127.0.0.1 ~all", "purpose": "SPF sender policy"},
        {
            "type": "TXT",
            "name": f"{md.dkim_selector}._domainkey",
            "value": md.dkim_public_key,
            "purpose": "2048-bit RSA DKIM signature key",
        },
        {
            "type": "TXT",
            "name": "_dmarc",
            "value": f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{md.domain}",
            "purpose": "DMARC alignment & reporting",
        },
    ]

    live_checks: dict[str, dict] = {}
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2.0
    resolver.lifetime = 2.0
    for key, qname, rtype in [
        ("mx", md.domain, "MX"),
        ("spf", md.domain, "TXT"),
        ("dkim", f"{md.dkim_selector}._domainkey.{md.domain}", "TXT"),
        ("dmarc", f"_dmarc.{md.domain}", "TXT"),
    ]:
        try:
            answers = resolver.resolve(qname, rtype)
            live_checks[key] = {"propagated": True, "observed": [str(r) for r in answers]}
        except Exception as exc:
            live_checks[key] = {"propagated": False, "error": str(exc)}

    return {
        "domain": md.domain,
        "mail_host": hostname,
        "required_records": required_records,
        "live_propagation": live_checks,
    }


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
    port25_open = False
    try:
        with socket.create_connection(("gmail-smtp-in.l.google.com", 25), timeout=3):
            port25_open = True
    except OSError:
        port25_open = False

    ptr_records: list[str] = []
    try:
        local_ip = socket.gethostbyname(hostname)
        rev = dns.reversename.from_address(local_ip)
        ptr_records = [str(r) for r in dns.resolver.resolve(rev, "PTR")]
    except Exception:
        pass

    return {"hostname": hostname, "port_25_egress_reachable": port25_open, "ptr_records": ptr_records}


@router.get("/mailboxes")
async def list_mailboxes(
    _: User = Depends(require_permission("mail:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    mboxes = (await db.execute(select(Mailbox).order_by(Mailbox.email))).scalars().all()
    return [
        {"id": m.id, "mail_domain_id": m.mail_domain_id, "email": m.email, "quota_mb": m.quota_mb, "is_active": m.is_active}
        for m in mboxes
    ]


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
    await _sync_mail_maps(db)
    await record_audit_event(
        db, actor=actor, request=request, permission="mail:write", action="create_mailbox", target_resource=f"mailbox:{email}"
    )
    await db.commit()
    return {"id": mbox.id, "email": mbox.email, "quota_mb": mbox.quota_mb}


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
    return {"queue": items, "raw_error": res.stderr if not res.ok else ""}


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
    elif action in {"hold", "delete"}:
        if not queue_id or not QUEUE_ID_RE.match(queue_id):
            raise HTTPException(status_code=400, detail="Valid Postfix queue_id required")
        flag = "-h" if action == "hold" else "-d"
        res = await executor.run_command(["/usr/sbin/postsuper", flag, queue_id])
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
    log_path = Path("/var/log/mail.log")
    if not log_path.exists():
        return {"lines": []}
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": content[-lines:]}


class CatchallUpdate(BaseModel):
    catchall_address: str | None = None


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
