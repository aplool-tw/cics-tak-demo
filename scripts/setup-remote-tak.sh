#!/usr/bin/env bash
# setup-remote-tak.sh — Interactive wizard for configuring config/remote-tak.yaml.
#
# Guides the operator step by step through every field of the remote TAK server
# connection config.  Writes (or overwrites with confirmation) the file
# config/remote-tak.yaml at the repository root.
#
# Usage:
#   bash scripts/setup-remote-tak.sh          # interactive wizard
#   bash scripts/setup-remote-tak.sh --check  # validate existing config
#
# After running, start a remote demo with:
#   bash scripts/demo-1drone-remote-tak.sh
#   bash scripts/demo-3drone-remote-tak.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUT_FILE="${ROOT_DIR}/config/remote-tak.yaml"
EXAMPLE_FILE="${ROOT_DIR}/config/remote-tak.example.yaml"

# ── colours ────────────────────────────────────────────────────────────────────
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
YELLOW=$'\033[1;33m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
RESET=$'\033[0m'

log()  { printf '%s[setup-remote-tak]%s %s\n' "${CYAN}"   "${RESET}" "$*"; }
ok()   { printf '%s[setup-remote-tak]%s %s\n' "${GREEN}"  "${RESET}" "$*"; }
warn() { printf '%s[setup-remote-tak]%s %s\n' "${YELLOW}" "${RESET}" "$*" >&2; }
die()  { printf '%s[setup-remote-tak] ERROR:%s %s\n' "${RED}" "${RESET}" "$*" >&2; exit 1; }

hr() { printf '%s%s%s\n' "${DIM}" "$(printf '─%.0s' {1..70})" "${RESET}"; }

# ── prompt helpers ─────────────────────────────────────────────────────────────
# ask <prompt> <default> → stores answer in REPLY
ask() {
    local prompt="$1"
    local default="${2:-}"
    local hint=""
    if [[ -n "${default}" ]]; then
        hint=" ${DIM}[${default}]${RESET}"
    fi
    printf '%s  ▶ %s%s%s: ' "${BOLD}" "${prompt}" "${RESET}" "${hint}"
    read -r REPLY </dev/tty
    if [[ -z "${REPLY}" && -n "${default}" ]]; then
        REPLY="${default}"
    fi
}

# ask_yn <prompt> <default y|n> → returns 0 (yes) or 1 (no)
ask_yn() {
    local prompt="$1"
    local default="${2:-y}"
    local hint
    if [[ "${default}" == "y" ]]; then hint="Y/n"; else hint="y/N"; fi
    printf '%s  ▶ %s%s [%s]: ' "${BOLD}" "${prompt}" "${RESET}" "${hint}"
    read -r REPLY </dev/tty
    REPLY="${REPLY:-${default}}"
    [[ "${REPLY,,}" == "y" ]]
}

# ── check mode ─────────────────────────────────────────────────────────────────
do_check() {
    log "Validating ${OUT_FILE} ..."
    if [[ ! -f "${OUT_FILE}" ]]; then
        die "config/remote-tak.yaml not found. Run without --check to create it."
    fi

    python3 - "${OUT_FILE}" <<'PY'
import sys, pathlib, yaml, ssl, os

path = pathlib.Path(sys.argv[1])
cfg  = yaml.safe_load(path.read_text()) or {}
ts   = cfg.get("tak_server", {})
ok   = True

def check(label, val, cond, msg=""):
    global ok
    mark = "\033[0;32m✓\033[0m" if cond else "\033[0;31m✗\033[0m"
    note = f"  {msg}" if msg else ""
    print(f"  {mark}  {label}: {val!r}{note}")
    if not cond:
        ok = False

host = ts.get("host", "")
port = ts.get("port", 8089)
use_ssl  = ts.get("use_ssl", True)
use_verify = ts.get("use_ssl_verify", False)
cert_file = ts.get("cert_file")
cert_pass = ts.get("cert_password")
ca_bundle = ts.get("ca_bundle")

check("host",           host, bool(host) and host not in ("127.0.0.1","localhost"),
      "(must be a non-localhost IP / hostname)")
check("port",           port, isinstance(port, int) and 1 <= port <= 65535)
check("use_ssl",        use_ssl,  isinstance(use_ssl, bool))
check("use_ssl_verify", use_verify, isinstance(use_verify, bool))

if cert_file:
    abs_cert = (pathlib.Path(sys.argv[1]).parent.parent / cert_file).resolve()
    check("cert_file",  cert_file, abs_cert.exists(),
          f"(file not found at {abs_cert})")
else:
    print("  ·  cert_file: null  (no mutual TLS)")

if ca_bundle:
    abs_ca = (pathlib.Path(sys.argv[1]).parent.parent / ca_bundle).resolve()
    check("ca_bundle",  ca_bundle, abs_ca.exists(),
          f"(file not found at {abs_ca})")
else:
    print("  ·  ca_bundle: null  (using system trust store)")

print()
if ok:
    print("\033[0;32m  All checks passed ✓\033[0m")
else:
    print("\033[0;31m  Some checks FAILED — fix the issues above before running a demo.\033[0m")
    sys.exit(1)
PY
}

# ── main wizard ────────────────────────────────────────────────────────────────
run_wizard() {
    clear 2>/dev/null || true
    printf '\n'
    printf '%s  ╔══════════════════════════════════════════════════════════════╗\n' "${BOLD}"
    printf '  ║   CICS TAK Demo — Remote TAK Server Setup Wizard            ║\n'
    printf '  ╚══════════════════════════════════════════════════════════════╝%s\n\n' "${RESET}"

    log "This wizard creates/updates: ${OUT_FILE}"
    log "Reference example:          ${EXAMPLE_FILE}"
    echo

    # ── guard: overwrite existing? ────────────────────────────────────────────
    if [[ -f "${OUT_FILE}" ]]; then
        warn "config/remote-tak.yaml already exists."
        if ! ask_yn "Overwrite it?" "y"; then
            log "Aborted — existing file kept."
            exit 0
        fi
        echo
    fi

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1 — TAK server address
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 1 of 6 — TAK Server Address%s\n\n' "${BOLD}" "${RESET}"
    printf '  Enter the IP address or hostname of your TAK server.\n'
    printf '  %sNOTE:%s Do NOT use 127.0.0.1 or localhost — those trigger local mode.\n\n' "${YELLOW}" "${RESET}"

    TAK_HOST=""
    while true; do
        ask "TAK server host (IP or hostname)" "192.168.1.100"
        TAK_HOST="${REPLY}"
        if [[ -z "${TAK_HOST}" ]]; then
            warn "Host cannot be empty."
        elif [[ "${TAK_HOST}" == "127.0.0.1" || "${TAK_HOST,,}" == "localhost" ]]; then
            warn "Using localhost triggers LOCAL mode — please enter a remote host."
        else
            break
        fi
    done
    ok "Host: ${TAK_HOST}"
    echo

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2 — Port
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 2 of 6 — TCP Port%s\n\n' "${BOLD}" "${RESET}"
    printf '  Standard TAK ports:\n'
    printf '    8089  — TLS/SSL (recommended)\n'
    printf '    8087  — plain TCP (no encryption)\n\n'

    TAK_PORT=""
    while true; do
        ask "TAK server port" "8089"
        TAK_PORT="${REPLY}"
        if [[ "${TAK_PORT}" =~ ^[0-9]+$ ]] && (( TAK_PORT >= 1 && TAK_PORT <= 65535 )); then
            break
        else
            warn "Enter a valid port number (1–65535)."
        fi
    done
    ok "Port: ${TAK_PORT}"
    echo

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3 — SSL
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 3 of 6 — TLS/SSL%s\n\n' "${BOLD}" "${RESET}"
    printf '  Most TAK servers use TLS (recommended).  Plain TCP is available\n'
    printf '  on port 8087 for lab/testing without certificates.\n\n'

    USE_SSL="true"
    USE_SSL_VERIFY="false"
    if ask_yn "Enable TLS/SSL?" "y"; then
        USE_SSL="true"
        ok "TLS: enabled"
        echo
        printf '  TAK Server certificate verification:\n'
        printf '    • If your TAK server has a self-signed cert → answer NO\n'
        printf '      (you will still get an encrypted channel; cert not validated)\n'
        printf '    • If your TAK server has a proper PKI cert → answer YES\n'
        printf '      and provide a CA bundle PEM in step 5.\n\n'
        if ask_yn "Verify TAK server certificate (use_ssl_verify)?" "n"; then
            USE_SSL_VERIFY="true"
        else
            USE_SSL_VERIFY="false"
        fi
        ok "verify server cert: ${USE_SSL_VERIFY}"
    else
        USE_SSL="false"
        USE_SSL_VERIFY="false"
        warn "TLS disabled — traffic is unencrypted.  Make sure port matches (e.g., 8087)."
    fi
    echo

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 4 — Client certificate (mutual TLS)
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 4 of 6 — Client Certificate (Mutual TLS)%s\n\n' "${BOLD}" "${RESET}"
    printf '  TAK servers typically require a client P12 certificate for mutual TLS.\n'
    printf '  Place the P12 file in  config/certs/  (it is git-ignored).\n'
    printf '  Path is relative to the repository root.\n\n'
    printf '  If you do not have a certificate yet, you can:\n'
    printf '    • Generate a self-signed PKI:  bash scripts/gen-certs.sh\n'
    printf '      → produces  config/certs/gateway.p12\n'
    printf '    • Skip for now and set cert_file to null.\n\n'

    CERT_FILE="null"
    CERT_PASSWORD="null"
    if ask_yn "Do you have a client P12 certificate?" "y"; then
        ask "Path to P12 cert (relative to repo root)" "config/certs/gateway.p12"
        CERT_FILE="${REPLY}"

        # Validate immediately
        ABS_CERT="${ROOT_DIR}/${CERT_FILE}"
        if [[ -f "${ABS_CERT}" ]]; then
            ok "Found: ${CERT_FILE}"
        else
            warn "File not found: ${ABS_CERT}"
            warn "You can copy the file there later; setup will continue."
        fi
        echo

        printf '  P12 certificate password (press Enter if none):\n'
        printf '  %s(input is hidden)%s\n\n' "${DIM}" "${RESET}"
        printf '%s  ▶ P12 password%s (Enter = no password): ' "${BOLD}" "${RESET}"
        read -rs CERT_PASSWORD_RAW </dev/tty
        echo
        if [[ -z "${CERT_PASSWORD_RAW}" ]]; then
            CERT_PASSWORD="null"
            ok "No P12 password set."
        else
            CERT_PASSWORD="\"${CERT_PASSWORD_RAW}\""
            ok "P12 password stored."
        fi
    else
        CERT_FILE="null"
        warn "No client certificate — mutual TLS will not be used."
        warn "Many TAK servers require mutual TLS; check your server config."
    fi
    echo

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 5 — CA bundle (only relevant when use_ssl_verify: true)
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 5 of 6 — CA Bundle PEM%s\n\n' "${BOLD}" "${RESET}"

    CA_BUNDLE="null"
    if [[ "${USE_SSL_VERIFY}" == "true" ]]; then
        printf '  Since you enabled server cert verification, provide the CA bundle PEM\n'
        printf '  that was used to sign your TAK server certificate.\n'
        printf '  Place it in  config/certs/  (git-ignored).  Path relative to repo root.\n\n'
        if ask_yn "Do you have a CA bundle PEM?" "y"; then
            ask "Path to CA bundle PEM" "config/certs/ca-bundle.pem"
            CA_BUNDLE="\"${REPLY}\""
            ABS_CA="${ROOT_DIR}/${REPLY}"
            if [[ -f "${ABS_CA}" ]]; then
                ok "Found: ${REPLY}"
            else
                warn "File not found: ${ABS_CA}"
                warn "You can copy the file there later; setup will continue."
            fi
        else
            CA_BUNDLE="null"
            warn "No CA bundle provided — if your server has a custom CA, verification will fail."
        fi
    else
        printf '  Skipping CA bundle (server cert verification is disabled).\n'
        printf '  If you need to verify your server cert later, edit ca_bundle in the YAML.\n'
    fi
    echo

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 6 — Advanced options
    # ══════════════════════════════════════════════════════════════════════════
    hr
    printf '\n%s  STEP 6 of 6 — Advanced Options%s\n\n' "${BOLD}" "${RESET}"
    printf '  The following options have sensible defaults for most deployments.\n'
    printf '  Press Enter to accept defaults.\n\n'

    ask "Include XML declaration in CoT messages (xml_declaration)" "true"
    XML_DECL="${REPLY}"
    [[ "${XML_DECL,,}" =~ ^(true|false)$ ]] || XML_DECL="true"

    ask "Max retry attempts before giving up (0 = unlimited)" "10"
    MAX_RETRIES="${REPLY}"
    [[ "${MAX_RETRIES}" =~ ^[0-9]+$ ]] || MAX_RETRIES="10"

    ask "Initial backoff delay seconds (backoff_initial_s)" "2.0"
    BACKOFF_INIT="${REPLY}"

    ask "Maximum backoff cap seconds (backoff_cap_s)" "60.0"
    BACKOFF_CAP="${REPLY}"

    ask "CoT queue max size (drop oldest when full)" "500"
    QUEUE_MAX="${REPLY}"
    [[ "${QUEUE_MAX}" =~ ^[0-9]+$ ]] || QUEUE_MAX="500"

    echo
    ok "Advanced options captured."

    # ── format cert_file field ─────────────────────────────────────────────────
    if [[ "${CERT_FILE}" == "null" ]]; then
        CERT_FILE_YAML="null"
    else
        CERT_FILE_YAML="\"${CERT_FILE}\""
    fi

    # ── write the file ─────────────────────────────────────────────────────────
    hr
    printf '\n%s  Writing config/remote-tak.yaml …%s\n\n' "${BOLD}" "${RESET}"

    mkdir -p "$(dirname "${OUT_FILE}")"
    cat >"${OUT_FILE}" <<YAML
# config/remote-tak.yaml — Generated by scripts/setup-remote-tak.sh
# $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# This file is git-ignored (may contain real IP / credentials).
# The annotated template lives at config/remote-tak.example.yaml.
#
# To regenerate: bash scripts/setup-remote-tak.sh
# To validate:   bash scripts/setup-remote-tak.sh --check

tak_server:
  host: "${TAK_HOST}"
  port: ${TAK_PORT}
  use_ssl: ${USE_SSL}
  use_ssl_verify: ${USE_SSL_VERIFY}
  cert_file: ${CERT_FILE_YAML}
  cert_password: ${CERT_PASSWORD}
  ca_bundle: ${CA_BUNDLE}
  xml_declaration: ${XML_DECL}
  max_retries: ${MAX_RETRIES}
  backoff_initial_s: ${BACKOFF_INIT}
  backoff_cap_s: ${BACKOFF_CAP}
  queue_maxsize: ${QUEUE_MAX}
YAML

    ok "Written: ${OUT_FILE}"
    echo

    # ── summary ────────────────────────────────────────────────────────────────
    printf '%s  ╔══════════════════════════════════════════════════════════════╗\n' "${BOLD}"
    printf '  ║   Configuration Summary                                      ║\n'
    printf '  ╚══════════════════════════════════════════════════════════════╝%s\n\n' "${RESET}"

    printf '  TAK Server  : %s%s:%s%s\n' "${GREEN}" "${TAK_HOST}" "${TAK_PORT}" "${RESET}"
    printf '  TLS / SSL   : %s\n' "${USE_SSL}"
    printf '  Verify cert : %s\n' "${USE_SSL_VERIFY}"
    printf '  Client cert : %s\n' "${CERT_FILE:-null}"
    printf '  CA bundle   : %s\n' "${CA_BUNDLE:-null}"
    echo

    # ── certificate placement reminder ────────────────────────────────────────
    if [[ "${CERT_FILE}" != "null" ]]; then
        ABS_CERT="${ROOT_DIR}/${CERT_FILE}"
        if [[ ! -f "${ABS_CERT}" ]]; then
            printf '%s  ⚠  ACTION REQUIRED:%s Copy your P12 certificate to:\n' "${YELLOW}" "${RESET}"
            printf '     %s\n\n' "${ABS_CERT}"
        fi
    fi
    if [[ "${USE_SSL_VERIFY}" == "true" && "${CA_BUNDLE}" != "null" ]]; then
        CA_PATH="${ROOT_DIR}/${CA_BUNDLE//\"/}"
        if [[ ! -f "${CA_PATH}" ]]; then
            printf '%s  ⚠  ACTION REQUIRED:%s Copy your CA bundle PEM to:\n' "${YELLOW}" "${RESET}"
            printf '     %s\n\n' "${CA_PATH}"
        fi
    fi

    # ── next steps ─────────────────────────────────────────────────────────────
    printf '%s  Next steps:%s\n\n' "${BOLD}" "${RESET}"
    printf '  1. Validate the config:\n'
    printf '       bash scripts/setup-remote-tak.sh --check\n\n'
    printf '  2. Start the remote TAK demo:\n'
    printf '       bash scripts/demo-1drone-remote-tak.sh   # single-drone scenario\n'
    printf '       bash scripts/demo-3drone-remote-tak.sh   # three-drone scenario\n\n'
    printf '  3. Stop the demo (Ctrl-C or):\n'
    printf '       bash scripts/demo-1drone-remote-tak.sh --stop\n\n'
    printf '  Need to regenerate self-signed certs?  bash scripts/gen-certs.sh\n\n'
}

# ── entry point ────────────────────────────────────────────────────────────────
case "${1:-}" in
    --check)
        do_check
        ;;
    --help|-h)
        cat <<EOF
Usage:
  bash scripts/setup-remote-tak.sh          — interactive wizard (creates config/remote-tak.yaml)
  bash scripts/setup-remote-tak.sh --check  — validate existing config/remote-tak.yaml
  bash scripts/setup-remote-tak.sh --help   — show this help

After running the wizard, start a remote demo:
  bash scripts/demo-1drone-remote-tak.sh
  bash scripts/demo-3drone-remote-tak.sh
EOF
        ;;
    "")
        run_wizard
        ;;
    *)
        die "Unknown argument: $1  (use --help for usage)"
        ;;
esac
