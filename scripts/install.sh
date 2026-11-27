#!/usr/bin/env bash
set -euo pipefail

# NexoPanel Idempotent One-Line Installer
# Supported Targets: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12 (Bookworm) [x86_64, aarch64]

NEXOPANEL_HOME="/opt/nexopanel"
NEXOPANEL_DATA="/var/lib/nexopanel"
NEXOPANEL_ETC="/etc/nexopanel"
NEXOPANEL_RUN="/run/nexopanel"
NEXOPANEL_LOG="/var/log/nexopanel"
NEXOPANEL_BACKUP="/var/backups/nexopanel"
MIN_RAM_MB=1024
MIN_DISK_GB=10

log() { echo -e "\033[1;32m[NexoPanel]\033[0m $*"; }
err() { echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }

# 1. Root & Hardware & OS Validation
if [[ $EUID -ne 0 ]]; then
  err "install.sh must be executed as root."
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|aarch64) ;;
  *) err "Unsupported architecture: $ARCH (supported: x86_64, aarch64)" ;;
esac

if [[ ! -f /etc/os-release ]]; then
  err "/etc/os-release not found."
fi
# shellcheck disable=SC1091
source /etc/os-release
OS_ID="${ID,,}"
OS_VER="${VERSION_ID:-}"

case "${OS_ID}:${OS_VER}" in
  ubuntu:22.04|ubuntu:24.04|debian:12)
    log "Verified supported OS: ${PRETTY_NAME} (${ARCH})"
    ;;
  *)
    err "Unsupported OS: ${PRETTY_NAME:-unknown} (ID=${OS_ID}, VERSION_ID=${OS_VER}). Supported: Ubuntu 22.04/24.04, Debian 12."
    ;;
esac

TOTAL_RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if (( TOTAL_RAM_MB < MIN_RAM_MB )); then
  err "Insufficient RAM (${TOTAL_RAM_MB} MB). Minimum required: ${MIN_RAM_MB} MB."
fi

AVAIL_DISK_GB=$(df -BG / | awk 'NR==2 {gsub("G",""); print int($4)}')
if (( AVAIL_DISK_GB < MIN_DISK_GB )); then
  err "Insufficient free disk space (${AVAIL_DISK_GB} GB). Minimum required: ${MIN_DISK_GB} GB."
fi

# 2. Non-interactive Package Installation
export DEBIAN_FRONTEND=noninteractive
log "Updating apt package index..."
apt-get update -qq

echo "postfix postfix/mailname string $(hostname -f)" | debconf-set-selections
echo "postfix postfix/main_mailer_type string 'Internet Site'" | debconf-set-selections

log "Installing delegated OS services (Nginx, Postfix, Dovecot, OpenDKIM, Bind9, MariaDB, PostgreSQL, Certbot, Python3)..."
apt-get install -y -q \
  nginx php-fpm \
  postfix postfix-pcre dovecot-core dovecot-imapd dovecot-pop3d opendkim opendkim-tools \
  bind9 bind9utils \
  mariadb-server postgresql \
  certbot python3 python3-venv python3-pip \
  curl tar unzip

# 3. Create unprivileged system user & directories
if ! id -u nexopanel >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin nexopanel
fi

mkdir -p "$NEXOPANEL_HOME" "$NEXOPANEL_DATA" "$NEXOPANEL_ETC" "$NEXOPANEL_RUN" "$NEXOPANEL_LOG" "$NEXOPANEL_BACKUP" /var/www/acme-challenge/.well-known/acme-challenge
chown -R nexopanel:nexopanel "$NEXOPANEL_DATA" "$NEXOPANEL_LOG" "$NEXOPANEL_BACKUP" "$NEXOPANEL_RUN"
chmod 750 "$NEXOPANEL_ETC"

# Master Fernet key (root-owned 0600)
if [[ ! -f "${NEXOPANEL_ETC}/master.key" ]]; then
  python3 -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' > "${NEXOPANEL_ETC}/master.key"
  chmod 0600 "${NEXOPANEL_ETC}/master.key"
  chown nexopanel:nexopanel "${NEXOPANEL_ETC}/master.key"
fi

# 4. Python Virtual Environment & Backend Installation
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ -d "${REPO_ROOT}/backend" ]]; then
  cp -r "${REPO_ROOT}/backend" "${NEXOPANEL_HOME}/"
fi

if [[ ! -d "${NEXOPANEL_HOME}/venv" ]]; then
  python3 -m venv "${NEXOPANEL_HOME}/venv"
fi
"${NEXOPANEL_HOME}/venv/bin/pip" install --quiet --upgrade pip
"${NEXOPANEL_HOME}/venv/bin/pip" install --quiet -r "${NEXOPANEL_HOME}/backend/requirements.txt"

# 5. Bootstrap SQLite WAL Schema & Initial Admin Credentials
INIT_ADMIN_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
PYTHONPATH="${NEXOPANEL_HOME}/backend" \
NEXOPANEL_DATABASE_PATH="${NEXOPANEL_DATA}/panel.db" \
NEXOPANEL_MASTER_KEY_PATH="${NEXOPANEL_ETC}/master.key" \
"${NEXOPANEL_HOME}/venv/bin/python" - <<PYEOF
import asyncio
from app.db.bootstrap import init_db_schema, seed_defaults
from app.db.session import AsyncSessionLocal

async def main():
    await init_db_schema()
    async with AsyncSessionLocal() as db:
        await seed_defaults(db, initial_admin_password="${INIT_ADMIN_PASS}")

asyncio.run(main())
PYEOF
chown nexopanel:nexopanel "${NEXOPANEL_DATA}/panel.db"*

# 6. Install systemd units (nexopanel-daemon.service & nexopanel.service)
cat > /etc/systemd/system/nexopanel-daemon.service <<EOF
[Unit]
Description=NexoPanel Privileged Root Execution Daemon
After=network.target

[Service]
Type=simple
User=root
ExecStart=${NEXOPANEL_HOME}/venv/bin/python ${NEXOPANEL_HOME}/backend/daemon/nexopanel_daemon.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/nexopanel.service <<EOF
[Unit]
Description=NexoPanel Control Plane API
After=network.target nexopanel-daemon.service
Requires=nexopanel-daemon.service

[Service]
Type=simple
User=nexopanel
Group=nexopanel
WorkingDirectory=${NEXOPANEL_HOME}/backend
Environment=NEXOPANEL_DATABASE_PATH=${NEXOPANEL_DATA}/panel.db
Environment=NEXOPANEL_MASTER_KEY_PATH=${NEXOPANEL_ETC}/master.key
ExecStart=${NEXOPANEL_HOME}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nginx mariadb postgresql postfix dovecot bind9 nexopanel-daemon nexopanel

SERVER_IP="$(hostname -I | awk '{print $1}')"
echo ""
log "========================================================"
log " NexoPanel Installation Complete!"
log " Panel URL:        http://${SERVER_IP}:8443"
log " Initial Username: admin"
log " Initial Password: ${INIT_ADMIN_PASS}"
log "========================================================"
