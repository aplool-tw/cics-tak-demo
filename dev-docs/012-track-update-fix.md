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

## Known Issues / Gotchas

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
