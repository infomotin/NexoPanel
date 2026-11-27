# NexoPanel

**NexoPanel** is a clean-room, production-grade Linux web hosting control panel built from scratch with **FastAPI**, **SQLAlchemy 2.0 (async)**, **SQLite 3 (WAL)**, and **Nuxt 3 (Vue 3 + TypeScript + Tailwind CSS + xterm.js)**.

---

## Architectural Boundaries

### 1. Single-Node Target with Multi-Node Readiness
NexoPanel manages a single Linux host (`localhost`) in this release. Every domain model, audit record, and command execution passes through a `node_id` context (`NodeExecutor` -> `LocalNodeExecutor`), enabling a future `RemoteNodeExecutor` (gRPC/SSH) without refactoring domain logic.

### 2. Bundled (Panel-Owned) vs. Delegated (OS-Managed) Services
* **Bundled (Panel-Owned):**
  * Python 3.11+ virtual environment, FastAPI ASGI control plane (`nexopanel.service`), Nuxt 3 frontend, SQLite 3 WAL database (`/var/lib/nexopanel/panel.db`), Jinja2 configuration templates, and the privilege-separated root helper daemon (`nexopanel-daemon.service` listening on `/run/nexopanel/daemon.sock` mode `0600`).
* **Delegated (OS-Managed via `apt-get` & `systemd`):**
  * **Web Server:** Nginx (`WebServerProvider` -> `NginxProvider`).
  * **Mail Stack:** Postfix, Dovecot, OpenDKIM, Rspamd (`OutboundMailRouter` for Direct Delivery or Authenticated SMTP Relay).
  * **DNS:** Bind9 (`named-checkzone` validation prior to reload).
  * **Databases:** MariaDB/MySQL and PostgreSQL.

### 3. Supported Operating Systems
* **Ubuntu 22.04 LTS**, **Ubuntu 24.04 LTS**, and **Debian 12 (Bookworm)** on `x86_64` and `aarch64`.
* Both `scripts/install.sh` and FastAPI startup (`app/core/os_gate.py`) strictly validate `/etc/os-release` and abort with a non-zero exit code on unsupported distributions.

---

## Security & Defensive Engineering
* **Zero Shell Interpolation:** All system binaries are executed via `asyncio.create_subprocess_exec` with explicit argument arrays and strict Pydantic/allowlist validation.
* **Privilege Separation:** The FastAPI worker runs as unprivileged `nexopanel`, delegating privileged file writes and service reloads to `nexopanel_daemon.py` over a `0600` Unix domain socket.
* **Secrets at Rest:** Third-party credentials (DKIM private keys, SMTP relay passwords, DNS-01 API tokens, TOTP secrets) are encrypted with **Fernet** (`AES-128-CBC + HMAC-SHA256`) using `/etc/nexopanel/master.key` (`0600`) and masked (`********`) in API responses and audit logs.
* **Authentication & RBAC:** Argon2id password hashing, optional RFC 6238 TOTP 2FA with single-use recovery codes, sliding-window rate limiting, Double-Submit CSRF protection, immutable append-only Audit Logs, and endpoint-level `Depends(require_permission("..."))`.

---

## Quick Start (Development)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export NEXOPANEL_SKIP_OS_CHECK=true
export NEXOPANEL_DAEMON_USE_MOCK_EXECUTOR=true
export NEXOPANEL_DATABASE_PATH=./dev_panel.db
export NEXOPANEL_MASTER_KEY_PATH=./dev_master.key
uvicorn app.main:app --reload --port 8443
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Production Installation (Ubuntu 22.04/24.04 or Debian 12)
```bash
sudo bash scripts/install.sh
```
