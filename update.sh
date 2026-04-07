#!/usr/bin/env bash
# DynaDash update script
# Pull the latest code and rebuild/restart everything.
# Must be run as root from the repository root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
WWW_DIR="/var/www/dynadash"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DynaDash]${NC} $*"; }
ok()    { echo -e "${GREEN}[DynaDash] ✓${NC} $*"; }
error() { echo -e "${RED}[DynaDash] ✗${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && error "This script must be run as root."

cd "${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# 1. Pull latest code
# ---------------------------------------------------------------------------
info "Pulling latest code…"
git pull origin "$(git rev-parse --abbrev-ref HEAD)"
ok "Code updated"

# ---------------------------------------------------------------------------
# 2. Update Python dependencies
# ---------------------------------------------------------------------------
info "Updating Python dependencies…"
"${BACKEND_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${BACKEND_DIR}/.venv/bin/pip" install --quiet -r "${BACKEND_DIR}/requirements.txt"
ok "Python dependencies updated"

# ---------------------------------------------------------------------------
# 3. Rebuild frontend
# ---------------------------------------------------------------------------
info "Rebuilding frontend…"
cd "${FRONTEND_DIR}"
npm ci --silent
npm run build --silent
cd "${SCRIPT_DIR}"
ok "Frontend rebuilt"

# ---------------------------------------------------------------------------
# 4. Deploy frontend
# ---------------------------------------------------------------------------
info "Deploying frontend…"
mkdir -p "${WWW_DIR}"
rm -rf "${WWW_DIR:?}"/*
cp -r "${FRONTEND_DIR}/dist/." "${WWW_DIR}/"
ok "Frontend deployed"

# ---------------------------------------------------------------------------
# 5. Restart services
# ---------------------------------------------------------------------------
info "Restarting dynadash-backend…"
systemctl restart dynadash-backend
sleep 2
if systemctl is-active --quiet dynadash-backend; then
    ok "Backend restarted"
else
    error "Backend failed to restart. Run: journalctl -u dynadash-backend -n 50"
fi

info "Reloading nginx…"
nginx -t
systemctl reload nginx
ok "nginx reloaded"

echo ""
echo -e "${GREEN}DynaDash updated successfully ✓${NC}"
echo ""
