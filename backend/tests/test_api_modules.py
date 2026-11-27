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
    md = await client.post("/api/v1/mail/domains", headers=admin_headers, json={"domain": "mail.example.com"})
    assert md.status_code == 201
    md_id = md.json()["id"]
    mbox = await client.post(
        "/api/v1/mail/mailboxes",
        headers=admin_headers,
        json={"mail_domain_id": md_id, "local_part": "hello", "password": "MailPassword123!"},
    )
    assert mbox.status_code == 201
    readiness = await client.get(f"/api/v1/mail/domains/{md_id}/dns-readiness", headers=admin_headers)
    assert readiness.status_code == 200
    assert len(readiness.json()["required_records"]) == 4

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


async def test_update_status_endpoint(client: AsyncClient, admin_headers: dict[str, str]):
    res = await client.get("/api/v1/system/updates", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    for key in ("enabled", "repo_url", "current_version", "update_available", "checked_at"):
        assert key in data
    assert data["repo_url"].endswith("NexoPanel")
