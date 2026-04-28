#!/usr/bin/env bash
# Smoke test: start cot-gateway against local stubs, observe TCP output, SIGINT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${CONFIG:-$ROOT/config/gateway.yaml}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

"${PYTHON:-python3}" -m cot_gateway --config "$CONFIG" >"$LOG" 2>&1 &
PID=$!
trap 'kill -INT $PID 2>/dev/null || true; rm -f "$LOG"' EXIT

sleep 2
echo "-- gateway log (first 20 lines) --"
head -20 "$LOG"

kill -INT "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
echo "-- smoke done --"
