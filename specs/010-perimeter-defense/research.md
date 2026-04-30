# Research: Feature 010 — Perimeter Defense

Generated: 2026-04-30  
Branch: `010-perimeter-defense`

---

## R1 — Map Legend Dashed-Line Reuse (FR-010-004)

**Decision**: Reuse the existing `.leg-line` CSS class (`border-top: 2px dashed`) for all three ring legend entries.

**Rationale**: The class is already defined in `server.py` and used for "Radar range" and "RF range" entries. Adding the three defense ring entries with the same class keeps visual consistency and satisfies the no-new-CSS constraint.

**Evidence** (`server.py` lines 40, 93–94):
```html
.leg-line{width:18px;height:0;flex-shrink:0;border-top:2px dashed}
<div class="leg-row"><span class="leg-line" style="border-color:#00BFFF"></span>Radar range</div>
<div class="leg-row"><span class="leg-line" style="border-color:#FFD700"></span>RF range</div>
```

**Alternatives considered**: Adding a new `.leg-ring` class — ruled out by FR-010-004.

---

## R2 — Ring Color Conflict Analysis (FR-010-002)

**Decision**: Use `#80deea` (Cyan 200), `#ffcc80` (Orange 200), `#ef9a9a` (Red 200) for rings 1 km / 2 km / 3 km respectively.

**Palette**: Material Design 200-shade pastels, per spec assumption.

**Conflict check** against all existing colors in `server.py`:

| Existing color | Usage | Conflict with proposed? |
|---|---|---|
| `#00BFFF` | EchoShield track / radar range | None — distinct from `#80deea` |
| `#FFD700` | Sentrycs track / RF range | None — distinct from `#ffcc80` |
| `#FF4444` | Fused track | None — distinct from `#ef9a9a` |
| `#2196F3` | Active drone / Holding point | None |
| `#FF9800` | Lost drone orange | None |
| `#00FF88` | Strategic point green | None |

**Conclusion**: All three pastel ring colors are visually distinct at a glance from every existing palette entry.

---

## R3 — Leaflet Tooltip Binding Syntax

**Decision**: Use `.bindTooltip(label, {className:'leaflet-tooltip-gw'})` chained directly on the `circle(...)` return value before `.addTo(siteLayer)`.

**Rationale**: The existing `leaflet-tooltip-gw` CSS class is already defined and produces the correct dark tactical styling. The `circle()` helper returns a `L.circle` object which supports `.bindTooltip()`. No extra layer state is needed.

**Pattern** (current ring draw line, `server.py` line 217):
```js
// Current
circle(s.lat,s.lon,rm,RING_COLORS[i]||'#ef5350','6 5').addTo(siteLayer);

// Proposed
const RING_LABELS = ['1km defense ring','2km defense ring','3km defense ring'];
circle(s.lat,s.lon,rm,RING_COLORS[i]||'#ef9a9a','6 5')
  .bindTooltip(RING_LABELS[i]||'defense ring',{className:'leaflet-tooltip-gw'})
  .addTo(siteLayer);
```

---

## R4 — Demo Drone Speed & Displacement Verification (FR-010-005)

**Decision**: `speed_ms: 35.0` in `services/uds/scenarios/demo_single_drone.yaml`.

**Displacement math** at zoom 13 per 3-second refresh:
- `35 m/s × 3 s = 105 m` — satisfies the ≥ 80 m criterion of FR-010-005 / SC-010-002.
- At zoom 13 (1 tile = 256 px covers ≈ 4.9 km): 105 m ≈ 5.5 px — clearly visible movement.

**Previous value**: 20 m/s → 60 m per refresh (≈ 3 px) — imperceptible.

**Updated event timing at 35 m/s** (drone starts 3 500 m north of sensor; sensor co-located with SP at `24.725806, 121.033750`):

| Event | Calc | Time |
|---|---|---|
| Enters EchoShield range (3 200 m) | (3500−3200)/35 | **≈ 9 s** |
| Passes 2 km mark | (3500−2000)/35 | **≈ 43 s** |
| Passes 1 km defense perimeter | (3500−1000)/35 | **≈ 71 s** |
| `detected_at_s` scenario threshold | hard-coded | **t = 75 s** (drone at ≈ 875 m) |
| Takeover fires (position-based) | first tick after DETECTED | **t ≈ 75 s+** (already inside perimeter) |
| `neutralized_at_s` | hard-coded | **t = 165 s** |

> **Note**: The prompt statement "t≈15s enters EchoShield" corresponds to the **old** 20 m/s speed. At 35 m/s the correct physics value is ~9 s. Plan and YAML comments use the physics-correct value.

---

## R5 — TrackSource Enum / JS SRC_COLOR Verification (FR-010-007)

**Decision**: No code change required. The enum values already match exactly.

**Evidence** (`track.py` lines 12–14):
```python
class TrackSource(str, Enum):
    ECHOSHIELD = "ECHOSHIELD"
    SENTRYCS   = "SENTRYCS"
    FUSED      = "FUSED"
```

**JS map** (`server.py` line 108):
```js
const SRC_COLOR = { ECHOSHIELD:'#00BFFF', SENTRYCS:'#FFD700', FUSED:'#FF4444' };
```

All three string `.value` attributes match the JS object keys verbatim. A verification comment will be added to `track.py` confirming this contract.

---

## R6 — detection_radius_m Field (FR-010-008)

**Decision**: Add `detection_radius_m: 8000.0` explicitly to `services/sentrycs-sim/config/demo.yaml`.

**Rationale**: The field already exists in `SentrycsConfig` with `default=8000.0`; adding it to the YAML makes the detection boundary self-documenting and removes the implicit reliance on the code default.

**No schema change needed**: `detection_radius_m` is already a defined field with `gt=0.0` validation.

---

## R7 — haversine_m Reuse (G7 — no new deps)

**Decision**: Import `haversine_m` from `.geo.wgs84`, the function that already exists in `sentrycs_sim`.

**Evidence** (`services/sentrycs-sim/src/sentrycs_sim/geo/wgs84.py`):
```python
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (for tests)."""
    ...
```

The function uses the spherical Earth approximation (WGS84 equatorial radius) — sufficient accuracy for ±100 m resolution at the 1 km defense perimeter scale.

**Import line** to add to `loop.py`:
```python
from .geo.wgs84 import haversine_m
```

---

## R8 — defense_radius_m Schema Addition (FR-010-010)

**Decision**: Add `defense_radius_m: Optional[float] = None` to `SentrycsConfig`. No minimum enforced at schema level per FR-010-010.

**Compatibility considerations**:
- `SentrycsConfig` has `extra="forbid"` — adding a new field with `None` default is backward-compatible; existing YAML configs that omit the field will simply get `None`.
- `frozen=True` — field is immutable after construction; no impact on the perimeter logic which only reads the value.
- Existing test fixtures that do not set `defense_radius_m` will continue to exercise the time-based path unchanged (FR-010-014).

**Import needed**: `from typing import Optional` is already imported in `config.py`; no new imports.

---

## R9 — Structured Log Event for Source Correlation Change (FR-010-009)

**Decision**: Enhance the existing `source_switch` log event in `cot_gateway/loop.py` `_emit_for_track` to include `entity_key`.

**Current state** (`loop.py` lines 108–110):
```python
self._log.info(
    "source_switch", old_uid=old_uid, new_uid=new_uid, track_id=track.track_id
)
```

**Gap**: `entity_key` is not logged. FR-010-009 requires it.

**Solution**: Add `entity_key` as the first entity key from `entity_keys_for(track)`. The function is already imported and called later in the same method.

```python
entity_key = entity_keys_for(track)[0] if entity_keys_for(track) else None
self._log.info(
    "source_switch",
    old_uid=old_uid,
    new_uid=new_uid,
    track_id=track.track_id,
    entity_key=entity_key,
)
```

**Alternatives considered**: Logging all entity keys as a list — unnecessary complexity; the FUSED track correlation case always has a deterministic primary key (`rf:<uid>`).

---

## R10 — Position-Based Takeover Logic (FR-010-011–016)

**Decision**: Modify step 4 of `run_one_tick()` in `sentrycs_sim/loop.py` to branch on `self.config.defense_radius_m is not None`.

**Guard conditions** (unchanged from current):
- `track.status not in (DetectionStatus.DETECTED, DetectionStatus.MITIGATING)` → skip
- `track.takeover_sent` → skip (idempotency, FR-010-016)
- `scenario is None` → skip

**New branch when `defense_radius_m` is set**:
```python
dist = haversine_m(self.config.sensor_lat, self.config.sensor_lon, track.lat, track.lon)
if dist < self.config.defense_radius_m:
    self._ensure_takeover_task(track, now_utc)
```

**Else branch** (time-based, unchanged):
```python
if elapsed < float(scenario.mitigating_at_s):
    continue
self._ensure_takeover_task(track, now_utc)
```

**MITIGATING status in guard**: The spec adds `DetectionStatus.MITIGATING` to the guard so that a drone already in MITIGATING state (takeover issued, waiting for landing) does not re-trigger. The current code only checks `DetectionStatus.DETECTED`; the expanded guard aligns with FR-010-013 and prevents the position check from re-firing on a drone already receiving a takeover command.

**Floating-point boundary**: Trigger condition is strict `<`, not `<=` — matches edge-case spec: "equality does not trigger."

---

## Summary of All Resolved Clarifications

| # | Question | Resolution | Source |
|---|---|---|---|
| C1 | Defense perimeter origin: sensor vs SP? | Sensor position — consistent with `detection_radius_m` | Spec §Clarifications |
| C2 | `mitigating_at_s` still required when `defense_radius_m` set? | Yes, required for backward compat; not evaluated as trigger | Spec §Clarifications |
| C3 | TrackSource values match JS SRC_COLOR keys? | Confirmed, no change needed | R5 above |
| C4 | Which pastel colors? | `#80deea` / `#ffcc80` / `#ef9a9a` — conflict check passed | R2 above |
| C5 | EchoShield entry timing at 35 m/s? | ≈ 9 s (not 15 s — old speed artefact in prompt) | R4 above |
