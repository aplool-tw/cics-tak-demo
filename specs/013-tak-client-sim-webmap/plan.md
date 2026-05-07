# Implementation Plan: 013-tak-client-sim-webmap

**Branch**: `feature/013-tak-client-sim-webmap` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/013-tak-client-sim-webmap/spec.md`

## Summary

Upgrade the `tak-client-sim` Leaflet web map with MIL-STD-2525C-compliant SVG icons (Unknown = grey circle+cross; Hostile = red diamond; stale = dimmed) and add a `use_ssl: bool` field to `ClientConfig` so the demo can connect to `tak_relay.py` over plaintext TCP. Deliver two new end-to-end demo shell scripts (`demo-1drone.sh`, `demo-3drone.sh`) that start all seven pipeline services in order, health-check them, and open three browser tabs simultaneously. No new Python dependencies; all icon changes are inline SVG inside `L.divIcon`.

---

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: aiohttp (web server), pydantic v2 (config), structlog (logging), asyncio (TCP), Leaflet 1.9.4 CDN (JS map — already in use)  
**Storage**: In-memory `CotStore` only (no persistence)  
**Testing**: pytest (existing test suite)  
**Target Platform**: Linux / macOS developer laptop (localhost demo)  
**Project Type**: Web service (embedded Leaflet map + aiohttp JSON API) + Bash orchestration scripts  
**Performance Goals**: Map refresh ≤ 2 s end-to-end (SC-001/SC-002); demo cold-start ≤ 30 s (SC-003)  
**Constraints**: G2 — no wire-contract changes; G7 — no new Python packages; G3 — structlog JSON logging only (no `print()` in production modules)  
**Scale/Scope**: Single-host demo, up to 3 drone tracks, 7 services

---

## Constitution Check

*GATE: Constitution file is a placeholder template (not yet ratified for this project). Applying spec-derived governance gates instead.*

| Gate | Requirement Source | Status |
|------|--------------------|--------|
| G2 — No wire-contract changes | FR-013, SC-008 | ✅ All icon changes are client-side JS only; `/events` and `/health` JSON shapes are unchanged |
| G7 — No new Python deps | FR-006, SC-007 | ✅ Inline SVG in `L.divIcon`; `use_ssl` uses stdlib `ssl` (already imported) |
| G3 — structlog JSON logging | FR-012 | ✅ `web_server.py` already uses `structlog`; no `print()` to add |
| Pydantic v2 extra="forbid" | `ClientConfig.model_config` | ✅ New `use_ssl` field added via Pydantic field declaration |
| Bash safety (`set -euo pipefail`) | Pattern from `demo-cot-gateway-map.sh` | ✅ Both new scripts follow this pattern |

**Result**: All gates pass. No violations requiring justification.

---

## Components

### C-1 — `web_server.py`: MIL-STD-2525C icon update

**File**: `services/tak-client-sim/src/tak_client_sim/web_server.py`  
**Scope**: JavaScript inside the `_MAP_HTML_TEMPLATE` string constant

**Changes**:

1. **`evtColors(color, isStale)`** — Replace with `makeIconShape(cotType, isStale)` that derives shape from `cot_type` prefix:
   - `a-u-*` → Unknown: grey outlined circle with interior diagonal cross (×)
   - `a-h-*` → Hostile: red filled diamond (45°-rotated square)
   - Any other prefix → fallback to UNKNOWN grey circle
   - `isStale=true` → override fill to `#546e7a`, opacity to `0.45`

2. **`makeDroneIcon(evt)`** — Replace circle `<circle>` SVG with shape-switching logic:
   - Reads `evt.cot_type` (already present in `/events` JSON payload via `CotEvent.cot_type`)
   - Renders Unknown: `<circle r="10" fill="#90a4ae" stroke="#546e7a" stroke-width="2"/>` + cross lines `<line x1="-5" y1="-5" x2="5" y2="5"/>` + `<line x1="5" y1="-5" x2="-5" y2="5"/>`
   - Renders Hostile: `<rect x="-8" y="-8" width="16" height="16" fill="#ef5350" stroke="#b71c1c" stroke-width="2" transform="rotate(45)"/>`
   - Stale overlay: apply `opacity="0.45"` at `<svg>` level and grey fill override
   - Arrow (speed > 0.3 m/s): existing `<polygon points="0,-7 -3,-1 3,-1">` rotated to `course`; preserved inside shape boundary

3. **Legend** (`legend.onAdd`) — Replace old entries:
   - Old: `灰色目標 (GREY)` circle-dot, `敵對目標 (RED)` circle-dot
   - New: `未知目標 Unknown (a-u-*)` with grey circle+cross SVG, `敵對目標 Hostile (a-h-*)` with red diamond SVG, `過期 Stale` dimmed sample

**Key invariants preserved**:
- `iconSize: [24, 24]`, `iconAnchor: [12, 12]`, `popupAnchor: [0, -16]`
- `viewBox="-12 -12 24 24"` (unchanged)
- No external image files or new JS libraries

---

### C-2 — `config.py`: `use_ssl` field

**File**: `services/tak-client-sim/src/tak_client_sim/config.py`

**Change**: Add field to `ClientConfig`:
```python
use_ssl: bool = True
```
Placed after `port`, before `use_ssl_verify`. Default `True` preserves backward compatibility for all existing configs that omit the field.

**`load_config()` update**: Add CLI override block:
```python
if getattr(args, "ssl", None) is True:
    base["use_ssl"] = True
if getattr(args, "no_ssl", False):
    base["use_ssl"] = False
```

---

### C-3 — `connection.py`: plaintext TCP support

**File**: `services/tak-client-sim/src/tak_client_sim/connection.py`

**Change** in `connect_with_retry()`:
```python
ssl_ctx = build_ssl_context(config) if config.use_ssl else None
# ...
reader, writer = await asyncio.open_connection(
    config.host, config.port, ssl=ssl_ctx, limit=65536
)
```
When `ssl_ctx` is `None`, `asyncio.open_connection` uses plaintext TCP. No new imports required (`ssl` already imported).

---

### C-4 — `__main__.py`: `--ssl` / `--no-ssl` CLI flags

**File**: `services/tak-client-sim/src/tak_client_sim/__main__.py`

**Add to `_build_parser()`**:
```python
p.add_argument("--ssl",    action="store_true", dest="ssl",    help="Force SSL/TLS connection")
p.add_argument("--no-ssl", action="store_true", dest="no_ssl", help="Plaintext TCP (no TLS)")
```

---

### C-5 — `demo.yaml`: set `use_ssl: false`

**File**: `services/tak-client-sim/config/demo.yaml`

**Add line**:
```yaml
use_ssl: false       # connects to tak_relay.py (plaintext TCP on :18089)
```

---

### C-6 — `scripts/demo-1drone.sh`

**New file**: `scripts/demo-1drone.sh`

**Pattern**: Derived from `scripts/demo-cot-gateway-map.sh` with extensions.

**Services launched** (in order):

| # | Service | Launch command | PID var | Health check |
|---|---------|---------------|---------|--------------|
| 1 | map-sim | `python3 -m map_sim --port 8090` | `MAPSIM_PID` | `GET http://127.0.0.1:18090/health` → 200 |
| 2 | uds | `python3 -m uds --scenario demo_single_drone.yaml --api-port 18080 --map-sim-url http://127.0.0.1:18090` | `UDS_PID` | TCP connect `:18080` |
| 3 | echoshield-sim | `python3 -m echoshield_sim --config demo.yaml` | `ECHO_PID` | `GET http://127.0.0.1:19001/info` → 200 |
| 4 | sentrycs-sim | `python3 -m sentrycs_sim --scenario config/demo.yaml` | `SNTR_PID` | `GET http://127.0.0.1:17070/health` → 200 |
| 5 | cot-gateway | `python3 -m cot_gateway --config demo.yaml` | `GW_PID` | `GET http://127.0.0.1:18092/health` → 200 |
| 6 | tak-relay | `python3 scripts/tak_relay.py --port 8089` | `RELAY_PID` | TCP connect `:18089` |
| 7 | tak-client-sim | `python3 -m tak_client_sim --config services/tak-client-sim/config/demo.yaml` | `TAK_PID` | `GET http://127.0.0.1:18093/health` → 200 |

**Pre-flight checks** (all before first service launch):
1. Config file existence: `UDS_SCENARIO`, `ECHO_CONFIG`, `SNTR_CONFIG`, `GW_CONFIG`, `TAK_CONFIG`
2. `command -v python3`
3. Python module importability: `map_sim`, `uds`, `echoshield_sim`, `sentrycs_sim`, `cot_gateway`, `tak_client_sim`
4. File existence: `[[ -f scripts/tak_relay.py ]]`
5. Port conflict check: ports 8089, 8090, 8092, 8093, 18080, 7070 — using `/dev/tcp` or `ss -ltn`

**Port check helper** (using bash `/dev/tcp`):
```bash
check_port_free() {
    local port=$1
    if bash -c "echo > /dev/tcp/127.0.0.1/${port}" 2>/dev/null; then
        die "Port ${port} is already in use. Stop the conflicting service first."
    fi
}
```

**Health-check loop**: 30-second timeout, 1-second poll interval, same pattern as reference script. Checks all 7 services; prints progress ticker `map:· uds:· echo:· sntr:· gw:· relay:· tak:·`.

**Browser launch** (after all healthy):
```bash
for url in "http://127.0.0.1:18090/objects" "http://127.0.0.1:18092/map" "http://127.0.0.1:18093/map"; do
    xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null || echo "Open manually: $url"
done
```

**Cleanup**: `trap cleanup INT TERM EXIT`; SIGTERM all PIDs → sleep 1 → SIGKILL; remove all 7 PID files under `.dev-runtime/pids/`.

**`--stop` flag**: Reads all 7 PID files, sends SIGTERM, removes files. Graceful if PID file missing.

**PID file names**: `map-sim.pid`, `uds.pid`, `echoshield-sim.pid`, `sentrycs-sim.pid`, `cot-gateway.pid`, `tak-relay.pid`, `tak-client-sim.pid`

**Scenario banner**: Single drone (TRK-E01, DJI Mavic 3, 35 m/s, N→S route, t=9s first track).

---

### C-7 — `scripts/demo-3drone.sh`

**New file**: `scripts/demo-3drone.sh`

**Diff from `demo-1drone.sh`**:
- `UDS_SCENARIO`: `demo_three_drones.yaml`
- `SNTR_CONFIG`: `config/demo_three_drones.yaml`
- Banner text: Three-drone scenario
- All other logic (health checks, browser URLs, cleanup) identical

**Implementation strategy**: Not a copy — share a common helper pattern via variables so both scripts are independently executable without a `source`-based dependency.

---

## Project Structure

### Documentation (this feature)

```text
specs/013-tak-client-sim-webmap/
├── plan.md              ← this file
├── research.md          ← MIL-STD-2525C SVG shapes, inline SVG approach, ssl=None
├── data-model.md        ← ClientConfig.use_ssl field change
├── quickstart.md        ← demo-1drone.sh / demo-3drone.sh runbook
└── tasks.md             ← generated by /speckit.tasks (not this command)
```

*(No `contracts/` directory — G2 freeze: no new wire contracts)*

### Source Code Changes

```text
services/tak-client-sim/
├── src/tak_client_sim/
│   ├── web_server.py        ← C-1: makeDroneIcon() + legend update
│   ├── config.py            ← C-2: use_ssl: bool = True
│   ├── connection.py        ← C-3: ssl=None when use_ssl=False
│   └── __main__.py          ← C-4: --ssl / --no-ssl flags
└── config/
    └── demo.yaml            ← C-5: use_ssl: false

scripts/
├── demo-1drone.sh           ← C-6: new end-to-end 1-drone demo
└── demo-3drone.sh           ← C-7: new end-to-end 3-drone demo
```

**Structure Decision**: Modifications to the existing `tak-client-sim` service (no new packages or services). Two new Bash scripts in `scripts/` following the established `demo-cot-gateway-map.sh` pattern.

---

## Implementation Order

| Priority | Component | Rationale |
|----------|-----------|-----------|
| P1 | C-2 + C-3 + C-4 + C-5 | `use_ssl` config plumbing — required for demo scripts to connect without TLS errors; minimal risk, pure addition |
| P1 | C-1 | MIL-STD-2525C icon update — highest-visibility change (SC-001/SC-002) |
| P2 | C-6 | `demo-1drone.sh` — end-to-end single drone demo |
| P3 | C-7 | `demo-3drone.sh` — trivial delta from C-6 |

## Complexity Tracking

*No violations — all gates pass without justification required.*
