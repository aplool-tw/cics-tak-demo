# Tasks: Feature 015 — CoT XML Standard Format Compliance + Remote TAK Server Support

**Feature ID**: 015  
**Branch**: `feature/015-cot-xml-compliance`  
**Input**: `specs/015-cot-xml-compliance/` (spec.md, plan.md, research.md, quickstart.md)  
**Approach**: TDD — all tests written and confirmed FAIL before any implementation (G1 MUST)  
**Scope**: 13 source/config files modified + 2 new test files + 4 new config/script files + 4 doc files

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no incomplete task dependencies)
- **[US1–US4]**: User story this task belongs to (maps to US-015-01 → US-015-04 from spec.md)
- Exact file paths are included in each task description
- Task dependencies noted inline as `Requires: T###`

---

## Phase 1: Setup — Baseline Verification

**Purpose**: Confirm the full existing test suite is green before any change is made. A clean
baseline is mandatory per G1 — no implementation may proceed if any pre-existing test is already
failing.

- [ ] T000 Verify baseline: run `cd services/cot-gateway && python3 -m pytest -q` (expect 180 passed, 0 failed) and `cd services/tak-client-sim && python3 -m pytest -q` (expect 99 passed, 0 failed) — both must be green before proceeding

---

## Phase 2: Foundational — G1 Failing Tests (Must Be Red Before Implementation)

**Purpose**: Write all unit tests for Feature 015 changes FIRST and confirm every new test
FAILS. No implementation work in Phase 3 may begin until all five test tasks below are red.

**⚠️ CRITICAL (G1)**: After writing T001–T005, run:

```bash
cd services/cot-gateway
python3 -m pytest tests/unit/test_generator_xml_decl.py tests/unit/test_config_xml_decl.py -v
```

Expected: **ALL new tests FAIL** (AttributeError / AssertionError). If any new test accidentally
passes before implementation, fix the test — it is not yet testing the right thing.

- [ ] T001 [P] [US1] Write unit tests for `xml_declaration=False` default: `test_xml_decl_false_default` and `test_xml_decl_false_explicit` assert `generate_cot(track)` output starts with `<event` (not `<?xml`) in `services/cot-gateway/tests/unit/test_generator_xml_decl.py`
- [ ] T002 [US1] Write unit tests for `xml_declaration=True`: `test_xml_decl_true` asserts `generate_cot(track, xml_declaration=True)` output starts with `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>` in `services/cot-gateway/tests/unit/test_generator_xml_decl.py` (Requires: T001)
- [ ] T003 [US1] Write unit tests for `<uid Droid>` presence: `test_uid_droid_present`, `test_uid_droid_equals_event_uid`, `test_uid_droid_is_first_detail_child`, `test_existing_elements_unchanged`, `test_uid_droid_special_chars_escaped`, and `test_compliance_matrix_all_8_scenarios` covering all 8 source × status combinations from `specs/005-cot-gateway/contracts/cot-xml.md §7` in `services/cot-gateway/tests/unit/test_generator_xml_decl.py` (Requires: T002)
- [ ] T004 [P] [US1] Write unit tests for `TakServerConfig.xml_declaration` field: `test_xml_declaration_field_default` (default `False`), `test_xml_declaration_field_true` (accepts `True`), `test_xml_declaration_roundtrip_yaml` (YAML with `xml_declaration: true` parses correctly), and `test_extra_field_still_forbidden` (`ValidationError` on unknown field) in `services/cot-gateway/tests/unit/test_config_xml_decl.py`
- [ ] T005 [US1] Write unit tests for `TakServerConfig.ca_bundle` field, CLI overrides, and SSL wiring: `test_ca_bundle_field_default` (default `None`), `test_ca_bundle_field_set` (accepts `"certs/ca.pem"`), `test_ca_bundle_wires_ssl_context` (mock `ssl.SSLContext.load_verify_locations` and assert called with `cafile="certs/ca.pem"` when `ca_bundle` is set and `use_ssl_verify=True`), `test_cli_tak_host_override`, `test_cli_tak_port_override`, `test_cli_no_ssl_flag`, `test_cli_partial_override_host_only`, and `test_cli_partial_override_port_only` — all asserting correct config values after `main(argv=[…])` in `services/cot-gateway/tests/unit/test_config_xml_decl.py` (Requires: T004)

**Checkpoint**: All T001–T005 written; run the test files and confirm every new test is red.

---

## Phase 3: User Story US-015-01 — CoT Gateway Real TAK Server Support (Priority: P1) 🎯 MVP

**Goal**: Operator connects `cot-gateway` to a real TAK server by editing one YAML config (or
passing two CLI flags); every generated CoT XML event includes `<uid Droid>` as the first child
of `<detail>`; `xml_declaration: true` prepends the ATAK-required XML declaration header.

**Independent Test**:

```bash
cd services/cot-gateway
python3 -m pytest tests/unit/test_generator_xml_decl.py tests/unit/test_config_xml_decl.py -v
# All new tests pass
python3 -m pytest -q
# 180+ passed, 0 failed (zero regressions)
```

### Implementation for US-015-01

- [ ] T006 [P] [US1] Add `ca_bundle: str | None = None` and `xml_declaration: bool = False` fields to `TakServerConfig` (after `cert_password` field, before `max_retries`) in `services/cot-gateway/src/cot_gateway/config.py`
- [ ] T007 [P] [US1] Add `ET.SubElement(detail, "uid", {"Droid": uid})` as the first child of `<detail>` — insert this line immediately before the existing `ET.SubElement(detail, "contact", …)` call, using the ET attribute API (not string concatenation) per FR-015-005 in `services/cot-gateway/src/cot_gateway/cot/generator.py`
- [ ] T008 [US1] Add `xml_declaration: bool = False` as a keyword-only parameter to `generate_cot()`; at the end of the function return `"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + ET.tostring(event, encoding="unicode")` when `True`, else `ET.tostring(event, encoding="unicode")` unchanged (per research.md R-001) in `services/cot-gateway/src/cot_gateway/cot/generator.py` (Requires: T007)
- [ ] T009 [US1] Update all three `generate_cot()` call sites (approximately lines 134, 148, 189) to pass `xml_declaration=self.config.tak_server.xml_declaration` as a keyword argument in `services/cot-gateway/src/cot_gateway/loop.py` (Requires: T006, T008)
- [ ] T006b [US1] Update `build_ssl_context()` in `services/cot-gateway/src/cot_gateway/tak/ssl_context.py`: after setting `ctx.verify_mode`, add `if cfg.ca_bundle and cfg.use_ssl_verify: ctx.load_verify_locations(cafile=cfg.ca_bundle)` — mirrors `tak-client-sim/connection.py:24–25` pattern (G5 Structural Symmetry). (Requires: T006)
- [ ] T010 [US1] Add `--tak-host HOST`, `--tak-port PORT`, and `--no-ssl` (action `store_true`) optional arguments to `_parse_args()`; apply overrides in `main()` using nested `model_copy(update={"tak_server": cfg.tak_server.model_copy(update=tak_overrides)})` following the `--web-host`/`--web-port` pattern; `--no-ssl` sets `use_ssl=False` in the override dict (research.md R-004) in `services/cot-gateway/src/cot_gateway/cli.py` (Requires: T006)
- [ ] T011 [US1] Create `services/cot-gateway/config/remote-tak.yaml` with documented placeholder values for `tak_server.host` (`"${TAK_HOST}"`), `.port` (8089), `.use_ssl` (`true`), `.use_ssl_verify` (`false`), `.cert_file`, `.cert_password`, `.ca_bundle` (`null`), `.xml_declaration` (`true`), `.max_retries` (5), plus stub `echoshield`, `sentrycs`, `logging`, and `web` sections; every field must have an inline comment explaining purpose and how to populate certificate paths (file: `services/cot-gateway/config/remote-tak.yaml`)

**Checkpoint**: `python3 -m pytest -q` inside `services/cot-gateway` shows 180+ passed, 0 failed.
CoT output contains `<uid Droid>`, `xml_declaration=True` produces the correct prefix, and
`--tak-host`/`--tak-port` overrides are reflected in the loaded config.

---

## Phase 4: User Story US-015-02 — TAK Client Sim Remote TAK Config (Priority: P2)

**Goal**: Operator runs `tak-client-sim --config services/tak-client-sim/config/remote-tak.yaml`
to connect to a real remote TAK server — no code changes required.

**Independent Test**:

```bash
cd services/tak-client-sim && python3 -m pytest -q
# 99 passed, 0 failed
# services/tak-client-sim/config/remote-tak.yaml exists and is valid YAML
```

### Implementation for US-015-02

- [ ] T012 [P] [US2] Create `services/tak-client-sim/config/remote-tak.yaml` with documented placeholder values for `host` (`"${TAK_HOST}"`), `port` (8089), `use_ssl` (`true`), `use_ssl_verify` (`false`), `ca_bundle` (`null`), and `max_retries` (0); every field must have an inline comment explaining purpose and cert placement; mirror the structure of the cot-gateway equivalent (file: `services/tak-client-sim/config/remote-tak.yaml`)

**Checkpoint**: File exists; `python3 -c "import yaml; yaml.safe_load(open('config/remote-tak.yaml'))"` succeeds; 99 tak-client-sim tests still pass.

---

## Phase 5: User Story US-015-03 — Remote TAK Demo Scripts (Priority: P2)

**Goal**: DevOps/field operator sets `TAK_HOST` (and optionally `TAK_PORT`, `TAK_USE_SSL`) and
runs a single script to start the full drone pipeline routed to a real TAK server; when `TAK_HOST`
is unset the scripts fall back to local `tak_relay.py` mode identically to the existing demos.

**Independent Test**:

```bash
bash -n scripts/demo-1drone-remote-tak.sh   # syntax check — exit 0
bash -n scripts/demo-3drone-remote-tak.sh   # syntax check — exit 0
# scripts/tak_relay.py is UNCHANGED (git diff shows no modification)
```

### Implementation for US-015-03

- [ ] T013 [P] [US3] Create `scripts/demo-1drone-remote-tak.sh`: inherit all helper functions (`preflight`, `cleanup`, `wait_for_health`) from `demo-1drone.sh`; when `[[ -n "${TAK_HOST:-}" ]]` is true, launch `cot-gateway` with `--tak-host "${TAK_HOST}" --tak-port "${TAK_PORT:-8089}"` and append `--no-ssl` if `TAK_USE_SSL=false`; skip `tak_relay.py` startup (omit port 8089 from `tcp_ready` preflight check); when `TAK_HOST` is unset, print a yellow warning and proceed identically to `demo-1drone.sh`; `chmod +x` (file: `scripts/demo-1drone-remote-tak.sh`)
- [ ] T014 [P] [US3] Create `scripts/demo-3drone-remote-tak.sh` with the same remote / local-fallback branching logic as T013 based on `demo-3drone.sh`; all three drone tracks must route to the real TAK server when `TAK_HOST` is set; append `--no-ssl` to cot-gateway invocation if `TAK_USE_SSL=false`; `chmod +x` (file: `scripts/demo-3drone-remote-tak.sh`)

**Checkpoint**: Both scripts pass `bash -n` syntax check; `git diff scripts/tak_relay.py` is empty (no modification to relay).

---

## Phase 6: User Story US-015-04 — Log vs Wire Format Documentation (Priority: P3)

**Goal**: Any developer reading the READMEs or `AGENTS.md` can immediately distinguish
structlog JSON log output from the CoT XML wire protocol — no room for confusion between
the two representations.

**Independent Test**: Open each of the four files below; confirm they explicitly state that
service logs are structured JSON (structlog) and that the wire protocol is CoT XML; confirm
the contract example shows `<uid Droid>` as the first child of `<detail>`.

### Implementation for US-015-04

- [ ] T015 [P] [US1] Update `specs/005-cot-gateway/contracts/cot-xml.md` §1: replace the sentence stating no XML declaration is present with a note that XML declaration is controlled by `tak_server.xml_declaration` config flag (default `false` = no declaration; `true` = ATAK-compatible prefix); update §2 XML schema example to show `<uid Droid="{UID}"/>` as the first child of `<detail>` and add a corresponding row to the field table (file: `specs/005-cot-gateway/contracts/cot-xml.md`)
- [ ] T016 [P] [US1] Update `services/cot-gateway/README.md`: add a "Connecting to a Real TAK Server" section documenting how to edit `config/remote-tak.yaml`, obtain and place P12/CA certificates, and run the gateway with `--config` and optional `--tak-host`/`--tak-port` overrides; add an explicit note in the logging section: *"Service logs are structured JSON (structlog); the wire protocol sent to TAK Server is CoT XML — the two formats are independent."* (file: `services/cot-gateway/README.md`)
- [ ] T017 [P] [US2] Update `services/tak-client-sim/README.md`: add a "Connecting to a Real TAK Server" section mirroring T016 adapted for the client simulator (reference `config/remote-tak.yaml`, cert placement, startup command); add the same log-vs-wire clarification note in the logging section (file: `services/tak-client-sim/README.md`)
- [ ] T018 [P] [US4] Update `AGENTS.md` §3 (Coding Standards / logging guidelines): add the note `⚠️ Log format ≠ wire format — cot-gateway and tak-client-sim emit structlog JSON to stdout/files; the bytes transmitted over TCP to the TAK Server are CoT XML. Do not confuse the two.` (file: `AGENTS.md`)

**Checkpoint**: All four documentation files updated; a reviewer reading them cold understands the log/wire distinction without referring to source code.

---

## Final Phase: Polish & Verification

**Purpose**: Gate-check confirming the entire Feature 015 deliverable — all 279+ tests pass and
zero lint violations exist across both services.

- [ ] T019 [P] Run full test suite for both services: `cd services/cot-gateway && python3 -m pytest -q` (must show 180+ passed, 0 failed) and `cd services/tak-client-sim && python3 -m pytest -q` (must show 99 passed, 0 failed) — zero regressions allowed across all 279+ tests (Requires: T001–T018)
- [ ] T020 [P] Run lint and format gate for both services: `cd services/cot-gateway && ruff check . && black --check src tests` and `cd services/tak-client-sim && ruff check . && black --check src tests` — both commands must exit 0 with no violations (Requires: T001–T018)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup / T000)**: No dependencies — run immediately
- **Phase 2 (Failing Tests / T001–T005)**: Requires T000 ✅ — **BLOCKS Phase 3**
- **Phase 3 (US-015-01 Implementation / T006–T011)**: Requires all of T001–T005 confirmed red
- **Phase 4 (US-015-02 / T012)**: Requires T000 ✅; can proceed in parallel with Phase 3
- **Phase 5 (US-015-03 / T013–T014)**: Requires T000 ✅; can proceed in parallel with Phases 3 & 4
- **Phase 6 (US-015-04 Docs / T015–T018)**: Requires T000 ✅; can proceed in parallel with Phases 3–5
- **Final Phase (T019–T020)**: Requires all T001–T018 complete

### User Story Dependency Graph

```
T000 [baseline OK]
 ├─▶ T001 [gen tests, red] ──▶ T002 ──▶ T003 [all generator tests red]
 │                                           │
 ├─▶ T004 [cfg tests, red] ──▶ T005         │
 │                               │           │
 │          T003 + T005 confirmed FAIL        │
 │                  │            │           │
 │            ┌─────┘────────────┘           │
 │            ▼                              ▼
 │        T006 [config.py fields] ◀──────────
 │          ├─▶ T007 [generator: uid Droid]
 │          │    └─▶ T008 [generator: xml_declaration param]
 │          │         └─▶ T009 [loop.py: thread config flag]
 │          └─▶ T010 [cli.py: --tak-host/--tak-port]
 │          T011 [cot-gateway remote-tak.yaml] ─── parallel with T006–T010
 │
 ├─▶ T012 [tak-client-sim remote-tak.yaml] ─────── parallel with Phase 3
 ├─▶ T013 [demo-1drone-remote-tak.sh] ──────────── parallel with Phases 3 & 4
 ├─▶ T014 [demo-3drone-remote-tak.sh] ──────────── parallel with Phases 3 & 4
 ├─▶ T015 [cot-xml.md contract update] ─────────── parallel with Phases 3–5
 ├─▶ T016 [cot-gateway README] ─────────────────── parallel with Phases 3–5
 ├─▶ T017 [tak-client-sim README] ──────────────── parallel with Phases 3–5
 └─▶ T018 [AGENTS.md] ──────────────────────────── parallel with Phases 3–5
           │
T001–T018 all complete
           │
     ┌─────┴─────┐
     ▼           ▼
   T019        T020
 [pytest]    [ruff+black]
```

### Within US-015-01 (Critical Path)

| Step | Task | Blocker |
|------|------|---------|
| 1 | T001 + T004 (parallel) | T000 |
| 2 | T002 | T001 |
| 3 | T003 | T002 |
| 4 | T005 | T004 |
| 5 | Confirm T001–T005 all FAIL | T003 + T005 |
| 6 | T006 + T007 (parallel) | T001–T005 confirmed red |
| 7 | T008 | T007 |
| 8 | T009 | T006 + T008 |
| 9 | T010 | T006 |
| 10 | T011 | independent (can be done any time after T000) |

### Parallel Opportunities

| Group | Tasks | Condition |
|-------|-------|-----------|
| Test file creation | T001–T003 ‖ T004–T005 | Different files; both start after T000 |
| Core implementation | T006 ‖ T007 | Different files (`config.py` vs `generator.py`) |
| Config + CLI | T010 ‖ T011 | Different files (`cli.py` vs `remote-tak.yaml`) |
| New configs | T011 ‖ T012 ‖ T013 ‖ T014 | Four different new files |
| Documentation | T015 ‖ T016 ‖ T017 ‖ T018 | Four different files |
| Verification | T019 ‖ T020 | Independent commands |

---

## Parallel Execution Examples

### Phase 2: Write Failing Tests Concurrently

```bash
# Two files can be created simultaneously (different file targets):

# Task A: generator tests
vim services/cot-gateway/tests/unit/test_generator_xml_decl.py
# → T001 (xml_declaration=False tests), T002 (xml_declaration=True tests), T003 (uid Droid tests)

# Task B: config tests
vim services/cot-gateway/tests/unit/test_config_xml_decl.py
# → T004 (xml_declaration field tests), T005 (ca_bundle + CLI override tests)

# Confirm both are red:
cd services/cot-gateway
python3 -m pytest tests/unit/test_generator_xml_decl.py tests/unit/test_config_xml_decl.py -v
# Expected: ALL new tests FAIL
```

### Phase 3: Core Source Edits Concurrently

```bash
# T006 (config.py) and T007 (generator.py) touch different files:
# Task A (T006): add ca_bundle + xml_declaration to config.py
# Task B (T007): add <uid Droid> SubElement to generator.py
# Then sequentially: T008 → T009 → T010 (each depends on prior)
```

### Phases 4–6: New Files All in Parallel

```bash
# All four tasks target separate files:
# T011: services/cot-gateway/config/remote-tak.yaml
# T012: services/tak-client-sim/config/remote-tak.yaml
# T013: scripts/demo-1drone-remote-tak.sh
# T014: scripts/demo-3drone-remote-tak.sh
# T015: specs/005-cot-gateway/contracts/cot-xml.md
# T016: services/cot-gateway/README.md
# T017: services/tak-client-sim/README.md
# T018: AGENTS.md
# → All 8 tasks (T011–T018) can run concurrently
```

---

## Implementation Strategy

### MVP First (US-015-01 Only — Phases 1–3)

1. Complete Phase 1 (T000) — verify 279 existing tests are green
2. Complete Phase 2 (T001–T005) — write failing tests; confirm all red
3. Complete Phase 3 (T006–T011) — implement US-015-01; confirm all green + no regressions
4. **STOP and VALIDATE**: `python3 -m pytest -q` → 180+ passed; CoT XML contains `<uid Droid>`;
   `xml_declaration=True` prefix works; `--tak-host`/`--tak-port` override confirmed
5. Demo / deploy MVP if ready

### Incremental Delivery

| Step | Completes | Delivers |
|------|-----------|---------|
| Phases 1 + 2 + 3 | T000–T011 | US-015-01: Real TAK connectivity + CoT XML compliance |
| Phase 4 | T012 | US-015-02: TAK client sim remote config |
| Phase 5 | T013–T014 | US-015-03: Remote TAK demo scripts |
| Phase 6 | T015–T018 | US-015-04: Documentation clarity |
| Final Phase | T019–T020 | Verified: all 279+ tests pass, lint clean → merge-ready |

---

## Task Summary

| Phase | Tasks | Count | Story | Parallel Groups |
|-------|-------|-------|-------|-----------------|
| Setup | T000 | 1 | — | — |
| Failing Tests | T001–T005 | 5 | US1 | T001–T003 ‖ T004–T005 |
| US-015-01 Impl | T006–T011 | 6 | US1 | T006 ‖ T007; T011 independent |
| US-015-02 | T012 | 1 | US2 | Parallel with Phase 3 |
| US-015-03 | T013–T014 | 2 | US3 | T013 ‖ T014 |
| US-015-04 Docs | T015–T018 | 4 | US1/US2/US4 | All 4 parallel |
| Polish | T019–T020 | 2 | — | T019 ‖ T020 |
| **Total** | **T000–T020** | **21** | **4 stories** | **5 parallel groups** |

**Files changed by this feature** (13 source + config, 2 new test, 4 new config/script, 4 doc):

| File | Task | Change type |
|------|------|-------------|
| `services/cot-gateway/tests/unit/test_generator_xml_decl.py` | T001–T003 | NEW |
| `services/cot-gateway/tests/unit/test_config_xml_decl.py` | T004–T005 | NEW |
| `services/cot-gateway/src/cot_gateway/config.py` | T006 | MODIFY |
| `services/cot-gateway/src/cot_gateway/cot/generator.py` | T007, T008 | MODIFY |
| `services/cot-gateway/src/cot_gateway/loop.py` | T009 | MODIFY |
| `services/cot-gateway/src/cot_gateway/cli.py` | T010 | MODIFY |
| `services/cot-gateway/config/remote-tak.yaml` | T011 | NEW |
| `services/tak-client-sim/config/remote-tak.yaml` | T012 | NEW |
| `scripts/demo-1drone-remote-tak.sh` | T013 | NEW |
| `scripts/demo-3drone-remote-tak.sh` | T014 | NEW |
| `specs/005-cot-gateway/contracts/cot-xml.md` | T015 | MODIFY (additive) |
| `services/cot-gateway/README.md` | T016 | MODIFY |
| `services/tak-client-sim/README.md` | T017 | MODIFY |
| `AGENTS.md` | T018 | MODIFY |

**Suggested MVP scope**: Phases 1–3 (T000–T011) delivers US-015-01 — the primary business goal
of real TAK server connectivity and CoT XML standard compliance.

---

## Constraints Checklist

- [x] **G1**: Tests written and confirmed FAIL before implementation (Phase 2 → Phase 3 gate)
- [x] **G2**: No breaking wire-contract changes — `<uid Droid>` is additive; `xml_declaration=False` default preserves byte-identical output
- [x] **G3**: No new log calls added in implementation; existing structlog patterns unchanged
- [x] **G4**: No new async coroutine paths; existing observability unchanged
- [x] **G5**: New test files go to `tests/unit/`; new config files mirror existing `demo.yaml` pattern
- [x] **G6**: No new persistence — all state in-memory
- [x] **G7**: `xml.etree.ElementTree` (stdlib) only; no new package dependencies
- [x] **Pydantic `extra="forbid"`**: New fields declared as proper model fields with defaults
- [x] **Frozen models**: CLI overrides use `model_copy(update=…)`, never direct mutation
- [x] **`tak_relay.py` unmodified**: FR-015-016 respected; local relay path untouched
- [x] **13-file change scope**: All changes confined to the 14 files listed in the table above
