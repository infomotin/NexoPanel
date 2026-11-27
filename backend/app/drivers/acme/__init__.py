"""ACMEv2 SSL/TLS drivers including pluggable DnsChallengeProvider for wildcard DNS-01."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx


class DnsProviderError(RuntimeError):
    """Granular error surfaced from DNS API providers during DNS-01 challenge."""

    def __init__(self, provider: str, code: str | int, message: str) -> None:
        self.provider = provider
        self.code = code
        self.message = message
        super().__init__(f"[{provider}] ({code}) {message}")


class DnsChallengeProvider(ABC):
    """Pluggable interface for DNS-01 ACME TXT record injection and cleanup."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def create_txt_record(self, domain: str, record_name: str, value: str) -> str:
        """Create _acme-challenge TXT record and return provider record ID."""

    @abstractmethod
    async def delete_txt_record(self, domain: str, record_id: str) -> None:
        """Remove _acme-challenge TXT record after ACME validation."""


class CloudflareDnsProvider(DnsChallengeProvider):
    """Cloudflare DNS v4 API implementation."""

    API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, api_token: str) -> None:
        self._token = api_token

    @property
    def provider_name(self) -> str:
        return "cloudflare"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _get_zone_id(self, client: httpx.AsyncClient, domain: str) -> str:
        root_domain = ".".join(domain.lstrip("*.").split(".")[-2:])
        resp = await client.get(f"{self.API_BASE}/zones", params={"name": root_domain}, headers=self._headers())
        data: dict[str, Any] = resp.json()
        if not resp.is_success or not data.get("success"):
            errs = data.get("errors", [{}])
            raise DnsProviderError("cloudflare", errs[0].get("code", resp.status_code), errs[0].get("message", resp.text))
        results = data.get("result", [])
        if not results:
            raise DnsProviderError("cloudflare", "ZONE_NOT_FOUND", f"No Cloudflare zone found for {root_domain}")
        return results[0]["id"]

    async def create_txt_record(self, domain: str, record_name: str, value: str) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            zone_id = await self._get_zone_id(client, domain)
            resp = await client.post(
                f"{self.API_BASE}/zones/{zone_id}/dns_records",
                headers=self._headers(),
                json={"type": "TXT", "name": record_name, "content": value, "ttl": 120},
            )
            data = resp.json()
            if not resp.is_success or not data.get("success"):
                errs = data.get("errors", [{}])
                raise DnsProviderError("cloudflare", errs[0].get("code", resp.status_code), errs[0].get("message", resp.text))
            return f"{zone_id}:{data['result']['id']}"

    async def delete_txt_record(self, domain: str, record_id: str) -> None:
        zone_id, rec_id = record_id.split(":", 1)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self.API_BASE}/zones/{zone_id}/dns_records/{rec_id}",
                headers=self._headers(),
            )
            if not resp.is_success:
                raise DnsProviderError("cloudflare", resp.status_code, resp.text)


class DigitalOceanDnsProvider(DnsChallengeProvider):
    """DigitalOcean DNS v2 API implementation."""

    API_BASE = "https://api.digitalocean.com/v2"

    def __init__(self, api_token: str) -> None:
        self._token = api_token

    @property
    def provider_name(self) -> str:
        return "digitalocean"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def create_txt_record(self, domain: str, record_name: str, value: str) -> str:
        root_domain = ".".join(domain.lstrip("*.").split(".")[-2:])
        relative_name = record_name.removesuffix(f".{root_domain}")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self.API_BASE}/domains/{root_domain}/records",
                headers=self._headers(),
                json={"type": "TXT", "name": relative_name, "data": value, "ttl": 120},
            )
            data = resp.json()
            if not resp.is_success:
                raise DnsProviderError("digitalocean", data.get("id", resp.status_code), data.get("message", resp.text))
            return f"{root_domain}:{data['domain_record']['id']}"

    async def delete_txt_record(self, domain: str, record_id: str) -> None:
        root_domain, rec_id = record_id.split(":", 1)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self.API_BASE}/domains/{root_domain}/records/{rec_id}",
                headers=self._headers(),
            )
            if not resp.is_success:
                raise DnsProviderError("digitalocean", resp.status_code, resp.text)


def build_dns_challenge_provider(provider_type: str, credentials: dict[str, str]) -> DnsChallengeProvider:
    if provider_type == "cloudflare":
        return CloudflareDnsProvider(api_token=credentials["api_token"])
    if provider_type == "digitalocean":
        return DigitalOceanDnsProvider(api_token=credentials["api_token"])
    raise ValueError(f"Unsupported DNS challenge provider: {provider_type!r}")
