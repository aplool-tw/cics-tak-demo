#!/usr/bin/env bash
# demo-cot-gateway-map-3drones.sh — Start the full CoT Gateway pipeline with a
# 3-drone convergence scenario and open the browser-based tactical map at
# http://127.0.0.1:18092/map
#
# Services started (all local):
#   map-sim        :18090  — receives drone positions from UDS
#   uds            :18080 — plays back three-drone invasion scenario
#   echoshield-sim :19000  — radar feed → CoT Gateway (TCP NDJSON)
#                  :19001  — HTTP info (sensor position)
#   sentrycs-sim   :17070  — RF detection API → CoT Gateway
#   cot-gateway    :18092  — correlates tracks, exposes web map viewer
#
# Usage:
#   scripts/demo-cot-gateway-map-3drones.sh           # start demo
#   scripts/demo-cot-gateway-map-3drones.sh --stop    # stop running demo
#
# Prerequisites (install once):
#   pip install -e services/map-sim           --break-system-packages
#   pip install -e services/uds               --break-system-packages
#   pip install -e services/echoshield-sim    --break-system-packages
#   pip install -e services/sentrycs-sim      --break-system-packages
#   pip install -e services/cot-gateway       --break-system-packages

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── paths ──────────────────────────────────────────────────────────────────────
UDS_SCENARIO="${ROOT_DIR}/services/uds/scenarios/demo_three_drones.yaml"
ECHO_CONFIG="${ROOT_DIR}/services/echoshield-sim/config/demo.yaml"
SNTR_SCENARIO="${ROOT_DIR}/services/sentrycs-sim/config/demo_three_drones.yaml"
GW_CONFIG="${ROOT_DIR}/services/cot-gateway/config/demo.yaml"

MAP_URL="http://127.0.0.1:18092/map"
GW_HEALTH="http://127.0.0.1:18092/health"
MAPSIM_HEALTH="http://127.0.0.1:18090/health"
SNTR_HEALTH="http://127.0.0.1:17070/health"
ECHO_INFO="http://127.0.0.1:19001/info"

LOG_DIR="${ROOT_DIR}/.dev-runtime/logs"
PID_DIR="${ROOT_DIR}/.dev-runtime/pids"

SERVICES=(map-sim uds echoshield-sim sentrycs-sim cot-gateway)

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[gw-demo]${RESET} $*"; }
ok()   { echo -e "${GREEN}[gw-demo]${RESET} $*"; }
warn() { echo -e "${YELLOW}[gw-demo]${RESET} $*"; }
die()  { echo -e "${RED}[gw-demo] ERROR:${RESET} $*" >&2; exit 1; }

# ── PIDs (empty = not started) ─────────────────────────────────────────────────
MAPSIM_PID=""; UDS_PID=""; ECHO_PID=""; SNTR_PID=""; GW_PID=""

# ── cleanup (registered early so all exit paths are covered) ──────────────────
cleanup() {
    trap - INT TERM EXIT
    echo
    local any=false
    for var in MAPSIM_PID UDS_PID ECHO_PID SNTR_PID GW_PID; do
        pid="${!var}"
        if [[ -n "${pid}" ]]; then any=true; fi
    done
    if ${any}; then
        log "Shutting down demo services..."
        for var in GW_PID SNTR_PID ECHO_PID UDS_PID MAPSIM_PID; do
            pid="${!var}"
            [[ -n "${pid}" ]] && { kill -TERM "${pid}" 2>/dev/null || true; }
        done
        sleep 1
        for var in GW_PID SNTR_PID ECHO_PID UDS_PID MAPSIM_PID; do
            pid="${!var}"
            [[ -n "${pid}" ]] && { kill -KILL "${pid}" 2>/dev/null || true; }
        done
        for svc in "${SERVICES[@]}"; do
            rm -f "${PID_DIR}/${svc}.pid"
        done
        ok "Stopped. Logs saved in ${LOG_DIR}/"
    fi
}
trap cleanup INT TERM EXIT

# ── banner ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  +===============================================================+"
echo "  |  CoT Gateway — Tactical Map Demo (3-drone staggered)       |"
echo "  |  TRK-E01(N/35ms) TRK-E02(NW/25ms) TRK-E03(NE/22ms)       |"
echo "  +===============================================================+"
echo -e "${RESET}"

# ── --stop mode ────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    trap - INT TERM EXIT
    log "Stopping demo services..."
    for svc in "${SERVICES[@]}"; do
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

# ── pre-flight ─────────────────────────────────────────────────────────────────
[[ -f "${UDS_SCENARIO}"   ]] || die "UDS scenario not found: ${UDS_SCENARIO}"
[[ -f "${ECHO_CONFIG}"    ]] || die "EchoShield config not found: ${ECHO_CONFIG}"
[[ -f "${SNTR_SCENARIO}"  ]] || die "Sentrycs config not found: ${SNTR_SCENARIO}"
[[ -f "${GW_CONFIG}"      ]] || die "CoT Gateway config not found: ${GW_CONFIG}"
command -v python3 &>/dev/null || die "python3 not found in PATH"

for mod in map_sim uds echoshield_sim sentrycs_sim cot_gateway; do
    python3 -c "import ${mod}" 2>/dev/null \
        || die "${mod} not installed — run: pip install -e services/${mod//_/-} --break-system-packages"
done

mkdir -p "${LOG_DIR}" "${PID_DIR}"

# ── scenario summary ───────────────────────────────────────────────────────────
echo
log "Three-drone staggered scenario (different distances & speeds):"
echo "  TRK-E01 (N)  : 24.757282N, 121.033750E  3.5km  35m/s  heading 180°"
echo "  TRK-E02 (NW) : 24.754419N, 121.002238E  4.5km  25m/s  heading 135°"
echo "  TRK-E03 (NE) : 24.749968N, 121.060359E  3.8km  22m/s  heading 225°"
echo "  SP (target)  : 24.725806N, 121.033750E"
echo "  HP (holding) : 24.735344N, 121.044252E  (NE 45°, 1.5km from SP)"
echo
echo "  Timeline (staggered by speed/distance):"
echo "    t=  9s : TRK-E01 enters EchoShield 3.2km range"
echo "    t= 27s : TRK-E03 enters EchoShield 3.2km range"
echo "    t= 43s : TRK-E01 DETECTED (Sentrycs 2km ring)"
echo "    t= 52s : TRK-E02 enters EchoShield 3.2km range"
echo "    t= 71s : TRK-E01 perimeter breach → MITIGATING → redirected to HP"
echo "    t= 82s : TRK-E03 DETECTED"
echo "    t=100s : TRK-E02 DETECTED"
echo "    t=120s : TRK-E01 NEUTRALIZED"
echo "    t=127s : TRK-E03 perimeter breach → MITIGATING → redirected to HP"
echo "    t=140s : TRK-E02 perimeter breach → MITIGATING → redirected to HP"
echo "    t=200s : TRK-E03 NEUTRALIZED"
echo "    t=210s : TRK-E02 NEUTRALIZED"
echo

# ── launch map-sim ─────────────────────────────────────────────────────────────
log "Starting map-sim on :18090..."
(cd "${ROOT_DIR}/services/map-sim" && exec python3 -m map_sim --port 18090) \
    >> "${LOG_DIR}/map-sim.log" 2>&1 &
MAPSIM_PID=$!
echo "${MAPSIM_PID}" > "${PID_DIR}/map-sim.pid"

# ── launch uds ─────────────────────────────────────────────────────────────────
log "Starting uds on :18080 with three-drone scenario..."
(cd "${ROOT_DIR}/services/uds" && exec python3 -m uds \
    --scenario "${UDS_SCENARIO}" \
    --api-port 18080 \
    --map-sim-url "http://127.0.0.1:18090") \
    >> "${LOG_DIR}/uds.log" 2>&1 &
UDS_PID=$!
echo "${UDS_PID}" > "${PID_DIR}/uds.pid"

# ── launch echoshield-sim ──────────────────────────────────────────────────────
log "Starting echoshield-sim (TCP :19000, HTTP /info :19001)..."
(cd "${ROOT_DIR}/services/echoshield-sim" && exec python3 -m echoshield_sim \
    --config "${ECHO_CONFIG}") \
    >> "${LOG_DIR}/echoshield-sim.log" 2>&1 &
ECHO_PID=$!
echo "${ECHO_PID}" > "${PID_DIR}/echoshield-sim.pid"

# ── launch sentrycs-sim ────────────────────────────────────────────────────────
log "Starting sentrycs-sim on :17070..."
(cd "${ROOT_DIR}/services/sentrycs-sim" && exec python3 -m sentrycs_sim \
    --scenario "${SNTR_SCENARIO}") \
    >> "${LOG_DIR}/sentrycs-sim.log" 2>&1 &
SNTR_PID=$!
echo "${SNTR_PID}" > "${PID_DIR}/sentrycs-sim.pid"

# ── launch cot-gateway ─────────────────────────────────────────────────────────
log "Starting cot-gateway (web map :18092)..."
(cd "${ROOT_DIR}/services/cot-gateway" && exec python3 -m cot_gateway \
    --config "${GW_CONFIG}") \
    >> "${LOG_DIR}/cot-gateway.log" 2>&1 &
GW_PID=$!
echo "${GW_PID}" > "${PID_DIR}/cot-gateway.pid"

log "PIDs: map-sim=${MAPSIM_PID} uds=${UDS_PID} echo=${ECHO_PID} sntr=${SNTR_PID} gw=${GW_PID}"
log "Logs: ${LOG_DIR}/"
echo

# ── health check loop ──────────────────────────────────────────────────────────
log "Waiting for all services to become healthy (up to 30s)..."
TIMEOUT=30
START=$(date +%s)
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - START ))

    for var_svc in "MAPSIM_PID:map-sim" "UDS_PID:uds" "ECHO_PID:echoshield-sim" "SNTR_PID:sentrycs-sim" "GW_PID:cot-gateway"; do
        var="${var_svc%%:*}"; svc="${var_svc##*:}"
        pid="${!var}"
        if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
            echo
            die "${svc} (pid ${pid}) exited unexpectedly. Check ${LOG_DIR}/${svc}.log"
        fi
    done

    if (( ELAPSED >= TIMEOUT )); then
        echo
        warn "Timed out — services may still be starting. Proceeding..."
        break
    fi

    MAP_OK=false; SNTR_OK=false; ECHO_OK=false; GW_OK=false; UDS_OK=false
    curl -sf "${MAPSIM_HEALTH}" -o /dev/null 2>/dev/null && MAP_OK=true || true
    curl -sf "${SNTR_HEALTH}"   -o /dev/null 2>/dev/null && SNTR_OK=true || true
    curl -sf "${ECHO_INFO}"     -o /dev/null 2>/dev/null && ECHO_OK=true || true
    curl -sf "${GW_HEALTH}"     -o /dev/null 2>/dev/null && GW_OK=true  || true
    bash -c "echo > /dev/tcp/127.0.0.1/18080" 2>/dev/null             && UDS_OK=true || true

    if ${MAP_OK} && ${SNTR_OK} && ${ECHO_OK} && ${GW_OK} && ${UDS_OK}; then
        echo
        ok "All services healthy ✓"
        break
    fi

    printf "\r  %2ds  map:%s  uds:%s  echo:%s  sntr:%s  gw:%s  " \
        "${ELAPSED}" \
        "$(${MAP_OK}  && echo '✓' || echo '·')" \
        "$(${UDS_OK}  && echo '✓' || echo '·')" \
        "$(${ECHO_OK} && echo '✓' || echo '·')" \
        "$(${SNTR_OK} && echo '✓' || echo '·')" \
        "$(${GW_OK}   && echo '✓' || echo '·')"
    sleep 1
done

# ── timeline reminder ──────────────────────────────────────────────────────────
echo
log "Timeline (staggered by speed/distance):"
echo "    t=  9s  TRK-E01 enters EchoShield 3.2km — first ECHO track on map"
echo "    t= 27s  TRK-E03 enters EchoShield 3.2km range"
echo "    t= 43s  TRK-E01 crosses 2km Sentrycs ring — DETECTED (fused → red)"
echo "    t= 52s  TRK-E02 enters EchoShield 3.2km range"
echo "    t= 71s  TRK-E01 perimeter breach → MITIGATING → takeover → HP"
echo "    t= 82s  TRK-E03 DETECTED"
echo "    t=100s  TRK-E02 DETECTED"
echo "    t=120s  TRK-E01 NEUTRALIZED"
echo "    t=127s  TRK-E03 perimeter breach → MITIGATING → takeover → HP"
echo "    t=140s  TRK-E02 perimeter breach → MITIGATING → takeover → HP"
echo "    t=200s  TRK-E03 NEUTRALIZED"
echo "    t=210s  TRK-E02 NEUTRALIZED"
echo

# ── open browser ───────────────────────────────────────────────────────────────
ok "Map viewer:  ${BOLD}${MAP_URL}${RESET}"
echo
echo -e "  Legend on map:"
echo "    ◆  EchoShield track  (cyan)     ⬡  Sentrycs track (yellow)"
echo "    ✈  Fused/correlated track (red)     ⊕  Strategic Point + rings"
echo "    H  Holding/landing point"
echo
echo -e "  Logs : ${LOG_DIR}/"
echo
xdg-open "${MAP_URL}" 2>/dev/null \
    || open  "${MAP_URL}" 2>/dev/null \
    || true
echo -e "  ${YELLOW}Press Ctrl-C to stop all demo services.${RESET}"
echo

# ── block until Ctrl-C or a service exits ──────────────────────────────────────
wait "${MAPSIM_PID}" "${UDS_PID}" "${ECHO_PID}" "${SNTR_PID}" "${GW_PID}" || true
