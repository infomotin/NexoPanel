"""Tests for completed backup restore, cron execution and app DB provisioning."""
from __future__ import annotations

import io
import tarfile

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.backups import UnsafeBackupArchive, _safe_extract


async def test_database_backup_and_restore(client: AsyncClient, admin_headers: dict[str, str]):
    run = await client.post(
        "/api/v1/backups/run",
        headers=admin_headers,
        json={"target_type": "database", "target_identifier": "app_prod"},
    )
    assert run.status_code == 201
    assert run.json()["size_bytes"] > 0
    manifest_id = run.json()["id"]

    restore = await client.post(
        f"/api/v1/backups/manifests/{manifest_id}/restore", headers=admin_headers
    )
    assert restore.status_code == 200
    assert "restored" in restore.json()["detail"].lower()


async def test_website_backup_restore_roundtrip(client: AsyncClient, admin_headers: dict[str, str]):
    site_dir = settings.WEB_ROOT_BASE / "roundtrip.example.com"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text("original", encoding="utf-8")

    run = await client.post(
        "/api/v1/backups/run",
        headers=admin_headers,
        json={"target_type": "website", "target_identifier": "roundtrip.example.com"},
    )
    assert run.status_code == 201

    (site_dir / "index.html").write_text("modified", encoding="utf-8")
    restore = await client.post(
        f"/api/v1/backups/manifests/{run.json()['id']}/restore", headers=admin_headers
    )
    assert restore.status_code == 200
    assert (site_dir / "index.html").read_text(encoding="utf-8") == "original"


def _write_tar(path, member_name: str) -> None:
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(member_name)
        data = b"escape"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))


def test_unsafe_archive_member_is_rejected(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    _write_tar(archive, "../escape.txt")
    with pytest.raises(UnsafeBackupArchive):
        _safe_extract(archive, tmp_path / "dest")


async def test_cron_backup_job_records_manifest(client: AsyncClient, admin_headers: dict[str, str]):
    site_dir = settings.WEB_ROOT_BASE / "cron.example.com"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text("cron", encoding="utf-8")

    create = await client.post(
        "/api/v1/cron",
        headers=admin_headers,
        json={
            "name": "Nightly Backup",
            "job_type": "backup_site",
            "schedule": "0 2 * * *",
            "command_or_target": "cron.example.com",
        },
    )
    assert create.status_code == 201
    cron_id = create.json()["id"]

    run = await client.post(f"/api/v1/cron/{cron_id}/run", headers=admin_headers)
    assert run.status_code == 200
    assert run.json()["status"] == "success"

    manifests = (await client.get("/api/v1/backups/manifests", headers=admin_headers)).json()
    assert any(
        m["target_type"] == "website" and m["target_identifier"] == "cron.example.com"
        for m in manifests
    )


async def test_app_deploy_persists_revealable_database_password(
    client: AsyncClient, admin_headers: dict[str, str]
):
    deploy = await client.post(
        "/api/v1/apps/deploy",
        headers=admin_headers,
        json={"app_slug": "wordpress", "domain": "persist.example.com"},
    )
    assert deploy.status_code == 201
    db_name = deploy.json()["db_name"]

    databases = (await client.get("/api/v1/databases", headers=admin_headers)).json()
    record = next(d for d in databases if d["db_name"] == db_name)
    assert record["has_password"] is True

    reveal = await client.get(
        f"/api/v1/databases/{record['id']}/password/reveal", headers=admin_headers
    )
    assert reveal.status_code == 200
    assert reveal.json()["password"]


async def test_firewall_advanced_controls(client: AsyncClient, admin_headers: dict[str, str]):
    # 1. Status
    status_res = await client.get("/api/v1/firewall/status", headers=admin_headers)
    assert status_res.status_code == 200
    assert "active" in status_res.json()
    assert "default_incoming" in status_res.json()

    # 2. Default policy & reload
    pol_res = await client.post(
        "/api/v1/firewall/default-policy",
        headers=admin_headers,
        json={"direction": "incoming", "policy": "deny"},
    )
    assert pol_res.status_code == 200

    reload_res = await client.post("/api/v1/firewall/reload", headers=admin_headers)
    assert reload_res.status_code == 200

    # 3. Listening ports
    ports_res = await client.get("/api/v1/firewall/listening-ports", headers=admin_headers)
    assert ports_res.status_code == 200
    ports = ports_res.json()
    assert isinstance(ports, list)
    assert any(p["port"] == "22" for p in ports)

    # 4. Services list & toggle
    svc_res = await client.get("/api/v1/firewall/services", headers=admin_headers)
    assert svc_res.status_code == 200
    services = svc_res.json()
    assert any(s["key"] == "web_https" for s in services)

    toggle_svc = await client.post(
        "/api/v1/firewall/services/toggle",
        headers=admin_headers,
        json={"service_key": "web_https", "enable": True, "source_ip": "any"},
    )
    assert toggle_svc.status_code == 200
    assert toggle_svc.json()["enabled"] is True

    # 5. IP rules (whole IP block with port='any' and CIDR)
    ip_rule = await client.post(
        "/api/v1/firewall/rules",
        headers=admin_headers,
        json={"port": "any", "protocol": "any", "action": "deny", "source_ip": "198.51.100.0/24", "comment": "Block subnet"},
    )
    assert ip_rule.status_code == 201
    rule_id = ip_rule.json()["id"]

    del_rule = await client.delete(f"/api/v1/firewall/rules/{rule_id}", headers=admin_headers)
    assert del_rule.status_code == 200

    # 6. Country blocks
    cat_res = await client.get("/api/v1/firewall/countries/catalog", headers=admin_headers)
    assert cat_res.status_code == 200
    assert any(c["code"] == "RU" for c in cat_res.json())

    cb_res = await client.post(
        "/api/v1/firewall/countries",
        headers=admin_headers,
        json={"country_code": "RU", "country_name": "Russia", "action": "deny"},
    )
    assert cb_res.status_code == 201
    block_id = cb_res.json()["id"]

    blocks_list = await client.get("/api/v1/firewall/countries", headers=admin_headers)
    assert blocks_list.status_code == 200
    assert any(b["country_code"] == "RU" for b in blocks_list.json())

    del_cb = await client.delete(f"/api/v1/firewall/countries/{block_id}", headers=admin_headers)
    assert del_cb.status_code == 200

    # 7. Fail2Ban
    f2b_res = await client.get("/api/v1/firewall/fail2ban?jail=sshd", headers=admin_headers)
    assert f2b_res.status_code == 200
    assert "currently_banned" in f2b_res.json()

    ban_res = await client.post(
        "/api/v1/firewall/fail2ban/ban",
        headers=admin_headers,
        json={"jail": "sshd", "ip": "203.0.113.199"},
    )
    assert ban_res.status_code == 200

    unban_res = await client.post(
        "/api/v1/firewall/fail2ban/unban",
        headers=admin_headers,
        json={"jail": "sshd", "ip": "203.0.113.199"},
    )
    assert unban_res.status_code == 200

    # 8. Live logs
    logs_res = await client.get("/api/v1/firewall/logs?lines=20", headers=admin_headers)
    assert logs_res.status_code == 200
    assert isinstance(logs_res.json(), list)

