#!/usr/bin/env bash
# dev-launcher.sh - Local development launcher for the CICS TAK PoC stack.
#
# Allows the developer to:
#   1. Choose which services to start (--services <csv>, default: all)
#   2. Override each service port and the URL of any upstream dependency
#
# All five services are designed to run on a single host. Inter-service URLs
# are computed automatically from --bind-host plus the per-service ports;
# any URL can be overridden explicitly with the --*-url flags below.
#
# Logs go to logs/<service>.log; PIDs to logs/<service>.pid. Ctrl-C shuts all down.
#
# Usage examples:
#   scripts/dev-launcher.sh                                    # start everything
#   scripts/dev-launcher.sh --services map-sim,uds             # only two services
#   scripts/dev-launcher.sh --uds-port 18080 --map-sim-port 18090
#   scripts/dev-launcher.sh --services cot-gateway --echoshield-host 10.0.0.5
#
# Tested under bash 5.x on Linux/macOS.
set -euo pipefail

# -------------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------------
ALL_SERVICES=(map-sim uds echoshield-sim sentrycs-sim cot-gateway)
SERVICES_CSV="all"

BIND_HOST="127.0.0.1"

UDS_PORT="8080"
MAP_SIM_PORT="8090"
ECHOSHIELD_PORT="9000"
SENTRYCS_PORT="7070"
TAK_HOST="127.0.0.1"
TAK_PORT="8089"
TAK_USE_SSL="false"

UDS_SCENARIO=""
SENTRYCS_SCENARIO=""

# Optional explicit URL overrides (empty = derive from host+port)
UDS_MAP_SIM_URL=""           # consumed by uds (push)
ECHOSHIELD_MAP_SIM_URL=""    # consumed by echoshield-sim (poll)
SENTRYCS_MAP_SIM_URL=""      # consumed by sentrycs-sim (poll)
SENTRYCS_UDS_URL=""          # consumed by sentrycs-sim (takeover)
GATEWAY_ECHOSHIELD_HOST=""
GATEWAY_ECHOSHIELD_PORT=""
GATEWAY_SENTRYCS_HOST=""
GATEWAY_SENTRYCS_PORT=""
GATEWAY_TAK_HOST=""
GATEWAY_TAK_PORT=""

VERBOSE_FLAG=""
KEEP_RUNTIME="false"

# -------------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.dev-runtime"
LOG_DIR="${RUNTIME_DIR}/logs"
PID_DIR="${RUNTIME_DIR}/pids"
GEN_DIR="${RUNTIME_DIR}/generated"

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
log()  { printf "\033[1;36m[launcher]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[launcher]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[launcher]\033[0m %s\n" "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: scripts/dev-launcher.sh [options]

Service selection
  --services <csv>           Comma list of services to start. Use 'all' for
                             everything. Default: all
                             Valid: map-sim, uds, echoshield-sim,
                                    sentrycs-sim, cot-gateway

Bind / per-service ports
  --bind-host <host>         Host the services bind to. Default: 127.0.0.1
  --uds-port <port>          Default 8080
  --map-sim-port <port>      Default 8090
  --echoshield-port <port>   Default 9000  (TCP feed)
  --sentrycs-port <port>     Default 7070
  --tak-host <host>          External TAK Server host. Default: 127.0.0.1
  --tak-port <port>          External TAK Server port. Default: 8089
  --tak-use-ssl              Enable SSL for TAK uplink (requires p12). Off by default.

Upstream URL/host overrides (optional; default: derived from --bind-host + ports)
  --uds-map-sim-url <url>            Map Sim base URL used by UDS push client
  --echoshield-map-sim-url <url>     Map Sim base URL used by EchoShield poller
  --sentrycs-map-sim-url <url>       Map Sim base URL used by Sentrycs poller
  --sentrycs-uds-url <url>           UDS base URL used by Sentrycs takeover client
  --gateway-echoshield-host <host>   EchoShield host the gateway connects to
  --gateway-echoshield-port <port>   EchoShield TCP port for the gateway
  --gateway-sentrycs-host <host>     Sentrycs host the gateway polls
  --gateway-sentrycs-port <port>     Sentrycs port the gateway polls
  --gateway-tak-host <host>          Override TAK host for gateway
  --gateway-tak-port <port>          Override TAK port for gateway

Scenarios (optional)
  --uds-scenario <path>      Default: services/uds/scenarios/single_drone_invasion.yaml
  --sentrycs-scenario <path> Default: services/sentrycs-sim/config/local.yaml

Misc
  --verbose                  Pass --verbose to every service
  --keep-runtime             Keep .dev-runtime/ after shutdown (logs + pid files)
  -h, --help                 Show this help

Examples
  # Start everything on default ports
  scripts/dev-launcher.sh

  # Only Map Sim + UDS, with custom Map Sim port
  scripts/dev-launcher.sh --services map-sim,uds --map-sim-port 18090

  # Connect Gateway to a remote EchoShield/TAK
  scripts/dev-launcher.sh --services cot-gateway \
      --gateway-echoshield-host 10.0.0.5 --gateway-tak-host tak.example.com
EOF
}

# -------------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --services)               SERVICES_CSV="$2"; shift 2 ;;
    --bind-host)              BIND_HOST="$2"; shift 2 ;;
    --uds-port)               UDS_PORT="$2"; shift 2 ;;
    --map-sim-port)           MAP_SIM_PORT="$2"; shift 2 ;;
    --echoshield-port)        ECHOSHIELD_PORT="$2"; shift 2 ;;
    --sentrycs-port)          SENTRYCS_PORT="$2"; shift 2 ;;
    --tak-host)               TAK_HOST="$2"; shift 2 ;;
    --tak-port)               TAK_PORT="$2"; shift 2 ;;
    --tak-use-ssl)            TAK_USE_SSL="true"; shift ;;
    --uds-map-sim-url)        UDS_MAP_SIM_URL="$2"; shift 2 ;;
    --echoshield-map-sim-url) ECHOSHIELD_MAP_SIM_URL="$2"; shift 2 ;;
    --sentrycs-map-sim-url)   SENTRYCS_MAP_SIM_URL="$2"; shift 2 ;;
    --sentrycs-uds-url)       SENTRYCS_UDS_URL="$2"; shift 2 ;;
    --gateway-echoshield-host) GATEWAY_ECHOSHIELD_HOST="$2"; shift 2 ;;
    --gateway-echoshield-port) GATEWAY_ECHOSHIELD_PORT="$2"; shift 2 ;;
    --gateway-sentrycs-host)  GATEWAY_SENTRYCS_HOST="$2"; shift 2 ;;
    --gateway-sentrycs-port)  GATEWAY_SENTRYCS_PORT="$2"; shift 2 ;;
    --gateway-tak-host)       GATEWAY_TAK_HOST="$2"; shift 2 ;;
    --gateway-tak-port)       GATEWAY_TAK_PORT="$2"; shift 2 ;;
    --uds-scenario)           UDS_SCENARIO="$2"; shift 2 ;;
    --sentrycs-scenario)      SENTRYCS_SCENARIO="$2"; shift 2 ;;
    --verbose)                VERBOSE_FLAG="--verbose"; shift ;;
    --keep-runtime)           KEEP_RUNTIME="true"; shift ;;
    -h|--help)                usage; exit 0 ;;
    *)                        die "Unknown argument: $1 (use --help)" ;;
  esac
done

# -------------------------------------------------------------------------
# Resolve service list
# -------------------------------------------------------------------------
declare -a SELECTED
if [[ "${SERVICES_CSV}" == "all" ]]; then
  SELECTED=("${ALL_SERVICES[@]}")
else
  IFS=',' read -r -a SELECTED <<< "${SERVICES_CSV}"
  for s in "${SELECTED[@]}"; do
    case "$s" in
      map-sim|uds|echoshield-sim|sentrycs-sim|cot-gateway) ;;
      *) die "Unknown service: '$s'" ;;
    esac
  done
fi

is_selected() {
  local needle="$1"
  for s in "${SELECTED[@]}"; do
    [[ "$s" == "$needle" ]] && return 0
  done
  return 1
}

# -------------------------------------------------------------------------
# Defaults derived from host+ports
# -------------------------------------------------------------------------
: "${UDS_MAP_SIM_URL:=http://${BIND_HOST}:${MAP_SIM_PORT}}"
: "${ECHOSHIELD_MAP_SIM_URL:=http://${BIND_HOST}:${MAP_SIM_PORT}}"
: "${SENTRYCS_MAP_SIM_URL:=http://${BIND_HOST}:${MAP_SIM_PORT}}"
: "${SENTRYCS_UDS_URL:=http://${BIND_HOST}:${UDS_PORT}}"
: "${GATEWAY_ECHOSHIELD_HOST:=${BIND_HOST}}"
: "${GATEWAY_ECHOSHIELD_PORT:=${ECHOSHIELD_PORT}}"
: "${GATEWAY_SENTRYCS_HOST:=${BIND_HOST}}"
: "${GATEWAY_SENTRYCS_PORT:=${SENTRYCS_PORT}}"
: "${GATEWAY_TAK_HOST:=${TAK_HOST}}"
: "${GATEWAY_TAK_PORT:=${TAK_PORT}}"

: "${UDS_SCENARIO:=${ROOT_DIR}/services/uds/scenarios/single_drone_invasion.yaml}"
: "${SENTRYCS_SCENARIO:=${ROOT_DIR}/services/sentrycs-sim/config/local.yaml}"

# -------------------------------------------------------------------------
# Runtime prep
# -------------------------------------------------------------------------
mkdir -p "${LOG_DIR}" "${PID_DIR}" "${GEN_DIR}"

PIDS=()
SVC_NAMES=()

cleanup() {
  trap - INT TERM EXIT
  log "Shutting down (${#PIDS[@]} processes)..."
  for i in "${!PIDS[@]}"; do
    local pid="${PIDS[$i]}"
    local name="${SVC_NAMES[$i]}"
    if kill -0 "$pid" 2>/dev/null; then
      log "  -> SIGTERM ${name} (pid ${pid})"
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  # Wait up to 5 seconds for graceful exit
  for _ in 1 2 3 4 5; do
    local still=0
    for pid in "${PIDS[@]}"; do
      kill -0 "$pid" 2>/dev/null && still=$((still+1)) || true
    done
    [[ $still -eq 0 ]] && break
    sleep 1
  done
  for i in "${!PIDS[@]}"; do
    local pid="${PIDS[$i]}"
    if kill -0 "$pid" 2>/dev/null; then
      warn "  -> SIGKILL ${SVC_NAMES[$i]} (pid ${pid})"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  if [[ "${KEEP_RUNTIME}" == "false" ]]; then
    rm -f "${PID_DIR}"/*.pid 2>/dev/null || true
  fi
  log "All services stopped. Logs: ${LOG_DIR}"
}
trap cleanup INT TERM EXIT

# -------------------------------------------------------------------------
# Spawner
# -------------------------------------------------------------------------
spawn() {
  local name="$1"; shift
  local cwd="$1"; shift
  local logfile="${LOG_DIR}/${name}.log"
  local pidfile="${PID_DIR}/${name}.pid"

  log "starting ${name}: $*"
  ( cd "${cwd}" && exec "$@" ) > "${logfile}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${pidfile}"
  PIDS+=("${pid}")
  SVC_NAMES+=("${name}")
}

# -------------------------------------------------------------------------
# Per-service launchers
# -------------------------------------------------------------------------
launch_map_sim() {
  spawn "map-sim" "${ROOT_DIR}/services/map-sim" \
    python3 -m map_sim --port "${MAP_SIM_PORT}" ${VERBOSE_FLAG}
}

launch_uds() {
  [[ -f "${UDS_SCENARIO}" ]] || die "UDS scenario not found: ${UDS_SCENARIO}"
  spawn "uds" "${ROOT_DIR}/services/uds" \
    python3 -m uds \
      --scenario "${UDS_SCENARIO}" \
      --api-port "${UDS_PORT}" \
      --map-sim-url "${UDS_MAP_SIM_URL}" \
      ${VERBOSE_FLAG}
}

launch_echoshield_sim() {
  local cfg="${GEN_DIR}/echoshield.yaml"
  cat > "${cfg}" <<EOF
sensor_lat: 24.0
sensor_lon: 121.0
sensor_alt_m: 10.0
max_range_m: 4800
update_rate_hz: 10
lost_grace_sec: 2.0

position_noise_m: 5.0
velocity_noise_ms: 0.5

noise_seed: null

map_sim_url: ${ECHOSHIELD_MAP_SIM_URL}
feed_host: ${BIND_HOST}
feed_port: ${ECHOSHIELD_PORT}
EOF
  spawn "echoshield-sim" "${ROOT_DIR}/services/echoshield-sim" \
    python3 -m echoshield_sim --config "${cfg}" ${VERBOSE_FLAG}
}

launch_sentrycs_sim() {
  [[ -f "${SENTRYCS_SCENARIO}" ]] || die "Sentrycs scenario not found: ${SENTRYCS_SCENARIO}"
  # The Sentrycs scenario YAML embeds map_sim_url / uds_url; render an
  # overridden copy so the user can redirect upstream URLs.
  local cfg="${GEN_DIR}/sentrycs.yaml"
  python3 - "${SENTRYCS_SCENARIO}" "${cfg}" \
      "${SENTRYCS_MAP_SIM_URL}" "${SENTRYCS_UDS_URL}" \
      "${BIND_HOST}" "${SENTRYCS_PORT}" <<'PY'
import sys, pathlib
import yaml
src, dst, map_url, uds_url, host, port = sys.argv[1:]
data = yaml.safe_load(pathlib.Path(src).read_text()) or {}
data["map_sim_url"] = map_url
data["uds_url"] = uds_url
data["api_host"] = host
data["api_port"] = int(port)
pathlib.Path(dst).write_text(yaml.safe_dump(data, sort_keys=False))
PY
  spawn "sentrycs-sim" "${ROOT_DIR}/services/sentrycs-sim" \
    python3 -m sentrycs_sim --scenario "${cfg}" --api-port "${SENTRYCS_PORT}" ${VERBOSE_FLAG}
}

launch_cot_gateway() {
  local cfg="${GEN_DIR}/gateway.yaml"
  cat > "${cfg}" <<EOF
echoshield:
  host: ${GATEWAY_ECHOSHIELD_HOST}
  port: ${GATEWAY_ECHOSHIELD_PORT}
  reconnect_interval_s: 5.0

sentrycs:
  enabled: true
  host: ${GATEWAY_SENTRYCS_HOST}
  port: ${GATEWAY_SENTRYCS_PORT}
  poll_interval_s: 1.0
  timeout_s: 2.0

correlator:
  distance_threshold_m: 50.0
  time_window_s: 3.0
  ttl_s: 10.0

tak_server:
  host: ${GATEWAY_TAK_HOST}
  port: ${GATEWAY_TAK_PORT}
  use_ssl: ${TAK_USE_SSL}
  use_ssl_verify: false
  max_retries: 5
  backoff_initial_s: 1.0
  backoff_cap_s: 60.0
  queue_maxsize: 500

logging:
  level: $([[ -n "${VERBOSE_FLAG}" ]] && echo DEBUG || echo INFO)
  json: true
EOF
  spawn "cot-gateway" "${ROOT_DIR}/services/cot-gateway" \
    python3 -m cot_gateway --config "${cfg}" ${VERBOSE_FLAG}
}

# -------------------------------------------------------------------------
# Main: print plan, then launch in dependency order
# -------------------------------------------------------------------------
log "CICS TAK PoC dev launcher"
log "  bind host           : ${BIND_HOST}"
log "  selected services   : ${SELECTED[*]}"
log "  uds port            : ${UDS_PORT}"
log "  map-sim port        : ${MAP_SIM_PORT}"
log "  echoshield port     : ${ECHOSHIELD_PORT}"
log "  sentrycs port       : ${SENTRYCS_PORT}"
log "  tak host:port       : ${TAK_HOST}:${TAK_PORT} (ssl=${TAK_USE_SSL})"
log "  uds -> map-sim url  : ${UDS_MAP_SIM_URL}"
log "  echo -> map-sim url : ${ECHOSHIELD_MAP_SIM_URL}"
log "  sentrycs -> map-sim : ${SENTRYCS_MAP_SIM_URL}"
log "  sentrycs -> uds     : ${SENTRYCS_UDS_URL}"
log "  gw -> echoshield    : ${GATEWAY_ECHOSHIELD_HOST}:${GATEWAY_ECHOSHIELD_PORT}"
log "  gw -> sentrycs      : ${GATEWAY_SENTRYCS_HOST}:${GATEWAY_SENTRYCS_PORT}"
log "  gw -> tak           : ${GATEWAY_TAK_HOST}:${GATEWAY_TAK_PORT}"
log "  runtime dir         : ${RUNTIME_DIR}"

# Order matters: start upstream services first so dependents have something to
# connect to. We keep it deterministic regardless of --services input order.
for svc in map-sim uds echoshield-sim sentrycs-sim cot-gateway; do
  is_selected "$svc" || continue
  case "$svc" in
    map-sim)        launch_map_sim ;;
    uds)            launch_uds ;;
    echoshield-sim) launch_echoshield_sim ;;
    sentrycs-sim)   launch_sentrycs_sim ;;
    cot-gateway)    launch_cot_gateway ;;
  esac
  sleep 0.4   # tiny stagger so logs interleave readably
done

log "All requested services launched."
log "Tail logs with:  tail -f ${LOG_DIR}/*.log"
log "Press Ctrl-C to stop everything."

# Wait until any child exits (or signal). On any single exit, propagate by
# tearing the rest down via the EXIT trap.
wait -n 2>/dev/null || true
warn "A service exited. Initiating shutdown of remaining processes."
