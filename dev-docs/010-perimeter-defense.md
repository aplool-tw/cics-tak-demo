# Feature 010 — Perimeter Defense

**Branch**: `feature/010-perimeter-defense`  
**Base**: `develop` (features 008 + 009 already merged)  
**Date**: 2026-04-30  
**Author**: Copilot

---

## Summary

Four targeted fixes and one new feature addressing UI readability, demo quality, track reliability, and automated perimeter defense in the Taiwan anti-drone TAK PoC.

---

## Changes

### 1. Map Legend — SP Defense Ring Colors & Entries

**Problem**: The 1 km / 2 km / 3 km radius rings around the Strategic Point (SP) were undocumented in the map legend. Their original colors (`#00e676` / `#ffca28` / `#ef5350`) conflicted with EchoShield sensor-range color (`#00BFFF`) and Sentrycs track/range color (`#FFD700`), making it impossible to distinguish ring types at a glance.

**Fix** (`services/cot-gateway/src/cot_gateway/web/server.py`):
- Changed `RING_COLORS` to pastel palette: `#80deea` (cyan-tint) / `#ffcc80` (peach) / `#ef9a9a` (rose).
- Added JavaScript `const RING_LABELS` array for hover tooltip text.
- Chained `.bindTooltip(RING_LABELS[i], ...)` on each ring `circle()` call so hovering a ring shows "1 km defense ring" etc.
- Inserted three new legend rows after "RF range" in the right panel HTML.

**Key decision**: Used `dashArray:'6 5'` for SP rings (unchanged) vs `dashArray:'8 5'` for sensor-range circles — the different dash spacing further distinguishes them even without color.

### 2. Demo Drone Speed 20 m/s → 35 m/s

**Problem**: At zoom 13 (≈5 km × 5 km view), a 20 m/s drone moves only ~40 m per 2-second map refresh — visually imperceptible as a "barely moved" dot.

**Fix** (`services/uds/scenarios/demo_single_drone.yaml`):
- `speed_ms: 20.0` → `speed_ms: 35.0`
- 35 m/s × 3 s refresh ≈ **105 m per tick** — clearly visible at zoom 13.

**Timing impact**: EchoShield entry (3.2 km from SP) now at ≈ t=9 s (was 15 s). Demo scenario time thresholds in `sentrycs-sim/config/demo.yaml` (`detected_at_s: 75`, `mitigating_at_s: 125`) are scenario-driven, not physics-driven — and are superseded by the new position-based defense trigger anyway.

### 3. FUSED Track Verification + Structured Log Enhancement

**Investigation outcome**: The `_emit_for_track` / `TrackStore` / `uid_for` logic was **already correct** before this feature. The pre-009 "FUSED never appears" bug was caused by Sentrycs tracks being silently dropped due to a `detection_status` key bug (fixed in 009). No correlator changes were required.

**Fixes**:
- Added guard test `test_track_source.py` confirming `TrackSource.{ECHOSHIELD,SENTRYCS,FUSED}.value` exactly match the JS `SRC_COLOR` keys in `server.py`. This prevents future renames from silently breaking the map coloring.
- Added wire-contract comment above `TrackSource` in `models/track.py`.
- Added `entity_keys=entity_keys_for(track)` to the `source_switch` structured log event in `loop.py` — improves observability when ECHO→FUSED transitions occur.

### 4. Defense Perimeter Auto-Takeover (New Feature)

**Design**: Position-based takeover trigger added to `sentrycs-sim` (Option A — keeps all drone tracking + UDS client logic in one service).

**Config** (`SentrycsConfig`):
- New field: `defense_radius_m: float | None = Field(default=None)`
- `None` → feature disabled, existing time-based trigger (`mitigating_at_s`) used unchanged (backward compatible).
- Set to `1000.0` in `sentrycs-sim/config/demo.yaml`.

**Logic** (`loop.py` step 4 of `run_one_tick`):
```
if defense_radius_m is not None:
    dist_m = haversine_m(sensor, drone)
    if dist_m < defense_radius_m → issue takeover
else:
    if elapsed >= mitigating_at_s → issue takeover
```

Guards:
- Only fires for `DETECTED` or `MITIGATING` status (MITIGATING guard is defensive — normally `takeover_sent=True` by then).
- `track.takeover_sent` flag prevents duplicate takeovers.
- Emits structured log event `perimeter_breach` with `uid`, `dist_m`, `defense_radius_m`.

**Haversine**: Reused `sentrycs_sim.geo.wgs84.haversine_m` — no new dependencies (G7 compliant).

---

## Test Results

| Service | Before | After | New Tests |
|---------|--------|-------|-----------|
| `uds` | 83 | 83 | 0 |
| `map-sim` | 107 | 107 | 0 |
| `echoshield-sim` | 74 | 74 | 0 |
| `sentrycs-sim` | 110 | 117 | +7 |
| `cot-gateway` | 94 | 95 | +1 |
| **Total** | **468** | **476** | **+8** |

New test files:
- `services/sentrycs-sim/tests/unit/test_loop.py` — 6 perimeter-defense tests (time-based + position-based + guards)
- `services/sentrycs-sim/tests/unit/test_config.py` — 1 `defense_radius_m` model validation test
- `services/cot-gateway/tests/unit/test_track_source.py` — 1 TrackSource wire-contract guard test

---

## Files Changed

```
services/cot-gateway/src/cot_gateway/web/server.py         ← RING_COLORS + RING_LABELS + tooltips + legend
services/cot-gateway/src/cot_gateway/models/track.py       ← wire-contract comment above TrackSource
services/cot-gateway/src/cot_gateway/loop.py               ← entity_keys in source_switch log
services/cot-gateway/tests/unit/test_track_source.py       ← NEW: guard test
services/sentrycs-sim/src/sentrycs_sim/config.py           ← defense_radius_m field
services/sentrycs-sim/src/sentrycs_sim/loop.py             ← haversine import + position-based branch
services/sentrycs-sim/config/demo.yaml                     ← detection_radius_m + defense_radius_m + comments
services/sentrycs-sim/tests/unit/test_loop.py              ← NEW: 6 unit tests
services/sentrycs-sim/tests/unit/test_config.py            ← +1 defense_radius_m test
services/uds/scenarios/demo_single_drone.yaml              ← speed_ms 20→35
```

---

## Known Issues / Gotchas

1. **EchoShield track disappears after takeover**: By design — drone flies to HP (24.725806, 121.071889) which is ~3855 m east of SP, outside EchoShield's 3200 m max range. Expected behavior.

2. **UDS ruff pre-existing warnings**: `services/uds` has ~37 pre-existing ruff lint warnings (unused imports, E702 semicolons). These are NOT introduced by this feature and exist from earlier work. They do not affect functionality or tests.

3. **MITIGATING guard in step 4**: The takeover loop now includes `MITIGATING` status as a trigger guard (in addition to `DETECTED`). In practice, by the time a track reaches `MITIGATING`, `takeover_sent` is already `True` — so this guard fires only in edge cases where a restart causes a missing flag. This is a plan-level defensive addition not required by spec.

4. **Backward compatibility**: Any YAML config without `defense_radius_m` will default to `None` → old time-based behavior. No migration required.

---

## Demo Walkthrough

```bash
# Start all services with demo configs
bash scripts/dev-launcher.sh

# Open map in browser
open http://localhost:8099/map

# Watch:
# t≈9s:  EchoShield picks up drone (3.2km range), ECHO-TRK-E01 appears (blue dot)
# t=75s: Sentrycs DETECTED at ~2km, FUSED-TRK-E01 replaces ECHO- (red dot)
# t≈71s: Drone crosses 1km defense ring → perimeter_breach logged → takeover issued to HP
# After takeover: drone flies east toward HP (121.071889E), EchoShield track fades at 3.2km
# Map legend shows pastel rings; hover over rings shows distance labels
```
