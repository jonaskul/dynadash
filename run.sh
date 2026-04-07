#!/usr/bin/env bash
# DynaDash — Proxmox VE LXC installer
#
# Run on the PVE host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
#
# Creates a Debian 12 LXC container and installs DynaDash inside it.

set -euo pipefail

# ── Repo ─────────────────────────────────────────────────────────────────────
REPO="https://github.com/jonaskul/dynadash.git"
BRANCH="main"
APP_DIR="/opt/dynadash"

# ── Defaults ──────────────────────────────────────────────────────────────────
DEF_HOSTNAME="dynadash"
DEF_RAM="1024"
DEF_SWAP="512"
DEF_DISK="8"
DEF_CPU="2"
DEF_BRIDGE="vmbr0"
DEF_NET="dhcp"

# ── Colours ───────────────────────────────────────────────────────────────────
RD='\033[0;31m'; GN='\033[0;32m'; CY='\033[0;36m'
YW='\033[0;33m'; BLD='\033[1m'; NC='\033[0m'

msg_info()  { echo -e "  ${CY}…${NC}  $*"; }
msg_ok()    { echo -e "  ${GN}✓${NC}  $*"; }
msg_error() { echo -e "\n  ${RD}✗  ERROR:${NC} $*\n" >&2; exit 1; }

# Print the failed command and line number on any unexpected error
trap 'echo -e "\n  ${RD}✗  Script failed at line ${LINENO}: ${BASH_COMMAND}${NC}\n" >&2' ERR

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
[[ $EUID -ne 0 ]]         && msg_error "Run as root on the Proxmox VE host."
command -v pct   &>/dev/null || msg_error "'pct' not found — is this a Proxmox VE host?"
command -v pveam &>/dev/null || msg_error "'pveam' not found — is this a Proxmox VE host?"

header

# ── Next available CT ID ──────────────────────────────────────────────────────
next_ctid() {
  local id=100
  while pct status "$id" &>/dev/null 2>&1; do (( id++ )); done
  echo "$id"
}

# ── Find storage that supports container rootfs ───────────────────────────────
# Checks pvesh storage list and returns the first storage with content type
# "rootdir" (or "images" for older PVE) and sufficient free space.
find_rootfs_storage() {
  pvesh get /nodes/"$(hostname -s)"/storage --output-format json 2>/dev/null \
    | python3 -c "
import sys, json
try:
    stores = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for s in stores:
    content = s.get('content', '')
    avail   = s.get('avail', 0)
    sid     = s.get('storage', '')
    stype   = s.get('type', '')
    # Must support rootdir (LXC rootfs) and have at least 10 GB free
    if ('rootdir' in content or 'images' in content) \
       and avail >= 10 * 1024**3 \
       and stype in ('lvmthin', 'zfspool', 'dir', 'lvm', 'btrfs', 'zfs'):
        print(sid)
        sys.exit(0)
sys.exit(1)
" 2>/dev/null || echo "local-lvm"
}

# ── Find storage that holds templates ────────────────────────────────────────
# Templates live on "local" (or whichever storage has content type "vztmpl").
find_template_storage() {
  pvesh get /nodes/"$(hostname -s)"/storage --output-format json 2>/dev/null \
    | python3 -c "
import sys, json
try:
    stores = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for s in stores:
    if 'vztmpl' in s.get('content', ''):
        print(s.get('storage', ''))
        sys.exit(0)
sys.exit(1)
" 2>/dev/null || echo "local"
}

# ── Ensure Debian 12 template is downloaded ───────────────────────────────────
ensure_template() {
  local tmpl_storage="$1"
  local tmpl
  tmpl=$(pveam list "$tmpl_storage" 2>/dev/null \
    | awk '/debian-12-standard/{print $1; exit}')

  if [[ -z "$tmpl" ]]; then
    msg_info "Updating template list…"
    pveam update 2>/dev/null || true
    local avail
    avail=$(pveam available --section system 2>/dev/null \
      | awk '/debian-12-standard/{print $2; exit}')
    [[ -z "$avail" ]] && msg_error "debian-12-standard not found in pveam available list."
    msg_info "Downloading Debian 12 template (this may take a moment)…"
    pveam download "$tmpl_storage" "$avail" \
      || msg_error "pveam download failed. Check internet connectivity."
    tmpl=$(pveam list "$tmpl_storage" 2>/dev/null \
      | awk '/debian-12-standard/{print $1; exit}')
  fi

  [[ -z "$tmpl" ]] && msg_error "Template not found after download attempt."
  msg_ok "Template: $tmpl"
  echo "$tmpl"
}

# ── Interactive prompts (reads from /dev/tty so curl-pipe works) ──────────────
ask() {
  local var="$1" prompt="$2" default="$3" val
  read -r -p "  $prompt [$default]: " val </dev/tty
  printf -v "$var" '%s' "${val:-$default}"
}

confirm() {
  local prompt="$1" ans
  read -r -p "  $prompt [y/N]: " ans </dev/tty
  [[ "${ans,,}" == y* ]]
}

# ── Detect defaults ───────────────────────────────────────────────────────────
STORAGE=$(find_rootfs_storage)
TMPL_STORAGE=$(find_template_storage)
CTID=$(next_ctid)

echo ""
echo -e "  ${BLD}Default settings:${NC}"
echo -e "  CT ID      : ${CY}${CTID}${NC}"
echo -e "  Hostname   : ${CY}${DEF_HOSTNAME}${NC}"
echo -e "  Rootfs     : ${CY}${STORAGE}${NC}  (template storage: ${TMPL_STORAGE})"
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

if confirm "Configure advanced settings? (RAM, disk, CPU, network…)"; then
  echo ""
  ask CTID      "CT ID"                   "$CTID"
  ask HOSTNAME  "Hostname"                "$DEF_HOSTNAME"
  ask STORAGE   "Rootfs storage"          "$STORAGE"
  ask RAM       "RAM (MB)"                "$DEF_RAM"
  ask SWAP      "Swap (MB)"               "$DEF_SWAP"
  ask DISK      "Disk size (GB)"          "$DEF_DISK"
  ask CPU       "CPU cores"               "$DEF_CPU"
  ask BRIDGE    "Network bridge"          "$DEF_BRIDGE"
  ask NET_IP    "IP (dhcp or x.x.x.x/x)" "$DEF_NET"
  if [[ "$NET_IP" != "dhcp" ]]; then
    ask NET_GW  "Gateway"                 ""
  fi
  echo ""
fi

# ── Template ──────────────────────────────────────────────────────────────────
TEMPLATE=$(ensure_template "$TMPL_STORAGE")

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
  --hostname     "$HOSTNAME"       \
  --memory       "$RAM"            \
  --swap         "$SWAP"           \
  --cores        "$CPU"            \
  --rootfs       "${STORAGE}:${DISK}" \
  --net0         "$NET_CONFIG"     \
  --features     nesting=1         \
  --unprivileged 1                 \
  --ostype       debian            \
  --start        0                 \
  --onboot       1                 \
  || msg_error "pct create failed (see output above). Check storage name and available space."
msg_ok "Container ${CTID} created"

# ── Start and wait ────────────────────────────────────────────────────────────
msg_info "Starting container…"
pct start "$CTID" || msg_error "pct start ${CTID} failed."

for i in $(seq 1 30); do
  pct exec "$CTID" -- true &>/dev/null 2>&1 && break
  sleep 1
done
pct exec "$CTID" -- true &>/dev/null 2>&1 \
  || msg_error "Container ${CTID} did not become ready after 30 s."
msg_ok "Container running"

# ── Bootstrap inside the container ────────────────────────────────────────────
msg_info "Installing git inside container…"
pct exec "$CTID" -- bash -c "
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq git curl ca-certificates
" || msg_error "Failed to install prerequisites inside the container."
msg_ok "Prerequisites ready"

msg_info "Cloning DynaDash (branch: ${BRANCH})…"
pct exec "$CTID" -- bash -c "
  git clone --branch '${BRANCH}' --depth 1 '${REPO}' '${APP_DIR}'
" || msg_error "git clone failed. Check internet connectivity inside the container."
msg_ok "Repository cloned to ${APP_DIR}"

msg_info "Running DynaDash installer inside container (takes a few minutes)…"
echo ""
pct exec "$CTID" -- bash "${APP_DIR}/install.sh" \
  || msg_error "install.sh failed (see output above)."

# ── Done ──────────────────────────────────────────────────────────────────────
CT_IP=$(pct exec "$CTID" -- bash -c "hostname -I | awk '{print \$1}'" 2>/dev/null \
        || echo "<container-ip>")

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
