# Tasks: CoT Gateway Track Update Fix

**Feature**: `012-track-update-fix`
**Branch**: `feature/012-track-update-fix`
**Input**: Design documents from `specs/012-track-update-fix/`
**Source files**: `services/cot-gateway/src/cot_gateway/` (5 files touched)
**Test files**: `services/cot-gateway/tests/` (1 updated + 3 new)
**Generated**: 2026-04-30

---

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelisable — operates on a different file with no dependency on an incomplete task
- **[US1/US2/US3]**: User story this task belongs to (maps to spec.md user stories)
- Exact file paths are relative to the repository root

---

## Dependency Graph

```
T001 (baseline)
  └─► T002 [P] ──► T003 ──► T004          (US1: RC3 → RC1)
      T005 [P] ──► T007 ──► T008          (US2: RC2-sig → RC2-loop)
      T006 [P] ──┘
      T009 [P] ──► T010                   (US3: RC4)

T004, T008, T010 ──► T011 ──► T012 [P]
                               T013 [P]
                               T014
```

**Cross-story parallelism**: T002, T005, T006, and T009 (all test files, all different) can be
written simultaneously. T003, T007, and T010 (implementations) can begin in parallel once their
respective test tasks are done.

---

## Phase 1: Setup

**Purpose**: Verify the pre-012 baseline is clean before any changes are made.

- [ ] T001 Verify pre-012 baseline by running `cd services/cot-gateway && pytest -v` and confirming all existing tests pass with zero failures (contract tests in `tests/contract/` must be green)

---

## Phase 3: User Story 1 — EchoShield Drone Moves Continuously Before Sentrycs Engages (Priority: P1) 🎯 MVP

**Goal**: Fix RC3 (missing `uid` field in `/tracks` payload) and RC1 (destructive `clearLayers()` in JS) so the drone marker advances smoothly in the browser with no freeze, snap, or blink during the EchoShield-only phase of the demo.

**Independent Test**: With only EchoShield Simulator running, observe the drone icon on `http://localhost:18092/map` for 30 seconds. The icon must advance continuously with no freeze or blink. Each `/tracks` JSON entry must include a `uid` field. `grep -n "clearLayers" services/cot-gateway/src/cot_gateway/web/server.py` must show no match inside `refreshTracks()`.

### Tests for User Story 1

> **Write this test FIRST, confirm it FAILS before implementing RC3.**

- [ ] T002 [P] [US1] Create `services/cot-gateway/tests/unit/test_track_store_uid.py` (new file): write unit tests covering FR-012-001 (`_serialize` includes `"uid"` key), FR-012-002 (`get_all()` passes dict key as uid argument), and FR-012-003 (every entry in the `get_all()` return value has a `"uid"` string field matching the expected prefix convention)

### Implementation for User Story 1

- [ ] T003 [US1] Fix `TrackStore._serialize` and `get_all()` in `services/cot-gateway/src/cot_gateway/web/track_store.py`: add `uid: str` as second positional parameter to `_serialize`, insert `"uid": uid` as the first key in the returned dict, and update the `get_all()` call-site to `_serialize(t, uid, uid in self._takeover_set)` (RC3 — FR-012-001/002/003); run `pytest tests/unit/test_track_store_uid.py` and `pytest tests/contract/` to confirm both pass
- [ ] T004 [US1] Replace `refreshTracks()` body in the `_HTML_TEMPLATE` JS section of `services/cot-gateway/src/cot_gateway/web/server.py` (RC1 — FR-012-004/005/006/007/008): (a) add `const droneMarkers = {};` at module level after the `trackLayer` declaration; (b) remove `trackLayer.clearLayers();` from `refreshTracks()`; (c) add upsert loop — for each track `t` in the `/tracks` response, if `droneMarkers[t.uid]` exists call `setLatLng`, `setIcon`, `bindTooltip` in-place, else create a new `L.marker`, add to `trackLayer`, and store in `droneMarkers[t.uid]`; (d) add stale-removal loop — build `currentUids = new Set(tracks.map(t => t.uid))`, then for each uid in `Object.keys(droneMarkers)` not in `currentUids` call `trackLayer.removeLayer(droneMarkers[uid])` and `delete droneMarkers[uid]`; (e) move arrow-line drawing into a separate pass over `tracks` (no `clearLayers`, arrows re-added each cycle); run `pytest tests/unit/test_server_js.py tests/unit/test_server.py` to confirm no regressions

**Checkpoint**: `pytest tests/unit/test_track_store_uid.py` passes; `/tracks` response includes `"uid"` on every entry; `refreshTracks()` contains no `clearLayers()` call; drone marker updates in-place on the live map.

---

## Phase 4: User Story 2 — FUSED Track Appears and All Single-Source Ghost Icons Disappear (Priority: P1)

**Goal**: Fix RC2 so `detect_source_switch` returns *all* distinct old uids (not just the first) and `_emit_for_track` clears every stale orphan uid from TrackStore, eliminating ghost grey icons on ATAK when FUSED supersedes both an ECHO and a SENTRYCS uid simultaneously.

**Independent Test**: Run the dual-sensor scenario with a mock TAK Server. At the source-switch event, confirm a `stale=time` CoT is emitted for **each** previously active single-source uid (potentially two), all before the first live FUSED CoT. Confirm the `/tracks` response contains no entries for superseded single-source uids after the switch.

### Tests for User Story 2

> **Write these tests FIRST, confirm they FAIL before implementing RC2.**

- [ ] T005 [P] [US2] Update `services/cot-gateway/tests/unit/test_uid_source_switch.py` (existing file — FR-012-018/019/020): change all `assert old is None` assertions to `assert old == []`; change all `assert old == "X"` assertions to `assert old == ["X"]`; add test case for FR-012-019 (dual-uid: both `radar:TRK-001 → ECHO-TRK-001` and `rf:DRN-001 → SENTRYCS-DRN-001` are in `prev_uid_by_entity_key` and the response list contains both); add test case for FR-012-020 (dedup: two entity keys map to the same old uid → list contains it exactly once)
- [ ] T006 [P] [US2] Create `services/cot-gateway/tests/integration/test_multi_uid_source_switch.py` (new file — FR-012-021): write integration test that mocks `TrackStore` and `TakTransmitter`, drives `_emit_for_track` with a FUSED track whose `detect_source_switch` returns two old uids (`ECHO-TRK-001`, `SENTRYCS-DRN-001`), then asserts: (a) two stale CoTs appear in the transmitter queue before the live FUSED CoT; (b) both old uids have been removed from `TrackStore`; (c) both old uids are absent from `seen_uids`

### Implementation for User Story 2

- [ ] T007 [US2] Change `detect_source_switch` return type to `tuple[list[str], str]` in `services/cot-gateway/src/cot_gateway/cot/uid.py` (RC2 — FR-012-009/010/011/014): replace the `break`-on-first-find loop with a deduplication loop using a `seen: set[str]`, collect all distinct old uids into `old_uids: list[str]`, return `(old_uids, new_uid)` replacing `(None, new_uid)` with `([], new_uid)`; remove the `Optional` import if unused; run `pytest tests/unit/test_uid_source_switch.py` to confirm all updated and new unit assertions pass
- [ ] T008 [US2] Update `GatewayMain._emit_for_track` in `services/cot-gateway/src/cot_gateway/loop.py` (RC2 — FR-012-012/013/014): change unpack from `old_uid, new_uid = detect_source_switch(...)` to `old_uids, new_uid = detect_source_switch(...)`; replace the `if old_uid is not None and old_uid != new_uid:` conditional block with `for old_uid in old_uids:` loop body that enqueues `generate_cot(..., force_stale_eq_time=True, override_uid=old_uid)`, calls `await self._track_store.remove(old_uid)`, discards `old_uid` from `self.seen_uids`, and logs one `source_switch` structured event per old uid; run `pytest tests/integration/test_multi_uid_source_switch.py tests/integration/` to confirm new integration test passes and no regressions

**Checkpoint**: `detect_source_switch` returns `(list[str], str)` for all cases; `_emit_for_track` iterates the full old-uid list; dual-uid integration test passes; no orphan uids remain in `TrackStore` after a multi-source switch.

---

## Phase 5: User Story 3 — Correlation Succeeds Regardless of Sensor Timestamp Timezone Format (Priority: P2)

**Goal**: Fix RC4 so `TrackCorrelator._within_match` normalises both timestamps to UTC-aware before subtraction, eliminating the silent `TypeError` that suppresses fusion matches when one sensor produces naïve datetimes.

**Independent Test**: Unit-inject all four naïve/aware timestamp combinations (`aware/aware`, `aware/naïve`, `naïve/aware`, `naïve/naïve`) into `_within_match`. Confirm no exception is raised and the correct within-window boolean is returned in each case.

### Tests for User Story 3

> **Write this test FIRST, confirm it FAILS before implementing RC4.**

- [ ] T009 [P] [US3] Create `services/cot-gateway/tests/unit/test_correlator_tz.py` (new file — FR-012-022): write a parametrised test covering all four timezone combinations — `(aware_utc, aware_utc)`, `(aware_utc, naive)`, `(naive, aware_utc)`, `(naive, naive)` — injected directly into `TrackCorrelator._within_match` via a mock `UnifiedTrack`; assert no `TypeError` is raised and the correct `True`/`False` result is returned based on whether the delta is within `time_window_s`; include a regression assertion that the `aware/aware` case gives the same result as the pre-fix code path

### Implementation for User Story 3

- [ ] T010 [US3] Add timezone normalisation to `TrackCorrelator._within_match` in `services/cot-gateway/src/cot_gateway/correlate/correlator.py` (RC4 — FR-012-015/016/017): after the distance guard `return False`, add two local-variable lines `ts_radar = radar.timestamp if radar.timestamp.tzinfo is not None else radar.timestamp.replace(tzinfo=timezone.utc)` and `ts_rf = rf.timestamp if rf.timestamp.tzinfo is not None else rf.timestamp.replace(tzinfo=timezone.utc)`; replace `abs((radar.timestamp - rf.timestamp).total_seconds())` with `abs((ts_radar - ts_rf).total_seconds())`; do not mutate `UnifiedTrack.timestamp`; do not add new imports (`timezone` is already imported); run `pytest tests/unit/test_correlator_tz.py tests/unit/test_correlator_match.py` to confirm new tests pass and existing correlator tests are not regressed

**Checkpoint**: `_within_match` handles all four tz combinations without raising `TypeError`; all four parametrised assertions in `test_correlator_tz.py` pass; `test_correlator_match.py` is unaffected.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Full regression validation, lint/format compliance, and G2 contract freeze confirmation across all Feature 012 changes.

- [ ] T011 Run `cd services/cot-gateway && pytest -v` to execute the complete test suite; confirm zero regressions against the pre-012 baseline, all new Feature 012 tests pass (T002, T005, T006, T009 test files), and the total failure count is 0
- [ ] T012 [P] Run `cd services/cot-gateway && ruff check src/ tests/` and fix any lint violations in the five modified source files (`track_store.py`, `server.py`, `uid.py`, `loop.py`, `correlator.py`) and three new/updated test files (`test_track_store_uid.py`, `test_uid_source_switch.py`, `test_correlator_tz.py`, `test_multi_uid_source_switch.py`)
- [ ] T013 [P] Run `cd services/cot-gateway && black --check src/ tests/` and apply `black` formatting to any modified file that fails the check; re-run `--check` to confirm zero violations
- [ ] T014 Verify G2 constraint by running `pytest tests/contract/ -v` and confirming all four contract tests pass without any modification to `tests/contract/test_cot_xml_schema.py`, `tests/contract/test_echodyne_wire.py`, `tests/contract/test_sentrycs_poller.py`, or `tests/contract/test_tak_uplink.py` (FR-012-023)

---

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 14 |
| Phase 1 (Setup) | 1 |
| User Story 1 (US1 — RC3+RC1) | 3 (T002–T004) |
| User Story 2 (US2 — RC2) | 4 (T005–T008) |
| User Story 3 (US3 — RC4) | 2 (T009–T010) |
| Polish (Phase 6) | 4 (T011–T014) |
| Parallelisable tasks [P] | 7 (T002, T005, T006, T009, T012, T013, T014) |
| New test files | 3 (`test_track_store_uid.py`, `test_correlator_tz.py`, `test_multi_uid_source_switch.py`) |
| Updated test files | 1 (`test_uid_source_switch.py`) |
| Source files modified | 5 (`track_store.py`, `server.py`, `uid.py`, `loop.py`, `correlator.py`) |

### MVP Scope

**Implement User Story 1 first** (T002 → T003 → T004): RC3 + RC1 together fix the most visible
demo defect (marker freeze/blink) and are the direct dependency chain. US2 (T005–T008) and US3
(T009–T010) can be started in parallel once the baseline is verified (T001).

### Parallel Execution Plan

All test-writing tasks are fully independent and can be parallelised:

```
Worker A: T002 → T003 → T004        (US1 full chain)
Worker B: T005 → T007 → T008        (US2 uid.py then loop.py)
          T006 ──┘ (can be done by Worker B alongside T005)
Worker C: T009 → T010               (US3 independent chain)
All: T011 → T012 [P] + T013 [P] + T014 [P]
```

### Constraints Reminder

| Constraint | Rule |
|-----------|------|
| **G2** | Do NOT modify `tests/contract/` fixture files or any external wire schema (EchoShield TCP JSON, Sentrycs `/detections`, TAK CoT XML, UDS `/command/takeover`) |
| **G7** | Do NOT add new packages to `pyproject.toml`; `datetime.timezone` (stdlib, already imported in `correlator.py`) is the only addition |
| **No mutation** | `UnifiedTrack.timestamp` MUST NOT be reassigned; use `ts_radar`/`ts_rf` local vars only |
| **Private API only** | Only `_serialize` (private helper) signature changes; `upsert`, `remove`, `mark_takeover`, `get_all` public API is unchanged |
