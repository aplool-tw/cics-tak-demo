# Tasks: SP/HP CoT Broadcasting

**Feature**: `014-sp-hp-cot`  
**Branch**: `feature/014-sp-hp-cot`  
**Input**: `specs/014-sp-hp-cot/plan.md` · `specs/014-sp-hp-cot/spec.md` · `specs/014-sp-hp-cot/data-model.md`  
**Approach**: TDD — failing tests written first, confirmed failing, then implemented; parallelisable groups marked `[P]`

---

## Format

```
- [ ] T### [P?] [StoryLabel?]  Description — file/path
```

- **`[P]`** task touches a distinct file set; can run concurrently with other `[P]` tasks
- **`[US1]`–`[US3]`** user-story scope (matches spec.md priorities)
- **No story label** on setup, foundational, or cross-cutting tasks

---

## Phase 1: Setup

> **No new service, virtual-environment, or dependency installation required.** Feature 014
> adds one new module and extends existing files inside the already-bootstrapped
> `cot-gateway` service. `pydantic v2`, `structlog`, `pytest`, and `pytest-asyncio` are
> all present.

**Prerequisite command** (run once before starting any task):

```bash
cd services/cot-gateway && python -m pytest --tb=short -q   # baseline: all existing tests pass
```

- [ ] T001  Confirm baseline: run `python -m pytest --tb=short -q` in `services/cot-gateway` and record the passing test count as the regression floor — `services/cot-gateway/`

---

## Phase 2: Foundational — `BroadcastConfig` (blocking prerequisite for all user stories)

> **Purpose**: The Pydantic model and its wire-up into `GatewayConfig` must exist before any
> XML generator or broadcaster can be implemented.  Both test tasks (T002, T003) can be
> written in parallel; neither depends on the implementation task (T004).
>
> **⚠ CRITICAL**: No US1/US2/US3 implementation task may begin until T004 is green.

### Write tests first (confirm FAIL before T004)

- [ ] T002 [P]  Write unit tests for `BroadcastConfig` model validation (plan test IDs C01–C06): default construction (`enabled=False`, `interval_s=30.0`, default lat/lon/alt values); `enabled=True` accepted; `sp_rings_m` entry ≤ 0 raises `ValidationError`; `sp_rings_m` negative entry raises `ValidationError`; `interval_s=0` raises `ValidationError`; extra field raises `ValidationError` (`extra="forbid"`) — `services/cot-gateway/tests/unit/test_broadcast_config.py`
- [ ] T003 [P]  Write unit tests for `load_config()` YAML integration (plan test IDs C07–C10): config file without `broadcast:` key loads with `cfg.broadcast.enabled is False`; config file with full `broadcast:` section parses all fields correctly; config file with invalid ring radius (`sp_rings_m: [-1.0]`) raises `ValidationError` at load time; `sp_rings_m: []` (empty list) is valid — `services/cot-gateway/tests/unit/test_broadcast_config.py`

### Implement (after T002–T003 confirmed failing)

- [ ] T004  Implement `BroadcastConfig` Pydantic model: `model_config = ConfigDict(extra="forbid")`, all fields with defaults per data-model.md, `@model_validator(mode="after")` iterating `sp_rings_m` for `r <= 0`; add `broadcast: BroadcastConfig = Field(default_factory=BroadcastConfig)` to `GatewayConfig` (not `Optional`) — `services/cot-gateway/src/cot_gateway/config.py`

**Checkpoint — Foundational**: `pytest tests/unit/test_broadcast_config.py` all green; existing `test_config_fail_fast.py` still passes with no regressions.

---

## Phase 3: US1 — SP Point Marker & Defense Ring Overlays (Priority: P1) 🎯 MVP

> **Goal**: TAK clients see the SP point marker and all configured defense rings within
> `2 × broadcast_interval_s` seconds of connecting.
>
> **Independent Test**: With `broadcast.enabled: true` and default SP coordinates, connect
> a TAK client and confirm the SP marker (`uid=CICS-014-SP`) and three ring overlays
> (`CICS-014-SP-RING-1000`, `-2000`, `-3000`) appear on the map within two intervals.
>
> **Dependencies**: T004 (BroadcastConfig) must be complete.

### Write tests first (confirm FAIL before T008)

- [ ] T005 [P] [US1]  Write unit tests for `generate_sp_cot()` XML attributes (plan test IDs X01–X05): UID is `"CICS-014-SP"`; type is `"a-f-G-U-C"`; callsign equals `cfg.sp_name`; stale equals `now + 2 × interval_s` (millisecond precision); `<point>` lat/lon/hae matches `cfg.sp_lat`, `cfg.sp_lon`, `cfg.sp_alt_m` — `services/cot-gateway/tests/unit/test_site_broadcaster.py`
- [ ] T006 [P] [US1]  Write unit tests for `generate_ring_cot()` XML attributes (plan test IDs X09–X14): UID is `"CICS-014-SP-RING-1000"` for `radius_m=1000.0`; type is `"u-d-c"`; `<ellipse minor="1000.0" major="1000.0" angle="0"/>` present; `radius_m=2500.5` → UID `"CICS-014-SP-RING-2500"` and ellipse semi-axes `"2500.5"`; `<point>` is at SP coordinates (not HP); stale follows `now + 2 × interval_s` — `services/cot-gateway/tests/unit/test_site_broadcaster.py`
- [ ] T007 [P] [US1]  Write test X15 (valid XML): assert `ET.fromstring(generate_sp_cot(cfg, NOW))` and `ET.fromstring(generate_ring_cot(cfg, 1000.0, NOW))` parse without error — `services/cot-gateway/tests/unit/test_site_broadcaster.py`

### Implement (after T005–T007 confirmed failing)

- [ ] T008 [US1]  Create `site_broadcaster.py` with module-level constants `SP_UID = "CICS-014-SP"`, `HP_UID = "CICS-014-HP"`, `_ring_uid(radius_m)` function; local `_iso_ms(dt)` helper (3-line copy, no coupling to `generator.py`); implement `generate_sp_cot(cfg, now) -> str` and `generate_ring_cot(cfg, radius_m, now) -> str` per data-model.md §3 XML examples; use `stale = now + timedelta(seconds=2 * cfg.interval_s)`; use `stdlib ET` only — `services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py`

**Checkpoint — US1**: T005–T007 tests all green; `generate_cot()` in `cot/generator.py` is NOT modified.

---

## Phase 4: US2 — HP Point Marker (Priority: P2)

> **Goal**: TAK clients see the HP point marker (`uid=CICS-014-HP`) with correct callsign
> and coordinates within `2 × broadcast_interval_s` seconds.
>
> **Independent Test**: With `broadcast.enabled: true` and HP coordinates set, verify
> `uid=CICS-014-HP` appears on a connected TAK client within two broadcast intervals.
>
> **Dependencies**: T008 (site_broadcaster.py module scaffolding) must be complete.

### Write tests first (confirm FAIL before T010)

- [ ] T009 [P] [US2]  Write unit tests for `generate_hp_cot()` XML attributes (plan test IDs X06–X08b): UID is `"CICS-014-HP"` (distinct from `"CICS-014-SP"`); type is `"a-f-G-U-C"` and callsign equals `cfg.hp_name`; `<point>` lat/lon/hae matches `cfg.hp_lat`, `cfg.hp_lon`, `cfg.hp_alt_m`; **stale = now + 2×interval_s** (mirrors FR-014-012, same logic as SP and ring stale tests); add `generate_hp_cot` to the valid-XML check in test X15 — `services/cot-gateway/tests/unit/test_site_broadcaster.py`

### Implement (after T009 confirmed failing)

- [ ] T010 [US2]  Add `generate_hp_cot(cfg, now) -> str` to `site_broadcaster.py`: same structure as SP but using `HP_UID`, `cfg.hp_lat`, `cfg.hp_lon`, `cfg.hp_alt_m`, `cfg.hp_name`, and `remarks="Site: HP"`; stale = `now + timedelta(seconds=2 * cfg.interval_s)` — `services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py`

**Checkpoint — US2**: T009 tests green; X15 valid-XML check now covers all three generators.

---

## Phase 5: US1 + US2 — `SitesBroadcaster` Loop & `GatewayMain` Wiring

> **Goal**: `SitesBroadcaster` enqueues the correct batch of messages immediately on start,
> repeats every `interval_s`, and stops cleanly when `stop_event` is set.
> `GatewayMain.run()` conditionally launches the broadcaster as an asyncio task.
>
> **Dependencies**: T008 (generate_sp_cot, generate_ring_cot) and T010 (generate_hp_cot)
> must be complete; T002–T004 must be green.

### Write tests first (confirm FAIL before T013–T014)

- [ ] T011 [P] [US1] [US2]  Write broadcaster enqueue / loop tests (plan test IDs B01–B03): with `sp_rings_m=[]` — exactly **2** messages enqueued (SP + HP) after one `broadcast_once`; with `sp_rings_m=[1000, 2000, 3000]` — exactly **5** messages enqueued; first emission happens synchronously before any `await` (set stop immediately after construction, call `await run()`, assert 5 messages in queue) — `services/cot-gateway/tests/unit/test_site_broadcaster.py`
- [ ] T012 [P] [US1]  Write broadcaster stop and wiring tests (plan test IDs B04–B05): `stop_event` set immediately after first cycle → only one batch enqueued, `run()` returns without error; `GatewayMain` constructed with `config.broadcast.enabled=False` → `sp_hp_broadcast_loop` coroutine NOT present in the coroutines list passed to the task supervisor — `services/cot-gateway/tests/unit/test_site_broadcaster.py`

### Implement (after T011–T012 confirmed failing)

- [ ] T013 [US1] [US2]  Add `SitesBroadcaster` class to `site_broadcaster.py`: `__init__(self, cfg, cot_queue, stop_event)` storing `_cfg`, `_queue`, `_stop`, `_log = get_logger("cot_gateway.broadcast")`; `_broadcast_once(now)` calling `put_nowait` for SP + HP + each ring in `cfg.sp_rings_m`, logging `QueueFull` at WARNING if raised; `async run()` emitting immediately, then `asyncio.wait_for(stop.wait(), timeout=interval_s)` loop, logging `broadcast_cycle` with `sp_uid`, `hp_uid`, `ring_count`, `interval_s` per FR-014-024 — `services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py`
- [ ] T014 [US1]  Add `sp_hp_broadcast_loop(self) -> None` async method to `GatewayMain` in `loop.py`: instantiates `SitesBroadcaster(cfg=self.config.broadcast, cot_queue=self.cot_queue, stop_event=self._stop)` then `await broadcaster.run()`; wire it in `run()` with `if self.config.broadcast.enabled: coroutines.append(self.sp_hp_broadcast_loop())` after the existing `sentrycs` conditional — `services/cot-gateway/src/cot_gateway/loop.py`

**Checkpoint — Loop**: T011–T012 tests green; `pytest services/cot-gateway` passes with no regressions; existing coroutine supervisor handles broadcaster exceptions without killing the gateway (G6 crash isolation).

---

## Phase 6: US3 — Operator Reconfigures via YAML (Priority: P3)

> **Goal**: All broadcast parameters (SP/HP coordinates, ring radii, interval, callsigns)
> are externally configurable in `gateway.yaml` without code changes; invalid values cause
> a clean startup failure with a `ValidationError`.
>
> **Independent Test**: Edit `demo.yaml`, restart gateway, verify updated positions and ring
> count appear on TAK client within one broadcast interval.
>
> **Dependencies**: T004 (BroadcastConfig schema) and T014 (broadcaster wiring) must be complete.

- [ ] T015 [US3]  Add `broadcast:` section to `demo.yaml` with `enabled: true`, `interval_s: 30.0`, all SP/HP coordinate fields (default values from data-model.md), `sp_rings_m: [1000.0, 2000.0, 3000.0]`; add a comment header documenting that omitting the `broadcast:` key or setting `enabled: false` disables the broadcaster with zero regression — `services/cot-gateway/config/demo.yaml`

**Checkpoint — US3**: `python -m cot_gateway --config config/demo.yaml` starts without errors; structured log shows `broadcast_cycle` events at the configured interval.

---

## Final Phase: Polish & Regression

- [ ] T016  Run full regression and quality gates: `cd services/cot-gateway && ruff check src/ tests/ && black --check src/ tests/ && python -m pytest -q`; confirm total passing test count equals baseline (T001) plus all new Feature 014 tests; confirm `cot/generator.py` is unmodified (G7) — `services/cot-gateway/`

---

## Dependency Graph

```
T001 (baseline)

T002─┐
T003─┘──T004                        (Foundational: BroadcastConfig)

         T004──T005─┐
                T006─┤──T008        (US1: generate_sp_cot + generate_ring_cot)
                T007─┘

         T008──T009──T010           (US2: generate_hp_cot)

T008──T010──T011─┐
             T012─┘──T013──T014     (US1+US2: SitesBroadcaster + loop wiring)

                   T004──T014──T015  (US3: demo.yaml activation)

                             T014──T016  (Polish: regression)
```

**User-story completion order** (suggested MVP scope):

| Increment | Stories | Tasks | Can ship independently? |
|-----------|---------|-------|------------------------|
| MVP       | Foundational + US1 | T001–T008 | ✅ yes — SP marker + rings broadcasting |
| Core      | US2 | T009–T010 | ✅ yes — adds HP marker to existing broadcaster |
| Loop      | US1 + US2 | T011–T014 | ✅ yes — live periodic broadcasting via asyncio task |
| Config    | US3 | T015 | ✅ yes — demo config activation |
| Polish    | —   | T016 | closes the feature |

---

## Parallel Execution Examples

### Test-writing phase — all `[P]` test tasks written simultaneously

```
Developer A: T002 (config model tests C01–C06)
Developer B: T003 (load_config YAML tests C07–C10)
```

```
Developer A: T005 (SP generator tests X01–X05)
Developer B: T006 (ring generator tests X09–X14)
Developer C: T007 (valid-XML test X15)
```

```
Developer A: T009 (HP generator tests X06–X08)
```

```
Developer A: T011 (broadcaster enqueue tests B01–B03)
Developer B: T012 (broadcaster stop + GatewayMain tests B04–B05)
```

### Implementation phase — sequential after tests confirmed failing

```
T004 → (T008 | T009 → T010) → T013 → T014 → T015
```

---

## Implementation Strategy

**Incremental delivery (G1 TDD enforced at every step)**:

1. **Foundation first**: `BroadcastConfig` (T002–T004) — unlocks everything; zero runtime effect until `enabled: true`.
2. **SP + rings** (T005–T008) — pure functions, independently testable; delivers US1 XML layer.
3. **HP marker** (T009–T010) — one additional generator function; delivers US2 XML layer.
4. **Live broadcasting** (T011–T014) — wires the broadcaster into `GatewayMain`; delivers the actual periodic emission.
5. **Config activation** (T015) — flips `enabled: true` in `demo.yaml`; makes the feature visible end-to-end.
6. **Polish** (T016) — ruff + black + full regression gate.

**Constitution gates** (enforced throughout):

| Gate | Enforcement point |
|------|-------------------|
| G1 TDD | T002–T003 FAIL before T004; T005–T007 FAIL before T008; T009 FAIL before T010; T011–T012 FAIL before T013–T014 |
| G2 `extra="forbid"` | T004 — `BroadcastConfig` must include `model_config = ConfigDict(extra="forbid")` |
| G3 structlog JSON | T013 — `get_logger("cot_gateway.broadcast")`, no `print()`, structured log fields only |
| G4 stdlib ET only | T008, T010 — `from xml.etree import ElementTree as ET`; no lxml |
| G5 Additive config | T004 — `Field(default_factory=BroadcastConfig)`, not `Optional`; missing key → disabled |
| G6 Crash isolation | T014 — broadcaster supervised by existing `GatewayMain.run()` error handler |
| G7 No `generator.py` mutation | T016 — `git diff HEAD -- services/cot-gateway/src/cot_gateway/cot/generator.py` must be empty |

**Quality gate** (run after each phase):

```bash
cd services/cot-gateway && ruff check src/ tests/ && black --check src/ tests/ && python -m pytest -q
```
