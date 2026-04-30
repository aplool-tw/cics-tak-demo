# Research: Feature 012 — CoT Gateway Track Update Fix

**Date**: 2026-04-30
**Status**: Complete — all questions pre-resolved during spec clarification session 2026-04-30

---

## Overview

Feature 012 is a focused bug-fix: four root causes (RC1–RC4) are fully diagnosed in the spec with
precise file/function-level attribution. No ambiguities remain. This document records the decisions
and their rationale so that the implementation tasks in `tasks.md` can reference explicit choices
without re-deriving them.

---

## Decision Registry

### R1 — `uid` Source in `/tracks` Payload (RC1/RC3)

**Decision**: Use the TrackStore dict key passed from `get_all()`'s `self._data.items()` iteration
as the `uid` value in `_serialize`.

**Rationale**: The TrackStore key *is* the authoritative CoT uid — it is the exact value written by
`_emit_for_track` via `await self._track_store.upsert(new_uid, track)`. Re-deriving the uid from
the track object inside `_serialize` would risk divergence if the track object's fields are stale or
if `uid_for()` is updated independently in a future feature. Using the dict key guarantees that the
`uid` field in the HTTP response always matches the CoT uid ATAK received.

**Alternatives considered**:
- Re-derive via `uid_for(track)` inside `_serialize` — *rejected*: adds coupling between the
  serializer and the uid derivation logic; divergence risk is non-zero over the feature lifetime.
- Add a `uid` field to `UnifiedTrack` — *rejected*: `UnifiedTrack` is a pure data model; uid
  derivation is deliberately placed in `cot/uid.py` to avoid model/business-logic coupling.

**Implementation**:
```python
# track_store.py — before
def _serialize(track: UnifiedTrack, takeover_issued: bool = False) -> dict[str, Any]:
    return {"source": ..., "track_id": ..., ...}

# track_store.py — after
def _serialize(track: UnifiedTrack, uid: str, takeover_issued: bool = False) -> dict[str, Any]:
    return {"uid": uid, "source": ..., "track_id": ..., ...}

# get_all() call-site — after
return [_serialize(t, uid, uid in self._takeover_set) for uid, t in self._data.items()]
```

---

### R2 — `detect_source_switch` Return Type (RC2)

**Decision**: Change return type from `tuple[Optional[str], str]` to `tuple[list[str], str]`.
An empty list `[]` replaces `None`; a single-element list `[old_uid]` replaces the scalar form;
a two-element list `[old_uid_1, old_uid_2]` handles the new dual-switch case.

**Rationale**: The current single-return design is the root cause of RC2. The loop over
`entity_keys_for(track)` exits on the first differing uid (`break`), discarding any second
differing uid that may exist under another entity key. The new implementation removes the `break`
and collects all distinct differing uids into a list. The iteration pattern in `_emit_for_track`
becomes `for old_uid in old_uids:` — uniform for 0, 1, or 2 uids with no special `None` check.

**Alternatives considered**:
- Keep `Optional[str]` + add a separate `extra_old_uids: list[str]` second return — *rejected*:
  awkward two-return pattern; existing callers would need to merge both returns anyway.
- Return `set[str]` — *rejected*: `list[str]` is sufficient; set semantics (unordered, hashable)
  are not required here and would complicate test assertions on ordering.

**Scope of callers**: Production call site = `_emit_for_track` in `loop.py` (one file). Test call
site = `test_uid_source_switch.py`. Both are in Feature 012 scope.

**Implementation**:
```python
# cot/uid.py — after
def detect_source_switch(
    track: UnifiedTrack, prev_uid_by_entity_key: dict[str, str]
) -> tuple[list[str], str]:
    new_uid = uid_for(track)
    old_uids: list[str] = []
    seen: set[str] = set()
    for key in entity_keys_for(track):
        prev = prev_uid_by_entity_key.get(key)
        if prev is not None and prev != new_uid and prev not in seen:
            old_uids.append(prev)
            seen.add(prev)
    return old_uids, new_uid
```

---

### R3 — JS Incremental Update Strategy (RC1)

**Decision**: Introduce a module-level `droneMarkers = {}` object initialised once at page-load,
persisted across all `refreshTracks()` calls. Replace `trackLayer.clearLayers()` with a three-step
incremental update:

1. **Upsert loop** — for each track in `/tracks` response:
   - If `uid` already in `droneMarkers`: call `marker.setLatLng()`, `marker.setIcon()`,
     `marker.setTooltipContent()` (or `bindTooltip`) on the existing marker.
   - If `uid` not in `droneMarkers`: create a new `L.marker()`, add to `trackLayer`, store in
     `droneMarkers[uid]`.
2. **Stale removal loop** — build a `Set` of uids in the response; for each uid in `droneMarkers`
   absent from the set: `trackLayer.removeLayer(droneMarkers[uid])`, `delete droneMarkers[uid]`.
3. **Arrow lines** — velocity arrows are stateless (no marker identity needed); they are still
   rebuilt on each cycle (add to `trackLayer`). Only non-arrow markers use the incremental path.
   *(Arrow lines can be made incremental in a future feature; for 012 they remain full-rebuild.)*
4. **Panel** — `#track-list` HTML panel continues to be fully rebuilt on each cycle (FR-012-008).

**Rationale**: The freeze/blink is directly caused by `clearLayers()` emptying the layer before
the rebuild loop runs. Under any poll-interval jitter a browser frame renders an empty `trackLayer`.
Marker mutation APIs (`setLatLng`, `setIcon`, `bindTooltip`) are standard Leaflet 1.9 APIs;
no workarounds needed.

**Alternatives considered**:
- Keep `clearLayers()` but add a CSS transition to hide blink — *rejected*: cosmetic fix for a
  semantic bug; also hides the absence of `uid` in the payload (RC3).
- WebSocket / SSE push for real-time updates — *rejected*: out of scope; adds new infrastructure
  beyond the RC1 root cause (the 2-second poll itself is acceptable).

**Scope boundary**: Only `refreshTracks()` and the drone `trackLayer` are in scope. `refreshSites()`
and `sensorLayer` already use `clearLayers()` inside the success branch (Feature 011 fix) — they
are not touched by Feature 012.

---

### R4 — Timezone Normalisation in `_within_match` (RC4)

**Decision**: Apply an inline two-line guard in `_within_match` using local variables only:
```python
ts_radar = radar.timestamp if radar.timestamp.tzinfo is not None else radar.timestamp.replace(tzinfo=timezone.utc)
ts_rf    = rf.timestamp    if rf.timestamp.tzinfo    is not None else rf.timestamp.replace(tzinfo=timezone.utc)
dt = abs((ts_radar - ts_rf).total_seconds())
```

**Rationale**: `datetime.timezone` is already imported in `correlator.py` (used in
`build_fused()`). The inline guard is the minimum change: no new imports, no mutation of
`UnifiedTrack`, no new helper function, no new file. Naïve datetimes are assumed UTC per the
project convention (all adapters produce UTC-aware datetimes; a naïve datetime is a production
sensor regression that should be handled defensively as UTC).

**Alternatives considered**:
- Normalise in `UnifiedTrack.__post_init__` — *rejected*: changes the data model contract;
  Feature 012 must not alter how tracks are stored.
- Add a shared `_to_utc(ts)` helper in `cot_gateway/utils.py` — *rejected*: introduces a new
  module (complexity cost); the guard is two lines, not worth abstracting.
- Use `pendulum` or `pytz` — *rejected*: G7 forbids new third-party packages.

---

### R5 — Test Strategy

**Decision**: Four test changes, minimal blast radius:

| File | Action | Covers |
|------|--------|--------|
| `tests/unit/test_uid_source_switch.py` | Update in-place: change `assert old is None` → `assert old == []` and `assert old == "X"` → `assert old == ["X"]`; add FR-012-019 (dual-uid case) and FR-012-020 (dedup case) | RC2 unit |
| `tests/unit/test_correlator_tz.py` | New file: 4 parametrised test cases (aware/aware, aware/naïve, naïve/aware, naïve/naïve) for `_within_match` | RC4 unit |
| `tests/unit/test_track_store_uid.py` | New file: verify `_serialize` includes `uid` field; verify `get_all()` passes key correctly | RC1/RC3 unit |
| `tests/integration/test_multi_uid_source_switch.py` | New file: mock `TrackStore` + `TakTransmitter`; drive `_emit_for_track` with 2-old-uid input; assert stale CoTs precede live CoT; assert both old uids removed from store + `seen_uids` | RC2 integration |

**Contract tests** (`tests/contract/`): **unchanged** — G2 guarantee. No fixture files modified.

---

## Resolved Clarifications (from spec session 2026-04-30)

| # | Question | Resolution |
|---|----------|------------|
| 1 | Should `uid` in `/tracks` use the TrackStore key or re-derive from track object? | TrackStore key from `self._data.items()` (see R1) |
| 2 | Should `detect_source_switch` return `(list[str], str)` breaking `(Optional[str], str)`? | Yes — empty list replaces `None`; no backwards-compat shim (see R2) |
| 3 | Should `_within_match` normalisation mutate `UnifiedTrack.timestamp`? | No — local variables only (see R4) |
| 4 | Does uid-keyed JS approach require changes to `refreshSites()` or sensor marker logic? | No — Feature 011 already fixed sensor layer; only `refreshTracks()` in scope (see R3) |
| 5 | Does adding `uid` to `/tracks` break Feature 011 takeover visual or `/map` panel? | No — panel reads named existing fields; additive new field is silently ignored (see R1) |
