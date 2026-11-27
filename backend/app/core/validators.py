"""Input validation helpers preventing command, path, and config injection."""
from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path

DOMAIN_RE = re.compile(
    r"^(?:\*\.)?(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)
LINUX_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
DB_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,127}$")
SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.@-]{1,64}$")
QUEUE_ID_RE = re.compile(r"^[A-F0-9]{6,20}$")


def validate_domain(value: str, allow_wildcard: bool = False) -> str:
    domain = value.strip().lower()
    if domain.startswith("*.") and not allow_wildcard:
        raise ValueError("Wildcard domains are not permitted in this context")
    if not DOMAIN_RE.match(domain):
        raise ValueError(f"Invalid RFC 1123 domain name: {value!r}")
    return domain


def validate_ip_address(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {value!r}") from exc
    return str(ip)


def validate_linux_username(value: str) -> str:
    if not LINUX_USERNAME_RE.match(value):
        raise ValueError(f"Invalid Linux username: {value!r}")
    return value


def validate_db_identifier(value: str) -> str:
    if not DB_IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return value


def validate_package_name(value: str) -> str:
    if not PACKAGE_NAME_RE.match(value):
        raise ValueError(f"Invalid Debian package name: {value!r}")
    return value


def canonicalize_safe_path(target_path: str, allowed_roots: list[str]) -> Path:
    """Resolve symlinks and '..' segments and ensure path stays within allowed_roots."""
    if "\x00" in target_path:
        raise ValueError("Null byte in path")
    resolved = Path(os.path.realpath(target_path))
    for root in allowed_roots:
        root_resolved = Path(os.path.realpath(root))
        if resolved == root_resolved or root_resolved in resolved.parents:
            return resolved
    raise PermissionError(f"Access denied: path '{resolved}' is outside permitted roots")


def sanitize_nginx_directive_value(value: str) -> str:
    """Reject control characters and dangerous directive terminators where single-value expected."""
    if any(ch in value for ch in ("\x00", "\r", "\n")):
        raise ValueError("Newlines or null bytes are not allowed in single-line config values")
    return value
