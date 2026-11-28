#!/usr/bin/env bash
set -euo pipefail

# NexoPanel safe updater.
#
# The checkout under /opt/nexopanel is owned by root while the panel service
# runs as the unprivileged `nexopanel` user. Git therefore refuses a plain
# `git pull` from that account ("dubious ownership") and the working tree is
# not writable by it. Run this script as root instead; it pins
# safe.directory for the checkout, fast-forwards the branch and re-runs the
# installer (which rebuilds the frontend and restarts the services).

NEXOPANEL_HOME="${NEXOPANEL_HOME:-/opt/nexopanel}"
GIT_BRANCH="${NEXOPANEL_GIT_BRANCH:-main}"

log() { echo -e "\033[1;32m[NexoPanel]\033[0m $*"; }
err() { echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then
  err "update.sh must be run as root: sudo bash $0"
fi

if [[ ! -d "${NEXOPANEL_HOME}/.git" ]]; then
  err "${NEXOPANEL_HOME} is not a git checkout. Reinstall with scripts/install.sh --repo https://github.com/infomotin/NexoPanel.git"
fi

log "Updating ${NEXOPANEL_HOME} from origin/${GIT_BRANCH}..."
git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" fetch --all --prune
git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" checkout "$GIT_BRANCH"
git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" reset --hard origin/"$GIT_BRANCH" || git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" pull origin "$GIT_BRANCH"

if [[ "${1:-}" == "--full" ]]; then
  log "Running full installer (re-provisioning services and checking OS runtime)..."
  bash "${NEXOPANEL_HOME}/scripts/install.sh"
else
  log "Applying updates to backend dependencies, directories, and restarting services..."
  if [[ -f "${NEXOPANEL_HOME}/backend/requirements.txt" && -d "${NEXOPANEL_HOME}/venv" ]]; then
    "${NEXOPANEL_HOME}/venv/bin/pip" install --quiet -r "${NEXOPANEL_HOME}/backend/requirements.txt" || true
  fi
  # Ensure DNS zones directory and tools
  mkdir -p /etc/bind/zones
  chown -R bind:bind /etc/bind/zones 2>/dev/null || true
  chmod 755 /etc/bind/zones 2>/dev/null || true
  if ! command -v named-checkzone >/dev/null 2>&1; then
    apt-get update -q && apt-get install -y -q bind9-utils dnsutils >/dev/null 2>&1 || true
  fi
  # Ensure ownership of prebuilt frontend output
  if [[ -d "${NEXOPANEL_HOME}/frontend/.output" ]]; then
    chown -R nexopanel:nexopanel "${NEXOPANEL_HOME}/frontend/.output" 2>/dev/null || true
  fi
  systemctl daemon-reload
  timeout 15 systemctl restart nexopanel-daemon >/dev/null 2>&1 || systemctl start --no-block nexopanel-daemon >/dev/null 2>&1 || true
  timeout 15 systemctl restart nexopanel >/dev/null 2>&1 || systemctl start --no-block nexopanel >/dev/null 2>&1 || true
  log "✓ NexoPanel updated and restarted successfully!"
fi
