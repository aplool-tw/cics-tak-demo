# Tasks: Unified Drone Simulator (UDS)

**Input**: Design documents from `/specs/001-uds/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Tests**: Tests are **required** for this feature (contract tests for `POST /command/takeover`, integration tests for push loop / closure / scenario loader, unit tests for WGS84 / state machine / trajectory). Follow TDD — write tests first, watch them fail, then implement.

**Organization**: Tasks are ordered by implementation flow (Setup → Tests → Core → Interface → CLI → Polish) per user direction, while each task is still tagged with the User Story it serves so stories remain independently verifiable.

## Format: `- [ ] T### [P?] [Story?] Description`

- **[P]**: Parallelizable (different file, no dependency on uncompleted task)
- **[US1/US2/US3]**: Maps to spec.md User Stories
- Every task points at an exact file path and is verifiable by a specific pytest test or `curl` smoke.

## Path Conventions

All paths relative to repo root. Service source tree is `services/uds/src/uds/`, tests live under `services/uds/tests/` (see plan.md §Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the `services/uds/` Python project skeleton and configuration so every later phase can import from `uds.*`.

- [ ] T001 Create `services/uds/` directory tree per plan.md §Project Structure (empty `src/uds/{models,scenario,geo,engine,push,api}/__init__.py`, `tests/{contract,integration,unit}/__init__.py`, `scenarios/`).
- [ ] T002 Create `services/uds/pyproject.toml` declaring Python ≥ 3.11, runtime deps (`aiohttp>=3.9`, `PyYAML>=6.0`, `pydantic>=2.6`, `structlog>=24.1`), dev/test deps (`pytest>=8.0`, `pytest-asyncio>=0.23`, `freezegun>=1.4`, `geopy>=2.4`, `ruff>=0.4`, `black>=24.3`), and the `uds = "uds.cli:main"` console entry point.
- [ ] T003 [P] Add `services/uds/pytest.ini` (or `[tool.pytest.ini_options]` in pyproject) with `asyncio_mode = "auto"` and `testpaths = ["tests"]`.
- [ ] T004 [P] Add `services/uds/README.md` that links to `specs/001-uds/spec.md` and `quickstart.md`.
- [ ] T005 [P] Configure lint/format: add `ruff` + `black` to `[project.optional-dependencies].dev` in `pyproject.toml` and configure (line-length 100, target-version py311).
- [ ] T006 [P] Create `services/uds/scenarios/single_drone_invasion.yaml` matching quickstart.md §3 (single `TRK-001`, `start_flying` at `at_s=0`).
- [ ] T007 [P] Create `services/uds/scenarios/drone_swarm.yaml` with 10 drones (upper bound for FR-UDS-010 / SC-004 tests).

**Checkpoint**: `cd services/uds && pip install -e .[dev]` succeeds; `pytest --collect-only` returns 0 tests.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared cross-cutting primitives that every later module imports. Must land before Phase 3+.

- [ ] T008 Implement `services/uds/src/uds/logging.py` — `configure_logging(verbose: bool)` using structlog JSON renderer + stdlib bridge; event names `state.transition`, `push.ok`, `push.backpressure`, `push.client_error`, `push.server_error`, `push.conn_error`, `push.timeout`, `takeover.accepted`, `takeover.rejected`, `scenario.loaded`, `scenario.fail_fast` (research.md §6). Unit test: `tests/unit/test_logging.py` asserts emitted record has required JSON keys.
- [ ] T009 Implement `services/uds/src/uds/config.py` — `Settings` dataclass holding `scenario_path`, `api_port=8080`, `map_sim_url="http://127.0.0.1:8090"`, `hz=10`, `verbose=False`, `debug=False`; include `Settings.from_args_and_scenario(args, scenario)` factory implementing **precedence: CLI > scenario YAML > default** for both `hz` (source: `--hz` > `scenario.update_hz` > 10) and `api_port` (source: `--api-port` > `scenario.servers.command_api_port` > 8080); validate resolved `hz ∈ [1, 20]` and `api_port ∈ [1, 65535]`, fail-fast on violation (FR-UDS-009, FR-UDS-011). Covered by `tests/unit/test_config.py` including precedence matrix.

**Checkpoint**: `python -c "from uds.logging import configure_logging; from uds.config import Settings"` succeeds.

---

## Phase 3: Tests First — Contract & Integration (TDD, write failing tests) ⚠️

**Purpose**: Lock the observable contract (HTTP + push) before any production code exists. Every test below MUST be committed red (xfail-free) and MUST pass by the end of Phase 5.

> NOTE: create `tests/conftest.py` first (T010) as all other tests depend on it.

- [ ] T010 [P] Create `services/uds/tests/conftest.py` with fixtures: (a) `scenario_tmpfile` factory that writes a caller-provided YAML, (b) `fake_map_server` aiohttp `TestServer` capturing `POST /objects/update` payloads with selectable response modes (`200`, `500`, `timeout`, `refused`), (c) `uds_app` async fixture booting `uds.api.server.create_app(settings)` against a freeport, (d) `frozen_clock` via freezegun for SC-008 reproducibility.

### Contract tests for US2 — `POST /command/takeover` (8 scenarios from spec.md §User Story 2)

- [ ] T011 [P] [US2] `tests/contract/test_takeover_contract.py::test_accept_flying_normal` — US2 Acceptance 1 + FR-UDS-004 + SC-003: POST with legal body on `FLYING_NORMAL` drone returns `200`, body `{status:"accepted", previous_state:"FLYING_NORMAL", new_state:"MITIGATING_TAKEOVER", estimated_landing_s: <number>, drone_id}` (contracts §1.2.1).
- [ ] T012 [P] [US2] `tests/contract/test_takeover_contract.py::test_unknown_drone_id_400` — US2 Acceptance 2: unknown `drone_id` → `400` `{status:"error", reason:"drone_id not found"}` (FR-UDS-015, Edge Case "無效 `drone_id`").
- [ ] T013 [P] [US2] `tests/contract/test_takeover_contract.py::test_landed_drone_400` — US2 Acceptance 3 + Edge Case "LANDED 後再接管": already-`LANDED` drone → `400` `already landed`; asserts `flight_state` unchanged after call (FR-UDS-015).
- [ ] T014 [P] [US2] `tests/contract/test_takeover_contract.py::test_idle_drone_409` — US2 Acceptance 4 + Edge Case "IDLE 接管 409": `IDLE` drone → **`409`** `drone not airborne` (explicitly distinct from 400); test asserts status_code == 409, not 400.
- [ ] T015 [P] [US2] `tests/contract/test_takeover_contract.py::test_invalid_coordinates_400` — US2 Acceptance 5 + Edge Case "座標越界": parametrized over `target_lat=999`, `target_lon=-181`, and missing `target_lat` → `400` `invalid coordinates` / `missing field: target_lat`.
- [ ] T016 [P] [US2] `tests/contract/test_takeover_contract.py::test_invalid_altitude_400` — US2 Acceptance 6 + Edge Case "alt<0": parametrized over `target_alt_m=-1` and omitted `target_alt_m` → `400` `invalid altitude` (FR-UDS-004, FR-UDS-015).
- [ ] T017 [P] [US2] `tests/contract/test_takeover_contract.py::test_consecutive_takeover_overwrites` — US2 Acceptance 7 + Edge Case "連續接管覆寫": 1st call moves drone to `MITIGATING_TAKEOVER`; 2nd call with new `target_*` while still `MITIGATING_TAKEOVER` → `200 accepted`, response body MUST NOT contain any `overwrite_flag`/`overwrite_count` key; asserts `DroneState.takeover_cmd.target_lat` equals the 2nd payload (FR-UDS-004, data-model.md §3.1).
- [ ] T018 [P] [US2] `tests/contract/test_takeover_contract.py::test_debug_endpoints_404_without_flag` — US2 Acceptance 8: default mode (`debug=False`) → `GET /status/TRK-001` and `GET /drones` both return **404** (routes unregistered). (FR-UDS-003a).
- [ ] T019 [P] [US2] `tests/contract/test_takeover_contract.py::test_invalid_json_body` — contracts/rest-api.md §1.2.2: malformed JSON body → `400` `invalid json`.
- [ ] T020 [P] [US2] `tests/contract/test_takeover_contract.py::test_unknown_field_rejected` — contracts/rest-api.md §1.1: `{...,"bogus":1}` → `400` `unknown field: bogus` (pydantic `extra="forbid"`).
- [ ] T021 [P] [US2] `tests/contract/test_takeover_contract.py::test_descent_speed_zero_or_negative` — contracts §4: `descent_speed_ms=0` / `-1` → `400` `invalid descent speed`.
- [ ] T022 [P] [US2] `tests/contract/test_takeover_contract.py::test_rejected_requests_have_no_side_effects` — FR-UDS-015: run every 400/409 case from T012–T016, assert `fake_map_server` received **zero** `POST /objects/update` calls between the request and its response, and assert drone `flight_state` unchanged.

### Integration tests for US1 — end-to-end takeover closure

- [ ] T023 [P] [US1] `tests/integration/test_takeover_closure.py::test_flying_to_mitigating_within_one_tick` — US1 Acceptance 1 + SC-003: boot UDS at 10 Hz with `TRK-001` already `FLYING_NORMAL`; POST takeover; assert the **next** payload received by `fake_map_server` carries `status="MITIGATING_TAKEOVER"` within ≤ 150 ms wall-clock.
- [ ] T024 [P] [US1] `tests/integration/test_takeover_closure.py::test_auto_lands_when_alt_and_speed_low` — US1 Acceptance 2 + FR-UDS-006 + SC-005: seed drone near landing point with `alt=3m, v=5m/s`; fast-forward loop; assert state traversal `MITIGATING_TAKEOVER → LANDING → LANDED` and that the last-observed payload for `TRK-001` has `status="LANDED"`.
- [ ] T025 [P] [US1] `tests/integration/test_takeover_closure.py::test_end_to_end_latency_under_sc002` — US1 Acceptance 3 + SC-002: with `descent_speed_ms=3` and landing distance ≤ 1 km at `speed_ms=15`, assert wall-clock from `POST /command/takeover` `200` to first `status="LANDED"` push ≤ 90 s (use freezegun + monotonic injection to keep test fast).

### Integration tests for US3 — push loop / Map Simulator client

- [ ] T026 [P] [US3] `tests/integration/test_push_loop.py::test_per_drone_request_per_tick` — US3 Acceptance 1 + FR-UDS-002: boot 3 active drones at 10 Hz; after exactly 1 tick, `fake_map_server` received exactly 3 POSTs (each body is single-drone JSON with all required fields from contracts §3.2).
- [ ] T027 [P] [US3] `tests/integration/test_push_loop.py::test_10hz_rate_window` — US3 Acceptance 2 + SC-001 + SC-004: run N=10 drones for 10 s; assert total push count ∈ `[950, 1050]` and per-drone count ∈ `[95, 105]`.
- [ ] T028 [P] [US3] `tests/integration/test_push_loop.py::test_landed_finalization` — US3 Acceptance 3 + FR-UDS-006 + Edge Case "LANDED 收尾": observe exactly one push with `status="LANDED"` for the drone, and zero further pushes for that `drone_id` in any subsequent tick.
- [ ] T029 [P] [US3] `tests/integration/test_push_loop.py::test_idle_drones_never_pushed` — data-model.md §1.2: drones still in `IDLE` (timeline not triggered) never appear in `fake_map_server` request log.
- [ ] T030 [P] [US3] `tests/integration/test_push_loop.py::test_map_sim_5xx_does_not_kill_loop` — FR-UDS-014 + Edge Case "Map Sim 不可用韌性": configure `fake_map_server` to return 500 for 30 s then 200; assert main loop stayed alive and `push.server_error` logged, and next successful tick after recovery reflected.
- [ ] T031 [P] [US3] `tests/integration/test_push_loop.py::test_map_sim_connection_refused_resilience` — SC-007: bring `fake_map_server` down for 30 s (simulate by closing the port), assert `uds` process keeps ticking (no uncaught exception), logs `push.conn_error`, and recovers within 1 tick when server returns.
- [ ] T032 [P] [US3] `tests/integration/test_push_loop.py::test_backpressure_drops_oldest` — contracts §3.3: artificially block worker (slow fake server, 2 s latency), push 5 queued items → warning log `push.backpressure` emitted with `drone_id` + `dropped_timestamp`, queue size never exceeds `maxsize=2`.

### Integration tests for scenario loader

- [ ] T033 [P] `tests/integration/test_scenario_loader.py::test_unknown_action_fails_fast` — FR-UDS-007 + Edge Case "場景 YAML `action` 未知值": YAML with `action: takeoff` → `ScenarioLoader` raises, process exits with code **2**, stderr contains `unknown action: takeoff`; HTTP server and main loop never start (assert `fake_map_server` saw 0 requests).
- [ ] T034 [P] `tests/integration/test_scenario_loader.py::test_empty_action_string_fails_fast` — `action: ""` → exit 2, message `unknown action: ''`.
- [ ] T035 [P] `tests/integration/test_scenario_loader.py::test_missing_required_field_fails_fast` — missing `scenario.drones` → exit 2, message `missing field: scenario.drones` (data-model.md §4.2).
- [ ] T036 [P] `tests/integration/test_scenario_loader.py::test_coordinate_out_of_range_fails_fast` — `start_lat: 999` → exit 2, `invalid coordinates: drones[0].start_lat=999 not in [-90, 90]`.
- [ ] T037 [P] `tests/integration/test_scenario_loader.py::test_too_many_drones_fails_fast` — 12 drones → exit 2, `too many drones: 12 (max 10)` (FR-UDS-010 upper bound).
- [ ] T038 [P] `tests/integration/test_scenario_loader.py::test_timeline_unknown_drone_id_fails_fast` — `timeline[].drone_id` not in `drones[]` → exit 2, `timeline references unknown drone_id: TRK-999`.
- [ ] T039 [P] `tests/integration/test_scenario_loader.py::test_duplicate_drone_id_fails_fast` — two drones share `drone_id` → exit 2, `duplicate drone_id: TRK-001`.

### Unit tests — geo, state machine, trajectory (will be written alongside / just before impl)

- [ ] T040 [P] `tests/unit/test_wgs84.py` — FR-UDS-008 + FR-UDS-012: test `haversine_m`, `bearing_deg`, `offset_wgs84` against `geopy.distance.distance` on 20 fixture points; assert error ≤ 1 m over 10 km; test `R = 6_371_000.0`; include antimeridian wrap test (`lon` result ∈ `[-180, 180]`).
- [ ] T041 [P] `tests/unit/test_wgs84.py::test_heading_clamp_30deg` — FR-UDS-013: diff 170° → clamped to +30°; diff -200° (wraps to +160°) → clamped to +30°.
- [ ] T042 [P] `tests/unit/test_state_machine.py` — FR-UDS-005: parametrized table of every allowed + disallowed transition; disallowed calls return unchanged state and log `state.transition.invalid`.
- [ ] T043 [P] `tests/unit/test_trajectory.py` — FR-UDS-008: straight flight toward waypoint advances `waypoint_index` on arrival; `MITIGATING_TAKEOVER` retargets to `takeover_cmd` target; descent ramps speed toward `descent_speed_ms`; `dt` clamp at 1.0 s (Edge Case "時鐘跳變").
- [ ] T044 [P] `tests/unit/test_trajectory.py::test_reproducibility_sc008` — SC-008: same seed YAML, two runs with freezegun-driven identical tick timestamps → same `(lat, lon, alt)` within 1 m at every sampled tick.

**Checkpoint (Phase 3)**: `pytest` → all tests **fail with ImportError / 404 / assertion** (expected — implementation absent). Commit red.

---

## Phase 4: Core (Data Model → Geo → State Machine → Trajectory → Engine Loop → Scenario Loader)

**Purpose**: Build deterministic in-memory simulation kernel. No I/O in this phase — only pure functions + dataclasses + the tick loop primitive.

### 4a. Data Model (blocks everything downstream)

- [ ] T045 [P] [US1] Implement `services/uds/src/uds/models/flight_state.py` — `FlightState(str, Enum)` with 5 members per data-model.md §1 (unblocks T042).
- [ ] T046 [P] [US1] Implement `services/uds/src/uds/models/drone_state.py` — `DroneState` dataclass with `slots=True`, all fields from data-model.md §2 (incl. `landed_finalized`, `last_tick_ts`).
- [ ] T047 [P] [US2] Implement `services/uds/src/uds/models/takeover.py` — `TakeoverCommand` dataclass (§3.1) and `TakeoverRequest` pydantic v2 model with `extra="forbid"`, all value-range validators (§3.2). Maps to contract tests T011–T021.

### 4b. Geo primitives

- [ ] T048 [US3] Implement `services/uds/src/uds/geo/wgs84.py` — `haversine_m`, `bearing_deg`, `offset_wgs84`, `clamp_turn` per research.md §5 (constants `R=6_371_000.0`); longitude wrap `((λ + 540) % 360) − 180`. Unblocks T040, T041.

### 4c. State machine (depends on 4a)

- [ ] T049 [US1] Implement `services/uds/src/uds/engine/state_machine.py` — `try_transition(drone, event) -> bool` enforcing the transition table in data-model.md §1.1; log `state.transition` and `state.transition.invalid`; enforce IDLE-not-pushed rule (§1.2). Unblocks T042.

### 4d. Trajectory engine (depends on 4a + 4b + 4c)

- [ ] T050 [US1] Implement `services/uds/src/uds/engine/trajectory.py` — `step(drone: DroneState, dt: float)` per data-model.md §2 推導規則; apply `dt = min(dt, 1.0)` (Edge Case "時鐘跳變"); call `state_machine.try_transition` when distance-to-target ≤ 100 m (→ LANDING) and when `alt_m ≤ 2 and v ≤ 0.5` (→ LANDED, FR-UDS-006); retargets to `takeover_cmd` while `MITIGATING_TAKEOVER`; apply `clamp_turn(±30°)`. Unblocks T043, T044.

### 4e. Main loop (depends on 4a–4d)

- [ ] T051 [US3] Implement `services/uds/src/uds/engine/loop.py` — `MainLoop(drones, hz, on_tick)` using `asyncio.get_event_loop().call_later`-style scheduling or `asyncio.sleep` with drift correction; each tick: compute `dt` from wall-clock, run `trajectory.step` for every drone, invoke `on_tick(drone)` callback for each drone whose `flight_state ∉ {IDLE}` AND `landed_finalized is False`; after a `LANDING → LANDED` transition enqueue the final payload **in the same tick** then set `landed_finalized = True` (FR-UDS-006). SC-001 validated in T027.

### 4f. Scenario loader (depends on 4a)

- [ ] T052 [US1] Implement `services/uds/src/uds/scenario/schema.py` — pydantic models `LatLon`, `Waypoint`, `LandingPoint`, `DroneSpec`, `TimelineEvent`, `Servers`, `Scenario`, `ScenarioFile` per data-model.md §4 (include `Literal["start_flying"]`, `min_length=1 / max_length=10` on `drones`).
- [ ] T053 [US1] Implement `services/uds/src/uds/scenario/loader.py` — `load_scenario(path) -> Scenario`: `yaml.safe_load` → `ScenarioFile.model_validate`; on `ValidationError` translate each error into the exact messages in data-model.md §4.2 (e.g. `unknown action: <value>`, `too many drones: N (max 10)`, `timeline references unknown drone_id`, `duplicate drone_id`); cross-field checks §4.1; print to `stderr`; raise `SystemExit(2)`. Unblocks T033–T039.
- [ ] T054 [US1] `build_initial_drones(scenario) -> dict[str, DroneState]` in `scenario/loader.py` — populate `DroneState` from `DroneSpec`, compute `operator_lat/lon` via `offset_wgs84(start, operator_bearing_deg, operator_distance_m)`, set `flight_state=IDLE`.

**Checkpoint (Phase 4)**: All Phase 3 **unit** tests (T040–T044) pass; integration tests for scenario loader (T033–T039) pass; all other tests still fail (no HTTP / push yet).

---

## Phase 5: Interface Layer (HTTP Server + Map Simulator Push Client)

**Purpose**: Wire the Core to the outside world. After this phase, the entire test suite from Phase 3 must pass.

### 5a. Map Simulator push client (US3)

- [ ] T055 [US3] Implement `services/uds/src/uds/push/map_client.py::MapClient` — single `aiohttp.ClientSession` (keep-alive); per-drone `asyncio.Queue(maxsize=2)`; `enqueue(drone)` uses `put_nowait`, on `QueueFull` pops oldest + logs `push.backpressure` with `drone_id` + `dropped_timestamp`; per-drone worker loops `get()` → `POST {map_sim_url}/objects/update` with `asyncio.timeout(0.5)`; classify response as `push.ok` / `push.client_error` / `push.server_error` / `push.conn_error` / `push.timeout`; **never propagate exceptions to main loop** (FR-UDS-014, SC-007). Unblocks T026, T027, T029–T032.
- [ ] T056 [US3] Implement `MapClient.finalize_landed(drone_id)` — enqueue the final `status="LANDED"` payload, then close that drone's queue/worker; subsequent `enqueue(drone)` for same id is a no-op. Unblocks T028.
- [ ] T057 [US3] Build push payload serializer in `push/map_client.py` — map `DroneState.velocity_ms → speed_ms`, `flight_state.value → status`, `datetime.now(UTC)` ISO 8601 ms precision (data-model.md §5, contracts §3.2).

### 5b. REST API server (US2)

- [ ] T058 [US2] Implement `services/uds/src/uds/api/server.py::create_app(settings, drones, map_client) -> aiohttp.web.Application` — wire aiohttp routes; only register debug routes when `settings.debug is True` (FR-UDS-003a).
- [ ] T059 [US2] Implement `services/uds/src/uds/api/takeover.py::handle_takeover(request)` — parse JSON; on `JSONDecodeError` → `400 invalid json`; run `TakeoverRequest.model_validate` and translate pydantic errors to the stable `reason` strings in contracts/rest-api.md §1.2.2 / §4 (`missing field: X`, `invalid type: X`, `invalid coordinates`, `invalid altitude`, `invalid descent speed`, `unknown field: X`); lookup drone; apply state-dependent mapping from data-model.md §3.3 (IDLE → **409** `drone not airborne`; LANDED → 400 `already landed`; FLYING_NORMAL / MITIGATING_TAKEOVER / LANDING → 200); on accept: build `TakeoverCommand`, attach to drone, call `state_machine.try_transition(drone, Event.TAKEOVER)`, compute `estimated_landing_s = haversine_m(drone, target) / descent_speed_ms`; ensure zero side-effects on error paths (FR-UDS-015). Unblocks T011–T022.
- [ ] T060 [US2] Implement `services/uds/src/uds/api/debug.py` — `GET /status/{drone_id}` and `GET /drones` handlers per contracts §2; registered **only** via `server.create_app` when `settings.debug is True`. Unblocks T018.

### 5c. Wire API + push + loop together

- [ ] T061 [US1] In `services/uds/src/uds/engine/loop.py`, accept `map_client` and in `on_tick`: call `map_client.enqueue(drone)` for each active drone; when `trajectory.step` transitions `LANDING → LANDED` this tick call `map_client.finalize_landed(drone_id)` (FR-UDS-006 same-tick guarantee). Unblocks T023–T025, T028.

**Checkpoint (Phase 5)**: `pytest services/uds/tests/contract tests/integration` → all green. All FR-UDS-001..010, 012..015 exercised by tests.

---

## Phase 6: CLI Integration

**Purpose**: Assemble the `python -m uds` entry point so the quickstart.md recipe works end-to-end.

- [ ] T062 Implement `services/uds/src/uds/cli.py::main()` — argparse for `--scenario` (required), `--api-port` (default 8080), `--map-sim-url` (default `http://127.0.0.1:8090`), `--hz` (default 10; validated 1–20), `--verbose` (flag), `--debug` (flag) per FR-UDS-011 / quickstart.md §2.2.
- [ ] T063 Implement `services/uds/src/uds/__main__.py` → `from uds.cli import main; main()` so `python -m uds …` works.
- [ ] T064 [US1] Boot sequence in `cli.py`: (1) `configure_logging(verbose)`, (2) `scenario = load_scenario(path)` — on `SystemExit(2)` propagate (FR-UDS-007), (3) create `drones = build_initial_drones(scenario)`, (4) open `aiohttp.ClientSession` → `MapClient`, (5) schedule `timeline` events (`start_flying → try_transition(IDLE→FLYING_NORMAL)`) via `asyncio.call_later`, (6) start `MainLoop` + aiohttp `AppRunner` under an `asyncio.TaskGroup` for unified lifecycle (plan.md Technical Context).
- [ ] T065 Smoke test `services/uds/tests/integration/test_cli_smoke.py` — spawn `python -m uds --scenario scenarios/single_drone_invasion.yaml --api-port <free> --map-sim-url <fake> --hz 10`, `curl POST /command/takeover` after 1 s, expect 200; kill process; asserts exit code 0 and logs contain `scenario.loaded`.
- [ ] T066 Smoke test `tests/integration/test_cli_smoke.py::test_debug_mode_registers_endpoints` — same as T065 but with `--debug`; `curl GET /drones` returns 200 JSON list; without flag returns 404 (quickstart §4.3).

**Checkpoint (Phase 6)**: quickstart.md §2 and §4 commands succeed on a developer machine.

---

## Phase 7: Polish & Cross-Cutting (Logging / Error Handling / Retry / SC Measurements)

**Purpose**: Harden observability and measure Success Criteria beyond functional correctness.

- [ ] T067 [P] Add `tests/integration/test_sc_metrics.py::test_sc001_per_drone_rate` — SC-001 explicit 10 s measurement @ 10 Hz with 1 drone, assert 95 ≤ count ≤ 105 (complements T027 N=10 case).
- [ ] T068 [P] Add `tests/integration/test_sc_metrics.py::test_sc002_end_to_end_under_90s` — SC-002 with `single_drone_invasion.yaml` default geometry (duplicate of T025 but against shipped YAML to exercise loader → loop → push path).
- [ ] T069 [P] Add `tests/integration/test_sc_metrics.py::test_sc003_takeover_http_p99_and_push_latency` — SC-003: 100 sequential takeover POSTs on 100 drones' worth of drones (reset per iteration); record HTTP response time; assert p99 ≤ 200 ms; assert first `MITIGATING_TAKEOVER` push within ≤ 1 tick (≤ 100 ms).
- [ ] T070 [P] Add `tests/integration/test_sc_metrics.py::test_sc004_ten_drones_10s` — SC-004: load `drone_swarm.yaml`, 10 drones, 10 s → total pushes ∈ `[950, 1050]`, per-drone std-dev commentary via logs.
- [ ] T071 [P] Add `tests/integration/test_sc_metrics.py::test_sc005_no_landed_flapping` — SC-005: feed altitude/velocity trace that crosses the `alt≤2 ∧ v≤0.5` threshold exactly once; assert `LANDED` transition happens within 1 tick and state never leaves `LANDED`.
- [ ] T072 [P] Add `tests/integration/test_sc_metrics.py::test_sc006_debug_freshness` — SC-006 (observability, non-contract): with `--debug`, `GET /status/TRK-001` response timestamp is within 1 tick of most recent main-loop completion.
- [ ] T073 [P] Add `tests/integration/test_sc_metrics.py::test_sc007_30s_outage` — SC-007: keep `fake_map_server` offline for 30 s while UDS runs; assert process never exits, `push.conn_error` counter grows monotonically; bring server back up, assert first push within next tick succeeds.
- [ ] T074 [P] Add `tests/integration/test_sc_metrics.py::test_sc008_reproducibility_1m` — SC-008: run same YAML twice with frozen clock; compare `(lat, lon, alt_m)` at 10 sampled ticks, assert L2 error ≤ 1 m per sample (extends T044 to the integration level).
- [ ] T075 [P] Implement `push.*` and `takeover.*` structured-log fields audit — `grep` through sources / tests to confirm every log site emits `drone_id` plus at least one of `{http_status, reason, error_class}` (research.md §6). For `push.timeout` / `push.conn_error` events, an `error_class` field (e.g. `asyncio.TimeoutError`, `aiohttp.ClientConnectionError`) is the required replacement for `http_status`. Add `tests/unit/test_logging.py::test_required_fields` that captures every emitted event and asserts key presence under this flexible rule.
- [ ] T076 [P] Harden `MapClient` error handling — explicitly catch `aiohttp.ClientConnectorError`, `asyncio.TimeoutError`, `aiohttp.ClientResponseError`; confirm `Exception` is never swallowed silently (reraise as structured log + drop). Unit test via `tests/unit/test_map_client_errors.py`.
- [ ] T077 [P] Document "no retry queue; next tick retries with freshest state" policy in `services/uds/README.md` §"Failure semantics" — FR-UDS-014 + research.md §3.1 / contracts §3.5.
- [ ] T078 [P] Add `services/uds/docs/cli.md` (optional) or extend README with `--debug` caveat ("NOT a contract endpoint") mirroring contracts §2.3.
- [ ] T079 Update `specs/001-uds/quickstart.md` §5 test commands if any path drifted; run `pytest` from repo root (single invocation) and attach summary in PR description.
- [ ] T080 Final coverage check: `pytest --cov=uds --cov-report=term-missing` ≥ 85 % lines in `uds/api/`, `uds/engine/`, `uds/push/`, `uds/scenario/` (soft target; fail-only if < 70 %).

**Checkpoint (Phase 7)**: All SC-001..SC-008 measured and green; every FR traced to at least one test (see Coverage Matrix below).

---

## Dependencies

```
Setup (T001–T007)
     │
Foundational (T008–T009)
     │
Tests-first (T010–T044)   ← must be red before Phase 4 implementation
     │
Core data model (T045–T047)  [P among themselves]
     │
Geo (T048) ── State machine (T049) ── Trajectory (T050)
     │            │                      │
     └────────────┴──────────────────────┘
                  │
            Main loop (T051)
                  │
            Scenario loader (T052–T054)
                  │
Interface: Push (T055–T057) + API (T058–T060) + Wiring (T061)
                  │
CLI integration (T062–T066)
                  │
Polish / SC tests (T067–T080)
```

Story-level independence:
- **US2** (takeover contract) is testable after Phase 5a+5b without CLI.
- **US3** (push loop) is testable after Phase 5a + 4e.
- **US1** (closure) requires Phase 5c wiring — it composes US2 + US3.

---

## Parallel Execution Examples

Inside Phase 3 (tests-first), all contract test cases T011–T022 are independent files/methods — developers can parallelize. Likewise T026–T032 (push loop) and T033–T039 (loader).

Inside Phase 4a (data model), T045 / T046 / T047 can be written concurrently.

Inside Phase 7 polish, T067–T074 are independent `test_sc_metrics.py::*` functions — run them as separate PRs.

---

## Coverage Matrix

| Spec item | Task(s) | Verified by test |
|-----------|--------|------------------|
| FR-UDS-001 | T046, T050, T051 | T043, T044 |
| FR-UDS-002 | T055, T057, T061 | T026, T027, T029 |
| FR-UDS-003 | T058, T059 | T011–T022 |
| FR-UDS-003a | T060, T062 | T018, T066 |
| FR-UDS-004 | T047, T059 | T011, T017 |
| FR-UDS-005 | T045, T049 | T042 |
| FR-UDS-006 | T050, T056, T061 | T024, T028, T071 |
| FR-UDS-007 | T052, T053 | T033–T039 |
| FR-UDS-008 | T048, T050 | T040, T043 |
| FR-UDS-009 | T009, T062 | T065 |
| FR-UDS-010 | T052 (`max_length=10`), T007 (swarm YAML) | T037, T070 |
| FR-UDS-011 | T062 | T065, T066 |
| FR-UDS-012 | T048 | T040 |
| FR-UDS-013 | T048 (`clamp_turn`), T050 | T041 |
| FR-UDS-014 | T055, T076 | T030, T031, T073 |
| FR-UDS-015 | T047, T059 | T012–T016, T019–T022 |
| SC-001 | T051, T055 | T027, T067 |
| SC-002 | T061, T064 | T025, T068 |
| SC-003 | T059, T061 | T023, T069 |
| SC-004 | T055, T007 | T027, T070 |
| SC-005 | T050 | T024, T071 |
| SC-006 | T060 | T072 |
| SC-007 | T055, T076 | T031, T073 |
| SC-008 | T048, T050 | T044, T074 |
| US1 Acceptance 1–3 | Phase 5c + 6 | T023, T024, T025 |
| US2 Acceptance 1–8 | Phase 5b | T011–T018 |
| US3 Acceptance 1–3 | Phase 5a + 4e | T026, T027, T028 |
| Edge: unknown action | T053 | T033, T034 |
| Edge: IDLE 409 | T059 | T014 |
| Edge: continuous takeover overwrite | T047, T059 | T017 |
| Edge: Map Sim unavailable | T055 | T030, T031, T073 |
| Edge: LANDED finalization | T050, T056 | T028 |
| Edge: coord out of range | T047, T053 | T015, T036 |
| Edge: alt < 0 | T047 | T016 |
| Edge: duplicate drone_id | T053 | T039 |
| Edge: clock jump (dt > 1 s) | T050 | T043 |

---

## Implementation Strategy (recommended rollout)

1. **MVP checkpoint** = Phase 1 + 2 + 3 (red tests) + 4 + 5 + 6 (all Phase 3 tests green, `curl` smoke works). Ship this as the first demoable UDS.
2. **Hardening checkpoint** = Phase 7 (SC measurements + logging audit). Ship when SC-001..SC-008 all green.
3. Keep US2 contract tests (T011–T022) frozen post-MVP — they are the public API contract (plan.md §Constitution Check).

---

## Extension Hooks

**Optional Hook**: git
Command: `/speckit.git.commit`
Description: Auto-commit after task generation

Prompt: Commit task changes?
To execute: `/speckit.git.commit`
