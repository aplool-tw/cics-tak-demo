#!/usr/bin/env bash
# smoke.sh — quick connectivity smoke test for tak-client-sim
# Usage: ./scripts/smoke.sh [HOST] [PORT]
set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-8089}"
TIMEOUT=5

echo "==> Smoke: connecting to TAK Server at ${HOST}:${PORT} (${TIMEOUT}s timeout)"

python3 -m tak_client_sim \
    --host "${HOST}" \
    --port "${PORT}" \
    --max-retries 1 \
    --timeout "${TIMEOUT}" \
    2>&1 &

PID=$!
sleep "${TIMEOUT}"

if kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}"
    echo "==> Smoke: process ran for ${TIMEOUT}s without error (OK)"
    exit 0
else
    wait "${PID}"
    EXIT=$?
    if [ "${EXIT}" -eq 0 ]; then
        echo "==> Smoke: process exited cleanly (OK)"
        exit 0
    else
        echo "==> Smoke: process exited with code ${EXIT} (FAIL)"
        exit 1
    fi
fi
