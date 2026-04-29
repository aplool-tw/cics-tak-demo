#!/usr/bin/env bash
# dev-launcher.sh - Local development launcher for the CICS TAK PoC stack.
#
# Allows the developer to:
#   1. Choose which services to start (--services <csv>, default: all)
#   2. Override each service port and the URL of any upstream dependency
#   3. Stop previously-started services (--stop) with live status display
#   4. List current service status (--status)
#
# All six services are designed to run on a single host. Inter-service URLs
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
#   scripts/dev-launcher.sh --status                           # show all service status
#   scripts/dev-launcher.sh --stop                             # stop all services
#   scripts/dev-launcher.sh --stop --services cot-gateway      # stop one service
#
# Tested under bash 5.x on Linux/macOS.
set -euo pipefail

# -------------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------------
ALL_SERVICES=(map-sim uds echoshield-sim sentrycs-sim cot-gateway tak-client-sim)
SERVICES_CSV="all"

BIND_HOST="127.0.0.1"

UDS_PORT="8080"
MAP_SIM_PORT="8090"
ECHOSHIELD_PORT="9000"
SENTRYCS_PORT="7070"
TAK_HOST="127.0.0.1"
TAK_PORT="8089"
TAK_USE_SSL="false"
TAK_CERT_DIR=""              # empty = "${ROOT_DIR}/infra/certs"
TAK_P12_PASSWORD_OVERRIDE="" # empty = use $TAK_P12_PASSWORD env or "takpoc"

UDS_SCENARIO=""
SENTRYCS_SCENARIO=""
ECHOSHIELD_CONFIG=""    # empty = use generated default (sensor@24.0,121.0)

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
STOP_MODE="false"
STATUS_MODE="false"

# tak-client-sim specific options (reuses TAK_HOST / TAK_PORT)
TAK_CLIENT_SIM_FILTER=""      # e.g. "FUSED" – empty = show all

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
# Early --config sourcing  (must happen before arg-parse so CLI flags win)
# -------------------------------------------------------------------------
CONFIG_FILE=""
for _i in "$@"; do
  if [[ "${_CONFIG_NEXT:-}" == "1" ]]; then
    CONFIG_FILE="${_i}"
    _CONFIG_NEXT=""
  fi
  [[ "${_i}" == "--config" ]] && _CONFIG_NEXT="1"
done
unset _i _CONFIG_NEXT

if [[ -n "${CONFIG_FILE}" ]]; then
  [[ -f "${CONFIG_FILE}" ]] || { echo "[launcher] ERROR: config file not found: ${CONFIG_FILE}" >&2; exit 1; }
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
fi

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
log()  { printf "\033[1;36m[launcher]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[launcher]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[launcher]\033[0m %s\n" "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: scripts/dev-launcher.sh [options]

Modes
  (default)                  Start selected services
  --stop                     Stop previously-started services (reads PID files)
  --status                   Show current status of all services (no start/stop)

Service selection
  --services <csv>           Comma list of services to start/stop/status. Use 'all'
                             for everything. Default: all
                             Valid: map-sim, uds, echoshield-sim,
                                    sentrycs-sim, cot-gateway, tak-client-sim

Bind / per-service ports
  --bind-host <host>         Host the services bind to. Default: 127.0.0.1
  --uds-port <port>          Default 8080
  --map-sim-port <port>      Default 8090
  --echoshield-port <port>   Default 9000  (TCP feed)
  --sentrycs-port <port>     Default 7070
  --tak-host <host>          External TAK Server host. Default: 127.0.0.1
  --tak-port <port>          External TAK Server port. Default: 8089
  --tak-use-ssl              Enable SSL for TAK uplink (requires p12). Off by default.
  --tak-cert-dir <dir>       Directory containing gateway.p12 + truststore.pem
                             when --tak-use-ssl is on. Default: <repo>/infra/certs
  --tak-p12-password <pwd>   Password for gateway.p12. Default: $TAK_P12_PASSWORD
                             env var, or 'takpoc' if unset.

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

TAK Client Simulator options
  --tak-client-sim-filter <prefix>   Only print CoT events whose UID starts with
                                     this prefix (e.g. FUSED). Default: show all.

Scenarios (optional)
  --uds-scenario <path>      Default: services/uds/scenarios/single_drone_invasion.yaml
  --sentrycs-scenario <path> Default: services/sentrycs-sim/config/local.yaml
  --echoshield-config <path> EchoShield sensor config file (e.g. services/echoshield-sim/config/e2e_scenario.yaml).
                             Overrides sensor lat/lon/range from the file; map_sim_url/feed_host/feed_port
                             are still injected dynamically. Default: generated config with sensor@24.0,121.0.

Misc
  --config <file>            Load configuration from a file (sourced as shell vars).
                             See scripts/dev-launcher.example.conf for all options.
                             CLI flags always override config file values.
  --verbose                  Pass --verbose to every service
  --keep-runtime             Keep .dev-runtime/ after shutdown (logs + pid files)
  -h, --help                 Show this help

Examples
  # Start everything on default ports
  scripts/dev-launcher.sh

  # Load a custom config file
  scripts/dev-launcher.sh --config scripts/dev-launcher.conf

  # Only Map Sim + UDS, with custom Map Sim port
  scripts/dev-launcher.sh --services map-sim,uds --map-sim-port 18090

  # Connect Gateway to a remote EchoShield/TAK and watch the CoT output
  scripts/dev-launcher.sh --services cot-gateway,tak-client-sim \
      --gateway-echoshield-host 10.0.0.5 --gateway-tak-host tak.example.com

  # Show status of all services
  scripts/dev-launcher.sh --status

  # Stop only the gateway
  scripts/dev-launcher.sh --stop --services cot-gateway
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
    --tak-cert-dir)           TAK_CERT_DIR="$2"; shift 2 ;;
    --tak-p12-password)       TAK_P12_PASSWORD_OVERRIDE="$2"; shift 2 ;;
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
    --echoshield-config)      ECHOSHIELD_CONFIG="$2"; shift 2 ;;
    --verbose)                VERBOSE_FLAG="--verbose"; shift ;;
    --keep-runtime)           KEEP_RUNTIME="true"; shift ;;
    --stop)                   STOP_MODE="true"; shift ;;
    --status)                 STATUS_MODE="true"; shift ;;
    --tak-client-sim-filter)  TAK_CLIENT_SIM_FILTER="$2"; shift 2 ;;
    --config)                 shift 2 ;;  # already processed above; skip both tokens
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
      map-sim|uds|echoshield-sim|sentrycs-sim|cot-gateway|tak-client-sim) ;;
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
  [[ ${#PIDS[@]} -eq 0 ]] && return 0   # nothing was started — status/stop modes
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

  if [[ -n "${ECHOSHIELD_CONFIG}" ]]; then
    [[ -f "${ECHOSHIELD_CONFIG}" ]] || die "EchoShield config not found: ${ECHOSHIELD_CONFIG}"
    # Merge user config with dynamic fields (map_sim_url, feed_host, feed_port)
    python3 - "${ECHOSHIELD_CONFIG}" "${cfg}" \
        "${ECHOSHIELD_MAP_SIM_URL}" "${BIND_HOST}" "${ECHOSHIELD_PORT}" <<'PY'
import sys, pathlib
import yaml
src, dst, map_url, host, port = sys.argv[1:]
data = yaml.safe_load(pathlib.Path(src).read_text()) or {}
data["map_sim_url"] = map_url
data["feed_host"] = host
data["feed_port"] = int(port)
pathlib.Path(dst).write_text(yaml.safe_dump(data, sort_keys=False))
PY
    log "  echoshield config : ${ECHOSHIELD_CONFIG}"
  else
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
  fi
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

launch_cot_gateway() {  local cfg="${GEN_DIR}/gateway.yaml"

  # Cert plumbing (only meaningful when --tak-use-ssl is on)
  local cert_dir="${TAK_CERT_DIR:-${ROOT_DIR}/infra/certs}"
  local cert_block=""
  if [[ "${TAK_USE_SSL}" == "true" ]]; then
    local p12="${cert_dir}/gateway.p12"
    [[ -f "${p12}" ]] || die "TAK SSL on but cert not found: ${p12} (run scripts/gen-certs.sh)"
    # Mirror certs into the gateway runtime config dir so the relative
    # path inside gateway.yaml (config/certs/gateway.p12) resolves.
    local svc_certs="${ROOT_DIR}/services/cot-gateway/config/certs"
    mkdir -p "${svc_certs}"
    cp "${cert_dir}/gateway.p12" "${svc_certs}/gateway.p12"
    [[ -f "${cert_dir}/truststore.pem" ]] && cp "${cert_dir}/truststore.pem" "${svc_certs}/truststore.pem"
    local pwd_val="${TAK_P12_PASSWORD_OVERRIDE:-${TAK_P12_PASSWORD:-takpoc}}"
    export TAK_P12_PASSWORD="${pwd_val}"
    cert_block=$(cat <<EOF
  cert_file: config/certs/gateway.p12
  cert_password: "\${TAK_P12_PASSWORD}"
EOF
)
  fi

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
${cert_block}
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

launch_tak_client_sim() {
  local args=(
    --host "${GATEWAY_TAK_HOST}"
    --port "${GATEWAY_TAK_PORT}"
    --max-retries 0
    --log-file "${LOG_DIR}/tak-client-sim-events.jsonl"
  )
  [[ -n "${TAK_CLIENT_SIM_FILTER}" ]] && args+=(--filter "${TAK_CLIENT_SIM_FILTER}")
  [[ "${TAK_USE_SSL}" == "true" ]]    && args+=(--use-ssl-verify)
  spawn "tak-client-sim" "${ROOT_DIR}/services/tak-client-sim" \
    python3 -m tak_client_sim "${args[@]}"
}

# -------------------------------------------------------------------------
# Stop mode: send SIGTERM/SIGKILL to processes from saved PID files
# -------------------------------------------------------------------------
stop_services() {
  local targets=("${SELECTED[@]}")
  local found=0

  log "Stopping services: ${targets[*]}"
  for name in "${targets[@]}"; do
    local pidfile="${PID_DIR}/${name}.pid"
    if [[ ! -f "${pidfile}" ]]; then
      warn "  ${name}: no pid file (${pidfile}), skipping"
      continue
    fi
    local pid
    pid=$(<"${pidfile}")
    if kill -0 "${pid}" 2>/dev/null; then
      log "  -> SIGTERM ${name} (pid ${pid})"
      kill -TERM "${pid}" 2>/dev/null || true
      found=$((found + 1))
    else
      warn "  ${name} (pid ${pid}): not running"
    fi
  done

  # Wait up to 5 s for graceful exit, then SIGKILL stragglers
  for _ in 1 2 3 4 5; do
    local still=0
    for name in "${targets[@]}"; do
      local pidfile="${PID_DIR}/${name}.pid"
      [[ -f "${pidfile}" ]] || continue
      local pid; pid=$(<"${pidfile}")
      kill -0 "${pid}" 2>/dev/null && still=$((still + 1)) || true
    done
    [[ $still -eq 0 ]] && break
    sleep 1
  done
  for name in "${targets[@]}"; do
    local pidfile="${PID_DIR}/${name}.pid"
    [[ -f "${pidfile}" ]] || continue
    local pid; pid=$(<"${pidfile}")
    if kill -0 "${pid}" 2>/dev/null; then
      warn "  -> SIGKILL ${name} (pid ${pid})"
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    rm -f "${pidfile}"
  done

  log "Done. (${found} process(es) signalled)"
  echo ""
  show_status
}

# -------------------------------------------------------------------------
# Status display: print a colour-coded table of service states
# -------------------------------------------------------------------------
show_status() {
  local all_svcs=("${ALL_SERVICES[@]}")
  local running=0 stopped=0 absent=0

  printf "\n"
  printf "  \033[1;37m%-20s %-8s %-10s %s\033[0m\n" "SERVICE" "PID" "STATUS" "LOG"
  printf "  %s\n" "----------------------------------------------------------------------"

  for name in "${all_svcs[@]}"; do
    local pidfile="${PID_DIR}/${name}.pid"
    local logfile="${LOG_DIR}/${name}.log"
    local pid_str="-"
    local status_label
    local log_str="-"

    [[ -f "${logfile}" ]] && log_str="${logfile}"

    if [[ -f "${pidfile}" ]]; then
      pid_str=$(<"${pidfile}")
      if kill -0 "${pid_str}" 2>/dev/null; then
        status_label="\033[1;32mrunning\033[0m"
        running=$((running + 1))
      else
        status_label="\033[1;31mstopped\033[0m"
        stopped=$((stopped + 1))
      fi
    else
      pid_str="-"
      status_label="\033[1;33mno-pid\033[0m"
      absent=$((absent + 1))
    fi

    printf "  %-20s %-8s %-20b %s\n" "${name}" "${pid_str}" "${status_label}" "${log_str}"
  done

  printf "  %s\n" "----------------------------------------------------------------------"
  printf "  running: \033[1;32m%d\033[0m  stopped: \033[1;31m%d\033[0m  no-pid: \033[1;33m%d\033[0m\n\n" \
    "${running}" "${stopped}" "${absent}"
}

# -------------------------------------------------------------------------
# Main: print plan, then launch in dependency order
# -------------------------------------------------------------------------
log "CICS TAK PoC dev launcher"
log "  bind host           : ${BIND_HOST}"
log "  selected services   : ${SELECTED[*]}"

# --status mode: show current service states and exit
if [[ "${STATUS_MODE}" == "true" ]]; then
  show_status
  exit 0
fi

# --stop mode: show status, terminate previously-started services, show status again
if [[ "${STOP_MODE}" == "true" ]]; then
  log "Current status before stop:"
  show_status
  stop_services
  exit 0
fi

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
log "  tak-client-sim      : ${GATEWAY_TAK_HOST}:${GATEWAY_TAK_PORT} filter=${TAK_CLIENT_SIM_FILTER:-<all>}"
log "  runtime dir         : ${RUNTIME_DIR}"

# Order matters: start upstream services first so dependents have something to
# connect to. We keep it deterministic regardless of --services input order.
for svc in map-sim uds echoshield-sim sentrycs-sim cot-gateway tak-client-sim; do
  is_selected "$svc" || continue
  case "$svc" in
    map-sim)          launch_map_sim ;;
    uds)              launch_uds ;;
    echoshield-sim)   launch_echoshield_sim ;;
    sentrycs-sim)     launch_sentrycs_sim ;;
    cot-gateway)      launch_cot_gateway ;;
    tak-client-sim)   launch_tak_client_sim ;;
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
