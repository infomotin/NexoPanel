"""Application configuration using Pydantic Settings."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXOPANEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "NexoPanel"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["production", "development", "testing"] = "production"
    DEBUG: bool = False

    # Bind & Network
    HOST: str = "0.0.0.0"
    PORT: int = 8443
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "https://localhost:8443"])

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def check_allowed_origins(cls, v: list[str]) -> list[str]:
        # The API allows credentialed requests, so a reflected/wildcard origin
        # would let any website make authenticated cross-origin calls.
        cleaned = [origin.strip().rstrip("/") for origin in v if origin and origin.strip()]
        for origin in cleaned:
            if origin in {"*", "null"} or "*" in origin:
                raise ValueError(
                    "ALLOWED_ORIGINS must list explicit origins when credentials are allowed"
                )
        return cleaned

    # Database (Bundled SQLite 3 WAL)
    DATABASE_PATH: Path = Path("/var/lib/nexopanel/panel.db")
    DATABASE_URL: str | None = None

    # Secrets & Security
    MASTER_KEY_PATH: Path = Path("/etc/nexopanel/master.key")
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30-day administrative session continuity
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CSRF_COOKIE_NAME: str = "nexopanel_csrf"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # Rate Limiting & Lockout
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 300
    AUTH_RATE_LIMIT_MAX_ATTEMPTS: int = 10
    AUTH_LOCKOUT_SECONDS: int = 900

    # Privilege-separated Root Daemon
    DAEMON_SOCKET_PATH: Path = Path("/run/nexopanel/daemon.sock")

    # Private staging directory shared with the privileged daemon: content that
    # the unprivileged worker prepares here (archives, extracted trees) may be
    # installed into the panel-owned roots.
    DAEMON_TEMP_DIR: Path = Path("/run/nexopanel/tmp")
    DAEMON_USE_MOCK_EXECUTOR: bool = False

    # Node Context (Single-Node default, Multi-Node ready)
    LOCAL_NODE_ID: str = "local-node-01"

    # OS Gate
    SKIP_OS_CHECK: bool = False

    # Paths
    LOG_DIR: Path = Path("/var/log/nexopanel")
    BACKUP_DIR: Path = Path("/var/backups/nexopanel")
    WEB_ROOT_BASE: Path = Path("/var/www")
    MAIL_DIR_BASE: Path = Path("/var/mail/vhosts")
    ALLOWED_FILE_ROOTS: list[str] = Field(default_factory=lambda: ["/var/www", "/var/backups/nexopanel", "/etc/nginx/sites-available"])

    # Terminal
    TERMINAL_IDLE_TIMEOUT_SECONDS: int = 900

    # DNS diagnostics (live resolution checks may be disabled on offline hosts)
    DNS_LIVE_CHECK_ENABLED: bool = True
    DNS_CHECK_TIMEOUT_SECONDS: float = 3.0

    # Update checks against the upstream Git repository
    UPDATE_CHECK_ENABLED: bool = True
    UPDATE_CHECK_TTL_SECONDS: int = 120
    GITHUB_REPO: str = "infomotin/NexoPanel"
    GITHUB_TOKEN: str | None = None

    @property
    def resolved_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"


settings = Settings()
