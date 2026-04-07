#!/usr/bin/env bash
# DynaDash — Proxmox VE LXC installer
#
# Run on the PVE host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
#
# Creates a Debian 12 LXC container and installs DynaDash inside it.

set -euo pipefail

# ── Repo ────────────────────────────────────────────────────────────────────
REPO="https://github.com/jonaskul/dynadash.git"
BRANCH="main"
APP_DIR="/opt/dynadash"

# ── Defaults ─────────────────────────────────────────────────────────────────
DEF_HOSTNAME="dynadash"
DEF_RAM="1024"
DEF_SWAP="512"
DEF_DISK="8"
DEF_CPU="2"
DEF_BRIDGE="vmbr0"
DEF_NET="dhcp"
DEF_TEMPLATE_DIST="debian-12-standard"

# ── Colours ──────────────────────────────────────────────────────────────────
BL='\033[0;34m'; RD='\033[0;31m'; GN='\033[0;32m'
CY='\033[0;36m'; YW='\033[0;33m'; BLD='\033[1m'; NC='\033[0m'

msg_info()  { echo -e "  ${CY}…${NC}  $*"; }
msg_ok()    { echo -e "  ${GN}✓${NC}  $*"; }
msg_warn()  { echo -e "  ${YW}!${NC}  $*"; }
msg_error() { echo -e "  ${RD}✗${NC}  $*" >&2; exit 1; }

header() {
cat <<'BANNER'

  ██████╗ ██╗   ██╗███╗   ██╗ █████╗ ██████╗  █████╗ ███████╗██╗  ██╗
  ██╔══██╗╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔══██╗██╔════╝██║  ██║
  ██║  ██║ ╚████╔╝ ██╔██╗ ██║███████║██║  ██║███████║███████╗███████║
  ██║  ██║  ╚██╔╝  ██║╚██╗██║██╔══██║██║  ██║██╔══██║╚════██║██╔══██║
  ██████╔╝   ██║   ██║ ╚████║██║  ██║██████╔╝██║  ██║███████║██║  ██║
  ╚═════╝    ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

  Dynalite lighting & HVAC dashboard — LXC Installer for Proxmox VE

BANNER
}

# ── Sanity checks ─────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]]        && msg_error "Run as root on the Proxmox VE host."
command -v pct  &>/dev/null || msg_error "pct not found — is this a Proxmox VE host?"
command -v pvesh &>/dev/null || msg_error "pvesh not found — is this a Proxmox VE host?"

header

# ── Next available CT ID ──────────────────────────────────────────────────────
next_ctid() {
  local id=100
  while pct status "$id" &>/dev/null 2>&1; do
    (( id++ ))
  done
  echo "$id"
}

# ── Find storage with enough free space (GB) ──────────────────────────────────
find_storage() {
  local need_gb="${1:-10}"
  pvesh get /nodes/"$(hostname)"/storage --output-format json 2>/dev/null \
    | python3 -c "
import sys, json
stores = json.load(sys.stdin)
for s in stores:
    avail = s.get('avail', 0)
    ctype = s.get('type', '')
    sid   = s.get('storage', '')
    # prefer local-lvm or zfspool; skip shared/nfs for simplicity
    if avail >= ${need_gb} * 1024**3 and ctype in ('lvmthin','zfspool','dir','lvm','btrfs'):
        print(sid)
        sys.exit(0)
sys.exit(1)
" 2>/dev/null || echo "local-lvm"
}

# ── Download template if not present ─────────────────────────────────────────
ensure_template() {
  local storage="$1"
  msg_info "Checking for Debian 12 template…"
  local tmpl
  tmpl=$(pveam list "$storage" 2>/dev/null \
    | awk '/debian-12-standard/{print $1; exit}')

  if [[ -z "$tmpl" ]]; then
    msg_info "Downloading Debian 12 standard template…"
    pveam update &>/dev/null
    local avail
    avail=$(pveam available --section system 2>/dev/null \
      | awk '/debian-12-standard/{print $2; exit}')
    [[ -z "$avail" ]] && msg_error "Could not find debian-12-standard in template list."
    pveam download "$storage" "$avail" &>/dev/null
    tmpl=$(pveam list "$storage" 2>/dev/null \
      | awk '/debian-12-standard/{print $1; exit}')
  fi
  msg_ok "Template: $tmpl"
  echo "$tmpl"
}

# ── Interactive config (whiptail if available, else plain prompts) ────────────
HAVE_WHIPTAIL=false
command -v whiptail &>/dev/null && HAVE_WHIPTAIL=true

ask() {
  # ask <var> <prompt> <default>
  local var="$1" prompt="$2" default="$3" val
  if $HAVE_WHIPTAIL; then
    val=$(whiptail --inputbox "$prompt" 8 60 "$default" \
      --title "DynaDash LXC Setup" 3>&1 1>&2 2>&3) || val="$default"
  else
    read -r -p "  $prompt [$default]: " val
    val="${val:-$default}"
  fi
  printf -v "$var" '%s' "$val"
}

confirm_advanced() {
  if $HAVE_WHIPTAIL; then
    whiptail --yesno "Configure advanced settings?\n(RAM, disk, CPU, network…)" \
      8 50 --title "DynaDash LXC Setup" 3>&1 1>&2 2>&3
  else
    read -r -p "  Configure advanced settings? [y/N]: " ans
    [[ "${ans,,}" == y* ]]
  fi
}

echo ""
echo -e "  ${BLD}Default settings:${NC}"
STORAGE=$(find_storage 10)
CTID=$(next_ctid)
echo -e "  CT ID      : ${CY}${CTID}${NC}"
echo -e "  Hostname   : ${CY}${DEF_HOSTNAME}${NC}"
echo -e "  Storage    : ${CY}${STORAGE}${NC}"
echo -e "  RAM / Swap : ${CY}${DEF_RAM} MB / ${DEF_SWAP} MB${NC}"
echo -e "  Disk       : ${CY}${DEF_DISK} GB${NC}"
echo -e "  CPU cores  : ${CY}${DEF_CPU}${NC}"
echo -e "  Network    : ${CY}${DEF_BRIDGE}, DHCP${NC}"
echo ""

HOSTNAME="$DEF_HOSTNAME"
RAM="$DEF_RAM"
SWAP="$DEF_SWAP"
DISK="$DEF_DISK"
CPU="$DEF_CPU"
BRIDGE="$DEF_BRIDGE"
NET_IP="$DEF_NET"
NET_GW=""

if confirm_advanced; then
  echo ""
  ask CTID     "CT ID"                   "$CTID"
  ask HOSTNAME "Hostname"                "$DEF_HOSTNAME"
  ask STORAGE  "Storage"                 "$STORAGE"
  ask RAM      "RAM (MB)"                "$DEF_RAM"
  ask SWAP     "Swap (MB)"               "$DEF_SWAP"
  ask DISK     "Disk size (GB)"          "$DEF_DISK"
  ask CPU      "CPU cores"               "$DEF_CPU"
  ask BRIDGE   "Network bridge"          "$DEF_BRIDGE"
  ask NET_IP   "IP (dhcp or x.x.x.x/x)" "$DEF_NET"
  if [[ "$NET_IP" != "dhcp" ]]; then
    ask NET_GW "Gateway"                 ""
  fi
fi

echo ""

# ── Template ──────────────────────────────────────────────────────────────────
TEMPLATE=$(ensure_template "$STORAGE")

# ── Build net config string ───────────────────────────────────────────────────
if [[ "$NET_IP" == "dhcp" ]]; then
  NET_CONFIG="name=eth0,bridge=${BRIDGE},ip=dhcp"
else
  NET_CONFIG="name=eth0,bridge=${BRIDGE},ip=${NET_IP}"
  [[ -n "$NET_GW" ]] && NET_CONFIG="${NET_CONFIG},gw=${NET_GW}"
fi

# ── Create container ──────────────────────────────────────────────────────────
msg_info "Creating LXC container ${CTID} (${HOSTNAME})…"
pct create "$CTID" "$TEMPLATE" \
  --hostname  "$HOSTNAME" \
  --memory    "$RAM" \
  --swap      "$SWAP" \
  --cores     "$CPU" \
  --rootfs    "${STORAGE}:${DISK}" \
  --net0      "$NET_CONFIG" \
  --features  nesting=1 \
  --unprivileged 1 \
  --ostype    debian \
  --start     0 \
  --onboot    1 \
  &>/dev/null
msg_ok "Container created"

msg_info "Starting container…"
pct start "$CTID"
# Wait for network / container to be ready
for i in $(seq 1 20); do
  pct exec "$CTID" -- true &>/dev/null 2>&1 && break
  sleep 1
done
pct exec "$CTID" -- true &>/dev/null 2>&1 || msg_error "Container did not become ready."
msg_ok "Container running"

# ── Install DynaDash inside the container ────────────────────────────────────
msg_info "Installing prerequisites inside container…"
pct exec "$CTID" -- bash -c "
  apt-get update -qq &&
  apt-get install -y -qq git curl ca-certificates
" &>/dev/null
msg_ok "Prerequisites installed"

msg_info "Cloning DynaDash repository (branch: ${BRANCH})…"
pct exec "$CTID" -- bash -c "
  git clone --branch '${BRANCH}' --depth 1 '${REPO}' '${APP_DIR}' -q
"
msg_ok "Repository cloned to ${APP_DIR}"

msg_info "Running DynaDash installer (this takes a few minutes)…"
pct exec "$CTID" -- bash "${APP_DIR}/install.sh"

# ── Done ─────────────────────────────────────────────────────────────────────
CT_IP=$(pct exec "$CTID" -- bash -c "hostname -I | awk '{print \$1}'" 2>/dev/null || echo "<container-ip>")

echo ""
echo -e "  ${GN}${BLD}════════════════════════════════════════════${NC}"
echo -e "  ${GN}${BLD}  DynaDash installed successfully!${NC}"
echo -e "  ${GN}${BLD}════════════════════════════════════════════${NC}"
echo ""
echo -e "  CT ID      : ${CY}${CTID}${NC}"
echo -e "  Dashboard  : ${CY}http://${CT_IP}/${NC}"
echo ""
echo -e "  On first launch you will be prompted for your"
echo -e "  Dynalite gateway IP, username, and password."
echo ""
echo -e "  To update later, run on the PVE host:"
echo -e "  ${YW}pct exec ${CTID} -- /opt/dynadash/update.sh${NC}"
echo ""
