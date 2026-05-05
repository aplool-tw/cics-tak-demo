# 012 — CoT Gateway Track Update Fix

## Summary

Feature 012 fixes two persistent CoT Gateway map issues:

1. EchoShield track position freeze in the web map (marker stayed at first position).
2. FUSED track not appearing cleanly when both EchoShield and Sentrycs tracked the same drone.

## Key Technical Decisions

- Switched map marker rendering from destructive `clearLayers()` redraws to incremental UID-keyed updates in `refreshTracks()`:
  - `droneMarkers[uid]` registry
  - `setLatLng()` for in-place position updates
  - stale-marker removal by uid diff
- Added dedicated `arrowLayer` and clear it per refresh to prevent velocity-arrow accumulation.
- Added `uid` to TrackStore serialized payloads so `/tracks` provides a stable identity key for frontend updates.
- Changed source-switch logic to return **all** old uids (`list[str]`) rather than first match only.
- Updated `_emit_for_track` to stale-emit and remove every old uid during source transitions.
- Made correlator timestamp comparison timezone-safe for mixed naive/aware datetimes.

## Post-implementation Bug Fix (EchoShield Tick Loop Crash)

After deploying RC1–RC4, end-to-end demo revealed the EchoShield marker
still froze in the map viewer. Root cause investigation over multiple sessions:

### Symptom
ECHO marker appeared at t=9s, stopped moving ~8s later. FUSED never appeared.
HTTP `/info` endpoint (aiohttp) kept responding, misleading investigators into
thinking the loop was "hung" rather than "crashed."

### True Root Cause: Pydantic ValidationError at tick ~91

When the drone passes due-north of the EchoShield sensor, the azimuth is 0° /
360°. The `azimuth_deg()` function in `geo/bearing.py` applied a `>= 360` guard
**before** `round(brg, 2)`. Python's `round(359.995, 2)` returns `360.0` due to
IEEE-754 double-precision rounding. After rounding, the guard was already past,
so `360.0` reached the `RadarTrack` pydantic model which has `lt=360`. The
resulting `ValidationError` propagated uncaught through `run_one_tick()` →
`run_forever()` → killed the entire tick coroutine. The aiohttp HTTP server was
a separate task and kept running, hiding the crash.

### Fix

1. **`geo/bearing.py`**: moved `round()` before the `>= 360` guard so the
   post-rounding value is always clamped to `[0, 360)`.

2. **`loop.py`**: added `except Exception` in `run_one_tick()` that logs
   `tick_error` and continues the loop (CancelledError still propagates).
   Added `try/except CancelledError/Exception` in `run_forever()` with
   structured ERROR logs (`run_forever_cancelled`, `run_forever_exception`)
   and a `run_forever_exit` INFO on any exit path.

3. **`feed/tcp_server.py`**: removed `await asyncio.sleep(0)` from
   `broadcast()`. The coroutine now has no yield points, preventing potential
   `CancelledError` injection from `asyncio.wait_for`'s internal task-cancel
   machinery. TCP data is flushed by the next tick's `await mapsim.fetch()`.

### Validation
- 74 echoshield-sim tests pass; 148 cot-gateway tests pass.
- Full 125s demo run: ECHO marker moves continuously t=9–43s;
  FUSED appears at t≈44s; continuous `correlation_hit` at 10 Hz confirmed.


- Full multi-service test runs can fail if port `9001` is already occupied by another local simulator process. Kill the specific PID before running `services/echoshield-sim` tests.
- `tak-client-sim` test suite currently emits existing `aiohttp` `NotAppKeyWarning` warnings; these are pre-existing and non-blocking.

## File Change Summary

### Source
- `services/cot-gateway/src/cot_gateway/web/track_store.py`
- `services/cot-gateway/src/cot_gateway/web/server.py`
- `services/cot-gateway/src/cot_gateway/cot/uid.py`
- `services/cot-gateway/src/cot_gateway/loop.py`
- `services/cot-gateway/src/cot_gateway/correlate/correlator.py`

### Tests
- `services/cot-gateway/tests/unit/test_track_store_uid.py` (new)
- `services/cot-gateway/tests/unit/test_uid_source_switch.py` (updated)
- `services/cot-gateway/tests/unit/test_correlator_tz.py` (new)
- `services/cot-gateway/tests/integration/test_multi_uid_source_switch.py` (new)
- `services/cot-gateway/tests/integration/test_us2_fusion_upgrade.py` (updated)

### Speckit Artifacts
- `specs/012-track-update-fix/spec.md`
- `specs/012-track-update-fix/plan.md`
- `specs/012-track-update-fix/research.md`
- `specs/012-track-update-fix/data-model.md`
- `specs/012-track-update-fix/quickstart.md`
- `specs/012-track-update-fix/tasks.md`
- `specs/012-track-update-fix/contracts/tracks-api.md`
