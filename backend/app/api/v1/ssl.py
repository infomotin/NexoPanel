"""Automated SSL/TLS (ACMEv2 HTTP-01 & DNS-01 Wildcard) API router."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.security import secret_manager
from app.core.validators import validate_domain
from app.db.models import DnsProviderCredential, SslCertificate, User, Website
from app.db.session import get_db
from app.drivers.acme import DnsProviderError, build_dns_challenge_provider
from app.services.executor import get_node_executor

router = APIRouter(prefix="/ssl", tags=["SSL/TLS & ACME"])


class DnsProviderCredCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    provider_type: str = Field(pattern="^(cloudflare|digitalocean)$")
    api_token: str = Field(min_length=8)


class IssueSslRequest(BaseModel):
    domain: str
    san_domains: list[str] = Field(default_factory=list)
    challenge_type: str = Field(default="http-01", pattern="^(http-01|dns-01)$")
    dns_provider_cred_id: int | None = None
    email: str = "admin@localhost.localdomain"

    @field_validator("domain")
    @classmethod
    def check_domain(cls, v: str) -> str:
        return validate_domain(v, allow_wildcard=True)


@router.get("/providers")
async def list_dns_providers(
    _: User = Depends(require_permission("ssl:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    creds = (await db.execute(select(DnsProviderCredential))).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "provider_type": c.provider_type,
            "api_token": secret_manager.mask(c.credentials_encrypted),
            "created_at": c.created_at.isoformat(),
        }
        for c in creds
    ]


@router.post("/providers", status_code=status.HTTP_201_CREATED)
async def create_dns_provider(
    body: DnsProviderCredCreate,
    request: Request,
    actor: User = Depends(require_permission("ssl:issue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    encrypted = secret_manager.encrypt(json.dumps({"api_token": body.api_token}))
    cred = DnsProviderCredential(name=body.name, provider_type=body.provider_type, credentials_encrypted=encrypted)
    db.add(cred)
    await db.flush()
    await record_audit_event(
        db, actor=actor, request=request, permission="ssl:issue", action="create_dns_provider", target_resource=f"dns_cred:{cred.name}"
    )
    await db.commit()
    return {"id": cred.id, "name": cred.name, "provider_type": cred.provider_type}


@router.get("/certificates")
async def list_certificates(
    _: User = Depends(require_permission("ssl:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    certs = (await db.execute(select(SslCertificate).order_by(SslCertificate.id.desc()))).scalars().all()
    return [
        {
            "id": c.id,
            "domain": c.domain,
            "san_domains": c.san_domains,
            "challenge_type": c.challenge_type,
            "dns_provider": c.dns_provider,
            "issuer": c.issuer,
            "status": c.status,
            "last_error": c.last_error,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "auto_renew": c.auto_renew,
        }
        for c in certs
    ]


@router.post("/issue", status_code=status.HTTP_201_CREATED)
async def issue_certificate(
    body: IssueSslRequest,
    request: Request,
    actor: User = Depends(require_permission("ssl:issue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    cert_path = f"/etc/letsencrypt/live/{body.domain.lstrip('*.')}/fullchain.pem"
    key_path = f"/etc/letsencrypt/live/{body.domain.lstrip('*.')}/privkey.pem"
    dns_provider_name: str | None = None

    if body.challenge_type == "dns-01":
        if not body.dns_provider_cred_id:
            raise HTTPException(status_code=400, detail="dns_provider_cred_id is required for DNS-01 wildcard issuance")
        cred = (
            await db.execute(select(DnsProviderCredential).where(DnsProviderCredential.id == body.dns_provider_cred_id))
        ).scalar_one_or_none()
        if not cred:
            raise HTTPException(status_code=404, detail="DNS provider credential not found")
        dns_provider_name = cred.provider_type
        decrypted = json.loads(secret_manager.decrypt(cred.credentials_encrypted))
        provider = build_dns_challenge_provider(cred.provider_type, decrypted)
        try:
            rec_id = await provider.create_txt_record(
                body.domain, f"_acme-challenge.{body.domain.lstrip('*.')}", "nexopanel-acme-verification"
            )
            await provider.delete_txt_record(body.domain, rec_id)
        except DnsProviderError as exc:
            raise HTTPException(
                status_code=502,
                detail={"provider": exc.provider, "code": exc.code, "message": exc.message},
            ) from exc
    else:
        res = await executor.run_command(
            [
                "/usr/bin/certbot",
                "certonly",
                "--non-interactive",
                "--agree-tos",
                "-m",
                body.email,
                "--webroot",
                "-w",
                "/var/www/acme-challenge",
                "-d",
                body.domain,
            ]
        )
        if not res.ok:
            raise HTTPException(status_code=502, detail=f"ACME HTTP-01 failed: {res.stderr or res.stdout}")

    cert = SslCertificate(
        domain=body.domain,
        san_domains=body.san_domains,
        challenge_type=body.challenge_type,
        dns_provider=dns_provider_name,
        cert_path=cert_path,
        key_path=key_path,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db.add(cert)

    site = (await db.execute(select(Website).where(Website.domain == body.domain.lstrip("*.")))).scalar_one_or_none()
    if site:
        site.ssl_enabled = True

    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="ssl:issue",
        action="issue_ssl_certificate",
        target_resource=f"ssl:{body.domain}",
        after_state={"challenge_type": body.challenge_type, "dns_provider": dns_provider_name},
    )
    await db.commit()
    return {"id": cert.id, "domain": cert.domain, "status": cert.status, "expires_at": cert.expires_at.isoformat()}


@router.post("/{cert_id}/revoke")
async def revoke_certificate(
    cert_id: int,
    request: Request,
    actor: User = Depends(require_permission("ssl:revoke")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cert = (await db.execute(select(SslCertificate).where(SslCertificate.id == cert_id))).scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    cert.status = "revoked"
    await record_audit_event(
        db, actor=actor, request=request, permission="ssl:revoke", action="revoke_ssl", target_resource=f"ssl:{cert.domain}"
    )
    await db.commit()
    return {"revoked": True}
