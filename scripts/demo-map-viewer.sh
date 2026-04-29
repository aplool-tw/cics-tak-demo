#!/usr/bin/env bash
# demo-map-viewer.sh — Start UDS + Map Sim with a 3-drone scenario
# and open the Leaflet.js map viewer for live validation.
#
# Usage:
#   scripts/demo-map-viewer.sh              # default: 3-drone multi-direction
#   scripts/demo-map-viewer.sh --stop       # stop running demo services
#
# Prerequisites: map-sim and uds must be installed (pip install -e services/...)
# The script delegates to dev-launcher.sh for service lifecycle management.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCHER="${SCRIPT_DIR}/dev-launcher.sh"
SCENARIO="${ROOT_DIR}/services/uds/scenarios/e2e_multi_drone.yaml"
MAP_URL="http://127.0.0.1:8090/map"
HEALTH_URL="http://127.0.0.1:8090/health"
UDS_HEALTH_URL="http://127.0.0.1:8080/health"

# ── colours ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[demo]${RESET} $*"; }
ok()   { echo -e "${GREEN}[demo]${RESET} $*"; }
warn() { echo -e "${YELLOW}[demo]${RESET} $*"; }
die()  { echo -e "${RED}[demo] ERROR:${RESET} $*" >&2; exit 1; }

# ── banner ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║  MAP SIM — Drone Tracker Demo (3 drones, Leaflet.js) ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── --stop passthrough ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    log "Stopping demo services (map-sim + uds)..."
    bash "${LAUNCHER}" --stop --services map-sim,uds
    ok "Services stopped."
    exit 0
fi

# ── pre-flight checks ─────────────────────────────────────────────────────────
[[ -f "${LAUNCHER}" ]]  || die "dev-launcher.sh not found at ${LAUNCHER}"
[[ -f "${SCENARIO}" ]]  || die "3-drone scenario not found at ${SCENARIO}"
command -v python3 &>/dev/null || die "python3 not found in PATH"

# ── print scenario summary ────────────────────────────────────────────────────
log "Scenario : ${SCENARIO}"
echo
echo -e "  ${BOLD}三架無人機劇本 — 同時從不同方向逼近目標${RESET}"
echo    "  ┌──────────┬────────────────────────────┬─────────┬──────────┐"
echo    "  │ Drone ID │ 起始位置                   │ 速度    │ 方向     │"
echo    "  ├──────────┼────────────────────────────┼─────────┼──────────┤"
echo    "  │ TRK-E0A  │ 24.806556, 121.033750 (北) │ 12 m/s  │ 正南 ↓   │"
echo    "  │ TRK-E0B  │ 24.725806, 120.962306 (西) │ 12 m/s  │ 正東 →   │"
echo    "  │ TRK-E0C  │ 24.784500, 121.087278 (東北)│ 12 m/s  │ 西南 ↙  │"
echo    "  └──────────┴────────────────────────────┴─────────┴──────────┘"
echo    "  目標 SP : 24.725806N, 121.033750E"
echo

# ── launch services via dev-launcher.sh ──────────────────────────────────────
log "Starting map-sim (port 8090) + uds (port 8080)..."
bash "${LAUNCHER}" \
    --services map-sim,uds \
    --uds-scenario "${SCENARIO}" &
LAUNCHER_PID=$!

# ── wait for both services to be healthy ─────────────────────────────────────
log "Waiting for services to become healthy..."
TIMEOUT=30
START=$(date +%s)
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - START ))
    if (( ELAPSED > TIMEOUT )); then
        warn "Timed out waiting for services after ${TIMEOUT}s."
        warn "Check logs in .dev-runtime/logs/ for details."
        break
    fi

    MAP_OK=false; UDS_OK=false
    curl -sf "${HEALTH_URL}" -o /dev/null 2>/dev/null && MAP_OK=true
    curl -sf "${UDS_HEALTH_URL}" -o /dev/null 2>/dev/null && UDS_OK=true

    if ${MAP_OK} && ${UDS_OK}; then
        ok "map-sim ✓  uds ✓ — both services ready"
        break
    fi

    printf "\r  waiting... %ds  (map-sim: %s  uds: %s)" \
        "${ELAPSED}" \
        "$(${MAP_OK} && echo '✓' || echo '…')" \
        "$(${UDS_OK} && echo '✓' || echo '…')"
    sleep 1
done
echo

# ── drones start staggered — remind the user ─────────────────────────────────
echo -e "${BOLD}  Drone start timeline:${RESET}"
echo    "    t=  0s  TRK-E0A begins flying"
echo    "    t= 30s  TRK-E0B begins flying"
echo    "    t= 60s  TRK-E0C begins flying"
echo

# ── print map URL ─────────────────────────────────────────────────────────────
ok "Map viewer ready →  ${BOLD}${MAP_URL}${RESET}"
echo
log "Opening map in default browser (if available)..."
# Try common commands; ignore failure gracefully
xdg-open "${MAP_URL}" 2>/dev/null \
    || open "${MAP_URL}" 2>/dev/null \
    || warn "Could not open browser automatically. Please open manually: ${MAP_URL}"

echo
echo -e "  ${YELLOW}Press Ctrl-C to stop all demo services.${RESET}"
echo

# ── wait for Ctrl-C ───────────────────────────────────────────────────────────
cleanup() {
    echo
    log "Shutting down demo services..."
    bash "${LAUNCHER}" --stop --services map-sim,uds 2>/dev/null || true
    kill "${LAUNCHER_PID}" 2>/dev/null || true
    ok "Done. Logs saved in .dev-runtime/logs/"
}
trap cleanup INT TERM

wait "${LAUNCHER_PID}" || true
