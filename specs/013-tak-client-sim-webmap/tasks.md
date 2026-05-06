---
description: "Task list for feature 013-tak-client-sim-webmap"
---

# Tasks: tak-client-sim-webmap (013)

**Input**: Design documents from `specs/013-tak-client-sim-webmap/`
**Branch**: `feature/013-tak-client-sim-webmap`
**Approach**: Test-First (G1) — every unit test task MUST be written and confirmed failing before its paired implementation task begins.

**Design documents used**:
- `spec.md` — US-001 (P1), US-002 (P2), US-003 (P3)
- `plan.md` — components C-1 through C-7, implementation order
- `data-model.md` — `ClientConfig.use_ssl` field spec, `CotEvent` field reference
- `research.md` — SVG shape specs, `ssl=None` decision, port-check idiom
- `quickstart.md` — service startup order, health-check URLs, scenario timeline

---

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no shared state)
- **[US1/US2/US3]**: User story this task belongs to
- All file paths are relative to the repository root (`/home/longtai/works/cics/cics-tak-demo/`)

---

## Phase 1: Setup

**Purpose**: Confirm the existing test baseline is clean before any changes.

- [ ] T001 Run `pytest services/tak-client-sim/tests/unit/` and confirm zero failures (baseline green-bar before any changes)

---

## Phase 2: Foundational — `use_ssl` Config Plumbing (C-2, C-3, C-4, C-5)

**Purpose**: Add `use_ssl: bool` to `ClientConfig` and propagate it through the connection layer. This is the **blocking prerequisite** for US-001's independent test (tak-client-sim must connect plaintext to `tak_relay.py`) and for both demo scripts (US-002, US-003).

**⚠️ CRITICAL**: Complete all tests (T002–T004) and confirm they FAIL before beginning T005–T008.

### Tests — write and confirm RED first

- [ ] T002 [P] Write failing unit tests for `ClientConfig.use_ssl` field: assert default=True, assert YAML `use_ssl: false` loads correctly, assert `use_ssl: true` round-trips, assert `ValidationError` on `extra="forbid"` still holds in `services/tak-client-sim/tests/unit/test_config_use_ssl.py`
- [ ] T003 [P] Write failing unit tests for `--ssl` / `--no-ssl` CLI override in `load_config()`: assert `--no-ssl` sets `use_ssl=False` overriding YAML, assert `--ssl` sets `use_ssl=True` overriding YAML, assert neither flag leaves config value unchanged in `services/tak-client-sim/tests/unit/test_config_use_ssl.py`
- [ ] T004 Write failing unit test for `connect_with_retry()` plaintext path: mock `asyncio.open_connection`, assert it is called with `ssl=None` when `use_ssl=False`, and assert it is called with an `ssl.SSLContext` instance when `use_ssl=True` in `services/tak-client-sim/tests/unit/test_config_use_ssl.py`

### Implementation

- [ ] T005 Add `use_ssl: bool = True` field immediately after `port` field in `ClientConfig` (preserves backward compatibility — omitting field in YAML defaults to True) in `services/tak-client-sim/src/tak_client_sim/config.py`
- [ ] T006 Add `--ssl` (`action="store_true"`, `dest="ssl"`) and `--no-ssl` (`action="store_true"`, `dest="no_ssl"`) arguments to `_build_parser()`, and add `getattr(args, "ssl", None)` / `getattr(args, "no_ssl", False)` override block in `load_config()` in `services/tak-client-sim/src/tak_client_sim/__main__.py`
- [ ] T007 Replace `ssl_ctx = build_ssl_context(config)` with `ssl_ctx = build_ssl_context(config) if config.use_ssl else None` in `connect_with_retry()` in `services/tak-client-sim/src/tak_client_sim/connection.py`
- [ ] T008 Add `use_ssl: false  # connects to tak_relay.py (plaintext TCP on :8089)` line after `use_ssl_verify` in `services/tak-client-sim/config/demo.yaml`

**Checkpoint**: Run `pytest services/tak-client-sim/tests/unit/test_config_use_ssl.py` — all T002–T004 tests must now be GREEN.

---

## Phase 3: US-001 — MIL-STD-2525C Icons (P1) 🎯 MVP

**Goal**: Replace the plain filled-circle markers in `_MAP_HTML_TEMPLATE` with MIL-STD-2525C-compliant SVG icons: grey circle+cross for Unknown (`a-u-*`), red diamond for Hostile (`a-h-*`), opacity-dimmed for stale, course arrow for speed > 0.3 m/s.

**Independent Test**: Start `scripts/tak_relay.py --port 8089`, then start `tak-client-sim` with `config/demo.yaml`. Inject a synthetic `a-u-A-M-F-Q-r` and `a-h-A-M-F-Q-r` CoT XML event via the relay. Open `:8093/map` and confirm the icon shapes match the MIL-STD-2525C specification.

**⚠️ CRITICAL**: Complete all tests (T009–T013) and confirm they FAIL before beginning T014–T018.

### Tests for US-001 — write and confirm RED first

- [ ] T009 [P] [US1] Write failing unit test for Unknown icon SVG: call a helper (or inspect `_build_map_html` output) and assert the resulting HTML contains `<circle r="10"`, `fill="#90a4ae"`, `stroke="#546e7a"`, and two `<line` cross elements for `cot_type="a-u-A-M-F-Q-r"` in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`
- [ ] T010 [P] [US1] Write failing unit test for Hostile icon SVG: assert HTML contains `<rect`, `transform="rotate(45)"`, `fill="#ef5350"`, `stroke="#b71c1c"` for `cot_type="a-h-A-M-F-Q-r"` in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`
- [ ] T011 [P] [US1] Write failing unit test for stale dimming: assert HTML contains `opacity:0.45` at SVG root level and grey fill `#546e7a` when `is_stale=true` for both Unknown and Hostile types in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`
- [ ] T012 [P] [US1] Write failing unit tests for course arrow: assert `<polygon` is present in SVG output when `speed=1.0` (and rotated to `course` value), and absent when `speed=0.2` in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`
- [ ] T013 [P] [US1] Write failing unit test for unknown `cot_type` fallback: assert `cot_type="a-f-A-M-F-Q-r"` (non-`a-u`, non-`a-h`) renders the same Unknown grey circle+cross SVG without throwing a JS error (verify via HTML string inspection) in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`
- [ ] T013b [P] [US1] Write failing unit test for legend update (G1 / FR-005): call `_build_map_html()`, extract the `legend.onAdd` block, assert it contains `未知目標 Unknown (a-u-*)`, `敵對目標 Hostile (a-h-*)`, `過期 Stale`, and that old string `灰色目標 (GREY)` is absent in `services/tak-client-sim/tests/unit/test_web_icon_logic.py`

### Implementation for US-001

- [ ] T014 [US1] Replace `evtColors()` with `makeIconShape(cotType, isStale)` JS function in `_MAP_HTML_TEMPLATE`: dispatch on `cotType.startsWith('a-u')` → Unknown SVG, `cotType.startsWith('a-h')` → Hostile SVG, else → Unknown fallback; apply `opacity:0.45` and `#546e7a` fill override when `isStale` in `services/tak-client-sim/src/tak_client_sim/web_server.py`
- [ ] T015 [US1] Implement Unknown branch SVG in `makeDroneIcon()`: `<circle r="10" fill="#90a4ae" stroke="#546e7a" stroke-width="2"/>` plus two `<line>` elements forming interior diagonal cross (×) with `stroke="#546e7a" stroke-width="1.5" stroke-linecap="round"` in `services/tak-client-sim/src/tak_client_sim/web_server.py`
- [ ] T016 [US1] Implement Hostile branch SVG in `makeDroneIcon()`: `<rect x="-8" y="-8" width="16" height="16" fill="#ef5350" stroke="#b71c1c" stroke-width="2" transform="rotate(45)"/>` within `viewBox="-12 -12 24 24"` in `services/tak-client-sim/src/tak_client_sim/web_server.py`
- [ ] T017 [US1] Wire stale overlay into `makeDroneIcon()`: apply `style="${isStale ? 'opacity:0.45' : ''}"` on `<svg>` root and override shape fill to `#546e7a` / stroke to `#37474f` when `isStale=true` in `services/tak-client-sim/src/tak_client_sim/web_server.py`
- [ ] T018 [US1] Preserve course-arrow `<polygon points="0,-7 -3,-1 3,-1">` inside icon body: render when `speed > 0.3`, rotate via `<g transform="rotate(${course})">`, keep `fill="white" opacity="0.85"` for both Unknown and Hostile shapes in `services/tak-client-sim/src/tak_client_sim/web_server.py`
- [ ] T019 [US1] Update `legend.onAdd()`: replace old grey/red circle-dot entries with inline SVG samples for Unknown (grey circle+cross), Hostile (red diamond), and Stale (dimmed Unknown); update label text to `未知目標 Unknown (a-u-*)`, `敵對目標 Hostile (a-h-*)`, `過期 Stale` in `services/tak-client-sim/src/tak_client_sim/web_server.py`

**Checkpoint**: Run `pytest services/tak-client-sim/tests/unit/test_web_icon_logic.py` — all T009–T013b tests must now be GREEN.

---

## Phase 4: US-002 — Single-Drone End-to-End Demo Script (P2)

**Goal**: Deliver `scripts/demo-1drone.sh` that starts all 7 pipeline services in order, health-checks them, opens 3 browser tabs, and cleans up on `Ctrl-C` or `--stop`.

**Independent Test**: Run `scripts/demo-1drone.sh` from repo root; confirm all 7 services start, health checks pass, 3 tabs open, drone track appears on `:8093/map` at t≈9s, and `Ctrl-C` leaves no orphan processes.

**⚠️ CRITICAL**: Complete all tests (T020–T021) and confirm they FAIL before beginning T022–T029.

### Tests for US-002 — write and confirm RED first

- [ ] T020 [P] [US2] Write failing test: use `subprocess.run` to invoke `scripts/demo-1drone.sh` with a missing config file path injected via env var (or temp YAML absence), assert exit code is non-zero and stderr contains an actionable file-not-found message in `services/tak-client-sim/tests/unit/test_demo_scripts.py`
- [ ] T021 [P] [US2] Write failing test: verify `scripts/demo-3drone.sh` references `demo_three_drones.yaml` for both `UDS_SCENARIO` and `SNTR_CONFIG` variables (grep-based assertion on script contents), and verify `scripts/demo-1drone.sh` references `demo_single_drone.yaml` for `UDS_SCENARIO` in `services/tak-client-sim/tests/unit/test_demo_scripts.py`

### Implementation for US-002

- [ ] T022 [US2] Create `scripts/demo-1drone.sh`: add `#!/usr/bin/env bash`, `set -euo pipefail`, `SCRIPT_DIR`, `die()` helper, `.dev-runtime/` directory setup, PID-file directory creation, and all config variable declarations (`UDS_SCENARIO`, `ECHO_CONFIG`, `SNTR_CONFIG`, `GW_CONFIG`, `TAK_CONFIG`) with their correct relative paths in `scripts/demo-1drone.sh`
- [ ] T023 [US2] Add pre-flight checks to `scripts/demo-1drone.sh`: (1) `command -v python3`, (2) `command -v curl` (required for health-check loop), (3) existence of all 5 config files, (4) Python module importability for `map_sim`, `uds`, `echoshield_sim`, `sentrycs_sim`, `cot_gateway`, `tak_client_sim` using `python3 -c "import <module>"`, (5) `[[ -f scripts/tak_relay.py ]]` file-existence check in `scripts/demo-1drone.sh`
- [ ] T024 [US2] Add `check_port_free()` helper (using `/dev/tcp` bash built-in) and pre-flight port conflict detection for ports 8089, 8090, 8092, 8093, 18080, 7070 — all checked before first service launch in `scripts/demo-1drone.sh`
- [ ] T025 [US2] Add 7-service launch block in correct startup order (map-sim → uds → echoshield-sim → sentrycs-sim → cot-gateway → tak-relay → tak-client-sim): each launched via `python3 -m <module>` (or `python3 scripts/tak_relay.py`) with `&`, PID captured to `<SVC>_PID`, and PID written to `.dev-runtime/pids/<svc-name>.pid` in `scripts/demo-1drone.sh`
- [ ] T026 [US2] Add health-check loop (30 s timeout, 1 s poll): HTTP checks via `curl -sf` for `:8090/health`, `:9001/info`, `:7070/health`, `:8092/health`, `:8093/health`; TCP checks via `/dev/tcp` for `:18080` and `:8089`; progress ticker `map:· uds:· echo:· sntr:· gw:· relay:· tak:·`; dead-process detection (PID no longer running triggers `die()`) in `scripts/demo-1drone.sh`
- [ ] T027 [US2] Add scenario banner output (single-drone TRK-E01 timeline) and browser-open loop for 3 URLs (`http://127.0.0.1:8090/objects`, `http://127.0.0.1:8092/map`, `http://127.0.0.1:8093/map`) using `xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null || echo "Open manually: $url"` in `scripts/demo-1drone.sh`
- [ ] T028 [US2] Add `cleanup()` function (SIGTERM all PIDs → `sleep 1` → SIGKILL, remove all 7 PID files from `.dev-runtime/pids/`) and `trap cleanup INT TERM EXIT`; add `--stop` flag handler (reads PID files, sends SIGTERM, removes files, graceful if PID file missing) in `scripts/demo-1drone.sh`
- [ ] T029 [US2] Set executable bit and run `shellcheck -S warning scripts/demo-1drone.sh` — fix all reported warnings before proceeding in `scripts/demo-1drone.sh`

**Checkpoint**: `shellcheck scripts/demo-1drone.sh` exits 0 and `pytest services/tak-client-sim/tests/unit/test_demo_scripts.py::test_demo_1drone_missing_config` passes GREEN.

---

## Phase 5: US-003 — Three-Drone End-to-End Demo Script (P3)

**Goal**: Deliver `scripts/demo-3drone.sh` — structurally identical to `demo-1drone.sh` but using the three-drone scenario config files.

**Independent Test**: Run `scripts/demo-3drone.sh`; confirm three distinct track UIDs appear on `:8093/map` and the script stops cleanly.

**⚠️ CRITICAL**: Confirm T021 (scenario-path assertion) is RED before beginning T030.

### Implementation for US-003

- [ ] T030 [P] [US3] Create `scripts/demo-3drone.sh` by copying `scripts/demo-1drone.sh` and substituting: `UDS_SCENARIO` → `services/uds/scenarios/demo_three_drones.yaml`, `SNTR_CONFIG` → `services/sentrycs-sim/config/demo_three_drones.yaml`, scenario banner text → three-drone variant; all other logic (health checks, browser URLs, cleanup, `--stop`) remains identical in `scripts/demo-3drone.sh`
- [ ] T031 [US3] Set executable bit and run `shellcheck -S warning scripts/demo-3drone.sh` — fix all reported warnings in `scripts/demo-3drone.sh`

**Checkpoint**: `pytest services/tak-client-sim/tests/unit/test_demo_scripts.py::test_demo_3drone_scenario_paths` passes GREEN.

---

## Final Phase: Polish & Cross-Cutting

- [ ] T032 [P] Run full pytest suite for tak-client-sim (`pytest services/tak-client-sim/tests/ -v`) and confirm zero failures and zero errors — includes all pre-existing tests plus T002–T004 and T009–T013b
- [ ] T032b [P] Wire-contract regression (SC-008 / M4): in `test_web_server.py` or standalone, load a known `CotEvent` fixture into `CotStore`, GET `/events`, assert response JSON contains exactly these keys: `uid, source, color, cot_type, lat, lon, hae, speed, course, remarks, time, stale, delta_s, is_stale, stale_in_s` — no extra, no missing fields
- [ ] T033 [P] Load `services/tak-client-sim/config/demo.yaml` through `ClientConfig` in a smoke-test assertion: `ClientConfig(**yaml.safe_load(open("services/tak-client-sim/config/demo.yaml")))` must not raise `ValidationError` — confirms T005 + T008 are consistent
- [ ] T033b [P] Run `grep -rn 'print(' services/tak-client-sim/src/tak_client_sim/` — assert zero matches in production modules (`web_server.py`, `config.py`, `cot_store.py`, `models.py`, `parser.py`) (FR-012/G3) — allowed only in `formatter.py` and `connection.py` per AGENTS.md exception
- [ ] T034 Run `shellcheck -S warning scripts/demo-1drone.sh scripts/demo-3drone.sh` as a final gate; confirm zero warnings and both files have executable bit set (`ls -la scripts/demo-*.sh`)

---

## Dependency Graph

```
T001 (baseline)
  └─ T002–T004 (use_ssl tests — RED)
       └─ T005–T008 (use_ssl impl — GREEN)
            ├─ T009–T013 (icon tests — RED)  ← depends on use_ssl in config (indirect)
            │    └─ T014–T019 (icon impl — GREEN)
            └─ T020–T021 (demo tests — RED)
                 └─ T022–T029 (demo-1drone impl — GREEN)
                      └─ T030–T031 (demo-3drone impl — GREEN)
                           └─ T032–T034 (polish)
```

**Parallelism within phases**:
- T002, T003, T004: can be written in any order (same file, same test session)
- T009, T010, T011, T012, T013: can be written in any order (same file)
- T020, T021: can be written in any order (same file)
- T030 can proceed as soon as T022 (template script) is stable
- T032, T033, T034: all parallelisable (different commands)

---

## Implementation Strategy

**MVP scope (deliver first)**: Phases 1–3 (T001–T019)
- `use_ssl` plumbing + MIL-STD-2525C icons together make the TAK client map demo-ready
- US-001 can be demonstrated independently before the shell scripts exist
- Estimated task count to MVP: 19 tasks

**Full delivery**: All phases (T001–T034)
- Total tasks: 34
- Tasks by story: Foundational: 7, US-001: 11, US-002: 10, US-003: 2, Polish: 3 (+ T001 baseline)

---

## Independent Test Criteria

| Story | Test Criteria | Minimum Dependencies |
|-------|--------------|---------------------|
| Foundational | `pytest test_config_use_ssl.py` → 3 tests GREEN | T005–T008 |
| US-001 | `pytest test_web_icon_logic.py` → 5 tests GREEN; hard-refresh `:8093/map` shows correct shapes | T014–T019 |
| US-002 | `shellcheck demo-1drone.sh` exits 0; missing-config test GREEN; end-to-end run opens 3 tabs | T022–T029 |
| US-003 | Scenario-paths test GREEN; `shellcheck demo-3drone.sh` exits 0 | T030–T031 |
