"""WebServerProvider abstraction and NginxProvider implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.drivers.distro import BaseDistroDriver

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


@dataclass
class VhostConfig:
    domain: str
    aliases: list[str]
    document_root: str
    runtime_type: str = "static"  # static | php | proxy
    php_version: str | None = None
    proxy_upstream: str | None = None
    custom_directives: str = ""
    ssl_enabled: bool = False
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    force_https: bool = False


class WebServerProvider(ABC):
    """Abstract interface for web server vhost generation and validation."""

    @abstractmethod
    def render_vhost(self, config: VhostConfig) -> str: ...

    @abstractmethod
    def vhost_config_path(self, domain: str) -> str: ...

    @abstractmethod
    def vhost_enabled_path(self, domain: str) -> str: ...

    @abstractmethod
    def test_config_command(self) -> list[str]: ...

    @abstractmethod
    def reload_command(self) -> list[str]: ...


class NginxProvider(WebServerProvider):
    """Concrete Nginx virtual host provider."""

    def __init__(self, distro: BaseDistroDriver) -> None:
        self._distro = distro
        self._jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(disabled_extensions=("j2",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_vhost(self, config: VhostConfig) -> str:
        template = self._jinja.get_template("nginx_vhost.conf.j2")
        return template.render(
            domain=config.domain,
            server_names=" ".join([config.domain, *config.aliases]),
            document_root=config.document_root,
            runtime_type=config.runtime_type,
            php_version=config.php_version or "8.2",
            proxy_upstream=config.proxy_upstream,
            custom_directives=config.custom_directives,
            ssl_enabled=config.ssl_enabled,
            ssl_cert_path=config.ssl_cert_path,
            ssl_key_path=config.ssl_key_path,
            force_https=config.force_https,
        )

    def vhost_config_path(self, domain: str) -> str:
        return f"{self._distro.paths.nginx_sites_available}/{domain}.conf"

    def vhost_enabled_path(self, domain: str) -> str:
        return f"{self._distro.paths.nginx_sites_enabled}/{domain}.conf"

    def test_config_command(self) -> list[str]:
        return [self._distro.paths.nginx_conf_test_bin, "-t"]

    def reload_command(self) -> list[str]:
        return self._distro.build_service_control_cmd("nginx", "reload")
