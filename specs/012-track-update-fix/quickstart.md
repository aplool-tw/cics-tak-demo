# Quickstart: Feature 012 — CoT Gateway Track Update Fix

**Date**: 2026-04-30
**Service**: `services/cot-gateway`
**Branch**: `feature/012-track-update-fix`

---

## What This Feature Does

Fixes four root causes that degrade the demo experience:

| RC | Symptom | Fix |
|----|---------|-----|
| RC1 | Drone marker freezes / blinks every 2 s on the tactical map | Replace destructive `clearLayers()` with uid-keyed incremental `droneMarkers` in JS |
| RC2 | Ghost grey ATAK icon lingers when both ECHO + SENTRYCS → FUSED | `detect_source_switch` now returns **all** distinct old uids; `_emit_for_track` clears each one |
| RC3 | JS cannot find `uid` in `/tracks` JSON to key the incremental update | `TrackStore._serialize` now embeds the TrackStore dict key as `"uid"` |
| RC4 | Fusion silently fails when one sensor timestamp is timezone-naïve | `_within_match` normalises both timestamps to UTC before subtraction |

---

## Prerequisites

```bash
# Python 3.11+
python --version       # Python 3.11.x or newer
cd services/cot-gateway
pip install -e ".[dev]"
```

---

## Running the Existing Test Suite (Baseline)

Before making changes, verify the pre-012 baseline passes:

```bash
cd services/cot-gateway
pytest
```

Expected: all tests pass, 0 failures. The contract tests (`tests/contract/`) must pass
**without modification** throughout the entire feature implementation (G2 constraint).

---

## Files to Change

```
services/cot-gateway/
├── src/cot_gateway/cot/uid.py            ← RC2: detect_source_switch
├── src/cot_gateway/correlate/correlator.py  ← RC4: _within_match tz normalisation
├── src/cot_gateway/loop.py               ← RC2: _emit_for_track loop
├── src/cot_gateway/web/track_store.py    ← RC1/RC3: _serialize + get_all
└── src/cot_gateway/web/server.py         ← RC1: JS refreshTracks() incremental strategy
```

---

## Step-by-Step Implementation Order

Implement in this order to keep the test suite green at each step:

### Step 1 — RC3: Add `uid` to `TrackStore._serialize` (lowest risk)

**File**: `src/cot_gateway/web/track_store.py`

Change `_serialize` to accept `uid: str` as second positional argument and include it as the
first key in the returned dict. Update the only call site in `get_all()`.

```python
# Before
def _serialize(track: UnifiedTrack, takeover_issued: bool = False) -> dict[str, Any]:
    return {
        "source": track.source.value,
        ...
    }

# get_all()
return [_serialize(t, uid in self._takeover_set) for uid, t in self._data.items()]

# After
def _serialize(track: UnifiedTrack, uid: str, takeover_issued: bool = False) -> dict[str, Any]:
    return {
        "uid": uid,
        "source": track.source.value,
        ...
    }

# get_all()
return [_serialize(t, uid, uid in self._takeover_set) for uid, t in self._data.items()]
```

**Verify**: `pytest tests/unit/test_track_store_uid.py` (new test, write first).
Run `pytest tests/contract/` — must still pass.

---

### Step 2 — RC4: Timezone normalisation in `_within_match` (zero-scope change)

**File**: `src/cot_gateway/correlate/correlator.py`

Add two local `ts_radar` / `ts_rf` lines inside `_within_match`. `timezone` is already imported.

```python
def _within_match(self, radar: UnifiedTrack, rf: UnifiedTrack) -> bool:
    if haversine_m(radar.lat, radar.lon, rf.lat, rf.lon) > self.distance_threshold_m:
        return False
    ts_radar = (
        radar.timestamp if radar.timestamp.tzinfo is not None
        else radar.timestamp.replace(tzinfo=timezone.utc)
    )
    ts_rf = (
        rf.timestamp if rf.timestamp.tzinfo is not None
        else rf.timestamp.replace(tzinfo=timezone.utc)
    )
    dt = abs((ts_radar - ts_rf).total_seconds())
    return dt <= self.time_window_s
```

**Verify**: `pytest tests/unit/test_correlator_tz.py` (new test, write first).
`pytest tests/unit/test_correlator_match.py` — must not regress.

---

### Step 3 — RC2: `detect_source_switch` return type change

**File**: `src/cot_gateway/cot/uid.py`

Change return type to `tuple[list[str], str]`. Collect all distinct old uids.

```python
def detect_source_switch(
    track: UnifiedTrack, prev_uid_by_entity_key: dict[str, str]
) -> tuple[list[str], str]:
    """Return (old_uids, new_uid) — all distinct prior uids that differ from new_uid."""
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

Remove the `Optional` import if no longer needed.

**Verify**: Update `test_uid_source_switch.py` first (change assert patterns), then run:
```bash
pytest tests/unit/test_uid_source_switch.py
```

---

### Step 4 — RC2: Update `_emit_for_track` to iterate old_uids list

**File**: `src/cot_gateway/loop.py`

Change the `old_uid, new_uid = detect_source_switch(...)` unpack and the conditional block:

```python
# Before
old_uid, new_uid = detect_source_switch(track, self.prev_uid_by_entity_key)
if old_uid is not None and old_uid != new_uid:
    final_xml = generate_cot(track, now=now, force_stale_eq_time=True, override_uid=old_uid)
    self.transmitter.enqueue(final_xml)
    self.seen_uids.discard(old_uid)
    if self._track_store is not None:
        await self._track_store.remove(old_uid)
    self._log.info("source_switch", old_uid=old_uid, new_uid=new_uid, ...)

# After
old_uids, new_uid = detect_source_switch(track, self.prev_uid_by_entity_key)
for old_uid in old_uids:
    final_xml = generate_cot(track, now=now, force_stale_eq_time=True, override_uid=old_uid)
    self.transmitter.enqueue(final_xml)
    self.seen_uids.discard(old_uid)
    if self._track_store is not None:
        await self._track_store.remove(old_uid)
    self._log.info(
        "source_switch",
        old_uid=old_uid,
        new_uid=new_uid,
        track_id=track.track_id,
        entity_keys=entity_keys_for(track),
    )
```

**Verify**:
```bash
pytest tests/integration/test_multi_uid_source_switch.py   # new test
pytest tests/integration/                                   # no regressions
```

---

### Step 5 — RC1: JS incremental `droneMarkers` update

**File**: `src/cot_gateway/web/server.py` (JS section inside `_HTML_TEMPLATE`)

1. Add `const droneMarkers = {};` after the layer group declarations (after `const trackLayer = ...`).
2. Replace `refreshTracks()` body with the incremental upsert + stale-removal logic.

Key changes:
- Remove `trackLayer.clearLayers();` at the top of `refreshTracks()`
- Add `droneMarkers` upsert loop using `t.uid`
- Add stale-removal loop using `Object.keys(droneMarkers)` vs `currentUids` Set
- Velocity arrow lines: keep on a separate pass (see data-model §4 note)
- `#track-list` panel: full HTML rebuild is acceptable (FR-012-008)

**Verify**:
```bash
pytest tests/unit/test_server_js.py   # existing JS tests
pytest tests/unit/test_server.py      # existing server tests
```

Manual smoke test: open `http://localhost:18092/map` — drone marker must move without blinking.

---

## Running All Tests

```bash
cd services/cot-gateway
pytest -v
```

Expected results:
- All pre-012 tests pass (zero regressions)
- All new Feature 012 tests pass
- `tests/contract/` passes without any fixture file changes (G2)

---

## Linting and Formatting

```bash
cd services/cot-gateway
ruff check src/ tests/
black --check src/ tests/
```

All modified files must report zero violations.

---

## Manual Smoke Test

### RC3 — Verify `uid` in `/tracks` response

```bash
# With gateway running:
curl -s http://localhost:18092/tracks | python3 -m json.tool | grep '"uid"'
# Expected: one "uid" line per active track, e.g. "uid": "ECHO-TRK-001"
```

### RC4 — Verify `_within_match` handles naïve timestamps

Run the new unit test directly:
```bash
pytest tests/unit/test_correlator_tz.py -v
```

### RC2 — Verify dual-uid stale CoT emission

Run the new integration test:
```bash
pytest tests/integration/test_multi_uid_source_switch.py -v
```

### RC1 — Verify no `clearLayers()` in `refreshTracks()`

```bash
grep -n "clearLayers" services/cot-gateway/src/cot_gateway/web/server.py
# Expected: only the refreshSites() lines (lines ~219-220); none inside refreshTracks()
```

---

## Full Scenario Walkthrough

1. Start the gateway with EchoShield simulator only:
   ```bash
   cot-gateway --config config/demo.yaml
   ```
2. Open `http://localhost:18092/map` in a browser.
3. Observe the drone icon advancing smoothly — **no blink** between 2-second refreshes (RC1).
4. Start the Sentrycs simulator. Wait for the fusion event.
5. Observe the ATAK TAK client — exactly one red FUSED icon appears; both prior grey icons
   disappear simultaneously (RC2).
6. Check `/tracks` response — `uid` field present in every entry (RC3).
7. Review gateway logs — `source_switch` events appear for each superseded uid (RC2).

---

## Key Constraints Reminder

| Constraint | Rule |
|-----------|------|
| **G2** | Do not modify any of: EchoShield TCP JSON, Sentrycs `/detections`, TAK CoT XML, UDS `/command/takeover` body, or any `tests/contract/` fixture file |
| **G7** | Do not add new third-party packages to `pyproject.toml`; use only stdlib `datetime.timezone` (already imported) |
| **No mutation** | `UnifiedTrack.timestamp` must not be reassigned; use local normalisation variables in `_within_match` only |
| **TrackStore public API** | `upsert`, `remove`, `mark_takeover`, `get_all` signatures are unchanged; only the private `_serialize` helper changes |
