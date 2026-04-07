#!/usr/bin/env bash
# DynaDash update script
# Rebuilds and restarts everything after a code update.
# Pass --skip-pull if the caller (run.sh) already did the git pull.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
WWW_DIR="/var/www/dynadash"
SKIP_PULL=false

for arg in "$@"; do
  [[ "$arg" == "--skip-pull" ]] && SKIP_PULL=true
done

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "  ${CYAN}•${NC} $*"; }
ok()    { echo -e "  ${GREEN}✓${NC} $*"; }
error() { echo -e "  ${RED}✗${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && error "Run as root."

cd "${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# 1. Pull latest code (skipped when called from run.sh which already did it)
# ---------------------------------------------------------------------------
if [[ "${SKIP_PULL}" == false ]]; then
  info "Pulling latest code…"
  git pull origin "$(git rev-parse --abbrev-ref HEAD)"
  ok "Code updated to $(git rev-parse --short HEAD)"
fi

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
npm install --silent
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
# 5. Regenerate systemd service (path may have changed or service may be new)
# ---------------------------------------------------------------------------
info "Updating systemd service…"
cat > /etc/systemd/system/dynadash-backend.service <<UNIT
[Unit]
Description=DynaDash FastAPI Backend
After=network.target influxdb.service
Wants=influxdb.service

[Service]
Type=simple
User=root
WorkingDirectory=${BACKEND_DIR}
ExecStart=${BACKEND_DIR}/.venv/bin/uvicorn main:app \\
    --host 127.0.0.1 \\
    --port 8000 \\
    --log-level info
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dynadash-backend
ReadWritePaths=${BACKEND_DIR}/data

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
ok "systemd service updated"

# ---------------------------------------------------------------------------
# 6. Restart services
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
nginx -t 2>/dev/null
systemctl reload nginx
ok "nginx reloaded"

LOCAL_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo -e "  ${GREEN}DynaDash updated successfully ✓${NC}"
echo -e "  Dashboard: ${CYAN}http://${LOCAL_IP}/${NC}"
echo ""
