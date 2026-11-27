"""Distro Strategy Pattern: BaseDistroDriver -> DebianFamilyDriver -> UbuntuDriver / DebianDriver."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DistroPaths:
    nginx_sites_available: str
    nginx_sites_enabled: str
    nginx_conf_test_bin: str
    bind_zones_dir: str
    bind_named_conf_local: str
    bind_checkzone_bin: str
    postfix_main_cf: str
    postfix_virtual_mailbox_domains: str
    postfix_virtual_mailbox_maps: str
    postfix_virtual_alias_maps: str
    postfix_sender_relay_maps: str
    postfix_sasl_passwd: str
    dovecot_passwd_file: str
    opendkim_keys_dir: str
    www_user: str
    www_group: str
    mail_user: str
    mail_group: str


class BaseDistroDriver(ABC):
    """Abstract base class isolating OS-specific commands, paths, and identities."""

    @property
    @abstractmethod
    def family(self) -> str: ...

    @property
    @abstractmethod
    def distro_id(self) -> str: ...

    @property
    @abstractmethod
    def paths(self) -> DistroPaths: ...

    @abstractmethod
    def service_unit_name(self, service: str) -> str: ...

    @abstractmethod
    def build_install_package_cmd(self, packages: list[str]) -> list[str]: ...

    @abstractmethod
    def build_remove_package_cmd(self, packages: list[str]) -> list[str]: ...

    @abstractmethod
    def build_upgrade_package_cmd(self, packages: list[str] | None = None) -> list[str]: ...

    @abstractmethod
    def build_service_control_cmd(self, service: str, action: str) -> list[str]: ...


class DebianFamilyDriver(BaseDistroDriver):
    """Shared implementation for Debian/Ubuntu (apt-get + systemd)."""

    _SERVICE_MAP: dict[str, str] = {
        "nginx": "nginx",
        "postfix": "postfix",
        "dovecot": "dovecot",
        "opendkim": "opendkim",
        "rspamd": "rspamd",
        "mariadb": "mariadb",
        "mysql": "mariadb",
        "postgresql": "postgresql",
        "bind9": "named",
        "named": "named",
        "php8.2-fpm": "php8.2-fpm",
        "php8.3-fpm": "php8.3-fpm",
        "nexopanel": "nexopanel",
    }

    @property
    def family(self) -> str:
        return "debian"

    @property
    def paths(self) -> DistroPaths:
        return DistroPaths(
            nginx_sites_available="/etc/nginx/sites-available",
            nginx_sites_enabled="/etc/nginx/sites-enabled",
            nginx_conf_test_bin="/usr/sbin/nginx",
            bind_zones_dir="/etc/bind/zones",
            bind_named_conf_local="/etc/bind/named.conf.local",
            bind_checkzone_bin="/usr/sbin/named-checkzone",
            postfix_main_cf="/etc/postfix/main.cf",
            postfix_virtual_mailbox_domains="/etc/postfix/virtual_mailbox_domains",
            postfix_virtual_mailbox_maps="/etc/postfix/virtual_mailbox_maps",
            postfix_virtual_alias_maps="/etc/postfix/virtual_alias_maps",
            postfix_sender_relay_maps="/etc/postfix/sender_dependent_relayhost_maps",
            postfix_sasl_passwd="/etc/postfix/sasl_passwd",
            dovecot_passwd_file="/etc/dovecot/users",
            opendkim_keys_dir="/etc/opendkim/keys",
            www_user="www-data",
            www_group="www-data",
            mail_user="vmail",
            mail_group="vmail",
        )

    def service_unit_name(self, service: str) -> str:
        if service not in self._SERVICE_MAP:
            raise ValueError(f"Unsupported or disallowed service name: {service!r}")
        return self._SERVICE_MAP[service]

    def build_install_package_cmd(self, packages: list[str]) -> list[str]:
        return ["/usr/bin/apt-get", "install", "-y", "-q", *packages]

    def build_remove_package_cmd(self, packages: list[str]) -> list[str]:
        return ["/usr/bin/apt-get", "remove", "-y", "-q", *packages]

    def build_upgrade_package_cmd(self, packages: list[str] | None = None) -> list[str]:
        if packages:
            return ["/usr/bin/apt-get", "install", "--only-upgrade", "-y", "-q", *packages]
        return ["/usr/bin/apt-get", "upgrade", "-y", "-q"]

    def build_service_control_cmd(self, service: str, action: str) -> list[str]:
        if action not in {"start", "stop", "restart", "reload", "status", "is-active"}:
            raise ValueError(f"Invalid systemd action: {action!r}")
        unit = self.service_unit_name(service)
        return ["/bin/systemctl", action, unit]


class UbuntuDriver(DebianFamilyDriver):
    @property
    def distro_id(self) -> str:
        return "ubuntu"


class DebianDriver(DebianFamilyDriver):
    @property
    def distro_id(self) -> str:
        return "debian"


def get_distro_driver(distro_id: str | None = None) -> BaseDistroDriver:
    if distro_id == "debian":
        return DebianDriver()
    return UbuntuDriver()
