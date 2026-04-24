#!/usr/bin/env bash
# Smoke: tail TCP feed for a few seconds + sanity-check Map Sim reachable.
set -euo pipefail

MAP_SIM_URL="${MAP_SIM_URL:-http://localhost:8090}"
FEED_HOST="${FEED_HOST:-localhost}"
FEED_PORT="${FEED_PORT:-9000}"
SECONDS_TO_TAIL="${SECONDS_TO_TAIL:-3}"

echo "[smoke] curl ${MAP_SIM_URL}/objects?lat=24.0&lon=121.0&radius_m=4800"
curl -sf "${MAP_SIM_URL}/objects?lat=24.0&lon=121.0&radius_m=4800" | head -c 400
echo
echo "[smoke] nc ${FEED_HOST} ${FEED_PORT}  (tailing ${SECONDS_TO_TAIL}s)"
timeout "${SECONDS_TO_TAIL}" nc "${FEED_HOST}" "${FEED_PORT}" | head -n 20 || true
echo "[smoke] done"
