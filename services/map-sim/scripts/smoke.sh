#!/usr/bin/env bash
# Smoke script for Map Simulator (quickstart.md §3).
# Usage: scripts/smoke.sh [host:port]
set -euo pipefail

HOST="${1:-127.0.0.1:18090}"
BASE="http://${HOST}"

echo "==> POST valid payload"
curl -sS -X POST "${BASE}/objects/update" \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "TRK-001",
    "lat": 25.0584745,
    "lon": 121.5654089,
    "alt_m": 100.8,
    "speed_ms": 15.1,
    "heading_deg": 180.2,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:01.000Z"
  }' | tee /dev/stderr; echo

echo "==> POST payload with extra fields"
curl -sS -X POST "${BASE}/objects/update" \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "TRK-002",
    "lat": 25.0410, "lon": 121.5800, "alt_m": 150.0,
    "speed_ms": 18.0, "heading_deg": 270.0,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:00.900Z",
    "model": "DJI Mavic 3",
    "operator_lat": 25.1, "operator_lon": 121.6
  }' | tee /dev/stderr; echo

echo "==> GET /objects radar radius=4800"
curl -sS "${BASE}/objects?lat=25.0330&lon=121.5654&radius_m=4800" | tee /dev/stderr; echo

echo "==> GET /objects/all"
curl -sS "${BASE}/objects/all" | tee /dev/stderr; echo

echo "==> DELETE /objects/TRK-001"
curl -sS -X DELETE "${BASE}/objects/TRK-001" | tee /dev/stderr; echo

echo "==> GET /health"
curl -sS "${BASE}/health" | tee /dev/stderr; echo
