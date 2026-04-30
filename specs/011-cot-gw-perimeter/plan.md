# Implementation Plan: CoT Gateway Perimeter Guard

**Branch**: `feature/011-cot-gw-perimeter` | **Date**: 2026-05-11 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/011-cot-gw-perimeter/spec.md`

## Summary

Feature 011 resolves five root causes (RC1–RC5) that degrade the Taiwan anti-drone TAK PoC demo experience. The primary change is architectural: the perimeter guard responsibility moves from `sentrycs-sim` to `cot-gateway`, which already acts as the authoritative fusion authority for all sensor tracks. A new `PerimeterGuard` module in `cot_gateway/perimeter/` evaluates every processed `UnifiedTrack` against a configurable SP exclusion radius and dispatches a one-shot `POST /command/takeover` to UDS using the existing frozen wire contract. Supporting changes fix browser cache-control headers, eliminate the sensor-marker flicker from premature `clearLayers()` calls, reduce the Sentrycs detection radius to a realistic 2 000 m, and surface a `takeover_issued` visual state on the tactical map.

## Technical Context

**Language/Version**: Python 3.11+ (tested on 3.12); JavaScript (ES2020, inline in server.py HTML template)  
**Primary Dependencies**: `aiohttp` (already in cot-gateway and sentrycs-sim), `pydantic v2`, `structlog`, `PyYAML` — no new packages  
**Storage**: In-memory only (G6 No Persistence); `TrackStore` extended with `_takeover_set: set[str]`  
**Testing**: `pytest` + `pytest-asyncio` + `freezegun` (existing); new unit + integration tests under `services/cot-gateway/tests/`  
**Target Platform**: Linux asyncio service; `aiohttp.web` for HTTP endpoints  
**Project Type**: Web service / library module addition  
**Performance Goals**: PerimeterGuard check must complete within one `process_loop` tick (≤ 250 ms per SC-011-003); single `await` HTTP call per breach event only  
**Constraints**: `asyncio.Lock` — no I/O inside lock body (G coding standard); one-shot idempotency keyed on entity key; 409 from UDS treated as success  
**Scale/Scope**: Single-drone demo scenario; multi-drone supported by design (independent per-entity-key latch)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

> **Constitution file** (`/.specify/memory/constitution.md`) is currently a placeholder with unfilled template sections. In its absence, the project self-governs via principles G1–G7 documented in `AGENTS.md §3.1`.

| ID | Principle | Status | Notes |
|----|-----------|--------|-------|
| G1 | Test-First | ✅ PASS | All new paths (PerimeterGuard, TrackStore.mark_takeover, cache headers, JS rendering) have test-first task ordering in tasks.md |
| G2 | Contract Freeze | ✅ PASS | No breaking changes to any frozen wire contract. `POST /command/takeover` body (`drone_id, target_lat, target_lon, target_alt_m`) is unchanged. TrackStore serialization gains a new `takeover_issued` field — additive only, existing consumers unaffected. |
| G3 | Structured Logging | ✅ PASS | New `perimeter_breach` event uses `logger.info("perimeter_breach", uid=…, dist_m=…, radius_m=…)` pattern |
| G4 | Observability | ✅ PASS | `perimeter_breach`, `perimeter_guard_disabled`, and `takeover_issued` events defined in FR-011-013 |
| G5 | Structural Symmetry | ✅ PASS | New `cot_gateway/perimeter/` package follows existing `cot_gateway/<module>/__init__.py + <class>.py` pattern |
| G6 | No Persistence | ✅ PASS | `_triggered` set and `_takeover_set` are in-memory; both cleared on service restart |
| G7 | Minimal Dependencies | ✅ PASS | Reuses `cot_gateway.correlate.haversine.haversine_m` (per FR-011-010); `aiohttp` already a dependency; no new packages |

**Post-design re-check**: All gates remain PASS after Phase 1 design. The `PerimeterGuardConfig` addition to `GatewayConfig` maintains `extra="forbid"` discipline. The `_check_cert_file` validator is unaffected.

## Project Structure

### Documentation (this feature)

```text
specs/011-cot-gw-perimeter/
├── plan.md              ← this file
├── research.md          ← Phase 0 output (dependency / approach confirmation)
├── quickstart.md        ← Phase 1 dev quickstart
└── tasks.md             ← Phase 2 output (TDD task list, /speckit.tasks)
```

*(No `data-model.md` — TrackStore change is minor and fully documented below.  
No `contracts/` — UDS wire contract is already frozen and unchanged.)*

### Source Code

```text
services/cot-gateway/
├── src/cot_gateway/
│   ├── perimeter/                 ← NEW package (RC3)
│   │   ├── __init__.py            ← exports PerimeterGuard
│   │   └── guard.py               ← PerimeterGuard class
│   ├── config.py                  ← ADD PerimeterGuardConfig + GatewayConfig.perimeter field
│   ├── loop.py                    ← ADD PerimeterGuard instantiation + check() call
│   └── web/
│       ├── track_store.py         ← ADD _takeover_set, mark_takeover(), takeover_issued in _serialize()
│       └── server.py              ← ADD Cache-Control headers; UPDATE droneIcon() + track panel JS
└── config/
    └── demo.yaml                  ← ADD perimeter: section (enabled, radius_m, sp_lat, sp_lon, uds_url, holding_*)

services/sentrycs-sim/
├── src/sentrycs_sim/
│   ├── config.py                  ← REMOVE defense_radius_m field
│   └── loop.py                    ← REMOVE position-based takeover block (step 4);
│                                    REPLACE with time-based DETECTED→MITIGATING transition
└── config/
    └── demo.yaml                  ← REMOVE defense_radius_m; UPDATE detection_radius_m=2000; REVISE timestamps

services/cot-gateway/tests/
├── unit/
│   ├── test_perimeter_guard.py    ← NEW (PerimeterGuard unit tests)
│   ├── test_track_store.py        ← EXTEND (mark_takeover, takeover_issued serialization)
│   └── test_config.py             ← EXTEND (PerimeterGuardConfig validation)
├── integration/
│   └── test_perimeter_integration.py  ← NEW (full loop: breach → UDS call → mark_takeover)
└── contract/                      ← no changes

services/sentrycs-sim/tests/
├── unit/
│   └── test_loop.py               ← UPDATE (remove defense_radius_m tests; add time-based MITIGATING tests)
├── integration/
│   └── test_loop_integration.py   ← UPDATE (verify no UDS calls after RC3 cleanup)
└── contract/                      ← no changes
```

**Structure Decision**: Single-module extension pattern — new `perimeter/` package inside existing `cot_gateway/` source tree, matching the established `correlate/`, `cot/`, `web/` sub-package layout. No new top-level service directories.

---

## Design Decisions

### A. PerimeterGuard — Synchronous Inline Call (not `asyncio.create_task`)

`AGENTS.md` prohibits ad-hoc `asyncio.create_task` in the processing hot path and bans I/O inside `asyncio.Lock`. `PerimeterGuard.check()` is therefore called with `await` directly inside `_emit_for_track`, after `track_store.upsert`. The UDS HTTP call is a single `aiohttp.ClientSession.post()` — already the pattern used by sentrycs-sim's `UdsClient`. Duration is bounded by `uds_timeout_s` (configurable, default 3 s), which is acceptable given the ≤ 250 ms SC goal is a soft log-latency target, not a hard tick deadline.

### B. PerimeterGuard Idempotency — Entity Key, Not CoT UID

The `_triggered: set[str]` latch inside `PerimeterGuard` is keyed on a composite entity key derived from `(radar_track_id, rf_track_id)`, matching the pattern in `cot_gateway.cot.uid.entity_keys_for()`. This prevents double-dispatch when a CoT UID source-switches from ECHOSHIELD→FUSED while the same physical drone is still inside the perimeter. The latch is **not** cleared on UDS error (retry is implicit on the next tick if `takeover_issued` is still `False` in TrackStore).

### C. `takeover_issued` Placement — TrackStore, Not PerimeterGuard

`takeover_issued` is a per-CoT-UID flag in `TrackStore`, set only after a successful UDS dispatch (HTTP 200 or 409). This allows the `/tracks` endpoint to surface it for UI rendering without coupling the web server to PerimeterGuard state. The entity-key idempotency in PerimeterGuard prevents re-dispatch even when the flag is absent on a newly-created UID after a source switch.

### D. sentrycs-sim DETECTED→MITIGATING Without UDS

After removing the position-based takeover block, `_advance_track` alone is insufficient to transition DETECTED→MITIGATING (it only handles MITIGATING→NEUTRALIZED). The replacement is a **time-based trigger** in step 4 of `run_one_tick`: iterate DETECTED tracks, compare `elapsed_s` to `scenario.mitigating_at_s`, and call `sm.transition(track, DetectionStatus.MITIGATING, reason="time_based", now=now_utc)`. The `track.takeover_sent` flag is set to `True` to prevent re-triggering. This preserves the existing state timeline without any UDS call from sentrycs-sim.

### E. Cache-Control — Module-Level Constant

A module-level dict `_NO_CACHE = {"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"}` is added to `server.py` and passed as `headers=_NO_CACHE` to `web.json_response()` in both `_tracks` and `_sites` handlers. The `_health` handler is excluded per FR-011-003.

### F. JS `clearLayers()` Fix — Move Inside Success Branch

The two `clearLayers()` calls in `refreshSites()` move from before the `if (!r.ok) return;` guard to immediately after it (inside the `try` block, before populating new markers). `refreshTracks()` already clears inside the success branch and requires no change.

### G. JS `droneIcon()` — `takeover_issued` Override

A ternary is added to `droneIcon()`:  
```js
const c = t.takeover_issued ? '#FF9800' : (lost ? '#777' : (SRC_COLOR[src]||'#888'));
```  
The `[TAKEOVER]` badge is appended to the side panel HTML string when `t.takeover_issued === true`. `SRC_COLOR` and `SRC_BORDER` tables are not modified (FR-011-027).

### H. `GatewayConfig.perimeter` — Optional None Field

`perimeter: Optional[PerimeterGuardConfig] = None` uses `Optional` (not `Field(default_factory=...)`) so that the field is absent from YAML by default, maintaining the `extra="forbid"` contract. When `perimeter` is present but `enabled: false`, `PerimeterGuard` is not instantiated. When `perimeter` is absent (`None`), the same code path is followed.

---

## TrackStore Data Model Changes

*No separate `data-model.md` is produced — changes are minor and fully specified here.*

### Current `TrackStore` (before Feature 011)

| Field | Type | Notes |
|-------|------|-------|
| `_data` | `dict[str, UnifiedTrack]` | UID → track |
| `_lock` | `asyncio.Lock` | protects `_data` |

### Extended `TrackStore` (Feature 011)

| Field | Type | Notes |
|-------|------|-------|
| `_data` | `dict[str, UnifiedTrack]` | unchanged |
| `_lock` | `asyncio.Lock` | unchanged; guards both `_data` and `_takeover_set` |
| `_takeover_set` | `set[str]` | UIDs for which a takeover has been successfully dispatched |

### New/Changed Methods

| Method | Signature | Behaviour |
|--------|-----------|-----------|
| `mark_takeover` | `async (uid: str) → None` | Acquires lock; adds `uid` to `_takeover_set` |
| `remove` | `async (uid: str) → None` | Acquires lock; pops from both `_data` and `_takeover_set` |
| `get_all` | `async () → list[dict]` | Serialized dict now includes `"takeover_issued": uid in _takeover_set` per entry |

**Note**: `_serialize` is updated to accept a `takeover_issued: bool` argument so that it remains a pure function with no store dependency (testable in isolation).

---

## PerimeterGuard API

```python
# services/cot-gateway/src/cot_gateway/perimeter/guard.py

class PerimeterGuard:
    def __init__(
        self,
        sp_lat: float,
        sp_lon: float,
        uds_url: str,
        radius_m: float,
        holding_lat: float,
        holding_lon: float,
        holding_alt_m: float,
        *,
        session: aiohttp.ClientSession,
    ) -> None: ...

    async def check(
        self,
        track: UnifiedTrack,
        uid: str,
        mark_takeover: Callable[[str], Awaitable[None]],
    ) -> None:
        """
        Called per-track after upsert. Fires when:
          - track.source in (SENTRYCS, FUSED)
          - track.detection_status in ("DETECTED", "MITIGATING")
          - haversine_m(sp_lat, sp_lon, track.lat, track.lon) < radius_m
          - entity_key NOT in _triggered

        On breach:
          1. log perimeter_breach(uid, dist_m, radius_m)
          2. add entity_key to _triggered
          3. POST {uds_url}/command/takeover
          4. On HTTP 200 or 409: await mark_takeover(uid)
          5. On other error: do NOT add to _triggered (allow retry next tick)
             [Note: entity_key already in _triggered → next tick re-evaluates but
             takes the "already triggered" early-exit path before reaching UDS call.
             For retry semantics, _triggered is NOT added until UDS confirms.]
        """
```

**Correction to user-provided design**: The `_triggered` set is populated **only after** a successful UDS dispatch (200 or 409) — not before — to allow retry on `FAILED_TRANSPORT`. This means on every tick until success, the entity key is re-evaluated and the UDS call is retried. Once success is confirmed, the entity key enters `_triggered` permanently (until service restart).

---

## Demo Config Changes

### `services/sentrycs-sim/config/demo.yaml` (RC3 + RC4)

```yaml
# Sentrycs demo config — local dev (all URLs point to 127.0.0.1)
# Drone starts 3 500 m north of SP at 35 m/s.
# t≈9s    enters EchoShield 3 200 m range → ECHOSHIELD track appears
# t≈43s   crosses 2 000 m ring → Sentrycs detects → source switches to FUSED
# t≈71s   crosses 1 000 m SP perimeter → cot-gateway PerimeterGuard fires takeover
# t=43s   Sentrycs detected_at_s (2000m / 35m/s ≈ 43s after 3500m start)
# t=71s   mitigating_at_s  ((3500-1000)/35 ≈ 71s)
# t=110s  neutralized_at_s (71 + 39s hold)

sensor_lat: 24.725806
sensor_lon: 121.033750
poll_interval_s: 0.5
detection_radius_m: 2000.0           # RC4: was 8000.0
map_sim_url: http://127.0.0.1:8090
uds_url: http://127.0.0.1:18080
api_host: 0.0.0.0
api_port: 7070
neutralized_hold_s: 30.0
mitigating_disappear_grace_s: 10.0

drones:
  - uid: TRK-E01
    model: "DJI Mavic 3"
    detected_at_s: 43
    mitigating_at_s: 71
    neutralized_at_s: 110
    operator_bearing_deg: 225
    operator_distance_m: 300
    takeover_target_lat: 24.725806
    takeover_target_lon: 121.071889
    takeover_target_alt_m: 50.0
```

*(No `defense_radius_m` key — RC3 cleanup. FR-011-016 / FR-011-019.)*

### `services/cot-gateway/config/demo.yaml` (RC3)

Add `perimeter:` section at end of file:

```yaml
perimeter:
  enabled: true
  uds_url: "http://127.0.0.1:18080"
  radius_m: 1000.0
  sp_lat: 24.725806
  sp_lon: 121.033750
  holding_lat: 24.725806
  holding_lon: 121.071889
  holding_alt_m: 50.0
  descent_speed_ms: 15.0
```

---

## Implementation Sequence (TDD Order)

The full TDD task breakdown is produced by `/speckit.tasks`. The high-level sequence below captures inter-task dependencies for planning purposes.

### Group 1 — Config & Schema (no runtime side-effects)
1. `PerimeterGuardConfig` Pydantic model in `config.py` + unit tests
2. `GatewayConfig.perimeter` optional field + `_check_cert_file` regression
3. `SentrycsConfig.defense_radius_m` removal + config tests updated

### Group 2 — TrackStore extension (pure Python, no aiohttp)
4. `mark_takeover` + `_takeover_set` + `_serialize(takeover_issued)` unit tests  
5. Implementation

### Group 3 — PerimeterGuard module (needs aiohttp mock)
6. Unit tests: breach detected, already triggered (no-op), source filter, 409 = success, transport error = no latch  
7. Implementation: `perimeter/guard.py`

### Group 4 — GatewayMain wiring
8. Integration test: `process_loop` → `PerimeterGuard.check()` called on breach track  
9. Implementation: `loop.py` changes

### Group 5 — Web / HTTP
10. `Cache-Control` header unit test + server.py implementation  
11. JS `clearLayers()` fix (visual — verified by manual test + spec review)  
12. JS `droneIcon()` `takeover_issued` rendering + `[TAKEOVER]` badge

### Group 6 — sentrycs-sim cleanup
13. Unit tests: time-based MITIGATING transition; no UDS calls after removal  
14. `loop.py` step 4 replacement + `config.py` field removal  
15. `demo.yaml` timestamp revision + `detection_radius_m: 2000.0`

### Group 7 — Demo config activation
16. `cot-gateway/config/demo.yaml` perimeter section  
17. End-to-end smoke: `scripts/dev-launcher.sh`, observe `perimeter_breach` log, orange icon

## Complexity Tracking

No constitution violations — all gates PASS.
