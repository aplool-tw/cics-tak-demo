#!/usr/bin/env bash
# demo-map-viewer.sh - Start UDS + Map Sim with a 3-drone scenario
# and open the Leaflet.js map viewer for live validation.
#
# Usage:
#   scripts/demo-map-viewer.sh              # start 3-drone demo
#   scripts/demo-map-viewer.sh --stop       # stop any running demo services
#
# Prerequisites: map-sim and uds must be installed
#   pip install -e services/map-sim --break-system-packages
#   pip install -e services/uds --break-system-packages

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCENARIO="${ROOT_DIR}/services/uds/scenarios/e2e_multi_drone.yaml"
MAP_URL="http://127.0.0.1:18090/map"
HEALTH_URL="http://127.0.0.1:18090/health"
UDS_HEALTH_URL="http://127.0.0.1:18080/health"
MAP_SIM_PORT="18090"
UDS_PORT="18080"
LOG_DIR="${ROOT_DIR}/.dev-runtime/logs"
PID_DIR="${ROOT_DIR}/.dev-runtime/pids"

# PIDs initialised empty so cleanup() is safe even on early exit
MAP_PID=""
UDS_PID=""

# --- colours -----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[demo]${RESET} $*"; }
ok()   { echo -e "${GREEN}[demo]${RESET} $*"; }
warn() { echo -e "${YELLOW}[demo]${RESET} $*"; }
die()  { echo -e "${RED}[demo] ERROR:${RESET} $*" >&2; exit 1; }

# --- cleanup (registered early so ALL exit paths are covered) ----------------
cleanup() {
    trap - INT TERM EXIT
    echo
    if [[ -n "${MAP_PID}" ]] || [[ -n "${UDS_PID}" ]]; then
        log "Shutting down demo services..."
        [[ -n "${MAP_PID}" ]] && { kill -TERM "${MAP_PID}" 2>/dev/null || true; }
        [[ -n "${UDS_PID}" ]] && { kill -TERM "${UDS_PID}" 2>/dev/null || true; }
        sleep 1
        [[ -n "${MAP_PID}" ]] && { kill -KILL "${MAP_PID}" 2>/dev/null || true; }
        [[ -n "${UDS_PID}" ]] && { kill -KILL "${UDS_PID}" 2>/dev/null || true; }
        rm -f "${PID_DIR}/map-sim.pid" "${PID_DIR}/uds.pid"
        ok "Done. Logs saved in ${LOG_DIR}/"
    fi
}
trap cleanup INT TERM EXIT

# --- banner ------------------------------------------------------------------
echo -e "${BOLD}"
echo "  +========================================================+"
echo "  |  MAP SIM -- Drone Tracker Demo (3 drones, Leaflet.js) |"
echo "  +========================================================+"
echo -e "${RESET}"

# --- --stop mode -------------------------------------------------------------
if [[ "${1:-}" == "--stop" ]]; then
    trap - INT TERM EXIT   # suppress cleanup() since we do it manually
    log "Stopping demo services..."
    for svc in map-sim uds; do
        pidfile="${PID_DIR}/${svc}.pid"
        if [[ -f "${pidfile}" ]]; then
            pid=$(<"${pidfile}")
            if kill -0 "${pid}" 2>/dev/null; then
                kill -TERM "${pid}" 2>/dev/null && ok "stopped ${svc} (pid ${pid})" || true
            else
                warn "${svc}: pid ${pid} not running"
            fi
            rm -f "${pidfile}"
        else
            warn "${svc}: no pid file found"
        fi
    done
    ok "Done."
    exit 0
fi

# --- pre-flight --------------------------------------------------------------
[[ -f "${SCENARIO}" ]] || die "3-drone scenario not found: ${SCENARIO}"
command -v python3 &>/dev/null || die "python3 not found in PATH"
python3 -c "import map_sim" 2>/dev/null \
    || die "map_sim not installed -- run: pip install -e services/map-sim --break-system-packages"
python3 -c "import uds" 2>/dev/null \
    || die "uds not installed -- run: pip install -e services/uds --break-system-packages"

mkdir -p "${LOG_DIR}" "${PID_DIR}"

# --- print scenario summary --------------------------------------------------
log "Scenario : ${SCENARIO}"
echo
log "3-drone scenario: different directions toward SP(24.725806N,121.033750E)"
echo "  TRK-E0A  24.806556, 121.033750 (North)   12m/s  South"
echo "  TRK-E0B  24.725806, 120.962306 (West )   12m/s  East"
echo "  TRK-E0C  24.784500, 121.087278 (NE   )   12m/s  SW"
echo

# --- launch map-sim ----------------------------------------------------------
log "Starting map-sim on port ${MAP_SIM_PORT}..."
(
    cd "${ROOT_DIR}/services/map-sim"
    exec python3 -m map_sim --port "${MAP_SIM_PORT}"
) >> "${LOG_DIR}/map-sim.log" 2>&1 &
MAP_PID=$!
echo "${MAP_PID}" > "${PID_DIR}/map-sim.pid"

# --- launch uds --------------------------------------------------------------
log "Starting uds on port ${UDS_PORT} with e2e_multi_drone scenario..."
(
    cd "${ROOT_DIR}/services/uds"
    exec python3 -m uds \
        --scenario "${SCENARIO}" \
        --api-port "${UDS_PORT}" \
        --map-sim-url "http://127.0.0.1:${MAP_SIM_PORT}"
) >> "${LOG_DIR}/uds.log" 2>&1 &
UDS_PID=$!
echo "${UDS_PID}" > "${PID_DIR}/uds.pid"

log "map-sim PID=${MAP_PID}  uds PID=${UDS_PID}"
log "Logs: ${LOG_DIR}/map-sim.log  ${LOG_DIR}/uds.log"

# --- health check loop -------------------------------------------------------
log "Waiting for services to become healthy (up to 30s)..."
TIMEOUT=30
START=$(date +%s)
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - START ))

    if ! kill -0 "${MAP_PID}" 2>/dev/null; then
        echo
        die "map-sim exited unexpectedly. Check ${LOG_DIR}/map-sim.log"
    fi
    if ! kill -0 "${UDS_PID}" 2>/dev/null; then
        echo
        die "uds exited unexpectedly. Check ${LOG_DIR}/uds.log"
    fi

    if (( ELAPSED >= TIMEOUT )); then
        echo
        warn "Timed out after ${TIMEOUT}s -- services may still be starting."
        warn "Check logs in ${LOG_DIR}/"
        break
    fi

    MAP_OK=false; UDS_OK=false
    curl -sf "${HEALTH_URL}" -o /dev/null 2>/dev/null && MAP_OK=true
    bash -c "echo > /dev/tcp/127.0.0.1/${UDS_PORT}" 2>/dev/null && UDS_OK=true

    if ${MAP_OK} && ${UDS_OK}; then
        echo
        ok "map-sim ok  uds ok  -- both services healthy"
        break
    fi

    printf "\r  waiting... %2ds  (map-sim: %s  uds: %s)  " \
        "${ELAPSED}" \
        "$(${MAP_OK} && echo 'ok' || echo '..')" \
        "$(${UDS_OK} && echo 'ok' || echo '..')"
    sleep 1
done

# --- drone timeline reminder -------------------------------------------------
echo
log "Drone start timeline:"
echo "    t=  0s  TRK-E0A begins flying (North -> South)"
echo "    t= 30s  TRK-E0B begins flying (West  -> East )"
echo "    t= 60s  TRK-E0C begins flying (NE    -> SW   )"
echo

# --- open browser ------------------------------------------------------------
ok "Map viewer: ${BOLD}${MAP_URL}${RESET}"
echo
xdg-open "${MAP_URL}" 2>/dev/null \
    || open  "${MAP_URL}" 2>/dev/null \
    || true

echo -e "  ${YELLOW}Ctrl-C to stop all demo services.${RESET}"
echo

# --- block until Ctrl-C or a service exits -----------------------------------
wait "${MAP_PID}" "${UDS_PID}" || true
