# Tasks: CoT Gateway Perimeter Guard

**Feature**: `011-cot-gw-perimeter`  
**Branch**: `feature/011-cot-gw-perimeter`  
**Input**: `specs/011-cot-gw-perimeter/plan.md` · `specs/011-cot-gw-perimeter/spec.md`  
**Approach**: TDD — failing test written first, then implementation; parallelisable groups marked `[P]`

---

## Format

```
- [X] [TaskID] [P?] [StoryLabel?]  Description — file/path
```

- **`[P]`** task touches a distinct file set; can run concurrently with other `[P]` tasks  
- **`[US1]`–`[US5]`** user-story scope (matches spec.md priorities)  
- **No story label** on setup, foundational, or cross-cutting tasks

---

## Phase 1: Setup

> **No dedicated setup tasks.** Feature 011 adds modules and extends existing files inside
> two already-bootstrapped services (`cot-gateway`, `sentrycs-sim`). No new service,
> virtual-environment, or dependency installation is required — `aiohttp`, `pydantic v2`,
> `structlog`, `pytest`, and `pytest-asyncio` are all present.

**Prerequisite commands** (run once before starting any task):

```bash
cd services/cot-gateway  && python -m pytest --tb=short -q   # baseline: ≥ 95 tests pass
cd services/sentrycs-sim && python -m pytest --tb=short -q   # baseline: ≥ 117 tests pass
```

---

## Phase 2: US1 & US2 — HTTP Cache-Control + Sensor-Marker Flicker Fix `[P]`

> **Goal**: Browser always receives fresh `/tracks` and `/sites` data on every poll; sensor
> markers stay visible during and after a slow or failed `/sites` fetch.  
>
> **Parallel opportunity**: Groups 1 and 2 touch different parts of `server.py` and different
> test files — all four test tasks (T001, T002, T005, T006) can be written simultaneously
> before either implementation task (T003, T004, T006) begins.

**Independent Test — US1**: Open DevTools network panel; confirm every `GET /tracks` response
carries `Cache-Control: no-store`; confirm drone icon advances between 2-second refresh cycles.

**Independent Test — US2**: Throttle `/sites` to 800 ms; confirm sensor markers remain visible
throughout the fetch cycle; confirm layers are only rebuilt after a successful response.

### Group 1 — Cache-Control headers `[P]`

> Write both unit tests first (T001, T002), verify they **fail**, then implement (T003, T004).

- [X] T001 [P] [US1]  Write unit test: `GET /tracks` response includes `Cache-Control: no-store` header — `services/cot-gateway/tests/unit/test_server.py`
- [X] T002 [P] [US2]  Write unit test: `GET /sites` response includes `Cache-Control: no-store` header — `services/cot-gateway/tests/unit/test_server.py`
- [X] T003 [US1] [US2]  Implement: add module-level `_NO_CACHE = {"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"}` constant and pass `headers=_NO_CACHE` to `web.json_response()` in `_tracks`, `_sites`, and `_health` handlers — `services/cot-gateway/src/cot_gateway/web/server.py`
- [X] T004 [US1] [US2]  Implement: add `{cache: 'no-store'}` option to the `fetch('/tracks', …)` and `fetch('/sites', …)` JS calls in the inline map template — `services/cot-gateway/src/cot_gateway/web/server.py`

### Group 2 — Sensor-marker flicker fix `[P]`

> Write the unit test first (T005), verify it **fails**, then move the `clearLayers` calls (T006).

- [X] T005 [P] [US2]  Write unit test: mock a failing `fetch('/sites')`; assert `siteLayer.clearLayers()` and `sensorLayer.clearLayers()` are **not** called when the fetch fails — `services/cot-gateway/tests/unit/test_server_js.py` *(or document as manual/spec-review test with inline comment if JS unit-test harness unavailable)*
- [X] T006 [US2]  Implement: move `siteLayer.clearLayers()` and `sensorLayer.clearLayers()` from before the `if (!r.ok) return;` guard to inside the `try` block immediately after `r.ok` check, before populating new markers — `services/cot-gateway/src/cot_gateway/web/server.py`

**Checkpoint — US1 + US2**: `pytest services/cot-gateway/tests/unit/test_server.py` passes; manual map smoke-test shows advancing drone icon and stable sensor markers.

---

## Phase 3: Foundational — PerimeterGuardConfig & TrackStore Extension

> **Purpose**: These two changes are blocking prerequisites for US3 (PerimeterGuard) and US5
> (takeover visualisation). No US3/US5 implementation task may begin until T007–T014 are
> all green.  
>
> **⚠ CRITICAL**: PerimeterGuard, GatewayMain wiring, and the map takeover badge all depend
> on the config schema and TrackStore API established here.

### Group 3 — PerimeterGuardConfig `[P]`

> Groups 3 and 4 are independent of each other (different files) — their test tasks can be
> written in parallel, but each group's implementation task waits for its own tests to pass.

- [X] T007 [P]  Write unit test: `PerimeterGuardConfig` with valid fields constructs without error; `enabled=False` is the default; `radius_m ≤ 0` raises `ValidationError`; missing required fields when `enabled=True` raise `ValidationError` — `services/cot-gateway/tests/unit/test_config.py`
- [X] T008 [P]  Write unit test: `load_config()` with a YAML blob containing a `perimeter:` section parses into a `GatewayConfig` whose `.perimeter` is a `PerimeterGuardConfig` with correct field values — `services/cot-gateway/tests/unit/test_config.py`
- [X] T009 [P]  Write unit test: `load_config()` with a YAML blob that has **no** `perimeter:` section returns a `GatewayConfig` whose `.perimeter` is `None` — `services/cot-gateway/tests/unit/test_config.py`
- [X] T010     Implement: add `PerimeterGuardConfig` Pydantic model with fields `enabled: bool = False`, `radius_m: float` (validator: `> 0`), `sp_lat: float`, `sp_lon: float`, `uds_url: str`, `holding_lat: float`, `holding_lon: float`, `holding_alt_m: float`; add `perimeter: Optional[PerimeterGuardConfig] = None` field to `GatewayConfig` — `services/cot-gateway/src/cot_gateway/config.py`

### Group 4 — TrackStore takeover flag

- [X] T011 [P]  Write unit test: `await track_store.mark_takeover(uid)` sets an internal flag for that UID — `services/cot-gateway/tests/unit/test_track_store.py`
- [X] T012 [P]  Write unit test: `await track_store.get_all()` includes `"takeover_issued": True` for a UID that has been marked, and `"takeover_issued": False` (or absent) for unmarked UIDs — `services/cot-gateway/tests/unit/test_track_store.py`
- [X] T013 [P]  Write unit test: `await track_store.remove(uid)` clears the takeover flag for that UID so it no longer appears in `_takeover_set` — `services/cot-gateway/tests/unit/test_track_store.py`
- [X] T014     Implement: add `_takeover_set: set[str] = field(default_factory=set)` to `TrackStore`; add `async mark_takeover(uid: str) → None` method (acquires `_lock`, adds `uid`); update `remove` to pop from both `_data` and `_takeover_set`; update `_serialize()` to accept `takeover_issued: bool` argument and include it in the returned dict; update `get_all()` to pass `takeover_issued=(uid in self._takeover_set)` — `services/cot-gateway/src/cot_gateway/web/track_store.py`

**Checkpoint — Foundational**: `pytest services/cot-gateway/tests/unit/test_config.py services/cot-gateway/tests/unit/test_track_store.py` all green; `GatewayConfig` rejects unknown fields (extra="forbid") still passes.

---

## Phase 4: US3 — CoT Gateway Issues Takeover on SP Perimeter Breach

> **Goal**: `PerimeterGuard` module evaluates every processed `UnifiedTrack` against the
> configured SP exclusion radius and dispatches a one-shot `POST /command/takeover` to UDS.
>
> **Independent Test**: Set `perimeter.radius_m: 1000.0` in `cot-gateway/config/demo.yaml`,
> run full demo; confirm exactly one `perimeter_breach` log event and one UDS takeover call.
>
> **Dependencies**: T007–T014 (Phase 3) must be complete.

### Group 5 — PerimeterGuard module (TDD)

> Write all seven unit tests (T015–T021) first; verify they all **fail**; then create the
> package (T022) and implement the class (T023).

- [X] T015 [P] [US3]  Write unit test: `PerimeterGuard.check()` does **not** fire for a track with `source=ECHOSHIELD` (wrong source — only SENTRYCS and FUSED trigger the guard) — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T016 [P] [US3]  Write unit test: `PerimeterGuard.check()` does **not** fire when the track's haversine distance to the SP is ≥ `radius_m` (track is outside the exclusion zone) — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T017 [P] [US3]  Write unit test: `PerimeterGuard.check()` fires (calls mock UDS) when a `SENTRYCS` track with `detection_status=DETECTED` enters `radius_m` — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T018 [P] [US3]  Write unit test: `PerimeterGuard.check()` fires when a `FUSED` track with `detection_status=MITIGATING` enters `radius_m` — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T019 [P] [US3]  Write unit test: `PerimeterGuard.check()` fires exactly **once** per entity key — a second call for the same track after a successful dispatch does not produce a second UDS call — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T020 [P] [US3]  Write unit test: UDS returns HTTP 409; guard treats this as success, calls `mark_takeover(uid)`, and adds entity key to `_triggered` — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T021 [P] [US3]  Write unit test: UDS transport raises `aiohttp.ClientError`; guard logs the error, does **not** raise, does **not** add entity key to `_triggered`, does **not** call `mark_takeover` — `services/cot-gateway/tests/unit/test_perimeter_guard.py`
- [X] T022 [US3]  Implement: create `services/cot-gateway/src/cot_gateway/perimeter/__init__.py` exporting `PerimeterGuard` — `services/cot-gateway/src/cot_gateway/perimeter/__init__.py`
- [X] T023 [US3]  Implement: create `PerimeterGuard` class with `__init__(sp_lat, sp_lon, uds_url, radius_m, holding_lat, holding_lon, holding_alt_m, *, session)` and `async check(track, uid, mark_takeover)` following the API spec in `plan.md §PerimeterGuard API`; use `cot_gateway.correlate.haversine.haversine_m` for distance; use `cot_gateway.cot.uid.entity_keys_for(track)` for idempotency latch; emit `perimeter_breach` structured log event before UDS dispatch; add entity key to `_triggered` only after HTTP 200 or 409 — `services/cot-gateway/src/cot_gateway/perimeter/guard.py`

### Group 6 — GatewayMain integration

- [X] T024 [US3]  Write integration test: construct a minimal `GatewayMain` with a mock `PerimeterGuard`; assert `_emit_for_track` calls `perimeter_guard.check()` for SENTRYCS and FUSED tracks and does **not** call it for ECHOSHIELD tracks — `services/cot-gateway/tests/integration/test_perimeter_integration.py`
- [X] T025 [US3]  Implement: in `GatewayMain.__init__`, instantiate `PerimeterGuard` when `config.perimeter` is not `None` and `config.perimeter.enabled is True`, passing the shared `aiohttp.ClientSession`; in `_emit_for_track`, `await self._perimeter_guard.check(track, uid, self._track_store.mark_takeover)` after `track_store.upsert` — `services/cot-gateway/src/cot_gateway/loop.py`

**Checkpoint — US3**: Integration test green; `pytest services/cot-gateway` passes with no regressions; full scenario log shows exactly one `perimeter_breach` event.

---

## Phase 5: US5 — Map Shows Orange "TAKEOVER" State for Intercepted Drones `[P]`

> **Goal**: After PerimeterGuard fires, the drone icon turns orange (`#FF9800`) and the side
> panel shows `[TAKEOVER]` within one 2-second refresh cycle.
>
> **Independent Test**: With `takeover_issued: true` in a `/tracks` response fixture,
> confirm `droneIcon()` returns an orange SVG and the panel HTML contains `[TAKEOVER]`.
>
> **Dependencies**: T014 (TrackStore `takeover_issued` field) must be complete.  
> **Note**: JS unit tests may be documented as manual/spec-review only if no JS test harness exists.

- [X] T026 [P] [US5]  Document (JS not unit-testable in this stack): orange icon expected when `takeover_issued=true`; record expected colour `#FF9800` and `[TAKEOVER]` label in a `# TEST:` comment block above `droneIcon()` for reviewer verification — `services/cot-gateway/src/cot_gateway/web/server.py`
- [X] T027 [P] [US5]  Implement: update `droneIcon()` ternary to `const c = t.takeover_issued ? '#FF9800' : (lost ? '#777' : (SRC_COLOR[src]||'#888'));`; append `${t.takeover_issued ? ' <b style="color:#FF9800">[TAKEOVER]</b>' : ''}` to the side-panel track-entry HTML string; do **not** modify `SRC_COLOR` or `SRC_BORDER` tables (FR-011-027) — `services/cot-gateway/src/cot_gateway/web/server.py`

**Checkpoint — US5**: Manual browser smoke-test: drone icon turns orange and panel shows `[TAKEOVER]` after perimeter breach.

---

## Phase 6: US4 — Sentrycs Detection Coverage Limited to 2 000 m

> **Goal**: Remove the misplaced perimeter guard from sentrycs-sim, set `detection_radius_m`
> to the realistic 2 000 m value, and replace the position-based takeover call with a
> time-based DETECTED→MITIGATING transition.
>
> **Independent Test**: Read `services/sentrycs-sim/config/demo.yaml`; confirm
> `detection_radius_m: 2000.0` and no `defense_radius_m` key; run integration test
> confirming zero UDS calls from sentrycs-sim.

- [X] T028 [P] [US4]  Write unit test: constructing `SentrycsConfig` from a YAML blob that contains a `defense_radius_m` field raises `ValidationError` (field is forbidden after RC3 cleanup) — `services/sentrycs-sim/tests/unit/test_config.py`
- [X] T029 [P] [US4]  Write unit test: `LoopRunner.run_one_tick()` with a DETECTED track does **not** invoke `UdsClient.post_takeover()` at any point in the tick — `services/sentrycs-sim/tests/unit/test_loop.py`
- [X] T030 [P] [US4]  Write unit test: `LoopRunner.run_one_tick()` transitions a DETECTED track to MITIGATING when `elapsed_s >= scenario.mitigating_at_s`; confirm `track.takeover_sent` is set to `True` to prevent re-triggering — `services/sentrycs-sim/tests/unit/test_loop.py`
- [X] T031 [US4]  Implement: remove `defense_radius_m: float` field from `SentrycsConfig` — `services/sentrycs-sim/src/sentrycs_sim/config.py`
- [X] T032 [US4]  Implement: in `LoopRunner.run_one_tick()` step 4, remove the position-based `haversine_m` perimeter check block and the `perimeter_breach` log event and `_ensure_takeover_task` call; replace with a time-based loop over DETECTED tracks: if `elapsed_s >= scenario.mitigating_at_s` and not `track.takeover_sent`, call `sm.transition(track, DetectionStatus.MITIGATING, reason="time_based", now=now_utc)` and set `track.takeover_sent = True` — `services/sentrycs-sim/src/sentrycs_sim/loop.py`
- [X] T033 [US4]  Implement: update `services/sentrycs-sim/config/demo.yaml` — set `detection_radius_m: 2000.0`; remove `defense_radius_m`; update drone `detected_at_s: 43`, `mitigating_at_s: 71`, `neutralized_at_s: 110`; add comment header documenting scenario timeline (`t≈9s` EchoShield, `t≈43s` Sentrycs detection at 2 000 m, `t≈71s` SP perimeter breach at 1 000 m, `t=110s` neutralised) consistent with 35 m/s drone speed — `services/sentrycs-sim/config/demo.yaml`

**Checkpoint — US4**: `pytest services/sentrycs-sim` passes with ≥ 117 baseline tests + new T028–T030 tests; zero UDS calls originate from sentrycs-sim in integration run.

---

## Final Phase: Polish & Cross-Cutting Concerns

> **Goal**: Activate the full feature end-to-end and confirm all success criteria.

- [X] T034  Implement: add `perimeter:` section to cot-gateway demo config with `enabled: true`, `uds_url: "http://127.0.0.1:18080"`, `radius_m: 1000.0`, `sp_lat: 24.725806`, `sp_lon: 121.033750`, `holding_lat: 24.725806`, `holding_lon: 121.071889`, `holding_alt_m: 50.0`, `descent_speed_ms: 15.0` — `services/cot-gateway/config/demo.yaml`

**End-to-end smoke** (manual, after T034):

```bash
# Terminal 1 — cot-gateway
cd services/cot-gateway && python -m cot_gateway --config config/demo.yaml

# Terminal 2 — sentrycs-sim
cd services/sentrycs-sim && python -m sentrycs_sim --config config/demo.yaml

# Verify:
# 1. Structured log shows perimeter_breach event with dist_m < 1000
# 2. Drone icon turns orange on map at http://localhost:18092/map
# 3. Side panel shows [TAKEOVER] badge
# 4. No UDS calls in sentrycs-sim logs
```

---

## Dependency Graph

```
T001──┐                               (US1: cache /tracks test)
T002──┤──T003──T004                   (US1+US2: cache headers impl)
T005──T006                            (US2: flicker fix, independent)

T007─┐
T008─┤──T010                          (Foundational: PerimeterGuardConfig)
T009─┘

T011─┐
T012─┤──T014                          (Foundational: TrackStore.mark_takeover)
T013─┘

         T015─┐
         T016─┤
         T017─┤
         T018─┤──T022──T023──T024──T025   (US3: PerimeterGuard → GatewayMain)
         T019─┤          ↑
         T020─┤      needs T010, T014
         T021─┘

                   T026──T027         (US5: map viz, needs T014)

T028─┐
T029─┤──T031──T032──T033              (US4: sentrycs-sim cleanup)
T030─┘

                              T025──T034   (Polish: demo config)
```

**User-story completion order** (suggested MVP scope):

| Increment | Stories | Tasks | Can ship independently? |
|-----------|---------|-------|------------------------|
| MVP       | US1 + US2 | T001–T006 | ✅ yes — pure HTTP/JS fixes |
| Core      | US3 | T007–T025 | ✅ yes — needs config + TrackStore first |
| Visual    | US5 | T026–T027 | ✅ yes — needs T014 only |
| Cleanup   | US4 | T028–T033 | ✅ yes — independent of US3/US5 |
| Activation | Config | T034 | depends on US3 complete |

---

## Parallel Execution Examples

### Sprint start — all `[P]` group tests written simultaneously

```
Developer A: T001, T002 (cache header tests)
Developer B: T005       (flicker test)
Developer C: T007, T008, T009 (config tests)
Developer D: T011, T012, T013 (TrackStore tests)
```

### After test phase — implementations parallelised across groups

```
Developer A: T003, T004 (server.py Cache-Control + JS fetch)
Developer B: T006       (server.py clearLayers move)
Developer C: T010       (config.py PerimeterGuardConfig)
Developer D: T014       (track_store.py mark_takeover)
```

### PerimeterGuard unit tests — all seven written in parallel

```
Developer A: T015, T016, T017
Developer B: T018, T019, T020, T021
```

### sentrycs-sim cleanup + map viz — run in parallel with US3 guard implementation

```
Developer A: T028, T029, T030, T031, T032, T033 (sentrycs-sim)
Developer B: T026, T027 (map viz JS — needs T014 done)
```

---

## Implementation Strategy

**Incremental delivery**:

1. **Immediate**: Ship US1 + US2 (T001–T006) — zero-risk HTTP header + JS one-liners; restores demo credibility immediately.
2. **Core**: Ship US3 (T007–T025) — the architectural centrepiece; add PerimeterGuard to cot-gateway.
3. **Visual**: Ship US5 (T026–T027) — closes the operator feedback loop; depends only on T014.
4. **Cleanup**: Ship US4 (T028–T033) — removes the misplaced guard from sentrycs-sim; independent.
5. **Activate**: T034 — flip the feature on in demo config.

**Quality gates** (run after each phase):

```bash
cd services/cot-gateway  && ruff check src/ tests/ && black --check src/ tests/ && pytest -q
cd services/sentrycs-sim && ruff check src/ tests/ && black --check src/ tests/ && pytest -q
```

**Final regression baseline** (SC-011-008):
- `cot-gateway`: ≥ 95 baseline + all new Feature 011 tests pass
- `sentrycs-sim`: ≥ 117 baseline + T028–T030 tests pass
