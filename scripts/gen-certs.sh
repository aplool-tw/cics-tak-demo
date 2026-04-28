#!/usr/bin/env bash
# gen-certs.sh - Generate self-signed PKI for the CICS TAK PoC.
#
# Produces a small CA + a TAK Server cert + a CoT Gateway client p12.
# All artifacts land in infra/certs/ by default.
#
# This is a development convenience. For production deployments use the
# real PKI process documented in docs/tak-server-deployment.md (your
# enterprise CA or TAK.gov-issued certificates) and place the equivalent
# files into infra/certs/ keeping the same filenames.
#
# Files produced
# ──────────────
#   ca.crt                CA certificate (public)
#   ca.key                CA private key (KEEP SAFE)
#   takserver.crt/.key    Server cert/key for the TAK Server stub or prod
#   gateway.crt/.key      CoT Gateway client cert/key
#   gateway.p12           CoT Gateway PKCS#12 bundle (consumed by services/cot-gateway)
#   truststore.pem        Trust store (copy of ca.crt) for Python ssl context
#
# All certs are valid for 825 days (Apple's max for trust chain trust).
#
# Usage:
#   scripts/gen-certs.sh                              # default settings
#   scripts/gen-certs.sh --output infra/certs --p12-password mypass
#   scripts/gen-certs.sh --tak-host tak.example.com   # cert SAN customization
#   scripts/gen-certs.sh --force                      # regenerate from scratch

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
OUTPUT_DIR="${ROOT_DIR}/infra/certs"
DAYS=825
CA_CN="CICS-TAK-PoC-CA"
TAK_CN="takserver"
TAK_HOST="localhost"
TAK_IPS=("127.0.0.1")
GATEWAY_CN="cot-gateway"
P12_PASSWORD="${TAK_P12_PASSWORD:-takpoc}"
FORCE="false"

log()  { printf "\033[1;36m[gen-certs]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[gen-certs]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[gen-certs]\033[0m %s\n" "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: scripts/gen-certs.sh [options]

Options
  --output <dir>         Output directory. Default: ${OUTPUT_DIR}
  --days <n>             Certificate validity. Default: ${DAYS}
  --ca-cn <cn>           CA Common Name. Default: ${CA_CN}
  --tak-cn <cn>          Server cert CN. Default: ${TAK_CN}
  --tak-host <host>      Add host to server cert SAN. Default: ${TAK_HOST}
                         (Pass multiple times for multiple SANs.)
  --tak-ip <ip>          Add IP to server cert SAN. Default: 127.0.0.1
                         (Pass multiple times.)
  --gateway-cn <cn>      Gateway client CN. Default: ${GATEWAY_CN}
  --p12-password <pwd>   PKCS#12 password for gateway.p12.
                         Default: \$TAK_P12_PASSWORD or 'takpoc'
  --force                Overwrite existing certs without confirmation
  -h, --help             Show this help

Examples
  scripts/gen-certs.sh
  scripts/gen-certs.sh --tak-host tak.lab --tak-ip 10.0.0.5
  scripts/gen-certs.sh --p12-password "\$(openssl rand -hex 16)"
EOF
}

# Parse args
SAN_HOSTS=("${TAK_HOST}")
SAN_IPS=("${TAK_IPS[@]}")
HOSTS_OVERRIDDEN="false"
IPS_OVERRIDDEN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)         OUTPUT_DIR="$2"; shift 2 ;;
    --days)           DAYS="$2"; shift 2 ;;
    --ca-cn)          CA_CN="$2"; shift 2 ;;
    --tak-cn)         TAK_CN="$2"; shift 2 ;;
    --tak-host)
      if [[ "${HOSTS_OVERRIDDEN}" == "false" ]]; then SAN_HOSTS=(); HOSTS_OVERRIDDEN="true"; fi
      SAN_HOSTS+=("$2"); shift 2 ;;
    --tak-ip)
      if [[ "${IPS_OVERRIDDEN}" == "false" ]]; then SAN_IPS=(); IPS_OVERRIDDEN="true"; fi
      SAN_IPS+=("$2"); shift 2 ;;
    --gateway-cn)     GATEWAY_CN="$2"; shift 2 ;;
    --p12-password)   P12_PASSWORD="$2"; shift 2 ;;
    --force)          FORCE="true"; shift ;;
    -h|--help)        usage; exit 0 ;;
    *)                die "Unknown argument: $1 (use --help)" ;;
  esac
done

command -v openssl >/dev/null 2>&1 || die "openssl is required but not found in PATH"

mkdir -p "${OUTPUT_DIR}"
cd "${OUTPUT_DIR}"

# Pre-flight: refuse to overwrite without --force
existing=()
for f in ca.crt ca.key takserver.crt takserver.key gateway.crt gateway.key gateway.p12 truststore.pem; do
  [[ -f "$f" ]] && existing+=("$f")
done
if [[ ${#existing[@]} -gt 0 && "${FORCE}" != "true" ]]; then
  warn "Existing certs found in ${OUTPUT_DIR}: ${existing[*]}"
  warn "Re-run with --force to overwrite. Aborting."
  exit 1
fi

# 1. Root CA -----------------------------------------------------------------
log "Step 1/4: generating root CA (${CA_CN})"
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days "${DAYS}" \
  -subj "/CN=${CA_CN}/O=CICS TAK PoC/C=TW" \
  -out ca.crt 2>/dev/null
cp ca.crt truststore.pem

# 2. TAK Server cert ---------------------------------------------------------
log "Step 2/4: generating TAK Server cert (CN=${TAK_CN}, SAN hosts=${SAN_HOSTS[*]}, ips=${SAN_IPS[*]})"

# Build openssl extension config dynamically
ext_file="$(mktemp)"
{
  echo "subjectAltName=@alt_names"
  echo "extendedKeyUsage=serverAuth,clientAuth"
  echo "[alt_names]"
  i=1
  for h in "${SAN_HOSTS[@]}"; do
    echo "DNS.${i} = ${h}"
    i=$((i+1))
  done
  i=1
  for ip in "${SAN_IPS[@]}"; do
    echo "IP.${i} = ${ip}"
    i=$((i+1))
  done
} > "${ext_file}"

openssl genrsa -out takserver.key 2048 2>/dev/null
openssl req -new -key takserver.key \
  -subj "/CN=${TAK_CN}/O=CICS TAK PoC/C=TW" \
  -out takserver.csr 2>/dev/null
openssl x509 -req -in takserver.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out takserver.crt -days "${DAYS}" -sha256 \
  -extfile "${ext_file}" 2>/dev/null
rm -f takserver.csr "${ext_file}"

# 3. CoT Gateway client cert -------------------------------------------------
log "Step 3/4: generating CoT Gateway client cert (CN=${GATEWAY_CN})"
gw_ext="$(mktemp)"
{
  echo "subjectAltName=DNS:${GATEWAY_CN}"
  echo "extendedKeyUsage=clientAuth"
} > "${gw_ext}"

openssl genrsa -out gateway.key 2048 2>/dev/null
openssl req -new -key gateway.key \
  -subj "/CN=${GATEWAY_CN}/O=CICS TAK PoC/C=TW" \
  -out gateway.csr 2>/dev/null
openssl x509 -req -in gateway.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out gateway.crt -days "${DAYS}" -sha256 \
  -extfile "${gw_ext}" 2>/dev/null
rm -f gateway.csr "${gw_ext}"

log "Step 4/4: bundling gateway.p12 (PKCS#12)"
openssl pkcs12 -export \
  -inkey gateway.key -in gateway.crt -certfile ca.crt \
  -name "${GATEWAY_CN}" -passout "pass:${P12_PASSWORD}" \
  -out gateway.p12 2>/dev/null

# Sane permissions for keys
chmod 600 ca.key takserver.key gateway.key gateway.p12
chmod 644 ca.crt takserver.crt gateway.crt truststore.pem

# Provide a friendly .env snippet developers can copy into .env / shells
env_snippet="${OUTPUT_DIR}/cert.env"
{
  echo "# Source this file (or copy into your shell) when running services that"
  echo "# consume the gateway p12. Generated by scripts/gen-certs.sh."
  echo "export TAK_P12_PASSWORD='${P12_PASSWORD}'"
  echo "export TAK_CERT_DIR='${OUTPUT_DIR}'"
} > "${env_snippet}"
chmod 600 "${env_snippet}"

log "Done. Artifacts in ${OUTPUT_DIR}:"
ls -1 "${OUTPUT_DIR}" | sed 's/^/  /'
log "PKCS#12 password (gateway.p12): ${P12_PASSWORD}"
log "Quick sanity check:"
echo "  openssl verify -CAfile ${OUTPUT_DIR}/ca.crt ${OUTPUT_DIR}/takserver.crt"
echo "  openssl verify -CAfile ${OUTPUT_DIR}/ca.crt ${OUTPUT_DIR}/gateway.crt"
echo "  openssl pkcs12 -in ${OUTPUT_DIR}/gateway.p12 -nokeys -passin pass:${P12_PASSWORD} | head"
