"""SQLAlchemy 2.0 ORM models for NexoPanel control-plane metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    users: Mapped[list[User]] = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_codes_hashed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    role: Mapped[Role] = relationship("Role", back_populates="users", lazy="joined")


class AuditLog(Base):
    """Immutable, append-only audit log for all mutating actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    source_ip: Mapped[str] = mapped_column(String(64), default="127.0.0.1", nullable=False)
    permission: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(255), nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)


class PanelSetting(Base):
    __tablename__ = "panel_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    document_root: Mapped[str] = mapped_column(String(512), nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), default="static", nullable=False)  # static, php, proxy
    php_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proxy_upstream: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_directives: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    force_https: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    app_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    subdomains: Mapped[list[Subdomain]] = relationship(
        "Subdomain", back_populates="parent_website", cascade="all, delete-orphan"
    )


class Subdomain(Base):
    __tablename__ = "subdomains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), nullable=False)
    fqdn: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    document_root: Mapped[str] = mapped_column(String(512), nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), default="static", nullable=False)
    php_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proxy_upstream: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dns_record_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    parent_website: Mapped[Website] = relationship("Website", back_populates="subdomains")


class DnsZone(Base):
    __tablename__ = "dns_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    primary_ns: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_email: Mapped[str] = mapped_column(String(255), nullable=False)
    serial: Mapped[int] = mapped_column(Integer, nullable=False)
    refresh: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    retry: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    expire: Mapped[int] = mapped_column(Integer, default=604800, nullable=False)
    minimum_ttl: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    records: Mapped[list[DnsRecord]] = relationship(
        "DnsRecord", back_populates="zone", cascade="all, delete-orphan"
    )


class DnsRecord(Base):
    __tablename__ = "dns_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("dns_zones.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)  # A, AAAA, CNAME, MX, TXT, NS, SRV, CAA
    value: Mapped[str] = mapped_column(Text, nullable=False)
    ttl: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    zone: Mapped[DnsZone] = relationship("DnsZone", back_populates="records")


class MailDomain(Base):
    __tablename__ = "mail_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    dkim_selector: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    dkim_public_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dkim_private_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outbound_mode: Mapped[str] = mapped_column(String(32), default="direct", nullable=False)  # direct | relay
    relay_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relay_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    catchall_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mailboxes: Mapped[list[Mailbox]] = relationship(
        "Mailbox", back_populates="mail_domain", cascade="all, delete-orphan"
    )
    aliases: Mapped[list[MailAlias]] = relationship(
        "MailAlias", back_populates="mail_domain", cascade="all, delete-orphan"
    )


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mail_domain_id: Mapped[int] = mapped_column(ForeignKey("mail_domains.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_crypt: Mapped[str] = mapped_column(String(255), nullable=False)
    quota_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mail_domain: Mapped[MailDomain] = relationship("MailDomain", back_populates="mailboxes")


class MailAlias(Base):
    __tablename__ = "mail_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mail_domain_id: Mapped[int] = mapped_column(ForeignKey("mail_domains.id", ondelete="CASCADE"), nullable=False)
    source_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    destination_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("source_email", "destination_email", name="uq_mail_alias_src_dst"),)
    mail_domain: Mapped[MailDomain] = relationship("MailDomain", back_populates="aliases")


class SslCertificate(Base):
    __tablename__ = "ssl_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    san_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    challenge_type: Mapped[str] = mapped_column(String(32), default="http-01", nullable=False)  # http-01 | dns-01
    dns_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cert_path: Mapped[str] = mapped_column(String(512), nullable=False)
    key_path: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str] = mapped_column(String(255), default="Let's Encrypt", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DnsProviderCredential(Base):
    __tablename__ = "dns_provider_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)  # cloudflare | digitalocean
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagedDatabase(Base):
    __tablename__ = "managed_databases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)  # mariadb | postgresql
    db_name: Mapped[str] = mapped_column(String(64), nullable=False)
    db_user: Mapped[str] = mapped_column(String(64), nullable=False)
    db_host: Mapped[str] = mapped_column(String(64), default="localhost", nullable=False)
    charset: Mapped[str] = mapped_column(String(32), default="utf8mb4", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("engine", "db_name", name="uq_managed_db_engine_name"),)


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # website | database | mail | full
    target_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_count: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    manifests: Mapped[list[BackupManifest]] = relationship(
        "BackupManifest", back_populates="job", cascade="all, delete-orphan"
    )


class BackupManifest(Base):
    __tablename__ = "backup_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("backup_jobs.id", ondelete="SET NULL"), nullable=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    job: Mapped[BackupJob | None] = relationship("BackupJob", back_populates="manifests")


class InstalledApp(Base):
    __tablename__ = "installed_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    app_slug: Mapped[str] = mapped_column(String(64), nullable=False)  # wordpress | laravel | static | nodejs | python
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    install_path: Mapped[str] = mapped_column(String(512), nullable=False)
    db_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FirewallRule(Base):
    __tablename__ = "firewall_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    port: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "80", "443", "8000:8100"
    protocol: Mapped[str] = mapped_column(String(16), default="tcp", nullable=False)  # tcp | udp | any
    action: Mapped[str] = mapped_column(String(16), default="allow", nullable=False)  # allow | deny
    source_ip: Mapped[str] = mapped_column(String(64), default="any", nullable=False)
    comment: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CronJob(Base):
    __tablename__ = "cron_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), default="local-node-01", nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)  # shell | url | backup_site | backup_db | log_rotate
    schedule: Mapped[str] = mapped_column(String(64), nullable=False)  # 5-field cron expression
    command_or_target: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FileTrashItem(Base):
    __tablename__ = "file_trash_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    trash_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

