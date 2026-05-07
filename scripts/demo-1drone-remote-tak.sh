#!/usr/bin/env bash
# demo-1drone-remote-tak.sh — Start the TAK pipeline with optional remote TAK server support.
#
# LOCAL MODE (default):  starts tak-relay locally, same as demo-1drone.sh
# REMOTE MODE (TAK_HOST): skips tak-relay, connects cot-gateway directly to real TAK server
#
# Usage (local):
#   bash scripts/demo-1drone-remote-tak.sh
#
# Usage (remote TAK server):
#   TAK_HOST=192.168.1.100 bash scripts/demo-1drone-remote-tak.sh
#   TAK_HOST=192.168.1.100 TAK_PORT=8089 TAK_USE_SSL=true bash scripts/demo-1drone-remote-tak.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── paths ──────────────────────────────────────────────────────────────────────
UDS_SCENARIO="${ROOT_DIR}/services/uds/scenarios/demo_single_drone.yaml"
ECHO_CONFIG="${ROOT_DIR}/services/echoshield-sim/config/demo.yaml"
SNTR_CONFIG="${ROOT_DIR}/services/sentrycs-sim/config/demo.yaml"
GW_CONFIG="${ROOT_DIR}/services/cot-gateway/config/demo.yaml"
TAK_CLIENT_CONFIG="${ROOT_DIR}/services/tak-client-sim/config/demo.yaml"

LOG_DIR="${ROOT_DIR}/.dev-runtime/logs"
PID_DIR="${ROOT_DIR}/.dev-runtime/pids"

# Remote TAK server support: set TAK_HOST env var to point to real TAK server
# TAK_PORT defaults to 8089, TAK_USE_SSL defaults to true
REMOTE_TAK_MODE=false
if [[ -n "${TAK_HOST:-}" ]]; then
    REMOTE_TAK_MODE=true
fi

TAK_PORT="${TAK_PORT:-8089}"
TAK_USE_SSL="${TAK_USE_SSL:-true}"

# Services list differs by mode
if [[ "${REMOTE_TAK_MODE}" == "true" ]]; then
    SERVICES=(map-sim uds echoshield-sim sentrycs-sim cot-gateway tak-client-sim)
else
    SERVICES=(map-sim uds echoshield-sim sentrycs-sim cot-gateway tak-relay tak-client-sim)
fi

URLS=(
    "http://127.0.0.1:8090/map"
    "http://127.0.0.1:8092/map"
    "http://127.0.0.1:8093/map"
)

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
YELLOW=$'\033[1;33m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

log() {
    printf '%s[tak-demo]%s %s\n' "${CYAN}" "${RESET}" "$*"
}

ok() {
    printf '%s[tak-demo]%s %s\n' "${GREEN}" "${RESET}" "$*"
}

warn() {
    printf '%s[tak-demo]%s %s\n' "${YELLOW}" "${RESET}" "$*"
}

die() {
    printf '%s[tak-demo] ERROR:%s %s\n' "${RED}" "${RESET}" "$*" >&2
    exit 1
}

pid_file() {
    local service="$1"
    printf '%s/%s.pid' "${PID_DIR}" "${service}"
}

assert_file() {
    local path="$1"
    local label="$2"
    [[ -f "${path}" ]] || die "${label} not found: ${path}"
}

check_port_free() {
    local port="$1"
    if (echo >"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1; then
        die "Port ${port} is already in use"
    fi
}

tcp_ready() {
    local port="$1"
    (echo >"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1
}

write_pid() {
    local service="$1"
    local pid="$2"
    printf '%s\n' "${pid}" >"$(pid_file "${service}")"
}

remove_pid_files() {
    local service=""
    for service in "${SERVICES[@]}"; do
        rm -f "$(pid_file "${service}")"
    done
}

status_mark() {
    local ready="$1"
    if [[ "${ready}" == "true" ]]; then
        printf '✓'
    else
        printf '·'
    fi
}

open_url() {
    local url="$1"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${url}" 2>/dev/null || printf 'Open manually: %s\n' "${url}"
    elif command -v open >/dev/null 2>&1; then
        open "${url}" 2>/dev/null || printf 'Open manually: %s\n' "${url}"
    else
        printf 'Open manually: %s\n' "${url}"
    fi
}

MAPSIM_PID=""
UDS_PID=""
ECHO_PID=""
SNTR_PID=""
GW_PID=""
RELAY_PID=""
TAK_CLIENT_PID=""

cleanup() {
    trap - INT TERM EXIT
    echo

    local any=false
    local pid=""
    for pid in "${MAPSIM_PID}" "${UDS_PID}" "${ECHO_PID}" "${SNTR_PID}" "${GW_PID}" "${RELAY_PID}" "${TAK_CLIENT_PID}"; do
        if [[ -n "${pid}" ]]; then
            any=true
            break
        fi
    done

    if [[ "${any}" == "true" ]]; then
        log "Shutting down demo services..."
        for pid in "${TAK_CLIENT_PID}" "${RELAY_PID}" "${GW_PID}" "${SNTR_PID}" "${ECHO_PID}" "${UDS_PID}" "${MAPSIM_PID}"; do
            if [[ -n "${pid}" ]]; then
                kill -TERM "${pid}" 2>/dev/null || true
            fi
        done
        sleep 1
        for pid in "${TAK_CLIENT_PID}" "${RELAY_PID}" "${GW_PID}" "${SNTR_PID}" "${ECHO_PID}" "${UDS_PID}" "${MAPSIM_PID}"; do
            if [[ -n "${pid}" ]]; then
                kill -KILL "${pid}" 2>/dev/null || true
            fi
        done
    fi

    remove_pid_files
    ok "Stopped. Logs saved in ${LOG_DIR}/"
}

stop_from_pidfiles() {
    trap - INT TERM EXIT
    log "Stopping demo services..."

    local service=""
    local pidfile=""
    local pid=""
    for service in "${SERVICES[@]}"; do
        pidfile="$(pid_file "${service}")"
        if [[ -f "${pidfile}" ]]; then
            pid="$(<"${pidfile}")"
            if kill -0 "${pid}" 2>/dev/null; then
                kill -TERM "${pid}" 2>/dev/null || true
                ok "stopped ${service} (pid ${pid})"
            else
                warn "${service}: pid ${pid} not running"
            fi
            rm -f "${pidfile}"
        else
            warn "${service}: no pid file found"
        fi
    done

    ok "Done."
    exit 0
}

preflight() {
    command -v python3 >/dev/null 2>&1 || die "python3 not found in PATH"
    command -v curl >/dev/null 2>&1 || die "curl not found in PATH"

    assert_file "${UDS_SCENARIO}" "UDS scenario"
    assert_file "${ECHO_CONFIG}" "EchoShield config"
    assert_file "${SNTR_CONFIG}" "Sentrycs config"
    assert_file "${GW_CONFIG}" "CoT Gateway config"
    assert_file "${TAK_CLIENT_CONFIG}" "TAK client config"

    if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
        assert_file "${ROOT_DIR}/scripts/tak_relay.py" "tak_relay script"
    fi

    local module=""
    for module in map_sim uds echoshield_sim sentrycs_sim cot_gateway tak_client_sim; do
        python3 -c "import ${module}" 2>/dev/null \
            || die "${module} not installed — run: pip install -e services/${module//_/-} --break-system-packages"
    done

    mkdir -p "${LOG_DIR}" "${PID_DIR}"

    local port=""
    for port in 8090 8092 8093 18080 7070; do
        check_port_free "${port}"
    done

    # Only check local relay port in local mode
    if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
        check_port_free 8089
    fi
}

check_dead_processes() {
    local pid="$1"
    local service="$2"
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then
        die "${service} (pid ${pid}) exited unexpectedly. Check ${LOG_DIR}/${service}.log"
    fi
}

wait_for_health() {
    log "Waiting for all services to become healthy (up to 30s)..."

    local timeout=30
    local start=""
    local now=0

    start="$(date +%s)"
    local elapsed=0
    local map_ok=false
    local uds_ok=false
    local echo_ok=false
    local sntr_ok=false
    local gw_ok=false
    local relay_ok=false
    local tak_ok=false

    while true; do
        now="$(date +%s)"
        elapsed=$((now - start))

        check_dead_processes "${MAPSIM_PID}" "map-sim"
        check_dead_processes "${UDS_PID}" "uds"
        check_dead_processes "${ECHO_PID}" "echoshield-sim"
        check_dead_processes "${SNTR_PID}" "sentrycs-sim"
        check_dead_processes "${GW_PID}" "cot-gateway"
        if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
            check_dead_processes "${RELAY_PID}" "tak-relay"
        fi
        check_dead_processes "${TAK_CLIENT_PID}" "tak-client-sim"

        map_ok=false
        uds_ok=false
        echo_ok=false
        sntr_ok=false
        gw_ok=false
        relay_ok=false
        tak_ok=false

        curl -sf "http://127.0.0.1:8090/health" -o /dev/null 2>/dev/null && map_ok=true || true
        curl -sf "http://127.0.0.1:9001/info" -o /dev/null 2>/dev/null && echo_ok=true || true
        curl -sf "http://127.0.0.1:7070/health" -o /dev/null 2>/dev/null && sntr_ok=true || true
        curl -sf "http://127.0.0.1:8092/health" -o /dev/null 2>/dev/null && gw_ok=true || true
        curl -sf "http://127.0.0.1:8093/health" -o /dev/null 2>/dev/null && tak_ok=true || true
        tcp_ready 18080 && uds_ok=true || true

        if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
            tcp_ready 8089 && relay_ok=true || true
        else
            relay_ok=true  # skip relay check in remote mode
        fi

        if [[ "${map_ok}" == "true" && "${uds_ok}" == "true" && "${echo_ok}" == "true" && "${sntr_ok}" == "true" && "${gw_ok}" == "true" && "${relay_ok}" == "true" && "${tak_ok}" == "true" ]]; then
            printf '\n'
            ok "All services healthy ✓"
            return
        fi

        if (( elapsed >= timeout )); then
            printf '\n'
            die "Timed out waiting for services to become healthy"
        fi

        printf '\r  %2ds  map:%s uds:%s echo:%s sntr:%s gw:%s relay:%s tak:%s' \
            "${elapsed}" \
            "$(status_mark "${map_ok}")" \
            "$(status_mark "${uds_ok}")" \
            "$(status_mark "${echo_ok}")" \
            "$(status_mark "${sntr_ok}")" \
            "$(status_mark "${gw_ok}")" \
            "$(status_mark "${relay_ok}")" \
            "$(status_mark "${tak_ok}")"
        sleep 1
    done
}

print_banner() {
    printf '%s\n' "${BOLD}"
    if [[ "${REMOTE_TAK_MODE}" == "true" ]]; then
        echo "  +=================================================================+"
        echo "  |  TAK pipeline demo (single-drone) — REMOTE TAK SERVER MODE     |"
        echo "  |  map-sim → uds → echoshield → sentrycs → gw → [${TAK_HOST}:${TAK_PORT}]  |"
        echo "  +=================================================================+"
        printf '%s\n' "${RESET}"
        echo
        log "Remote TAK server: ${TAK_HOST}:${TAK_PORT} (SSL=${TAK_USE_SSL})"
        warn "Ensure TAK_HOST is reachable and certificates are in place."
        echo "  cert_file: services/cot-gateway/config/certs/gateway.p12"
        echo
    else
        echo "  +=================================================================+"
        echo "  |  TAK pipeline demo (single-drone)                               |"
        echo "  |  map-sim → uds → echoshield → sentrycs → gw → relay → tak-client |"
        echo "  +=================================================================+"
        printf '%s\n' "${RESET}"
        echo
    fi
    log "Single-drone invasion scenario (TRK-E01):"
    echo "  Route  : 24.757306N,121.033750E  →  SP(24.725806N,121.033750E)"
    echo "  Speed  : 35 m/s heading south"
    echo "  t=  9s : EchoShield emits first track"
    echo "  t= 43s : Sentrycs DETECTED inside 2 km ring"
    echo "  t= 71s : MITIGATING → takeover to HP"
    echo "  t=110s : NEUTRALIZED → redirected to HP"
    echo
}

launch_services() {
    log "Starting map-sim on :8090..."
    (cd "${ROOT_DIR}/services/map-sim" && exec python3 -m map_sim --port 8090) >>"${LOG_DIR}/map-sim.log" 2>&1 &
    MAPSIM_PID=$!
    write_pid "map-sim" "${MAPSIM_PID}"

    log "Starting uds on :18080..."
    (cd "${ROOT_DIR}/services/uds" && exec python3 -m uds --scenario "${UDS_SCENARIO}" --api-port 18080 --map-sim-url "http://127.0.0.1:8090") >>"${LOG_DIR}/uds.log" 2>&1 &
    UDS_PID=$!
    write_pid "uds" "${UDS_PID}"

    log "Starting echoshield-sim (:9000 / :9001)..."
    (cd "${ROOT_DIR}/services/echoshield-sim" && exec python3 -m echoshield_sim --config "${ECHO_CONFIG}") >>"${LOG_DIR}/echoshield-sim.log" 2>&1 &
    ECHO_PID=$!
    write_pid "echoshield-sim" "${ECHO_PID}"

    log "Starting sentrycs-sim on :7070..."
    (cd "${ROOT_DIR}/services/sentrycs-sim" && exec python3 -m sentrycs_sim --scenario "${SNTR_CONFIG}") >>"${LOG_DIR}/sentrycs-sim.log" 2>&1 &
    SNTR_PID=$!
    write_pid "sentrycs-sim" "${SNTR_PID}"

    if [[ "${REMOTE_TAK_MODE}" == "true" ]]; then
        local gw_extra_args=""
        gw_extra_args="--tak-host ${TAK_HOST} --tak-port ${TAK_PORT}"
        if [[ "${TAK_USE_SSL}" == "false" ]]; then
            gw_extra_args="${gw_extra_args} --no-ssl"
        fi
        log "Starting cot-gateway on :8092 → remote TAK ${TAK_HOST}:${TAK_PORT}..."
        # shellcheck disable=SC2086
        (cd "${ROOT_DIR}/services/cot-gateway" && exec python3 -m cot_gateway --config "${GW_CONFIG}" ${gw_extra_args}) >>"${LOG_DIR}/cot-gateway.log" 2>&1 &
    else
        log "Starting cot-gateway on :8092..."
        (cd "${ROOT_DIR}/services/cot-gateway" && exec python3 -m cot_gateway --config "${GW_CONFIG}") >>"${LOG_DIR}/cot-gateway.log" 2>&1 &
    fi
    GW_PID=$!
    write_pid "cot-gateway" "${GW_PID}"

    if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
        log "Starting tak-relay on :8089..."
        (cd "${ROOT_DIR}" && exec python3 "${ROOT_DIR}/scripts/tak_relay.py" --port 8089) >>"${LOG_DIR}/tak-relay.log" 2>&1 &
        RELAY_PID=$!
        write_pid "tak-relay" "${RELAY_PID}"
    fi

    log "Starting tak-client-sim on :8093..."
    (cd "${ROOT_DIR}/services/tak-client-sim" && exec python3 -m tak_client_sim --config "${TAK_CLIENT_CONFIG}") >>"${LOG_DIR}/tak-client-sim.log" 2>&1 &
    TAK_CLIENT_PID=$!
    write_pid "tak-client-sim" "${TAK_CLIENT_PID}"

    local relay_info="${RELAY_PID:-N/A (remote mode)}"
    log "PIDs: map=${MAPSIM_PID} uds=${UDS_PID} echo=${ECHO_PID} sntr=${SNTR_PID} gw=${GW_PID} relay=${relay_info} tak=${TAK_CLIENT_PID}"
    log "Logs: ${LOG_DIR}/"
}

open_maps() {
    echo
    ok "Open browser views:"
    local url=""
    for url in "${URLS[@]}"; do
        echo "  ${url}"
        open_url "${url}"
    done
    echo
    echo "  Press Ctrl-C to stop all demo services."
    echo
}

trap cleanup INT TERM EXIT

if [[ "${1:-}" == "--stop" ]]; then
    stop_from_pidfiles
fi

preflight
print_banner
launch_services
wait_for_health
open_maps

if [[ "${REMOTE_TAK_MODE}" == "false" ]]; then
    wait "${MAPSIM_PID}" "${UDS_PID}" "${ECHO_PID}" "${SNTR_PID}" "${GW_PID}" "${RELAY_PID}" "${TAK_CLIENT_PID}"
else
    wait "${MAPSIM_PID}" "${UDS_PID}" "${ECHO_PID}" "${SNTR_PID}" "${GW_PID}" "${TAK_CLIENT_PID}"
fi
