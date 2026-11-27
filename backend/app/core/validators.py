"""Input validation helpers preventing command, path, and config injection."""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit

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


def escape_sql_string_literal(value: str) -> str:
    """Escape a value for a single-quoted SQL string literal.

    Only the quote is doubled.  This is safe *only* when the session uses
    ``NO_BACKSLASH_ESCAPES`` (MySQL/MariaDB) or ``standard_conforming_strings``
    (PostgreSQL); both are set explicitly by the caller because MySQL's default
    sql_mode treats a backslash as an escape character, which would otherwise
    let a password such as ``aa\\'`` terminate the literal early and inject
    SQL into a statement executed with root database privileges.
    """
    if "\x00" in value:
        raise ValueError("Null byte not allowed in SQL string literals")
    return value.replace("'", "''")


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


def is_public_address(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_outbound_url(url: str, *, allowed_schemes: tuple[str, ...] = ("http", "https")) -> str:
    """Validate a user-supplied URL before the server fetches it (SSRF guard).

    Rejects non-HTTP(S) schemes and any host that resolves to a loopback,
    link-local (cloud metadata), private or otherwise internal address, so the
    panel cannot be used as a proxy into the host's internal network.
    """
    parsed = urlsplit((url or "").strip())
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must contain a hostname")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Host could not be resolved: {host}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise ValueError(f"Host could not be resolved: {host}")
    for address in addresses:
        if not is_public_address(address):
            raise ValueError(f"Refusing to contact internal address: {address}")
    return url


def validate_proxy_upstream(value: str) -> str:
    """Validate an nginx proxy_pass upstream (scheme://host[:port])."""
    raw = (value or "").strip()
    if any(ch in raw for ch in ("\x00", "\r", "\n", "{", "}", ";", " ")):
        raise ValueError(f"Invalid proxy upstream: {value!r}")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid proxy upstream scheme: {value!r}")
    if not parsed.hostname:
        raise ValueError(f"Invalid proxy upstream host: {value!r}")
    if parsed.username or parsed.password:
        raise ValueError("Proxy upstream must not contain credentials")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(f"Invalid proxy upstream: {value!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid proxy upstream port: {value!r}") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError(f"Invalid proxy upstream port: {value!r}")
    return raw


def sanitize_nginx_directive_value(value: str) -> str:
    """Reject control characters and dangerous directive terminators where single-value expected."""
    if any(ch in value for ch in ("\x00", "\r", "\n")):
        raise ValueError("Newlines or null bytes are not allowed in single-line config values")
    return value
