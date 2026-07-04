#!/usr/bin/env bash
#
# One-command deploy to the BrewSignal Raspberry Pi.
#
# Encodes the safe sequence that's easy to get wrong by hand:
#   fetch -> reset --hard origin/<branch> -> conditional frontend build
#   (BUILD_TARGET=pi, only when frontend/ actually changed) -> restart -> verify.
#
# The Pi builds the frontend itself: backend/static is gitignored, so the
# built assets never travel through git. A backend-only change skips the
# (slow) build entirely.
#
# Usage:
#   deploy/deploy.sh              # deploy whatever is on origin/<branch>
#   deploy/deploy.sh --push       # push the local branch first, then deploy
#
# Config via env (defaults shown):
#   BREWSIGNAL_PI_HOST=192.168.4.218
#   BREWSIGNAL_PI_USER=pi
#   BREWSIGNAL_REMOTE_DIR=/opt/brewsignal
#   BREWSIGNAL_BRANCH=master
#   BREWSIGNAL_PI_PASS=...        # if set, uses sshpass; else relies on SSH keys
#
set -euo pipefail

PI_HOST="${BREWSIGNAL_PI_HOST:-192.168.4.218}"
PI_USER="${BREWSIGNAL_PI_USER:-pi}"
REMOTE_DIR="${BREWSIGNAL_REMOTE_DIR:-/opt/brewsignal}"
BRANCH="${BREWSIGNAL_BRANCH:-master}"
PORT="${BREWSIGNAL_PORT:-8080}"

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[deploy] %s\033[0m\n' "$*" >&2; exit 1; }

ssh_pi() {
  if [ -n "${BREWSIGNAL_PI_PASS:-}" ]; then
    command -v sshpass >/dev/null || die "BREWSIGNAL_PI_PASS set but sshpass not installed"
    sshpass -p "$BREWSIGNAL_PI_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$PI_USER@$PI_HOST" "$@"
  else
    ssh -o ConnectTimeout=10 "$PI_USER@$PI_HOST" "$@"
  fi
}

# --- optional push of the local branch ---------------------------------------
if [ "${1:-}" = "--push" ]; then
  log "Pushing local $BRANCH to origin..."
  git push origin "$BRANCH"
fi

# --- warn if local and origin disagree (deploying stale code is a classic trap)
git fetch origin "$BRANCH" >/dev/null 2>&1 || true
LOCAL_REF="$(git rev-parse "$BRANCH" 2>/dev/null || echo unknown)"
ORIGIN_REF="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo unknown)"
if [ "$LOCAL_REF" != "$ORIGIN_REF" ]; then
  log "WARNING: local $BRANCH ($LOCAL_REF) != origin/$BRANCH ($ORIGIN_REF)."
  log "         Deploying origin/$BRANCH. Use --push to publish local commits first."
fi

# --- remote: fetch, reset, conditional build, restart -------------------------
log "Deploying origin/$BRANCH to $PI_USER@$PI_HOST:$REMOTE_DIR ..."
ssh_pi "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

OLD=\$(git rev-parse HEAD)
git fetch origin
NEW=\$(git rev-parse "origin/$BRANCH")

git reset --hard "origin/$BRANCH"
echo "[pi] HEAD: \$(git log --oneline -1)"

# Sync backend Python deps only when the dependency manifest changed between
# OLD and NEW. A new pyproject dependency otherwise crash-loops the service
# with ModuleNotFoundError (bit us with scalar-fastapi, 2026-07-04).
# uv sync --locked installs exactly what uv.lock pins (and prunes removed
# deps), matching how Railway builds; --locked also fails loudly if the lock
# is stale relative to pyproject instead of silently re-resolving on the Pi.
if ! git diff --quiet "\$OLD" "\$NEW" -- pyproject.toml uv.lock; then
  echo "[pi] dependency manifest changed -> uv sync --locked"
  command -v uv >/dev/null 2>&1 || .venv/bin/pip install -q 'uv==0.9.0'
  UV_BIN=\$(command -v uv || echo .venv/bin/uv)
  "\$UV_BIN" sync --locked --no-dev >/tmp/brewsignal-uv.log 2>&1 \
    || { echo "[pi] DEP SYNC FAILED — tail of log:"; tail -20 /tmp/brewsignal-uv.log; exit 1; }
else
  echo "[pi] no dependency changes -> skipping dep sync"
fi

# Rebuild the frontend only when frontend/ changed between OLD and NEW, or when
# the built output is missing. Avoids a slow npm build on backend-only deploys.
if [ ! -f backend/static/index.html ] || ! git diff --quiet "\$OLD" "\$NEW" -- frontend/; then
  echo "[pi] frontend changed (or no build present) -> BUILD_TARGET=pi npm run build"
  ( cd frontend && BUILD_TARGET=pi npm run build >/tmp/brewsignal-build.log 2>&1 ) \
    || { echo "[pi] BUILD FAILED — tail of log:"; tail -20 /tmp/brewsignal-build.log; exit 1; }
else
  echo "[pi] no frontend changes -> skipping build"
fi

echo "[pi] restarting service..."
sudo systemctl restart brewsignal
REMOTE

# --- verify -------------------------------------------------------------------
log "Verifying..."
sleep 6
ACTIVE="$(ssh_pi "systemctl is-active brewsignal" 2>/dev/null || echo inactive)"
CODE="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$PI_HOST:$PORT/" 2>/dev/null || echo 000)"
log "service=$ACTIVE  http=$CODE"

if [ "$ACTIVE" = "active" ] && [ "$CODE" = "200" ]; then
  log "DEPLOY OK"
else
  die "DEPLOY FAILED (service=$ACTIVE http=$CODE) — check: ssh $PI_USER@$PI_HOST 'journalctl -u brewsignal -n 50'"
fi
