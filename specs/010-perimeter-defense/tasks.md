# Tasks: Feature 010 — Perimeter Defense

**Feature ID**: `010`
**Branch**: `010-perimeter-defense`
**Input**: `specs/010-perimeter-defense/` (spec.md, plan.md, research.md, quickstart.md)
**Services touched**: `cot-gateway`, `sentrycs-sim`, `uds`
**Files changed**: 7 across 2 services + 1 UDS YAML
**Tests**: TDD for US4 (perimeter takeover) and US3 (enum verification); visual-only for US1; YAML-only for US2

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[US#]**: Which user story this task belongs to
- TDD tasks: write **failing** tests first, then make them pass

---

## Phase 1: User Story 1 — Defense Ring Visibility (Priority: P1) 🎯 MVP

**Goal**: Operator can read map legend and immediately identify the three defense rings by their distinct pastel dashed lines, with correct tooltips on hover.

**Independent Test**: Load `/map` page → legend panel shows three dashed-line entries labeled "1 km defense ring", "2 km defense ring", "3 km defense ring" in colors distinct from `#00BFFF` (EchoShield) and `#FFD700` (Sentrycs). Hover each SP ring circle → tooltip reads the matching distance label.

> **Note**: Item 1 is an HTML/JS change embedded in `server.py`. No new Python unit tests are required (change is visual). Verification is done by running the existing cot-gateway integration test suite to confirm zero regressions.

### Implementation for User Story 1

- [X] T001 [US1] Update `RING_COLORS` constant from `['#00e676','#ffca28','#ef5350']` to `['#80deea','#ffcc80','#ef9a9a']` in `services/cot-gateway/src/cot_gateway/web/server.py`
- [X] T002 [US1] Add `const RING_LABELS = ['1km defense ring','2km defense ring','3km defense ring']` constant and chain `.bindTooltip(RING_LABELS[i]||'defense ring',{className:'leaflet-tooltip-gw'})` before `.addTo(siteLayer)` in the ring `forEach` loop in `services/cot-gateway/src/cot_gateway/web/server.py`
- [X] T003 [US1] Insert three dashed legend entries into the HTML legend panel (after the existing "RF range" `leg-row`, before `leg-sep`), reusing `.leg-row` / `.leg-line` CSS classes, with inline `border-color` `#80deea` / `#ffcc80` / `#ef9a9a`, labeled "1km defense ring" / "2km defense ring" / "3km defense ring" in `services/cot-gateway/src/cot_gateway/web/server.py`
- [X] T004 [US1] Run existing cot-gateway test suite to confirm zero regressions after HTML/JS edits: `cd services/cot-gateway && pytest -q`

**Checkpoint**: US1 complete — legend is readable, ring colors are distinct, tooltips work.

---

## Phase 2: User Story 4 — Automatic Perimeter-Based Drone Takeover (Priority: P1) [TDD]

**Goal**: When `defense_radius_m` is configured, the sentrycs-sim loop automatically issues a takeover command the moment a DETECTED drone's great-circle distance to the sensor falls strictly below that threshold — exactly once per drone lifecycle. When `defense_radius_m` is absent, pre-010 time-based behavior is preserved exactly.

**Independent Test**: Configure `defense_radius_m: 1000.0` in `sentrycs-sim/config/demo.yaml`, run demo scenario → UDS takeover API fires when and only when drone first crosses 1 km. With `defense_radius_m` absent → time-based takeover at `mitigating_at_s` fires unchanged.

> **TDD Order**: Write ALL failing tests (T005–T010) first, confirm they fail, then implement (T011–T013), then confirm tests pass (T014).

### Tests for User Story 4 — Write FIRST (must FAIL before implementation) ⚠️

- [X] T005 [US4] Create `services/sentrycs-sim/tests/unit/test_loop.py`; write test `test_time_based_takeover_when_no_defense_radius`: with `defense_radius_m=None` and `elapsed >= mitigating_at_s`, confirm `_ensure_takeover_task` is called (pre-010 time-based path unchanged)
- [X] T006 [US4] Add test `test_position_based_takeover_triggers_inside_perimeter` to `services/sentrycs-sim/tests/unit/test_loop.py`: with `defense_radius_m=1000.0` and drone haversine distance to sensor = 900 m, confirm `_ensure_takeover_task` is called on that tick
- [X] T007 [US4] Add test `test_position_based_no_takeover_outside_perimeter` to `services/sentrycs-sim/tests/unit/test_loop.py`: with `defense_radius_m=1000.0` and drone distance = 1100 m, confirm `_ensure_takeover_task` is NOT called
- [X] T008 [US4] Add test `test_no_takeover_for_neutralized_drone` to `services/sentrycs-sim/tests/unit/test_loop.py`: with `defense_radius_m=1000.0` and drone status `NEUTRALIZED` at 900 m, confirm `_ensure_takeover_task` is NOT called
- [X] T009 [US4] Add test `test_no_duplicate_takeover_after_sent` to `services/sentrycs-sim/tests/unit/test_loop.py`: with `defense_radius_m=1000.0`, `takeover_sent=True`, and drone at 900 m, confirm `_ensure_takeover_task` is NOT called a second time
- [X] T010 [P] [US4] Add test `test_defense_radius_field_in_config` to `services/sentrycs-sim/tests/unit/test_config.py`: confirm `SentrycsConfig` parses `defense_radius_m: 1000.0` without error and that `defense_radius_m=None` (omitted) is also valid and yields `None`

### Implementation for User Story 4 (make tests pass)

- [X] T011 [P] [US4] Add `defense_radius_m: Optional[float] = Field(default=None)` field to `SentrycsConfig` (after `detection_radius_m`; no `gt=0.0` constraint per FR-010-010; add `Optional` import if missing) in `services/sentrycs-sim/src/sentrycs_sim/config.py`
- [X] T012 [P] [US4] Add `from .geo.wgs84 import haversine_m` import and replace the step-4 takeover block in `run_one_tick()` with the position-based / time-based branch: when `self.config.defense_radius_m is not None` compute `haversine_m(sensor_lat, sensor_lon, track.lat, track.lon)` and trigger if `dist < defense_radius_m`; otherwise fall back to `elapsed >= mitigating_at_s` in `services/sentrycs-sim/src/sentrycs_sim/loop.py`
- [X] T013 [US4] Add `detection_radius_m: 8000.0` (explicit, was implicit default) and `defense_radius_m: 1000.0` (with explanatory inline comment) after `poll_interval_s` in `services/sentrycs-sim/config/demo.yaml`
- [X] T014 [US4] Run all 6 perimeter-defense unit tests and confirm they pass: `cd services/sentrycs-sim && pytest tests/unit/test_loop.py tests/unit/test_config.py -v`

**Checkpoint**: US4 complete — perimeter takeover fires correctly, time-based fallback preserved, idempotency verified.

---

## Phase 3: User Story 2 — Perceptible Drone Movement (Priority: P2)

**Goal**: Drone marker moves ≥ 80 m per 3-second map refresh at zoom 13, making drone approach visibly dramatic during demo. Comment header in `demo.yaml` documents physics-correct timing at 35 m/s.

**Independent Test**: Start demo scenario, open map at zoom 13 → drone marker moves a clearly visible distance between consecutive refreshes (35 m/s × 3 s = 105 m).

> **Note**: YAML-only changes — no Python code modified, no new tests needed.

### Implementation for User Story 2

- [X] T015 [P] [US2] Change `speed_ms: 20.0` to `speed_ms: 35.0` and update the `description` field to document the new speed ("35m/s 快速啟動") in `services/uds/scenarios/demo_single_drone.yaml`
- [X] T016 [P] [US2] Replace the comment block at the top of `services/sentrycs-sim/config/demo.yaml` with the 35 m/s physics-correct timing narrative (t≈9s EchoShield entry; t≈43s 2km ring; t≈71s 1km perimeter crossing; t=75s DETECTED; t=75s+ immediate takeover; t≈165s NEUTRALIZED) — run after T013 since both touch this file

**Checkpoint**: US2 complete — drone moves visibly, comment header is accurate for 35 m/s.

---

## Phase 4: User Story 3 — FUSED Track Source Verification (Priority: P2) [TDD]

**Goal**: Confirm `TrackSource` enum string values exactly match the JS `SRC_COLOR` map keys (`ECHOSHIELD`, `SENTRYCS`, `FUSED`); add a wire-contract comment; enhance `source_switch` log event with `entity_key` field.

**Independent Test**: `TrackSource.ECHOSHIELD.value == "ECHOSHIELD"`, `.SENTRYCS == "SENTRYCS"`, `.FUSED == "FUSED"` — confirmed by new unit test. CoT Gateway structured log emits `source_switch` with `old_uid`, `new_uid`, `track_id`, and `entity_key`.

> **TDD Order**: Write failing test (T017) first, then implement (T018–T019), then confirm pass (T020).

### Test for User Story 3 — Write FIRST (must FAIL before implementation) ⚠️

- [X] T017 [US3] Create `services/cot-gateway/tests/unit/test_track_source.py`; write test `test_track_source_enum_values_match_js_src_color_keys`: assert `TrackSource.ECHOSHIELD.value == "ECHOSHIELD"`, `TrackSource.SENTRYCS.value == "SENTRYCS"`, `TrackSource.FUSED.value == "FUSED"` (will pass immediately since values already match — this test documents the wire contract and guards against future renames)

### Implementation for User Story 3

- [X] T018 [P] [US3] Add the wire-contract comment block `# String values are the canonical source identifiers used by the JS SRC_COLOR map in web/server.py. Do NOT rename without updating both sides.` immediately above the `TrackSource` class in `services/cot-gateway/src/cot_gateway/models/track.py`
- [X] T019 [P] [US3] In `_emit_for_track()`, update the `source_switch` `self._log.info(...)` call to include `entity_key=_ekeys[0] if _ekeys else None` (using the already-imported `entity_keys_for`) in `services/cot-gateway/src/cot_gateway/loop.py`
- [X] T020 [US3] Run unit tests to confirm T017 passes and no source-switch regressions: `cd services/cot-gateway && pytest tests/unit/test_track_source.py tests/unit/test_uid_source_switch.py -v`

**Checkpoint**: US3 complete — enum contract documented and guarded, log event carries full context.

---

## Phase 5: Polish & Integration Verification

**Purpose**: Lint all modified services, run full regression suites, and smoke-test the complete end-to-end scenario.

- [X] T021 [P] Run `ruff check . && black --check .` in `services/cot-gateway` — confirm zero lint errors
- [X] T022 [P] Run `ruff check . && black --check .` in `services/sentrycs-sim` — confirm zero lint errors
- [X] T023 [P] Run full cot-gateway pytest suite: `cd services/cot-gateway && pytest -q` — confirm 0 regressions across all 94 tests
- [X] T024 [P] Run full sentrycs-sim pytest suite: `cd services/sentrycs-sim && pytest -q` — confirm 0 regressions across all 110 tests (including new loop + config tests)
- [X] T025 [P] Run full uds pytest suite: `cd services/uds && pytest -q` — confirm 0 regressions across all 83 tests
- [X] T026 Run end-to-end smoke test per `specs/010-perimeter-defense/quickstart.md`: start UDS + sentrycs-sim + echoshield-sim + cot-gateway, open `http://localhost:18080/map`, verify legend entries, drone movement, fused-track transition, and perimeter-triggered takeover log event

**Checkpoint**: All 468 tests pass, lint clean, smoke test confirms all 4 user stories end-to-end.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (US1)**: Independent — start immediately, touches only `cot-gateway/server.py`
- **Phase 2 (US4)**: Independent from US1 — touches only `sentrycs-sim` files; can proceed in parallel with Phase 1 if staffed
- **Phase 3 (US2)**: T015 is fully independent; T016 depends on T013 (Phase 2) completing first — both edit `sentrycs-sim/config/demo.yaml`
- **Phase 4 (US3)**: Independent from all previous phases — touches only `cot-gateway/models/track.py` and `cot-gateway/loop.py`
- **Phase 5 (Polish)**: Depends on all prior phases complete

### Cross-Phase File Conflict

| File | Modified by | Order required |
|---|---|---|
| `services/sentrycs-sim/config/demo.yaml` | T013 (US4, Phase 2) and T016 (US2, Phase 3) | T013 **must** complete before T016 |

### Within-Phase TDD Sequence (Phase 2)

```
T005–T009  →  (confirm FAIL)  →  T011 + T012  →  T013  →  T014  →  (confirm PASS)
T010       →  (confirm FAIL)  →  T011          →         T014
```

### Within-Phase TDD Sequence (Phase 4)

```
T017  →  (confirm FAIL or note it trivially passes as guard test)  →  T018 + T019  →  T020
```

### Parallel Opportunities

- **Phase 1 vs Phase 2**: Different services — run concurrently if two developers available
- **Phase 2 tests (T005–T009 vs T010)**: T010 (`test_config.py`) is a different file from T005–T009 (`test_loop.py`) — write in parallel
- **Phase 2 implementation (T011 vs T012)**: Different files (`config.py` vs `loop.py`) — implement in parallel
- **Phase 3 (T015 vs T016)**: Different files (`uds/scenarios/demo_single_drone.yaml` vs `sentrycs-sim/config/demo.yaml`) — edit in parallel (after T013)
- **Phase 4 implementation (T018 vs T019)**: Different files (`models/track.py` vs `loop.py`) — implement in parallel
- **Phase 5 (T021–T025)**: All independent — run all lint + test suites in parallel

---

## Parallel Execution Example: Phase 2 (US4)

```bash
# Step 1: Write failing tests in parallel (different files)
Task A: Add tests test_time_based_takeover, test_position_based_* × 4 in
         services/sentrycs-sim/tests/unit/test_loop.py          (T005-T009)

Task B: Add test_defense_radius_field_in_config in
         services/sentrycs-sim/tests/unit/test_config.py        (T010)

# Step 2: Confirm tests FAIL
cd services/sentrycs-sim && pytest tests/unit/test_loop.py tests/unit/test_config.py -v
# Expected: ImportError or AttributeError on defense_radius_m / haversine branch

# Step 3: Implement in parallel (different files)
Task A: Add defense_radius_m field in config.py                 (T011)
Task B: Add haversine_m import + rewrite step-4 block in loop.py (T012)

# Step 4: Apply YAML config
T013: Add detection_radius_m + defense_radius_m to demo.yaml

# Step 5: Confirm tests PASS
cd services/sentrycs-sim && pytest tests/unit/test_loop.py tests/unit/test_config.py -v
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 4, both P1)

1. Complete Phase 1: US1 legend + colors (quick, visual, zero risk)
2. Complete Phase 2: US4 perimeter takeover (TDD, main headline feature)
3. **STOP and VALIDATE**: Run `pytest -q` in sentrycs-sim + open map to confirm legend
4. Demo-ready at this point for core capabilities

### Incremental Delivery

1. **Phase 1** → Map legend readable, ring colors distinct → visual demo-ready
2. **Phase 2** → Perimeter takeover fires on proximity → headline capability live
3. **Phase 3** → Drone moves visibly on map → demo flow compelling
4. **Phase 4** → Track source verified, log events enriched → engineering confidence
5. **Phase 5** → All 468 tests green, lint clean, smoke test passes → ship

### Single-Developer Sequence

```
T001 → T002 → T003 → T004
T005 → T006 → T007 → T008 → T009 → T010 (+ T010 in parallel)
T011 + T012 (parallel, different files)
T013 → T014
T015 + T016 (parallel, different files; T016 after T013)
T017 → T018 + T019 (parallel) → T020
T021 + T022 + T023 + T024 + T025 (all parallel) → T026
```

---

## Summary

| Phase | Stories | Tasks | New test files | Files modified |
|---|---|---|---|---|
| Phase 1 | US1 (P1) | T001–T004 | none | `server.py` |
| Phase 2 | US4 (P1) | T005–T014 | `test_loop.py` (new) | `config.py`, `loop.py`, `demo.yaml` |
| Phase 3 | US2 (P2) | T015–T016 | none | `demo_single_drone.yaml`, `demo.yaml` |
| Phase 4 | US3 (P2) | T017–T020 | `test_track_source.py` (new) | `track.py`, `loop.py` |
| Phase 5 | Polish | T021–T026 | — | — |
| **Total** | **4 stories** | **26 tasks** | **2 new** | **7 files** |

**Parallel opportunities**: 11 tasks marked `[P]`

**Suggested MVP scope**: Phase 1 (T001–T004) + Phase 2 (T005–T014) — delivers both P1 user stories with full TDD coverage.

---

## Notes

- `[P]` = different files, no unmet dependencies — safe to execute concurrently
- TDD gate: run `pytest` after writing each failing test to confirm it fails with the right error
- T016 has a hard dependency on T013 (same file) — do not start T016 until T013 is committed
- `mitigating_at_s` remains **required** in `DroneScenario` YAML schema (backward compat) — do not remove it
- No new Python dependencies introduced — `haversine_m` reused from `sentrycs_sim.geo.wgs84`
- No wire contract changes — `defense_radius_m` is internal YAML config only
- The `defense_radius_m` field intentionally has no `gt=0.0` Pydantic constraint (FR-010-010)
- Pastel colors `#80deea` / `#ffcc80` / `#ef9a9a` are confirmed conflict-free against all existing palette entries (see `research.md` R2)
