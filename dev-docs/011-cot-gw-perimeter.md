# dev-docs/011-cot-gw-perimeter.md

**Feature**: 011 — CoT Gateway Perimeter Guard  
**Branch**: `feature/011-cot-gw-perimeter`  
**Date**: 2026-04-30  
**Author**: Copilot

---

## Summary

This feature fixes 5 root causes discovered in the TAK PoC demo:

1. **RC1** — EchoShield track frozen on map (browser GET cache)
2. **RC2** — EchoShield sensor marker briefly disappears (premature `clearLayers()`)
3. **RC3** — Perimeter takeover moved from sentrycs-sim to CoT Gateway
4. **RC4** — Sentrycs detection radius corrected to 2000 m; scenario timing updated
5. **RC5** — Post-takeover drone shows orange `[TAKEOVER]` visual state on map

---

## Key Technical Decisions

### A. Cache-Control headers (RC1)

`aiohttp.web.json_response()` does not set `Cache-Control` by default. Browsers aggressively cache `GET` responses without a `Cache-Control: no-store` directive, causing the `/tracks` polling loop to return the first-ever response on every call.

**Fix**: added module-level constant:
```python
_NO_CACHE = {"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"}
```
Applied to `/tracks` and `/sites` handlers (not `/health` — intentionally excluded per spec FR-011-003 to avoid cache overhead on health checks). JS `fetch()` calls updated with `{cache: 'no-store'}` as defence-in-depth.

### B. `clearLayers()` move (RC2)

Original code called `siteLayer.clearLayers()` and `sensorLayer.clearLayers()` at the top of `refreshSites()`, before the fetch completed. A slow or failed `/sites` response left the layer empty for the full 30-second interval.

**Fix**: moved both `clearLayers()` calls to inside the `try` block, immediately after `if (!r.ok) return;` and before repopulating the layer.

### C. PerimeterGuard module (RC3)

New package `cot_gateway/perimeter/guard.py`:

```
services/cot-gateway/src/cot_gateway/perimeter/
    __init__.py
    guard.py          ← PerimeterGuard class
```

`PerimeterGuard.check(track, uid=..., mark_takeover=...)`:
- Only fires for `TrackSource.SENTRYCS` or `TrackSource.FUSED` with `detection_status in {"DETECTED","MITIGATING"}`
- Calls `haversine_m(sp_lat, sp_lon, track.lat, track.lon)` — reuses `cot_gateway.correlate.haversine.haversine_m` (G7 compliant, no new deps)
- Idempotency latch: `track.track_id` added to `_triggered: set[str]` **before** the async UDS call to prevent double-fire
- Handles HTTP 409 ("already mitigating") as success
- On transport error: logs `takeover_transport_failed` and returns — does NOT raise
- On success (200 or 409): calls `mark_takeover(uid)` to set `takeover_issued=True` in TrackStore

### D. SP vs holding point coordinates

The `PerimeterGuardConfig` in YAML contains two distinct coordinate pairs:
- `radius_m` / no explicit SP coords → the SP lat/lon comes from `config.web.sp_lat` / `config.web.sp_lon` in `GatewayMain`
- `holding_lat`, `holding_lon`, `holding_alt_m` → the UDS takeover TARGET (holding point ~3.8 km east of SP)

This design avoids duplicating SP coordinates between `web:` and `perimeter:` sections of the same YAML file.

### E. sentrycs-sim cleanup (RC3 / RC4)

**Removed**: `defense_radius_m` field from `SentrycsConfig` and the position-based takeover block from `LoopRunner.run_one_tick()`.

**Replaced**: the old "step 4 — schedule takeovers" with a simple time-based `DETECTED→MITIGATING` transition:
```python
for track in list(self.registry):
    if track.status is not DetectionStatus.DETECTED:
        continue
    scenario = self.config.drone_by_uid(track.uid)
    if scenario and elapsed >= float(scenario.mitigating_at_s):
        self.sm.transition(track, DetectionStatus.MITIGATING, reason="time_based", now=now_utc)
        track.takeover_sent = True
```
`_ensure_takeover_task()` is kept in the codebase (it may still be called by other code paths in future) but is **no longer called** from the main tick loop. `UdsClient` remains wired but unused.

**Result**: zero UDS calls originate from sentrycs-sim during a normal demo run.

### F. Idempotency latch lifetime

The `_triggered` set in `PerimeterGuard` is permanent for the service lifetime (cleared only on restart). This is G6 compliant — PoC services are memory-only. The spec AC-5 ("latch clears on TTL expiry") was deprioritised in favour of the simpler permanent-latch model per `plan.md §B`.

### G. takeover_issued in TrackStore

```python
class TrackStore:
    _takeover_set: set[str]   # UIDs with active takeover

    async def mark_takeover(uid: str) -> None  # adds to set
    async def remove(uid: str) -> None         # also discards from set
    async def get_all() -> list[dict]          # includes "takeover_issued": bool
```

`_serialize(track, takeover_issued=False)` receives the flag from `get_all()` which checks `uid in self._takeover_set` inside the lock.

---

## File Change Summary

| File | Change |
|------|--------|
| `cot-gateway/config.py` | Add `PerimeterGuardConfig` + optional `perimeter` field on `GatewayConfig` |
| `cot-gateway/loop.py` | Wire `PerimeterGuard` into `__init__` and `_emit_for_track` |
| `cot-gateway/perimeter/__init__.py` | New package |
| `cot-gateway/perimeter/guard.py` | New `PerimeterGuard` class (123 lines) |
| `cot-gateway/web/server.py` | `_NO_CACHE` headers, JS flicker fix, `droneIcon` takeover state |
| `cot-gateway/web/track_store.py` | `mark_takeover`, `_takeover_set`, `takeover_issued` in serialized output |
| `cot-gateway/config/demo.yaml` | Add `perimeter:` section |
| `sentrycs-sim/config.py` | Remove `defense_radius_m` |
| `sentrycs-sim/loop.py` | Remove position-based takeover; add time-based DETECTED→MITIGATING |
| `sentrycs-sim/config/demo.yaml` | `detection_radius_m: 2000.0`, updated timing |
| `cot-gateway/tests/unit/test_server.py` | New: cache header tests |
| `cot-gateway/tests/unit/test_server_js.py` | New: JS `cache: 'no-store'` template tests |
| `cot-gateway/tests/unit/test_track_store_takeover.py` | New: TrackStore takeover flag tests |
| `cot-gateway/tests/unit/test_perimeter_config.py` | New: PerimeterGuardConfig validation tests |
| `cot-gateway/tests/unit/test_perimeter_guard.py` | New: PerimeterGuard 7-scenario unit tests |
| `cot-gateway/tests/integration/test_perimeter_integration.py` | New: end-to-end perimeter trigger test |
| `sentrycs-sim/tests/unit/test_loop.py` | Updated: remove defense_radius_m test cases |
| `sentrycs-sim/tests/integration/*.py` | Updated: remove UDS call expectations |
| `specs/011-cot-gw-perimeter/` | Speckit artifacts: spec, plan, research, quickstart, tasks |

---

## Test Results

| Service | Before | After | Delta |
|---------|--------|-------|-------|
| cot-gateway | ~95 | 127 | +32 |
| sentrycs-sim | 117 | 117 | 0 |
| uds | 83 | 83 | 0 |
| map-sim | 107 | 107 | 0 |
| echoshield-sim | 74 | 74 | 0 |
| tak-client-sim | 59 | 59 | 0 |
| **Total** | **535** | **567** | **+32** |

All pass. `ruff check` + `black --check` clean on all modified services.

---

## Demo Timeline (updated)

With drone starting 3500 m north of SP at 35 m/s:

| Time | Event |
|------|-------|
| t≈9s | Drone enters EchoShield 3200 m radar range |
| t≈43s | Drone enters Sentrycs 2000 m detection range → `DETECTED` |
| t≈71s | Drone crosses SP 1000 m perimeter → CoT Gateway fires `POST /command/takeover` to UDS |
| t=71s | Map shows orange drone icon + `[TAKEOVER]` badge |
| t=71s | sentrycs-sim transitions to `MITIGATING` (time-based) |
| t=110s | sentrycs-sim transitions to `NEUTRALIZED` |
| t=140s | NEUTRALIZED removed from registry (30 s hold) |

---

## Known Issues / Gotchas

1. **SP coordinates duplication**: The perimeter center is read from `config.web.sp_lat/sp_lon`, not from a dedicated `sp_lat/sp_lon` in `PerimeterGuardConfig`. If the SP moves (different sites_file), the web config must be updated too.

2. **Idempotency latch is service-lifetime**: A drone that was already taken over and later re-enters the perimeter after a long absence will NOT trigger a second takeover. Service restart resets the latch.

3. **takeover_sent flag re-use**: `DroneTrack.takeover_sent` is re-used in sentrycs-sim to mark the time-based MITIGATING transition. It was originally used to prevent double-UDS-calls, but now prevents double-MITIGATING transitions. Semantically still correct but the name is slightly misleading.

4. **JS tests via template grep**: The JS `{cache: 'no-store'}` fix is verified by scanning the rendered HTML template in `test_server_js.py` — there is no headless browser test harness. This is acceptable for a PoC.
