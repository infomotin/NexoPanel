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
    # DNS
    zone = await client.post("/api/v1/dns/zones", headers=admin_headers, json={"domain": "zone.example.com"})
    assert zone.status_code == 201
    zone_id = zone.json()["id"]
    rec = await client.post(
        f"/api/v1/dns/zones/{zone_id}/records",
        headers=admin_headers,
        json={"name": "www", "record_type": "A", "value": "192.0.2.10", "ttl": 300},
    )
    assert rec.status_code == 201

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

    # FTP Account
    roots = (await client.get("/api/v1/files/roots", headers=admin_headers)).json()["roots"]
    ftp_res = await client.post(
        "/api/v1/ftp",
        headers=admin_headers,
        json={"username": "ftp_user1", "password": "FtpPassword123!", "home_directory": roots[0]},
    )
    assert ftp_res.status_code == 201
    assert ftp_res.json()["username"] == "ftp_user1"

