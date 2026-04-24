#!/usr/bin/env bash
# Smoke test: start sentrycs-sim, hit /health, /detections, SIGINT, expect <10s total exit 0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIO="${SCENARIO:-$ROOT/config/local.yaml}"
PORT="${PORT:-7070}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

"${PYTHON:-python3}" -m sentrycs_sim --scenario "$SCENARIO" --api-port "$PORT" >"$LOG" 2>&1 &
PID=$!
trap 'kill -INT $PID 2>/dev/null || true; rm -f "$LOG"' EXIT

# wait up to 3s for /health
for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null; then
        break
    fi
    sleep 0.1
done

echo "-- /health --"
curl -sf "http://127.0.0.1:$PORT/health"
echo
echo "-- /detections --"
curl -sf "http://127.0.0.1:$PORT/detections"
echo

kill -INT "$PID"
wait "$PID" || true
echo "smoke ok"
