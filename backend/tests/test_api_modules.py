"""End-to-end API tests covering Auth, RBAC, Websites, DNS, Mail, SSL, Files, Apps, Backups & Audit."""
from __future__ import annotations

from httpx import AsyncClient


async def test_health_and_auth_flow(client: AsyncClient, admin_headers: dict[str, str]):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


async def test_rbac_enforcement_denies_unprivileged_user(client: AsyncClient, admin_headers: dict[str, str]):
    roles = (await client.get("/api/v1/rbac/roles", headers=admin_headers)).json()
    auditor = next(r for r in roles if r["name"] == "Auditor")

    create_u = await client.post(
        "/api/v1/rbac/users",
        headers=admin_headers,
        json={"username": "auditor1", "email": "auditor1@example.com", "password": "Password123!", "role_id": auditor["id"]},
    )
    assert create_u.status_code == 201

    login_res = await client.post("/api/v1/auth/login", json={"username": "auditor1", "password": "Password123!"})
    auditor_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Auditor can read websites but cannot create them
    assert (await client.get("/api/v1/sites", headers=auditor_headers)).status_code == 200
    deny = await client.post(
        "/api/v1/sites",
        headers=auditor_headers,
        json={"domain": "blocked.example.com", "runtime_type": "static"},
    )
    assert deny.status_code == 403


async def test_websites_subdomains_and_apps(client: AsyncClient, admin_headers: dict[str, str]):
    site_res = await client.post(
        "/api/v1/sites",
        headers=admin_headers,
        json={"domain": "example.com", "runtime_type": "php", "php_version": "8.2"},
    )
    assert site_res.status_code == 201
    site_id = site_res.json()["id"]

    sub_res = await client.post(
        "/api/v1/sites/subdomains",
        headers=admin_headers,
        json={"website_id": site_id, "prefix": "api", "runtime_type": "proxy", "proxy_upstream": "http://127.0.0.1:4000"},
    )
    assert sub_res.status_code == 201
    assert sub_res.json()["fqdn"] == "api.example.com"

    app_res = await client.post(
        "/api/v1/apps/deploy",
        headers=admin_headers,
        json={"app_slug": "wordpress", "domain": "blog.example.com"},
    )
    assert app_res.status_code == 201
    assert app_res.json()["db_name"].startswith("np_")


async def test_dns_mail_ssl_and_backups(client: AsyncClient, admin_headers: dict[str, str]):
    # DNS (Zones, Records Edit, Providers, Pull & Logs)
    zone = await client.post("/api/v1/dns/zones", headers=admin_headers, json={"domain": "zone.example.com"})
    assert zone.status_code == 201
    zone_id = zone.json()["id"]
    rec = await client.post(
        f"/api/v1/dns/zones/{zone_id}/records",
        headers=admin_headers,
        json={"name": "www", "record_type": "A", "value": "192.0.2.10", "ttl": 300},
    )
    assert rec.status_code == 201
    rec_id = rec.json()["id"]
    upd = await client.put(
        f"/api/v1/dns/records/{rec_id}",
        headers=admin_headers,
        json={"value": "192.0.2.20", "ttl": 600},
    )
    assert upd.status_code == 200
    assert upd.json()["value"] == "192.0.2.20"

    zones_list = (await client.get("/api/v1/dns/zones", headers=admin_headers)).json()
    assert any(z["domain"] == "zone.example.com" and z["record_count"] >= 2 for z in zones_list)

    prov = await client.post(
        "/api/v1/dns/providers",
        headers=admin_headers,
        json={"name": "CF Prod", "provider_type": "cloudflare", "api_token": "cf-secret-token-123"},
    )
    assert prov.status_code == 201
    prov_id = prov.json()["id"]
    assert len((await client.get("/api/v1/dns/providers", headers=admin_headers)).json()) >= 2
    assert (await client.post("/api/v1/dns/zones/pull", headers=admin_headers)).status_code == 200
    assert len((await client.get("/api/v1/dns/logs", headers=admin_headers)).json()) >= 1
    assert (await client.delete(f"/api/v1/dns/providers/{prov_id}", headers=admin_headers)).status_code == 200

    # Mail
    status = await client.get("/api/v1/mail/status", headers=admin_headers)
    assert status.status_code == 200
    assert "postfix" in status.json()["services"]

    md = await client.post("/api/v1/mail/domains", headers=admin_headers, json={"domain": "mail.example.com"})
    assert md.status_code == 201
    md_id = md.json()["id"]
    mbox = await client.post(
        "/api/v1/mail/mailboxes",
        headers=admin_headers,
        json={"mail_domain_id": md_id, "local_part": "hello", "password": "MailPassword123!"},
    )
    assert mbox.status_code == 201
    mbox_id = mbox.json()["id"]

    updated = await client.put(
        f"/api/v1/mail/mailboxes/{mbox_id}",
        headers=admin_headers,
        json={"quota_mb": 2048, "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["quota_mb"] == 2048
    assert updated.json()["is_active"] is False

    alias = await client.post(
        "/api/v1/mail/aliases",
        headers=admin_headers,
        json={
            "mail_domain_id": md_id,
            "source_email": "sales@mail.example.com",
            "destination_email": "hello@mail.example.com",
        },
    )
    assert alias.status_code == 201
    assert (await client.delete(f"/api/v1/mail/aliases/{alias.json()['id']}", headers=admin_headers)).status_code == 200

    readiness = await client.get(f"/api/v1/mail/domains/{md_id}/dns-readiness", headers=admin_headers)
    assert readiness.status_code == 200
    assert len(readiness.json()["required_records"]) == 5
    assert readiness.json()["live_checks_enabled"] is False

    # Server config & services
    cfg = await client.get("/api/v1/mail/config", headers=admin_headers)
    assert cfg.status_code == 200
    assert cfg.json()["max_message_size_mb"] >= 5

    cfg_up = await client.put(
        "/api/v1/mail/config",
        headers=admin_headers,
        json={"max_message_size_mb": 50, "tls_security_level": "may"},
    )
    assert cfg_up.status_code == 200

    svc = await client.post("/api/v1/mail/services/postfix/restart", headers=admin_headers)
    assert svc.status_code == 200
    assert svc.json()["ok"] is True

    # Client config & mobileconfig
    c_conf = await client.get("/api/v1/mail/client-config?email=hello@mail.example.com", headers=admin_headers)
    assert c_conf.status_code == 200
    assert c_conf.json()["protocols"]["imap"]["port_ssl"] == 993

    m_conf = await client.get("/api/v1/mail/client-config/mobileconfig?email=hello@mail.example.com", headers=admin_headers)
    assert m_conf.status_code == 200
    assert "com.apple.mail.managed" in m_conf.text

    # Test email
    test_mail = await client.post(
        "/api/v1/mail/test-email",
        headers=admin_headers,
        json={"sender": "hello@mail.example.com", "recipient": "recipient@example.org", "subject": "Test", "body": "Body"},
    )
    assert test_mail.status_code == 200

    # Sync DNS
    sync_res = await client.post(f"/api/v1/mail/domains/{md_id}/sync-dns", headers=admin_headers)
    assert sync_res.status_code == 200

    # Queue management
    q_req = await client.post("/api/v1/mail/queue/requeue?queue_id=ALL", headers=admin_headers)
    assert q_req.status_code == 200

    assert (await client.delete(f"/api/v1/mail/domains/{md_id}", headers=admin_headers)).status_code == 200

    # SSL HTTP-01 (mock executor)
    ssl_res = await client.post(
        "/api/v1/ssl/issue",
        headers=admin_headers,
        json={"domain": "zone.example.com", "challenge_type": "http-01"},
    )
    assert ssl_res.status_code == 201

    # Backups
    bkp = await client.post(
        "/api/v1/backups/run",
        headers=admin_headers,
        json={"target_type": "website", "target_identifier": "example.com"},
    )
    assert bkp.status_code == 201
    assert bkp.json()["size_bytes"] > 0

    # Audit log recorded mutating actions
    audits = await client.get("/api/v1/system/audit-logs", headers=admin_headers)
    assert audits.status_code == 200
    assert len(audits.json()) >= 5


async def test_firewall_cron_processes_docker_and_trash(client: AsyncClient, admin_headers: dict[str, str]):
    # Firewall
    fw = await client.post(
        "/api/v1/firewall/rules",
        headers=admin_headers,
        json={"port": "443", "protocol": "tcp", "action": "allow", "source_ip": "any", "comment": "HTTPS"},
    )
    assert fw.status_code == 201
    assert len((await client.get("/api/v1/firewall/rules", headers=admin_headers)).json()) == 1

    # Cron
    cron = await client.post(
        "/api/v1/cron",
        headers=admin_headers,
        json={"name": "Rotate Logs", "job_type": "log_rotate", "schedule": "0 3 * * *", "command_or_target": "nginx"},
    )
    assert cron.status_code == 201
    cron_id = cron.json()["id"]
    run_res = await client.post(f"/api/v1/cron/{cron_id}/run", headers=admin_headers)
    assert run_res.status_code == 200
    assert run_res.json()["status"] == "success"

    # Processes
    procs = await client.get("/api/v1/processes?limit=10", headers=admin_headers)
    assert procs.status_code == 200
    assert len(procs.json()) > 0

    # Docker
    dkr = await client.get("/api/v1/docker/containers", headers=admin_headers)
    assert dkr.status_code == 200

    # Website rewrite presets
    presets = await client.get("/api/v1/sites/rewrite-presets", headers=admin_headers)
    assert presets.status_code == 200
    assert "wordpress" in presets.json()

    # FTP Account Full aaPanel Workflow & Security Validation
    roots = (await client.get("/api/v1/files/roots", headers=admin_headers)).json()["roots"]

    # Security: reject invalid username & critical directory / path traversal
    bad_user = await client.post(
        "/api/v1/ftp",
        headers=admin_headers,
        json={"username": "bad user!", "password": "FtpPassword123!", "home_directory": roots[0]},
    )
    assert bad_user.status_code == 422

    bad_path = await client.post(
        "/api/v1/ftp",
        headers=admin_headers,
        json={"username": "ftp_sec1", "password": "FtpPassword123!", "home_directory": "/etc"},
    )
    assert bad_path.status_code == 403

    ftp_res = await client.post(
        "/api/v1/ftp",
        headers=admin_headers,
        json={"username": "ftp_user1", "password": "FtpPassword123!", "home_directory": roots[0], "quota_mb": 512, "note": "Initial"},
    )
    assert ftp_res.status_code == 201
    ftp_id = ftp_res.json()["id"]
    assert ftp_res.json()["username"] == "ftp_user1"

    # Reveal & Rotate password
    reveal = await client.get(f"/api/v1/ftp/{ftp_id}/password/reveal", headers=admin_headers)
    assert reveal.status_code == 200
    assert reveal.json()["password"] == "FtpPassword123!"

    rot = await client.put(f"/api/v1/ftp/{ftp_id}/password", headers=admin_headers, json={"password": "NewStrongPass99!"})
    assert rot.status_code == 200

    # Set Path (set_user_home) & Note & Quota & Status Toggle
    assert (await client.put(f"/api/v1/ftp/{ftp_id}/home", headers=admin_headers, json={"home_directory": f"{roots[0]}/site_sub", "migrate": True})).status_code == 200
    assert (await client.put(f"/api/v1/ftp/{ftp_id}/note", headers=admin_headers, json={"note": "Updated Note"})).status_code == 200
    assert (await client.put(f"/api/v1/ftp/{ftp_id}/quota", headers=admin_headers, json={"quota_mb": 1024})).status_code == 200
    assert (await client.post(f"/api/v1/ftp/{ftp_id}/toggle", headers=admin_headers)).json()["is_active"] is False

    # Logs, Port, Firewall Sync, Security Hardening, Scan & Whitelist
    assert (await client.get(f"/api/v1/ftp/{ftp_id}/logs/login", headers=admin_headers)).status_code == 200
    assert (await client.get(f"/api/v1/ftp/{ftp_id}/logs/action", headers=admin_headers)).status_code == 200
    assert (await client.put("/api/v1/ftp/port", headers=admin_headers, json={"port": 2121})).status_code == 200
    assert (await client.put("/api/v1/ftp/port", headers=admin_headers, json={"port": 99999})).status_code == 422
    assert (await client.put("/api/v1/ftp/security", headers=admin_headers, json={"no_anonymous": True, "forbid_root": True})).status_code == 200
    assert (await client.post("/api/v1/ftp/log-analysis/scan", headers=admin_headers, json={"types": ["login_error", "area", "upload_shell", "anonymous"], "day": 30})).status_code == 200
    assert (await client.post("/api/v1/ftp/whitelist", headers=admin_headers, json={"ip": "invalid-ip"})).status_code == 422
    assert (await client.post("/api/v1/ftp/whitelist", headers=admin_headers, json={"ip": "203.0.113.10"})).status_code == 200
    assert "203.0.113.10" in (await client.get("/api/v1/ftp/whitelist", headers=admin_headers)).json()["ips"]
    assert (await client.delete("/api/v1/ftp/whitelist/203.0.113.10", headers=admin_headers)).status_code == 200

    # Batch Delete
    batch = await client.post("/api/v1/ftp/batch-delete", headers=admin_headers, json={"ids": [ftp_id]})
    assert batch.status_code == 200
    assert batch.json()["results"][0]["ok"] is True


async def test_packages_catalog_and_runtimes(client: AsyncClient, admin_headers: dict[str, str]):
    # 1. Curated package catalog
    catalog_res = await client.get("/api/v1/system/packages/catalog", headers=admin_headers)
    assert catalog_res.status_code == 200
    catalog = catalog_res.json()
    assert len(catalog) > 10
    slugs = [p["slug"] for p in catalog]
    assert "nginx" in slugs
    assert "php8.5" in slugs
    assert "php8.4" in slugs
    assert "mariadb" in slugs
    assert "pure-ftpd" in slugs

    # Filter by category
    php_res = await client.get("/api/v1/system/packages/catalog?category=PHP", headers=admin_headers)
    assert php_res.status_code == 200
    assert all(p["category"] == "PHP" for p in php_res.json())

    # 2. PHP runtime detection
    php_runtimes_res = await client.get("/api/v1/system/runtimes/php", headers=admin_headers)
    assert php_runtimes_res.status_code == 200
    runtimes = php_runtimes_res.json()
    assert any(r["version"] == "8.5" for r in runtimes)
    assert any(r["version"] == "8.4" for r in runtimes)
    assert any(r["version"] == "8.3" for r in runtimes)

    # 3. Curated service control
    svc_res = await client.post(
        "/api/v1/system/packages/curated/nginx/control",
        headers=admin_headers,
        json={"service": "nginx", "action": "restart"},
    )
    assert svc_res.status_code == 200
    assert svc_res.json()["ok"] is True

    # 4. Curated package install streaming
    install_res = await client.post(
        "/api/v1/system/packages/curated/nginx/install",
        headers=admin_headers,
    )
    assert install_res.status_code == 200
    assert "text/event-stream" in install_res.headers.get("content-type", "")

    # Curated package install streaming with cookie auth & dummy "Bearer null"
    login_resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPassword123!"})
    assert login_resp.status_code == 200
    access_cookie = login_resp.cookies.get("access_token")
    csrf_token = login_resp.json().get("csrf_token") or login_resp.cookies.get("nexopanel_csrf")
    install_cookie_res = await client.post(
        "/api/v1/system/packages/curated/redis/install",
        cookies={"access_token": access_cookie, "nexopanel_csrf": csrf_token},
        headers={"Authorization": "Bearer null", "X-CSRF-Token": csrf_token},
    )
    assert install_cookie_res.status_code == 200
    assert "text/event-stream" in install_cookie_res.headers.get("content-type", "")

    # Multi-token fallback: Stale Bearer token in header falls back seamlessly to valid access_token cookie
    stale_bearer_res = await client.post(
        "/api/v1/system/packages/curated/redis/install",
        cookies={"access_token": access_cookie, "nexopanel_csrf": csrf_token},
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.stale", "X-CSRF-Token": csrf_token},
    )
    assert stale_bearer_res.status_code == 200
    assert "text/event-stream" in stale_bearer_res.headers.get("content-type", "")

    # Multi-token fallback: URL query parameter ?token= fallback
    query_param_res = await client.post(
        f"/api/v1/system/packages/curated/redis/install?token={access_cookie}",
        headers={"Authorization": "Bearer expired_junk"},
    )
    assert query_param_res.status_code == 200
    assert "text/event-stream" in query_param_res.headers.get("content-type", "")

    # 5. Curated package uninstall streaming
    uninstall_res = await client.post(
        "/api/v1/system/packages/curated/nginx/uninstall",
        headers=admin_headers,
    )
    assert uninstall_res.status_code == 200
    assert "text/event-stream" in uninstall_res.headers.get("content-type", "")

    # 6. Update cache
    update_res = await client.post(
        "/api/v1/system/packages/update-cache",
        headers=admin_headers,
    )
    assert update_res.status_code == 200
    assert "text/event-stream" in update_res.headers.get("content-type", "")

    # 7. Global APT package search & info
    search_res = await client.get("/api/v1/system/packages/search?query=nginx", headers=admin_headers)
    assert search_res.status_code == 200
    assert "packages" in search_res.json()

    # 8. Python runtimes detection
    py_runtimes_res = await client.get("/api/v1/system/runtimes/python", headers=admin_headers)
    assert py_runtimes_res.status_code == 200
    py_runtimes = py_runtimes_res.json()
    assert any(r["version"] == "3.12" for r in py_runtimes)
    assert any(r["version"] == "3.13" for r in py_runtimes)

    # 9. PHP and Python security update endpoints
    php_sec_res = await client.post("/api/v1/system/packages/php/security-update", headers=admin_headers)
    assert php_sec_res.status_code == 200
    assert "text/event-stream" in php_sec_res.headers.get("content-type", "")

    py_sec_res = await client.post("/api/v1/system/packages/python/security-update", headers=admin_headers)
    assert py_sec_res.status_code == 200
    assert "text/event-stream" in py_sec_res.headers.get("content-type", "")

    # 10. Install from source endpoint
    src_res = await client.post(
        "/api/v1/system/packages/source/install",
        headers=admin_headers,
        json={
            "name": "redis-test",
            "source_type": "tarball",
            "url": "https://download.redis.io/redis-stable.tar.gz",
            "build_tool": "make",
            "install_command": "true",
        },
    )
    assert src_res.status_code == 200
    assert "text/event-stream" in src_res.headers.get("content-type", "")



async def test_dns_nameserver_setup_and_zone_health(client: AsyncClient, admin_headers: dict[str, str]):
    ns = await client.get("/api/v1/dns/nameservers", headers=admin_headers)
    assert ns.status_code == 200
    data = ns.json()
    for key in ("server_ip", "ns1", "ns2", "bind_status", "bind_healthy", "zone_count", "record_count"):
        assert key in data

    updated = await client.put(
        "/api/v1/dns/nameservers",
        headers=admin_headers,
        json={"public_ip": "203.0.113.10", "ns1": "ns1.example.com", "ns2": "ns2.example.com"},
    )
    assert updated.status_code == 200
    assert updated.json()["ns1"] == "ns1.example.com"

    bad = await client.put(
        "/api/v1/dns/nameservers",
        headers=admin_headers,
        json={"public_ip": "not-an-ip", "ns1": "ns1.example.com", "ns2": "ns2.example.com"},
    )
    assert bad.status_code == 422

    zone = await client.post(
        "/api/v1/dns/zones",
        headers=admin_headers,
        json={
            "domain": "health.example.com",
            "primary_ns": "ns1.example.com",
            "secondary_ns": "ns2.example.com",
        },
    )
    assert zone.status_code == 201
    zone_id = zone.json()["id"]

    # Test zone with email-formatted admin_email and trailing dot nameserver (alaqsamadrasah.com)
    zone2 = await client.post(
        "/api/v1/dns/zones",
        headers=admin_headers,
        json={
            "domain": "alaqsamadrasah.com",
            "primary_ns": "ns1.nexogiant.com.",
            "secondary_ns": "ns2.nexogiant.com",
            "admin_email": "hostmaster@localhost.localdomain",
        },
    )
    assert zone2.status_code == 201
    assert zone2.json()["domain"] == "alaqsamadrasah.com"

    zone_records = (await client.get(f"/api/v1/dns/zones/{zone_id}/records", headers=admin_headers)).json()
    assert len([r for r in zone_records if r["record_type"] == "NS"]) == 2
    await client.post(
        f"/api/v1/dns/zones/{zone_id}/records",
        headers=admin_headers,
        json={"name": "@", "record_type": "A", "value": "203.0.113.10", "ttl": 300},
    )

    check = await client.post(f"/api/v1/dns/zones/{zone_id}/check", headers=admin_headers)
    assert check.status_code == 200
    result = check.json()
    assert result["zone"] == "health.example.com"
    assert result["overall"] in {"pass", "warn", "fail"}
    assert {"pass", "warn", "fail"} == set(result["summary"].keys())
    ids = {c["id"] for c in result["checks"]}
    assert {"zone_file", "bind_service", "ns_records", "apex", "soa"} <= ids

    missing = await client.post("/api/v1/dns/zones/9999/check", headers=admin_headers)
    assert missing.status_code == 404


async def test_system_updates_and_remote_git_comparison(client: AsyncClient, admin_headers: dict[str, str]):
    from unittest.mock import patch
    from app.core.config import settings

    # 1. Test update check endpoint when disabled in test env
    res = await client.get("/api/v1/system/updates?force=true", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "update_available" in data
    assert data["enabled"] is False

    # 2. Test when enabled and installed / remote commits are different
    with patch.object(settings, "UPDATE_CHECK_ENABLED", True), \
         patch("app.services.updater._local_git_commit", return_value="1111111111111111111111111111111111111111"), \
         patch("app.services.updater._github_json") as mock_gh:
        mock_gh.side_effect = [
            ([{"sha": "2222222222222222222222222222222222222222", "commit": {"message": "feat: new feature", "author": {"name": "test"}}}], None),
            (None, None),  # releases
            ({"status": "ahead", "ahead_by": 5, "behind_by": 0}, None),  # compare
        ]
        diff_res = await client.get("/api/v1/system/updates?force=true", headers=admin_headers)
        assert diff_res.status_code == 200
        diff_data = diff_res.json()
        assert diff_data["update_available"] is True
        assert diff_data["current_commit"] == "1111111111111111111111111111111111111111"
        assert diff_data["latest_commit"] == "2222222222222222222222222222222222222222"
        assert diff_data["commits_behind"] == 5
        assert diff_data["enabled"] is True



async def test_update_status_endpoint(client: AsyncClient, admin_headers: dict[str, str]):
    res = await client.get("/api/v1/system/updates", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    for key in ("enabled", "repo_url", "current_version", "update_available", "checked_at"):
        assert key in data
    assert data["repo_url"].endswith("NexoPanel")


async def test_system_logs_catalog_read_and_drop_caches(client: AsyncClient, admin_headers: dict[str, str]):
    # 1. Catalog
    cat_res = await client.get("/api/v1/system/logs/catalog", headers=admin_headers)
    assert cat_res.status_code == 200
    catalog = cat_res.json()
    assert isinstance(catalog, list)
    target_ids = {item["id"] for item in catalog}
    assert {"syslog", "nginx_access", "nginx_error", "nexopanel"} <= target_ids

    # 2. Read log
    read_res = await client.get("/api/v1/system/logs/read?target=syslog&lines=50", headers=admin_headers)
    assert read_res.status_code == 200
    read_data = read_res.json()
    assert "entries" in read_data
    assert "lines" in read_data
    assert read_data["target"] == "syslog"

    # 3. Drop caches
    drop_res = await client.post("/api/v1/system/drop-caches", headers=admin_headers)
    assert drop_res.status_code == 200
    drop_data = drop_res.json()
    assert "ok" in drop_data
    assert "freed_mb" in drop_data
    assert "memory_used_percent" in drop_data


async def test_database_queries_active_and_summary(client: AsyncClient, admin_headers: dict[str, str]):
    # 1. Summary
    sum_res = await client.get("/api/v1/databases/queries/summary", headers=admin_headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert "total_active" in sum_data
    assert "mariadb_running" in sum_data

    # 2. Active queries for MariaDB
    act_res = await client.get("/api/v1/databases/queries/active?engine=mariadb", headers=admin_headers)
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["engine"] == "mariadb"
    assert "stats" in act_data
    assert "queries" in act_data

    # 3. Active queries for PostgreSQL
    pg_res = await client.get("/api/v1/databases/queries/active?engine=postgresql", headers=admin_headers)
    assert pg_res.status_code == 200
    assert pg_res.json()["engine"] == "postgresql"


async def test_domain_monitoring_overview_and_traffic(client: AsyncClient, admin_headers: dict[str, str]):
    # 1. Global traffic overview
    ov_res = await client.get("/api/v1/sites/monitoring/overview", headers=admin_headers)
    assert ov_res.status_code == 200
    ov_data = ov_res.json()
    assert "status_distribution" in ov_data
    assert "2xx" in ov_data["status_distribution"]
    assert "top_paths" in ov_data
    assert "top_ips" in ov_data
    assert "recent_requests" in ov_data
