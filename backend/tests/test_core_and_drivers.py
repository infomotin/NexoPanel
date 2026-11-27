"""Tests for OS Gatekeeper, DistroDriver, Validators, and Security Primitives."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.os_gate import UnsupportedOSError, validate_host_environment
from app.core.security import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_dovecot_sha512_crypt,
    hash_password,
    secret_manager,
    verify_password,
    verify_recovery_code,
)
from app.core.validators import canonicalize_safe_path, validate_db_identifier, validate_domain
from app.drivers.distro import DebianDriver, UbuntuDriver
from app.drivers.mail import OutboundMailRouter, OutboundRouteConfig, generate_dkim_keypair


def test_os_gate_accepts_ubuntu_2404(tmp_path: Path):
    os_rel = tmp_path / "os-release"
    os_rel.write_text('ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\n')
    with patch("platform.machine", return_value="x86_64"):
        info = validate_host_environment(os_release_path=os_rel, skip_check=False)
        assert info is not None
        assert info.distro_id == "ubuntu"
        assert info.version_id == "24.04"


def test_os_gate_rejects_unsupported_distro(tmp_path: Path):
    os_rel = tmp_path / "os-release"
    os_rel.write_text('ID=centos\nVERSION_ID="7"\nPRETTY_NAME="CentOS 7"\n')
    with patch("platform.machine", return_value="x86_64"):
        with pytest.raises(UnsupportedOSError):
            validate_host_environment(os_release_path=os_rel, skip_check=False)


def test_validators_and_path_canonicalization(tmp_path: Path):
    assert validate_domain("example.com") == "example.com"
    assert validate_domain("*.example.com", allow_wildcard=True) == "*.example.com"
    with pytest.raises(ValueError):
        validate_domain("invalid_domain;rm -rf /")

    assert validate_db_identifier("app_prod_01") == "app_prod_01"
    with pytest.raises(ValueError):
        validate_db_identifier("drop table users;--")

    root = tmp_path / "www"
    root.mkdir()
    safe = canonicalize_safe_path(str(root / "site/index.html"), [str(root)])
    assert str(root) in str(safe)

    with pytest.raises(PermissionError):
        canonicalize_safe_path(str(root / "../../etc/passwd"), [str(root)])


def test_security_primitives():
    hashed = hash_password("SuperSecret123!")
    assert verify_password("SuperSecret123!", hashed)
    assert not verify_password("WrongPass", hashed)

    dovecot_hash = hash_dovecot_sha512_crypt("MailSecret99!")
    assert dovecot_hash.startswith("{SHA512-CRYPT}$6$")

    cipher = secret_manager.encrypt("my-cloudflare-token")
    assert secret_manager.decrypt(cipher) == "my-cloudflare-token"
    assert secret_manager.mask(cipher) == "********"

    totp_sec = generate_totp_secret()
    assert len(totp_sec) >= 16

    plain, hashed_codes = generate_recovery_codes(4)
    ok, remaining = verify_recovery_code(plain[0], hashed_codes)
    assert ok is True
    assert len(remaining) == 3


def test_distro_and_mail_drivers():
    ubuntu = UbuntuDriver()
    debian = DebianDriver()
    assert ubuntu.build_service_control_cmd("nginx", "reload") == ["/bin/systemctl", "reload", "nginx"]
    assert debian.build_install_package_cmd(["nginx"]) == ["/usr/bin/apt-get", "install", "-y", "-q", "nginx"]

    priv, pub = generate_dkim_keypair(2048)
    assert "BEGIN PRIVATE KEY" in priv
    assert pub.startswith("v=DKIM1; h=sha256; k=rsa; p=")

    routes = [OutboundRouteConfig(domain="example.com", mode="relay", relay_host="smtp.sendgrid.net", relay_port=587, relay_username="apikey", relay_password="secret")]
    assert "@example.com [smtp.sendgrid.net]:587" in OutboundMailRouter.render_sender_relay_maps(routes)
    assert "[smtp.sendgrid.net]:587 apikey:secret" in OutboundMailRouter.render_sasl_passwd(routes)
