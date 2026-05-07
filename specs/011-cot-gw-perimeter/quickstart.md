# Developer Quickstart: Feature 011 — CoT Gateway Perimeter Guard

**Branch**: `feature/011-cot-gw-perimeter`  
**Services modified**: `cot-gateway`, `sentrycs-sim`

---

## What This Feature Does

Five concurrent fixes:

| RC | Fix | Where |
|----|-----|-------|
| RC1 | `Cache-Control: no-store` on `/tracks` + `/sites` | `server.py` |
| RC2 | Move `clearLayers()` inside success branch of `refreshSites()` | `server.py` (JS) |
| RC3 | New `PerimeterGuard` module fires UDS takeover at SP perimeter breach | `cot_gateway/perimeter/` + `loop.py` |
| RC4 | Sentrycs `detection_radius_m` → 2 000 m | `sentrycs-sim/config/demo.yaml` |
| RC5 | Orange `[TAKEOVER]` badge when `takeover_issued=true` | `server.py` (JS) |

---

## Prerequisites

```bash
# Python 3.11+ must be active
python3 --version  # >= 3.11

# From repo root — install both services in editable mode
pip install -e "services/cot-gateway[dev]"
pip install -e "services/sentrycs-sim[dev]"
```

---

## Running Tests

### cot-gateway (target: ≥ 95 baseline + new 011 tests)

```bash
cd services/cot-gateway
ruff check .
black --check src tests
python3 -m pytest -q
```

### sentrycs-sim (target: ≥ 117 baseline + updated tests)

```bash
cd services/sentrycs-sim
ruff check .
black --check src tests
python3 -m pytest -q
```

### Run all at once

```bash
cd services/cot-gateway && python3 -m pytest -q && \
cd ../sentrycs-sim && python3 -m pytest -q
```

---

## Running the Demo Scenario

### 1. Start all services

```bash
# From repo root
scripts/dev-launcher.sh
```

Or individually:

```bash
# Terminal 1 — UDS (drone intercept service)
cd services/uds && python3 -m uds --port 18080

# Terminal 2 — Map Sim (drone position simulator)
cd services/map-sim && python3 -m map_sim

# Terminal 3 — Sentrycs Sim (RF sensor simulator)
cd services/sentrycs-sim && python3 -m sentrycs_sim --config config/demo.yaml

# Terminal 4 — EchoShield Sim (radar sensor simulator)
cd services/echoshield-sim && python3 -m echoshield_sim --config config/e2e_scenario.yaml

# Terminal 5 — CoT Gateway (fusion + perimeter guard)
cd services/cot-gateway && python3 -m cot_gateway --config config/demo.yaml
```

### 2. Open the tactical map

```
http://localhost:18092/map
```

### 3. Expected event timeline (drone starts 3 500 m north of SP, 35 m/s)

| Time | Event |
|------|-------|
| t ≈ 9 s | EchoShield first detects drone at 3 200 m range → blue `◆` appears |
| t ≈ 43 s | Drone enters 2 000 m Sentrycs range → source switches to FUSED → red `✈` |
| t ≈ 71 s | Drone crosses 1 000 m SP perimeter → PerimeterGuard fires UDS takeover |
| t ≈ 71 s + 2 s | Map refreshes → drone icon turns **orange** `✈`, panel shows `[TAKEOVER]` |
| t ≈ 110 s | Drone neutralized → icon fades |

### 4. Verify PerimeterGuard fired

Look for this structured log line in cot-gateway output (JSON):

```json
{"event": "perimeter_breach", "uid": "FUSED-TRK-E01", "dist_m": 999.X, "radius_m": 1000.0, "level": "info", ...}
```

Followed by:

```json
{"event": "takeover_issued", "uid": "FUSED-TRK-E01", "http_status": 200, "level": "info", ...}
```

### 5. Verify no UDS call from sentrycs-sim

In sentrycs-sim logs, confirm **no** `uds_takeover` or `perimeter_breach` events after t = 0.

---

## Key Files Changed

### New Files

| Path | Description |
|------|-------------|
| `services/cot-gateway/src/cot_gateway/perimeter/__init__.py` | Package export |
| `services/cot-gateway/src/cot_gateway/perimeter/guard.py` | `PerimeterGuard` class |
| `services/cot-gateway/tests/unit/test_perimeter_guard.py` | PerimeterGuard unit tests |
| `services/cot-gateway/tests/integration/test_perimeter_integration.py` | End-to-end breach test |

### Modified Files

| Path | Change |
|------|--------|
| `services/cot-gateway/src/cot_gateway/config.py` | Add `PerimeterGuardConfig`, `GatewayConfig.perimeter` |
| `services/cot-gateway/src/cot_gateway/loop.py` | Instantiate + call `PerimeterGuard.check()` |
| `services/cot-gateway/src/cot_gateway/web/track_store.py` | Add `_takeover_set`, `mark_takeover()`, update `_serialize` |
| `services/cot-gateway/src/cot_gateway/web/server.py` | Cache-Control headers; `clearLayers()` fix; `droneIcon()` orange + badge |
| `services/cot-gateway/config/demo.yaml` | Add `perimeter:` section |
| `services/sentrycs-sim/src/sentrycs_sim/config.py` | Remove `defense_radius_m` field |
| `services/sentrycs-sim/src/sentrycs_sim/loop.py` | Replace step 4 with time-based MITIGATING transition |
| `services/sentrycs-sim/config/demo.yaml` | `detection_radius_m: 2000.0`, remove `defense_radius_m`, revise timestamps |

---

## Configuration Reference

### `cot-gateway/config/demo.yaml` — new `perimeter:` section

```yaml
perimeter:
  enabled: true
  uds_url: "http://127.0.0.1:18080"
  radius_m: 1000.0
  sp_lat: 24.725806       # SP = Strategic Point (same as web.sp_lat)
  sp_lon: 121.033750
  holding_lat: 24.725806  # HP = Holding Point (takeover landing target)
  holding_lon: 121.071889
  holding_alt_m: 50.0
  descent_speed_ms: 15.0  # stored in config; not sent in UDS wire call
```

To **disable** the perimeter guard without removing the section:

```yaml
perimeter:
  enabled: false
  # ... other fields ignored when enabled: false
```

To **remove** the guard entirely, delete the `perimeter:` key — `GatewayConfig.perimeter` defaults to `None`.

---

## Debugging

### Track frozen on map (RC1)

In browser DevTools → Network → filter `/tracks` → check response headers:

```
Cache-Control: no-store, no-cache
Pragma: no-cache
```

If missing, check `server.py` `_NO_CACHE` constant and `_tracks` handler.

### Sensor marker blinks (RC2)

Throttle `/sites` in DevTools → Network → "Slow 3G". Markers should stay visible during fetch. If they disappear, check that `siteLayer.clearLayers()` is inside the `if (r.ok)` branch in `refreshSites()`.

### PerimeterGuard not firing

1. Confirm `perimeter.enabled: true` in `config/demo.yaml`
2. Confirm `perimeter.radius_m` > actual drone distance to SP at trigger time
3. Check that `track.source` is `SENTRYCS` or `FUSED` (EchoShield-only tracks do not trigger)
4. Check that `track.detection_status` is `DETECTED` or `MITIGATING`
5. Look for `perimeter_guard_disabled` log — means SP coords missing or config invalid

### Orange icon not appearing (RC5)

1. Confirm `/tracks` response includes `"takeover_issued": true` for the affected track
2. Check `droneIcon()` function has the `t.takeover_issued` branch
3. Confirm `TrackStore.mark_takeover(uid)` was called (check `takeover_issued` log event)

---

## Test Coverage Targets

| Suite | Baseline (pre-011) | Target (post-011) |
|-------|--------------------|-------------------|
| `cot-gateway` pytest | ≥ 95 | ≥ 95 + all new 011 tests |
| `sentrycs-sim` pytest | ≥ 117 | ≥ 117 (no regressions; some tests updated) |
| `ruff check` | clean | clean |
| `black --check` | clean | clean |

---

## Spec Reference

- Spec: `specs/011-cot-gw-perimeter/spec.md`
- Plan: `specs/011-cot-gw-perimeter/plan.md`
- Research: `specs/011-cot-gw-perimeter/research.md`
- Tasks: `specs/011-cot-gw-perimeter/tasks.md` (generated by `/speckit.tasks`)
