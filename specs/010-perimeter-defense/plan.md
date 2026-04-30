# Implementation Plan: Feature 010 — Perimeter Defense

**Feature ID**: `010`  
**Branch**: `010-perimeter-defense`  
**Spec**: `specs/010-perimeter-defense/spec.md`  
**Research**: `specs/010-perimeter-defense/research.md`  
**Created**: 2026-04-30  
**Status**: Ready for implementation

---

## Technical Context

| Item | Detail |
|---|---|
| Services touched | `cot-gateway`, `sentrycs-sim`, `uds` |
| Key files | `server.py`, `loop.py` (×2), `config.py`, `track.py`, `demo.yaml` (×2), `demo_single_drone.yaml` |
| Test suites | 94 + 110 + 83 + 74 + 107 = 468 pytest tests across all services |
| Linter | ruff + black |
| No new deps | `haversine_m` from existing `sentrycs_sim.geo.wgs84` |
| No wire contract changes | `defense_radius_m` is internal to sentrycs-sim; no REST API change |
| No data model changes | `UnifiedTrack`, `TrackSource`, CoT format all unchanged |

### NEEDS CLARIFICATION → all resolved

See `research.md` — all R1–R10 items resolved. No blockers.

---

## Constitution Check

The project constitution file is present but contains placeholder template text only (no enacted principles). Governance passes by default; the following self-imposed gates apply from the spec and constraints section:

| Gate | Rule | Status |
|---|---|---|
| G2 | No wire contract changes | ✅ No REST API additions; `defense_radius_m` is YAML-only internal config |
| G7 | No new Python dependencies | ✅ `haversine_m` reused from `sentrycs_sim.geo.wgs84` |
| Tests | All 468 pytest tests must pass | Enforced in §Verification |
| Lint | ruff + black clean | Enforced in §Verification |

---

## Phase 0 — Research ✅

**Artifact**: `specs/010-perimeter-defense/research.md` (complete)

All NEEDS CLARIFICATION items resolved:
- Ring colors validated against all existing palette entries (R2)
- Tooltip bind pattern confirmed via Leaflet API (R3)
- Speed displacement math verified: 35 m/s × 3 s = 105 m ≥ 80 m (R4)
- TrackSource enum verified as already correct (R5)
- haversine_m confirmed available in geo.wgs84 (R7)
- SentrycsConfig extra="forbid" + frozen=True compatibility confirmed (R8)
- Source-switch log gap identified and fix designed (R9)

---

## Phase 1 — Implementation Plan

### Item 1 — Fix Map Legend & Ring Colors

**File**: `services/cot-gateway/src/cot_gateway/web/server.py`

#### 1a. Update RING_COLORS constant

**Location**: line 209 inside `refreshSites()` JS function.

```js
// BEFORE
const RING_COLORS = ['#00e676','#ffca28','#ef5350'];

// AFTER
const RING_COLORS = ['#80deea','#ffcc80','#ef9a9a'];
```

#### 1b. Add RING_LABELS constant and tooltip bindings

Replace the ring draw line (currently line 217):

```js
// BEFORE
(s.ranges_m||[]).forEach((rm,i)=>{
  circle(s.lat,s.lon,rm,RING_COLORS[i]||'#ef5350','6 5').addTo(siteLayer);
});

// AFTER
const RING_LABELS = ['1km defense ring','2km defense ring','3km defense ring'];
(s.ranges_m||[]).forEach((rm,i)=>{
  circle(s.lat,s.lon,rm,RING_COLORS[i]||'#ef9a9a','6 5')
    .bindTooltip(RING_LABELS[i]||'defense ring',{className:'leaflet-tooltip-gw'})
    .addTo(siteLayer);
});
```

#### 1c. Add three legend entries in HTML panel

Insert after the existing `<div class="leg-row">..RF range..</div>` entry (currently line 94), before the `<div class="leg-sep">`:

```html
<div class="leg-row"><span class="leg-line" style="border-color:#80deea"></span>1km defense ring</div>
<div class="leg-row"><span class="leg-line" style="border-color:#ffcc80"></span>2km defense ring</div>
<div class="leg-row"><span class="leg-line" style="border-color:#ef9a9a"></span>3km defense ring</div>
```

**Reuses**: `.leg-row` and `.leg-line` CSS classes — no new CSS (FR-010-004).

#### Acceptance checks for Item 1

- `RING_COLORS` contains no `#00e676`, `#ffca28`, or `#ef5350` after the change
- HTML template contains exactly three legend rows for "1km/2km/3km defense ring"
- Each ring's `forEach` loop calls `.bindTooltip()` before `.addTo()`
- ruff/black: no Python change needed (JS is embedded string); no lint impact

---

### Item 2 — Increase Drone Speed

#### 2a. UDS scenario speed

**File**: `services/uds/scenarios/demo_single_drone.yaml`

```yaml
# BEFORE
      description: "單架無人機から正北 3.5km 處向戰略要點…"
      speed_ms: 20.0

# AFTER — change speed only; description update below
      speed_ms: 35.0
```

Update the `description` field to document the new speed:
```yaml
      description: "單架無人機從正北 3.5km 處向戰略要點 SP(24.725806N,121.033750E) 逼近（示範用，35m/s 快速啟動）"
```

#### 2b. Sentrycs demo config comment header

**File**: `services/sentrycs-sim/config/demo.yaml`

Replace the current comment block at the top:

```yaml
# BEFORE
# Sentrycs demo config — local dev (all URLs point to 127.0.0.1)
# Drone starts 3.5km from SP at 20m/s (demo_single_drone.yaml).
# t=15s  enters EchoShield 3.2km range
# t=75s  enters 2km range → Sentrycs DETECTED
# t=125s enters 1km range → Sentrycs MITIGATING (triggers takeover to HP)
# t=165s NEUTRALIZED

# AFTER
# Sentrycs demo config — local dev (all URLs point to 127.0.0.1)
# Drone starts 3.5km from SP at 35m/s (demo_single_drone.yaml).
# t≈9s   enters EchoShield 3.2km range
# t≈43s  drone at 2km from sensor
# t≈71s  drone crosses 1km defense perimeter (defense_radius_m: 1000.0)
# t=75s  detected_at_s threshold → Sentrycs DETECTED (drone at ≈875m, already inside perimeter)
# t=75s+ first DETECTED tick → takeover fires immediately (position-based)
# t=165s NEUTRALIZED
```

> The old t=15s was computed at 20 m/s. At 35 m/s: (3500−3200)/35 ≈ 9 s.

#### Acceptance checks for Item 2

- `demo_single_drone.yaml` has `speed_ms: 35.0`
- `35 × 3 = 105 ≥ 80 m` — displacement criterion met
- Comment header in `sentrycs-sim/config/demo.yaml` shows `35m/s` and physics-correct timestamps

---

### Item 3 — Verify/Fix Track Source Serialization

**File**: `services/cot-gateway/src/cot_gateway/models/track.py`

**Finding** (R5): `TrackSource` enum values already match JS `SRC_COLOR` keys exactly. No code change required.

**Action**: Add a one-line comment above the enum confirming the wire contract:

```python
# String values are the canonical source identifiers used by the JS SRC_COLOR
# map in web/server.py. Do NOT rename without updating both sides.
class TrackSource(str, Enum):
    ECHOSHIELD = "ECHOSHIELD"
    SENTRYCS = "SENTRYCS"
    FUSED = "FUSED"
```

#### 3b. Enhance source_switch log event (FR-010-009)

**File**: `services/cot-gateway/src/cot_gateway/loop.py`

In `_emit_for_track`, the existing `source_switch` event is missing `entity_key` (R9). Update:

```python
# BEFORE
self._log.info(
    "source_switch", old_uid=old_uid, new_uid=new_uid, track_id=track.track_id
)

# AFTER
_ekeys = entity_keys_for(track)
self._log.info(
    "source_switch",
    old_uid=old_uid,
    new_uid=new_uid,
    track_id=track.track_id,
    entity_key=_ekeys[0] if _ekeys else None,
)
```

`entity_keys_for` is already imported at the top of `loop.py`.

#### Acceptance checks for Item 3

- `TrackSource.ECHOSHIELD.value == "ECHOSHIELD"` — confirmed by comment, verified in tests
- `source_switch` log event fields: `old_uid`, `new_uid`, `track_id`, `entity_key`

---

### Item 4 — Defense Perimeter Takeover

#### 4a. Add defense_radius_m to SentrycsConfig

**File**: `services/sentrycs-sim/src/sentrycs_sim/config.py`

Add the new optional field to `SentrycsConfig`, after `detection_radius_m`:

```python
# BEFORE
    detection_radius_m: float = Field(default=8000.0, gt=0.0)

# AFTER
    detection_radius_m: float = Field(default=8000.0, gt=0.0)
    defense_radius_m: Optional[float] = Field(default=None)
```

`Optional` is already available via `from typing import Optional` — check current imports; if not present, add it. (Pydantic `Optional[float]` maps to `float | None`; alternatively use `float | None` directly since Python 3.10+ union syntax is already used elsewhere in the file.)

> The field has no `gt=0.0` constraint — per FR-010-010: "no minimum enforced at schema level".

#### 4b. Modify run_one_tick() step 4

**File**: `services/sentrycs-sim/src/sentrycs_sim/loop.py`

**Import addition** (top of file, after existing geo imports):
```python
from .geo.wgs84 import haversine_m
```

**Replace step 4 block** (currently lines 146–156):

```python
# BEFORE (step 4)
        # 4. schedule takeovers for tracks at mitigating_at_s.
        for track in list(self.registry):
            if track.status is not DetectionStatus.DETECTED:
                continue
            if track.takeover_sent:
                continue
            scenario = self.config.drone_by_uid(track.uid)
            if scenario is None:
                continue
            if elapsed < float(scenario.mitigating_at_s):
                continue
            self._ensure_takeover_task(track, now_utc)

# AFTER (step 4 with position-based branch)
        # 4. schedule takeovers — position-based when defense_radius_m is set,
        #    otherwise fall back to the scenario mitigating_at_s time threshold.
        for track in list(self.registry):
            if track.status not in (DetectionStatus.DETECTED, DetectionStatus.MITIGATING):
                continue
            if track.takeover_sent:
                continue
            scenario = self.config.drone_by_uid(track.uid)
            if scenario is None:
                continue
            if self.config.defense_radius_m is not None:
                # Position-based trigger: fire when drone crosses the defense perimeter.
                dist = haversine_m(
                    self.config.sensor_lat,
                    self.config.sensor_lon,
                    track.lat,
                    track.lon,
                )
                if dist < self.config.defense_radius_m:
                    self._ensure_takeover_task(track, now_utc)
            else:
                # Time-based fallback (pre-010 behavior, unchanged).
                if elapsed < float(scenario.mitigating_at_s):
                    continue
                self._ensure_takeover_task(track, now_utc)
```

**Key behavioral changes**:
- Guard expanded to include `DetectionStatus.MITIGATING` — prevents re-triggering on drones already receiving a takeover (idempotency via `takeover_sent` flag already handles this, but the status guard makes intent explicit).
- When `defense_radius_m is None`: behavior is **identical** to pre-010 (time-based, FR-010-014).
- Trigger uses strict `<` (not `<=`) — equality does not fire (spec edge case).

#### 4c. Update demo.yaml with detection_radius_m and defense_radius_m

**File**: `services/sentrycs-sim/config/demo.yaml`

Add both fields after `poll_interval_s`:

```yaml
# BEFORE (relevant excerpt)
sensor_lat: 24.725806
sensor_lon: 121.033750
poll_interval_s: 0.5
map_sim_url: http://127.0.0.1:8090

# AFTER
sensor_lat: 24.725806
sensor_lon: 121.033750
poll_interval_s: 0.5
detection_radius_m: 8000.0   # explicit — was implicit code default
defense_radius_m: 1000.0     # perimeter trigger: takeover fires when drone < 1km from sensor
map_sim_url: http://127.0.0.1:8090
```

#### Acceptance checks for Item 4

- `SentrycsConfig` parses `defense_radius_m: 1000.0` from YAML without error
- `SentrycsConfig` parses YAML without `defense_radius_m` (field is `None`) — old behavior preserved
- `run_one_tick()` fires `_ensure_takeover_task` when `haversine_m(...) < 1000.0` and `takeover_sent` is False
- No second takeover fires after `takeover_sent` is True
- Time-based path triggers when `defense_radius_m` is `None` and `elapsed >= mitigating_at_s`

---

## Phase 2 — Verification

### Linting

```bash
cd services/cot-gateway   && ruff check . && black --check .
cd services/sentrycs-sim  && ruff check . && black --check .
# (uds only has YAML change — no Python lint needed)
```

### Test suite

```bash
# From repo root
cd services/cot-gateway  && pytest -q   # 94 tests
cd services/sentrycs-sim && pytest -q   # 110 tests (includes loop, config, geo)
cd services/uds          && pytest -q   # 83 tests
# echoshield-sim and uds-gateway suites as applicable
```

Expected outcome: zero regressions. The following test categories are most directly impacted:

| Test category | Why it matters |
|---|---|
| `test_server.py` (cot-gateway web) | HTML template and JS content assertions |
| `test_loop.py` (sentrycs-sim) | Step 4 takeover trigger behavior |
| `test_config.py` (sentrycs-sim) | `defense_radius_m` field parsing |
| `test_track.py` (cot-gateway models) | TrackSource enum values |
| `test_loop.py` (cot-gateway) | `source_switch` log event fields |

### Manual end-to-end smoke test

See `specs/010-perimeter-defense/quickstart.md` for the exact command sequence.

---

## File Change Summary

| File | Change type | Items |
|---|---|---|
| `services/cot-gateway/src/cot_gateway/web/server.py` | Edit | 1a, 1b, 1c |
| `services/cot-gateway/src/cot_gateway/models/track.py` | Comment addition | 3 |
| `services/cot-gateway/src/cot_gateway/loop.py` | Edit (log event) | 3b |
| `services/uds/scenarios/demo_single_drone.yaml` | Edit | 2a |
| `services/sentrycs-sim/config/demo.yaml` | Edit | 2b, 4c |
| `services/sentrycs-sim/src/sentrycs_sim/config.py` | Edit (new field) | 4a |
| `services/sentrycs-sim/src/sentrycs_sim/loop.py` | Edit (step 4 + import) | 4b |

**Total files**: 7  
**New files**: 0  
**Schema/wire contract changes**: 0  
**New Python dependencies**: 0

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `SentrycsConfig extra="forbid"` rejects unknown fields in test fixtures | Low | Medium | Field has `default=None` → omitting it from YAML is valid; existing fixtures unaffected |
| MITIGATING guard addition changes existing MITIGATING-path test expectations | Low | Low | `takeover_sent` flag already prevents double-fire; guard is defensive only |
| Pastel colors fail accessibility at low brightness | Low | Low | Operators use map with high contrast; colors are distinct at saturation |
| Comment header t≈9s differs from prompt's "t≈15s" | Low | None | Physics-correct value used; old value was at 20 m/s |
| JS string in Python file triggers false ruff/black warnings | Very low | None | Embedded JS is inside a triple-quoted string; linters ignore it |
