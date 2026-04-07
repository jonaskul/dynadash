#!/usr/bin/env bash
# DynaDash — One-liner installer / updater
#
# Fresh install:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
#
# Update existing install:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jonaskul/dynadash/main/run.sh)"
#   (the script detects an existing installation and runs update instead)

set -euo pipefail

REPO="https://github.com/jonaskul/dynadash.git"
BRANCH="main"
INSTALL_DIR="/opt/dynadash"

# Colours
BL='\033[0;34m'
RD='\033[0;31m'
GN='\033[0;32m'
CY='\033[0;36m'
YW='\033[0;33m'
BLD='\033[1m'
NC='\033[0m'

header() {
  echo -e "
${BL}${BLD}  ██████╗ ██╗   ██╗███╗   ██╗ █████╗ ${NC}
${BL}${BLD}  ██╔══██╗╚██╗ ██╔╝████╗  ██║██╔══██╗${NC}
${CY}${BLD}  ██║  ██║ ╚████╔╝ ██╔██╗ ██║███████║${NC}
${CY}${BLD}  ██║  ██║  ╚██╔╝  ██║╚██╗██║██╔══██║${NC}
${CY}${BLD}  ██████╔╝   ██║   ██║ ╚████║██║  ██║${NC}
${CY}${BLD}  ╚═════╝    ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝${NC}
${CY}${BLD}  ██████╗  █████╗ ███████╗██╗  ██╗${NC}
${CY}${BLD}  ██╔══██╗██╔══██╗██╔════╝██║  ██║${NC}
${CY}${BLD}  ██║  ██║███████║███████╗███████║${NC}
${CY}${BLD}  ██║  ██║██╔══██║╚════██║██╔══██║${NC}
${CY}${BLD}  ██████╔╝██║  ██║███████║██║  ██║${NC}
${CY}${BLD}  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝${NC}
  ${YW}Dynalite lighting & HVAC dashboard${NC}
"
}

msg()   { echo -e "  ${CY}•${NC} $*"; }
ok()    { echo -e "  ${GN}✓${NC} $*"; }
warn()  { echo -e "  ${YW}!${NC} $*"; }
err()   { echo -e "  ${RD}✗${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && err "Run as root:  sudo bash -c \"\$(curl -fsSL ...)\""

header

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  # ── UPDATE ──────────────────────────────────────────────────────────────
  echo -e "  ${BLD}Existing installation found — updating…${NC}\n"
  cd "${INSTALL_DIR}"
  msg "Pulling latest code…"
  git fetch origin "${BRANCH}" -q
  git reset --hard "origin/${BRANCH}" -q
  ok "Code updated to $(git rev-parse --short HEAD)"
  bash "${INSTALL_DIR}/update.sh" --skip-pull
else
  # ── FRESH INSTALL ────────────────────────────────────────────────────────
  echo -e "  ${BLD}No existing installation found — installing to ${INSTALL_DIR}…${NC}\n"
  msg "Installing git…"
  apt-get update -qq
  apt-get install -y -qq git
  msg "Cloning DynaDash repository…"
  git clone --branch "${BRANCH}" --depth 1 "${REPO}" "${INSTALL_DIR}" -q
  ok "Repository cloned"
  bash "${INSTALL_DIR}/install.sh"
fi
