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
git -c "safe.directory=${NEXOPANEL_HOME}" -C "$NEXOPANEL_HOME" pull --ff-only origin "$GIT_BRANCH"

log "Re-running installer to rebuild the frontend and restart services..."
bash "${NEXOPANEL_HOME}/scripts/install.sh"
