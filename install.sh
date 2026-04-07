#!/usr/bin/env bash
# DynaDash install script
# Idempotent — safe to re-run on an already-installed system.
# Must be run as root (or with sudo) on Debian/Ubuntu.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
WWW_DIR="/var/www/dynadash"
INFLUX_ORG="home"
INFLUX_BUCKET="dynadash"
INFLUX_USER="admin"
INFLUX_PASS="dynadash-influx-$(openssl rand -hex 8)"
CONFIG_YAML="${BACKEND_DIR}/config.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DynaDash]${NC} $*"; }
ok()    { echo -e "${GREEN}[DynaDash] ✓${NC} $*"; }
error() { echo -e "${RED}[DynaDash] ✗${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && error "This script must be run as root."

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
info "Installing system packages…"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nodejs npm \
    nginx \
    curl jq openssl ca-certificates gnupg

# ---------------------------------------------------------------------------
# 2. InfluxDB 2.x via official apt repo
# ---------------------------------------------------------------------------
if ! command -v influx &>/dev/null; then
    info "Adding InfluxData apt repository…"
    curl -fsSL https://repos.influxdata.com/influxdata-archive_compat.key \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg
    echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' \
        > /etc/apt/sources.list.d/influxdata.list
    apt-get update -qq
    apt-get install -y -qq influxdb2 influxdb2-cli
    ok "InfluxDB installed"
else
    ok "InfluxDB already installed"
fi

# ---------------------------------------------------------------------------
# 3. Start InfluxDB
# ---------------------------------------------------------------------------
info "Enabling and starting InfluxDB…"
systemctl enable influxdb --quiet
systemctl start influxdb

# Wait for InfluxDB to be ready
for i in $(seq 1 15); do
    if influx ping &>/dev/null 2>&1; then break; fi
    sleep 1
done
influx ping &>/dev/null 2>&1 || error "InfluxDB did not become ready in time."
ok "InfluxDB is running"

# ---------------------------------------------------------------------------
# 4. Initialise InfluxDB (idempotent)
# ---------------------------------------------------------------------------
if [[ -f "${CONFIG_YAML}" ]] && grep -q "token:" "${CONFIG_YAML}" 2>/dev/null; then
    info "InfluxDB already initialised — skipping setup"
    INFLUX_TOKEN="$(grep 'token:' "${CONFIG_YAML}" | awk '{print $2}' | tr -d '"')"
else
    info "Initialising InfluxDB…"
    # Check if already set up
    if influx org list &>/dev/null 2>&1; then
        info "InfluxDB already has config — creating token only"
        INFLUX_TOKEN="$(influx auth create \
            --org "${INFLUX_ORG}" \
            --all-access \
            --description "dynadash" \
            --json 2>/dev/null | jq -r '.token' || true)"
        if [[ -z "${INFLUX_TOKEN}" ]]; then
            INFLUX_TOKEN="$(influx auth list --json 2>/dev/null | jq -r '.[0].token')"
        fi
    else
        influx setup \
            --username "${INFLUX_USER}" \
            --password "${INFLUX_PASS}" \
            --org "${INFLUX_ORG}" \
            --bucket "${INFLUX_BUCKET}" \
            --retention 0 \
            --force &>/dev/null
        INFLUX_TOKEN="$(influx auth list --json | jq -r '.[0].token')"
    fi
    ok "InfluxDB initialised"

    # Write config.yaml
    info "Writing ${CONFIG_YAML}…"
    cat > "${CONFIG_YAML}" <<EOF
influxdb:
  url: "http://localhost:8086"
  token: "${INFLUX_TOKEN}"
  org: "${INFLUX_ORG}"
  bucket: "${INFLUX_BUCKET}"

polling_interval_seconds: 10
EOF
    ok "config.yaml written"
fi

# ---------------------------------------------------------------------------
# 5. Python virtual environment & dependencies
# ---------------------------------------------------------------------------
info "Setting up Python virtual environment…"
if [[ ! -d "${BACKEND_DIR}/.venv" ]]; then
    python3 -m venv "${BACKEND_DIR}/.venv"
fi
"${BACKEND_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${BACKEND_DIR}/.venv/bin/pip" install --quiet -r "${BACKEND_DIR}/requirements.txt"
ok "Python dependencies installed"

# ---------------------------------------------------------------------------
# 6. Build frontend
# ---------------------------------------------------------------------------
info "Installing frontend npm dependencies…"
cd "${FRONTEND_DIR}"
npm ci --silent
info "Building frontend…"
npm run build --silent
ok "Frontend built"

# ---------------------------------------------------------------------------
# 7. Deploy frontend to nginx web root
# ---------------------------------------------------------------------------
info "Deploying frontend to ${WWW_DIR}…"
mkdir -p "${WWW_DIR}"
rm -rf "${WWW_DIR:?}"/*
cp -r "${FRONTEND_DIR}/dist/." "${WWW_DIR}/"
ok "Frontend deployed"

# ---------------------------------------------------------------------------
# 8. Configure nginx
# ---------------------------------------------------------------------------
info "Configuring nginx…"
cp "${SCRIPT_DIR}/nginx/dynadash.conf" /etc/nginx/sites-enabled/dynadash
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
ok "nginx configured and reloaded"

# ---------------------------------------------------------------------------
# 9. Install and start systemd service
# ---------------------------------------------------------------------------
info "Installing systemd service…"
# Generate the service file with the correct install path baked in.
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
systemctl enable dynadash-backend --quiet
systemctl restart dynadash-backend
sleep 2
if systemctl is-active --quiet dynadash-backend; then
    ok "dynadash-backend service is running"
else
    error "dynadash-backend service failed to start. Run: journalctl -u dynadash-backend -n 50"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
LOCAL_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DynaDash installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo -e "  Dashboard URL:  ${CYAN}http://${LOCAL_IP}/${NC}"
echo ""
echo -e "  On first launch, you will be prompted to enter"
echo -e "  your Dynalite gateway IP, username, and password."
echo -e "  After saving, add your areas in the Area Manager."
echo ""
