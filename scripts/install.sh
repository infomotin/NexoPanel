#!/usr/bin/env bash
set -euo pipefail

# NexoPanel Idempotent One-Line Installer (Git Repo & Release Package Ready)
# Supported Targets: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Ubuntu 26.04 LTS, Debian 12 (Bookworm) [x86_64, aarch64]

NEXOPANEL_HOME="/opt/nexopanel"
NEXOPANEL_DATA="/var/lib/nexopanel"
NEXOPANEL_ETC="/etc/nexopanel"
NEXOPANEL_RUN="/run/nexopanel"
NEXOPANEL_LOG="/var/log/nexopanel"
NEXOPANEL_BACKUP="/var/backups/nexopanel"
MIN_RAM_MB=1024
MIN_DISK_GB=10

GIT_REPO="${NEXOPANEL_GIT_REPO:-}"
GIT_BRANCH="${NEXOPANEL_GIT_BRANCH:-main}"
REBUILD_FRONTEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      GIT_REPO="$2"
      shift 2
      ;;
    --branch)
      GIT_BRANCH="$2"
      shift 2
      ;;
    --rebuild|--rebuild-frontend)
      REBUILD_FRONTEND=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done

log() { echo -e "\033[1;32m[NexoPanel]\033[0m $*"; }
err() { echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }

# 1. Root, Architecture, OS & Hardware Validation
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
  ubuntu:22.04|ubuntu:24.04|ubuntu:26.04|debian:12)
    log "Verified supported OS: ${PRETTY_NAME} (${ARCH})"
    ;;
  *)
    err "Unsupported OS: ${PRETTY_NAME:-unknown} (ID=${OS_ID}, VERSION_ID=${OS_VER}). Supported: Ubuntu 22.04/24.04/26.04 LTS, Debian 12."
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

# 2. Non-interactive Package Installation (Minimized Ubuntu/Debian safe)
export DEBIAN_FRONTEND=noninteractive
log "Updating apt package index..."
apt-get update -qq

echo "postfix postfix/mailname string $(hostname -f)" | debconf-set-selections
echo "postfix postfix/main_mailer_type string 'Internet Site'" | debconf-set-selections

log "Installing delegated OS services & runtime dependencies..."
apt-get install -y -q \
  ca-certificates curl git tar unzip gnupg lsb-release \
  nginx php-fpm \
  postfix postfix-pcre dovecot-core dovecot-imapd dovecot-pop3d opendkim opendkim-tools \
  bind9 bind9utils \
  mariadb-server postgresql \
  pure-ftpd \
  ufw fail2ban \
  certbot python3 python3-venv python3-pip

# 3. Create unprivileged system user & directories
if ! id -u nexopanel >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin nexopanel
fi

mkdir -p "$NEXOPANEL_HOME" "$NEXOPANEL_DATA" "$NEXOPANEL_ETC" "$NEXOPANEL_RUN" "$NEXOPANEL_LOG" "$NEXOPANEL_BACKUP" /var/www/acme-challenge/.well-known/acme-challenge
chown -R nexopanel:nexopanel "$NEXOPANEL_DATA" "$NEXOPANEL_LOG" "$NEXOPANEL_BACKUP" "$NEXOPANEL_RUN"
chown root:nexopanel "$NEXOPANEL_ETC"
chmod 750 "$NEXOPANEL_ETC"

if [[ ! -f "${NEXOPANEL_ETC}/master.key" ]]; then
  python3 -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' > "${NEXOPANEL_ETC}/master.key"
  chmod 0600 "${NEXOPANEL_ETC}/master.key"
  chown nexopanel:nexopanel "${NEXOPANEL_ETC}/master.key"
fi

# 4. Acquire NexoPanel Source (Git Repo OR Local/Release Package)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$NEXOPANEL_HOME" || cd /tmp

if [[ -n "$GIT_REPO" ]]; then
  log "Cloning/updating NexoPanel from Git repository: ${GIT_REPO} (${GIT_BRANCH})..."
  if [[ -d "${NEXOPANEL_HOME}/.git" ]]; then
    git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" fetch --all --prune
    git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" checkout "$GIT_BRANCH"
    git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" pull --ff-only origin "$GIT_BRANCH"
  else
    rm -rf "${NEXOPANEL_HOME:?}/backend" "${NEXOPANEL_HOME:?}/frontend"
    git clone --branch "$GIT_BRANCH" --depth 1 "$GIT_REPO" "$NEXOPANEL_HOME"
  fi
  REBUILD_FRONTEND=1
elif [[ "$REPO_ROOT" == "$NEXOPANEL_HOME" ]]; then
  # Running the installer from the installed checkout itself (e.g. after a
  # `git pull`). Copying the tree onto itself would delete backend/ before it
  # could be read, so use the in-place sources and just rebuild the frontend.
  log "Using in-place sources from ${NEXOPANEL_HOME}..."
  [[ -d "${NEXOPANEL_HOME}/.git" ]] && REBUILD_FRONTEND=1
elif [[ -d "${REPO_ROOT}/backend" ]]; then
  log "Installing/updating NexoPanel from local source (${REPO_ROOT})..."
  rm -rf "${NEXOPANEL_HOME}/backend"
  cp -r "${REPO_ROOT}/backend" "${NEXOPANEL_HOME}/"
  if [[ -d "${REPO_ROOT}/frontend" ]]; then
    mkdir -p "${NEXOPANEL_HOME}/frontend"
    if [[ -d "${REPO_ROOT}/.git" ]]; then
      REBUILD_FRONTEND=1
      tar -C "${REPO_ROOT}/frontend" --exclude='node_modules' --exclude='.nuxt' --exclude='.output' --exclude='dist' -cf - . | tar -C "${NEXOPANEL_HOME}/frontend" -xf -
    else
      tar -C "${REPO_ROOT}/frontend" --exclude='node_modules' -cf - . | tar -C "${NEXOPANEL_HOME}/frontend" -xf -
    fi
  fi
else
  GIT_REPO="https://github.com/infomotin/NexoPanel.git"
  log "No local backend directory found; cloning from ${GIT_REPO} (${GIT_BRANCH})..."
  rm -rf "${NEXOPANEL_HOME:?}/backend" "${NEXOPANEL_HOME:?}/frontend"
  git clone --branch "$GIT_BRANCH" --depth 1 "$GIT_REPO" "$NEXOPANEL_HOME"
  REBUILD_FRONTEND=1
fi

# 5. Build Frontend Static Bundle if not pre-packaged or source updated
if [[ -d "${NEXOPANEL_HOME}/frontend" ]] && { [[ "$REBUILD_FRONTEND" -eq 1 ]] || [[ ! -f "${NEXOPANEL_HOME}/frontend/.output/public/index.html" ]]; }; then
  if ! command -v node >/dev/null 2>&1 || (( $(node -v | sed 's/v\([0-9]*\).*/\1/') < 20 )); then
    log "Installing Node.js 22 LTS for frontend build..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -q nodejs
  fi
  log "Building Nuxt 3 static frontend bundle..."
  SERVER_IP="$(hostname -I | awk '{print $1}')"
  export NUXT_PUBLIC_API_BASE="/api/v1"
  export NUXT_PUBLIC_WS_BASE="ws://${SERVER_IP}:8443/api/v1"
  rm -rf "${NEXOPANEL_HOME}/frontend/.output" "${NEXOPANEL_HOME}/frontend/.nuxt"
  if [[ -d "${NEXOPANEL_HOME}/frontend/node_modules" && ! -x "${NEXOPANEL_HOME}/frontend/node_modules/.bin/nuxt" ]]; then
    rm -rf "${NEXOPANEL_HOME}/frontend/node_modules"
  fi
  (
    cd "${NEXOPANEL_HOME}/frontend"
    npm install --no-audit --no-fund --ignore-scripts
    chmod -R a+rX "${NEXOPANEL_HOME}/frontend/node_modules" 2>/dev/null || true
    find "${NEXOPANEL_HOME}/frontend/node_modules" -type f \( -path "*/.bin/*" -o -path "*/bin/*" -o -name "esbuild" \) -exec chmod +x {} + 2>/dev/null || true
    node ./node_modules/nuxt/bin/nuxt.mjs prepare
    node ./node_modules/nuxt/bin/nuxt.mjs generate
  )
fi

# 6. Python Virtual Environment & Backend Dependencies
if [[ ! -d "${NEXOPANEL_HOME}/venv" ]]; then
  python3 -m venv "${NEXOPANEL_HOME}/venv"
fi
"${NEXOPANEL_HOME}/venv/bin/pip" install --quiet --upgrade pip
"${NEXOPANEL_HOME}/venv/bin/pip" install --quiet -r "${NEXOPANEL_HOME}/backend/requirements.txt"

# 7. Bootstrap SQLite WAL Schema & Initial Admin Credentials
INIT_ADMIN_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
CREATED_PW=$(PYTHONPATH="${NEXOPANEL_HOME}/backend" \
NEXOPANEL_DATABASE_PATH="${NEXOPANEL_DATA}/panel.db" \
NEXOPANEL_MASTER_KEY_PATH="${NEXOPANEL_ETC}/master.key" \
"${NEXOPANEL_HOME}/venv/bin/python" - <<PYEOF
import asyncio
from app.db.bootstrap import init_db_schema, seed_defaults
from app.db.session import AsyncSessionLocal

async def main():
    await init_db_schema()
    async with AsyncSessionLocal() as db:
        pw = await seed_defaults(db, initial_admin_password="${INIT_ADMIN_PASS}")
        if pw:
            print(pw)

asyncio.run(main())
PYEOF
)
chown nexopanel:nexopanel "${NEXOPANEL_DATA}/panel.db"*

# 8. Install systemd units (nexopanel-daemon.service & nexopanel.service)
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
Description=NexoPanel Control Plane API & UI
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
systemctl enable --now nginx mariadb postgresql postfix dovecot named fail2ban
systemctl enable --now pure-ftpd >/dev/null 2>&1 || true
systemctl enable nexopanel-daemon nexopanel
systemctl restart nexopanel-daemon nexopanel

# Open panel port in UFW if active
if ufw status | grep -q "Status: active"; then
  ufw allow 8443/tcp >/dev/null 2>&1 || true
fi

SERVER_IP="$(hostname -I | awk '{print $1}')"
echo ""
log "========================================================"
log " NexoPanel Installation / Upgrade Complete!"
log " Panel URL:        http://${SERVER_IP}:8443"
log " Initial Username: admin"
if [[ -n "$CREATED_PW" ]]; then
  log " Initial Password: ${CREATED_PW}"
else
  log " Initial Password: (preserved existing admin password)"
fi
log "========================================================"
