"""Tests for expanded Panel Settings, SMTP tests, S3 tests, and Maintenance controls."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_settings_list_and_map(client: AsyncClient, admin_headers: dict[str, str]):
    # List settings
    res = await client.get("/api/v1/system/settings", headers=admin_headers)
    assert res.status_code == 200
    settings_list = res.json()
    assert isinstance(settings_list, list)
    assert len(settings_list) >= 10
    keys = {s["key"] for s in settings_list}
    assert "panel_title" in keys
    assert "admin_email" in keys

    # Settings map
    map_res = await client.get("/api/v1/system/settings/map", headers=admin_headers)
    assert map_res.status_code == 200
    s_map = map_res.json()
    assert isinstance(s_map, dict)
    assert "panel_title" in s_map
    assert "session_timeout_minutes" in s_map


@pytest.mark.asyncio
async def test_settings_batch_and_single_update(client: AsyncClient, admin_headers: dict[str, str]):
    # Single update
    put_res = await client.put(
        "/api/v1/system/settings/panel_title",
        headers=admin_headers,
        json={"value": "Custom Brand Panel"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["updated"] is True

    # Batch update
    batch_res = await client.post(
        "/api/v1/system/settings/batch",
        headers=admin_headers,
        json={
            "settings": {
                "panel_title": "Enterprise NexoPanel",
                "admin_email": "ops@example.com",
                "timezone": "America/New_York",
                "force_https": "true",
            }
        },
    )
    assert batch_res.status_code == 200
    assert batch_res.json()["ok"] is True
    assert batch_res.json()["updated_count"] == 4

    # Verify updated values
    map_res = await client.get("/api/v1/system/settings/map", headers=admin_headers)
    assert map_res.status_code == 200
    s_map = map_res.json()
    assert s_map["panel_title"] == "Enterprise NexoPanel"
    assert s_map["admin_email"] == "ops@example.com"
    assert s_map["timezone"] == "America/New_York"
    assert s_map["force_https"] == "true"


@pytest.mark.asyncio
async def test_settings_tests_and_maintenance(client: AsyncClient, admin_headers: dict[str, str]):
    # Test SMTP
    smtp_res = await client.post(
        "/api/v1/system/settings/test-smtp",
        headers=admin_headers,
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_encryption": "tls",
            "smtp_user": "test_user",
            "smtp_password": "test_password",
            "smtp_from_email": "alerts@example.com",
        },
    )
    assert smtp_res.status_code == 200
    assert smtp_res.json()["ok"] is True

    # Test S3
    s3_res = await client.post(
        "/api/v1/system/settings/test-s3",
        headers=admin_headers,
        json={
            "s3_bucket": "my-backup-bucket",
            "s3_region": "us-east-1",
            "s3_access_key": "AKIAIOSFODNN7EXAMPLE",
            "s3_secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        },
    )
    assert s3_res.status_code == 200
    assert s3_res.json()["ok"] is True

    # Clean cache
    clean_res = await client.post("/api/v1/system/settings/clean-cache", headers=admin_headers)
    assert clean_res.status_code == 200
    assert clean_res.json()["ok"] is True

    # Restart service
    restart_res = await client.post(
        "/api/v1/system/maintenance/restart-service",
        headers=admin_headers,
        json={"service": "nginx", "action": "reload"},
    )
    assert restart_res.status_code == 200
    assert restart_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_settings_export_import_reset(client: AsyncClient, admin_headers: dict[str, str]):
    # Export
    exp_res = await client.get("/api/v1/system/settings/export", headers=admin_headers)
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert "settings" in exp_data
    assert exp_data["version"] == "1.0"

    # Import
    imp_res = await client.post(
        "/api/v1/system/settings/import",
        headers=admin_headers,
        json={"settings": {"panel_title": "Imported Panel", "timezone": "Asia/Tokyo"}},
    )
    assert imp_res.status_code == 200
    assert imp_res.json()["ok"] is True

    # Verify import
    map_res = await client.get("/api/v1/system/settings/map", headers=admin_headers)
    assert map_res.json()["panel_title"] == "Imported Panel"
    assert map_res.json()["timezone"] == "Asia/Tokyo"

    # Reset defaults
    reset_res = await client.post("/api/v1/system/settings/reset-defaults", headers=admin_headers)
    assert reset_res.status_code == 200
    assert reset_res.json()["ok"] is True

    # Verify defaults
    map_def = await client.get("/api/v1/system/settings/map", headers=admin_headers)
    assert map_def.json()["panel_title"] == "NexoPanel"
    assert map_def.json()["timezone"] == "UTC"
