"""Mail stack drivers: DKIM keygen, Postfix/Dovecot config builders, and OutboundMailRouter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_dkim_keypair(bits: int = 2048) -> tuple[str, str]:
    """Generate a 2048-bit RSA keypair for OpenDKIM. Returns (private_pem, dns_txt_public_value)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    import base64

    b64_pub = base64.b64encode(public_der).decode("ascii")
    dns_value = f"v=DKIM1; h=sha256; k=rsa; p={b64_pub}"
    return private_pem, dns_value


@dataclass(frozen=True)
class OutboundRouteConfig:
    domain: str
    mode: Literal["direct", "relay"]
    relay_host: str | None = None
    relay_port: int = 587
    relay_username: str | None = None
    relay_password: str | None = None


class OutboundMailRouter:
    """Unified interface generating Postfix sender_dependent_relayhost_maps & sasl_passwd entries."""

    @staticmethod
    def build_relay_map_line(route: OutboundRouteConfig) -> str | None:
        if route.mode != "relay" or not route.relay_host:
            return None
        return f"@{route.domain} [{route.relay_host}]:{route.relay_port}"

    @staticmethod
    def build_sasl_passwd_line(route: OutboundRouteConfig) -> str | None:
        if route.mode != "relay" or not route.relay_host or not route.relay_username:
            return None
        return f"[{route.relay_host}]:{route.relay_port} {route.relay_username}:{route.relay_password or ''}"

    @staticmethod
    def render_sender_relay_maps(routes: list[OutboundRouteConfig]) -> str:
        lines = ["# Managed by NexoPanel OutboundMailRouter"]
        for r in routes:
            line = OutboundMailRouter.build_relay_map_line(r)
            if line:
                lines.append(line)
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_sasl_passwd(routes: list[OutboundRouteConfig]) -> str:
        lines = ["# Managed by NexoPanel OutboundMailRouter (mode 0600)"]
        for r in routes:
            line = OutboundMailRouter.build_sasl_passwd_line(r)
            if line:
                lines.append(line)
        return "\n".join(lines) + "\n"
