"""Firewall (UFW), Fail2Ban, and SSH Hardening API router."""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.rbac import require_permission
from app.core.validators import validate_ip_address
from app.db.models import FirewallRule, User
from app.db.session import get_db
from app.services.executor import get_node_executor

router = APIRouter(prefix="/firewall", tags=["Firewall & Intrusion Prevention"])

PORT_RE = re.compile(r"^\d{1,5}(?::\d{1,5})?$")


class FirewallRuleCreate(BaseModel):
    port: str = Field(min_length=1, max_length=15)
    protocol: str = Field(default="tcp", pattern="^(tcp|udp|any)$")
    action: str = Field(default="allow", pattern="^(allow|deny)$")
    source_ip: str = Field(default="any", max_length=64)
    comment: str = Field(default="", max_length=255)

    @field_validator("port")
    @classmethod
    def check_port(cls, v: str) -> str:
        if not PORT_RE.match(v.strip()):
            raise ValueError("Port must be 1-65535 or range start:end")
        return v.strip()

    @field_validator("source_ip")
    @classmethod
    def check_source(cls, v: str) -> str:
        if v.strip().lower() == "any":
            return "any"
        return validate_ip_address(v)


class SshConfigUpdate(BaseModel):
    ssh_port: int = Field(default=22, ge=1, le=65535)
    permit_root_login: bool = True
    password_auth: bool = True


class UnbanIpRequest(BaseModel):
    jail: str = Field(default="sshd", pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    ip: str

    @field_validator("ip")
    @classmethod
    def check_ip(cls, v: str) -> str:
        return validate_ip_address(v)


@router.get("/status")
async def get_firewall_status(_: User = Depends(require_permission("firewall:read"))) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/sbin/ufw", "status", "verbose"])
    return {"active": "Status: active" in res.stdout or executor.use_mock, "raw": res.stdout}


@router.post("/toggle")
async def toggle_firewall(
    enable: bool,
    request: Request,
    actor: User = Depends(require_permission("firewall:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    cmd = ["/usr/sbin/ufw", "--force", "enable"] if enable else ["/usr/sbin/ufw", "disable"]
    res = await executor.run_command(cmd)
    await record_audit_event(
        db, actor=actor, request=request, permission="firewall:write", action="toggle_firewall", target_resource=f"ufw:{enable}"
    )
    await db.commit()
    return {"ok": res.ok, "enabled": enable}


@router.get("/rules")
async def list_firewall_rules(
    _: User = Depends(require_permission("firewall:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rules = (await db.execute(select(FirewallRule).order_by(FirewallRule.id.desc()))).scalars().all()
    return [
        {
            "id": r.id,
            "port": r.port,
            "protocol": r.protocol,
            "action": r.action,
            "source_ip": r.source_ip,
            "comment": r.comment,
            "created_at": r.created_at.isoformat(),
        }
        for r in rules
    ]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_firewall_rule(
    body: FirewallRuleCreate,
    request: Request,
    actor: User = Depends(require_permission("firewall:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    port_spec = f"{body.port}/{body.protocol}" if body.protocol != "any" else body.port
    cmd = ["/usr/sbin/ufw", body.action]
    if body.source_ip != "any":
        cmd.extend(["from", body.source_ip, "to", "any", "port", body.port])
        if body.protocol != "any":
            cmd.extend(["proto", body.protocol])
    else:
        cmd.append(port_spec)
    res = await executor.run_command(cmd)
    if not res.ok:
        raise HTTPException(status_code=500, detail=f"UFW rule failed: {res.stderr or res.stdout}")

    rule = FirewallRule(
        port=body.port,
        protocol=body.protocol,
        action=body.action,
        source_ip=body.source_ip,
        comment=body.comment,
    )
    db.add(rule)
    await db.flush()
    await record_audit_event(
        db,
        actor=actor,
        request=request,
        permission="firewall:write",
        action="add_firewall_rule",
        target_resource=f"ufw:{body.action}:{port_spec}",
    )
    await db.commit()
    return {"id": rule.id, "port": rule.port, "protocol": rule.protocol, "action": rule.action}


@router.delete("/rules/{rule_id}")
async def delete_firewall_rule(
    rule_id: int,
    request: Request,
    actor: User = Depends(require_permission("firewall:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rule = (await db.execute(select(FirewallRule).where(FirewallRule.id == rule_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Firewall rule not found")

    executor = get_node_executor()
    port_spec = f"{rule.port}/{rule.protocol}" if rule.protocol != "any" else rule.port
    await executor.run_command(["/usr/sbin/ufw", "delete", rule.action, port_spec])
    await db.delete(rule)
    await record_audit_event(
        db, actor=actor, request=request, permission="firewall:write", action="delete_firewall_rule", target_resource=port_spec
    )
    await db.commit()
    return {"deleted": True}


@router.get("/fail2ban")
async def get_fail2ban_status(_: User = Depends(require_permission("firewall:read"))) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/fail2ban-client", "status", "sshd"])
    return {"jail": "sshd", "raw": res.stdout, "ok": res.ok}


@router.post("/fail2ban/unban")
async def unban_ip(
    body: UnbanIpRequest,
    request: Request,
    actor: User = Depends(require_permission("firewall:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    executor = get_node_executor()
    res = await executor.run_command(["/usr/bin/fail2ban-client", "set", body.jail, "unbanip", body.ip])
    await record_audit_event(
        db, actor=actor, request=request, permission="firewall:write", action="fail2ban_unban", target_resource=f"{body.jail}:{body.ip}"
    )
    await db.commit()
    return {"ok": res.ok, "unbanned": body.ip}
