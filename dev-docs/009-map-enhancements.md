# Dev-doc 009 — Map Enhancements & Track Disappearance Fixes

Feature branch: `feature/009-map-enhancements`  
Base: `develop`  
Affected services: `cot-gateway`, `sentrycs-sim`

---

## Summary

Three improvements to the CoT Gateway web map viewer and the Sentrycs / UDS
take-over pipeline:

| # | Item | Kind |
|---|------|------|
| 1 | Brightness & opacity sliders for the map tile layer | Enhancement |
| 2 | Fix Sentrycs tracks never appearing; increase TTL for demo resilience | Bug fix |
| 3 | Drone takeover redirects to HP instead of current position | Bug fix |

---

## Item 1 — Map Display Controls (brightness / opacity)

### What changed
`services/cot-gateway/src/cot_gateway/web/server.py`

A compact floating control panel (`#map-ctrl`, bottom-left) was added to
`_HTML_TEMPLATE` with two `<input type="range">` sliders:

| Slider | Range | Default |
|--------|-------|---------|
| Brightness | 20 % – 150 % | 100 % |
| Opacity    | 20 % – 100 % | 100 % |

On every `input` event the JS function `applyTileStyle()` applies:
```js
tileLayer.getContainer().style.filter  = `brightness(${bri/100})`;
tileLayer.getContainer().style.opacity = String(opa/100);
```

The tile layer is now captured as `const tileLayer = L.tileLayer(…).addTo(map)`.

### Design notes
* `getContainer()` is synchronously available after `addTo(map)` because
  Leaflet calls `onAdd()` (which sets `_container`) during the same tick.
* Brightness is applied via CSS `filter`; opacity via the `opacity` CSS
  property so they compose correctly.
* No new JS dependencies; no server-side changes.

---

## Item 2 — Sentrycs Tracks Never Appearing (+ TTL resilience)

### Root cause
`services/cot-gateway/src/cot_gateway/sentrycs/adapter.py`

`_detection_to_track()` was reading `d["status"]` but
`DetectionResponse.model_dump()` produces `detection_status` as the key.
Every poll of `/detections` silently raised `KeyError` caught by the inner
`except (KeyError, ValueError)` guard → no Sentrycs track ever reached
`track_store`.

The bug was masked in the contract-test fixture
(`tests/contract/test_sentrycs_poller.py`) which also used `"status"` in
`SAMPLE`, causing the adapter to appear correct under test.

### Fix — one-line change
```python
# before
detection_status=d["status"],
# after
detection_status=d["detection_status"],
```

### Collateral fixture updates (3 test files)
All Sentrycs stub dicts in the cot-gateway integration tests that used
`"status": "DETECTED"` were renamed to `"detection_status": "DETECTED"`.
The one late-scenario override in `test_us2_fusion_upgrade.py` that used
`dict(RF, status="NEUTRALIZED")` was updated to
`dict(RF, detection_status="NEUTRALIZED")`.

### TTL increase
`services/cot-gateway/config/demo.yaml`:  
`correlator.ttl_s` raised from **10 s → 30 s** to improve demo resilience
(a brief reconnect of the EchoShield TCP connection could otherwise expire
tracks before the operator notices).

---

## Item 3 — Takeover Target SP → HP

### Root cause
`services/sentrycs-sim/src/sentrycs_sim/uds/client.py`

`call_takeover(track)` unconditionally sent the drone's **current position**
(`track.lat`, `track.lon`) as `target_lat` / `target_lon`.  After UDS
received this, the trajectory engine treated that position as the destination,
so the drone effectively hovered in place instead of flying to the Holding
Point (HP = 24.725806, 121.071889).

### Changes

#### `config.py` — new optional fields on `DroneScenario`
```python
takeover_target_lat: float | None = None   # None → fall back to track.lat
takeover_target_lon: float | None = None   # None → fall back to track.lon
takeover_target_alt_m: float = Field(default=0.0, ge=0.0)
```
`extra="forbid"` / `frozen=True` are preserved; existing YAML configs that
do not include these fields use the backward-compatible defaults.

#### `uds/client.py` — optional target parameters
```python
async def call_takeover(
    self,
    track: DroneTrack,
    *,
    target_lat: float | None = None,
    target_lon: float | None = None,
    target_alt_m: float = 0.0,
) -> TakeoverResult:
```
When `target_lat` / `target_lon` are `None` the body falls back to
`float(track.lat)` / `float(track.lon)` — preserving all existing contract
tests that call `call_takeover(track)` without explicit coordinates.

#### `loop.py` — pass scenario HP coords in `_ensure_takeover_task`
```python
scenario = self.config.drone_by_uid(uid)
target_lat  = scenario.takeover_target_lat  if scenario else None
target_lon  = scenario.takeover_target_lon  if scenario else None
target_alt_m = scenario.takeover_target_alt_m if scenario else 0.0
```
The values are captured **before** the async closure runs to avoid
reading a stale track position.

#### `config/demo.yaml` — HP coordinates for TRK-E01
```yaml
takeover_target_lat: 24.725806   # HP — ~3850m due east of SP
takeover_target_lon: 121.071889  # HP — outside EchoShield 3200m range
takeover_target_alt_m: 50.0      # HP holding altitude
```

### Why HP is outside EchoShield range
EchoShield max range is 3200 m; HP is ~3850 m from SP.  Once UDS redirects
the drone to HP it will eventually leave the EchoShield detection zone and
the `Lost` + TTL lifecycle completes naturally.

---

## Key Coordinates (reference)
| Point | Lat | Lon | Note |
|-------|-----|-----|------|
| SP (Strategic) | 24.725806 | 121.033750 | Sensors co-located |
| HP (Holding)   | 24.725806 | 121.071889 | ~3850 m E of SP |
| Drone start    | 24.757306 | 121.033750 | ~3500 m N of SP |

---

## Files Changed

| Service | File | Change |
|---------|------|--------|
| cot-gateway | `src/cot_gateway/sentrycs/adapter.py` | `d["status"]` → `d["detection_status"]` |
| cot-gateway | `src/cot_gateway/web/server.py` | Brightness/opacity sliders, capture `tileLayer` ref |
| cot-gateway | `config/demo.yaml` | `ttl_s` 10 → 30 |
| cot-gateway | `tests/contract/test_sentrycs_poller.py` | Fix `SAMPLE` key `status` → `detection_status` |
| cot-gateway | `tests/integration/test_us2_fusion_upgrade.py` | Fix stub key; fix `dict(RF, status=…)` override |
| cot-gateway | `tests/integration/test_us2_no_cross_match.py` | Fix stub key |
| sentrycs-sim | `src/sentrycs_sim/config.py` | Add `takeover_target_*` fields to `DroneScenario` |
| sentrycs-sim | `src/sentrycs_sim/uds/client.py` | Add optional target params to `call_takeover` |
| sentrycs-sim | `src/sentrycs_sim/loop.py` | Pass target coords from scenario in `_ensure_takeover_task` |
| sentrycs-sim | `config/demo.yaml` | Add HP target coords for TRK-E01 |

---

## Test Results
| Suite | Tests | Result |
|-------|-------|--------|
| cot-gateway | 94 | ✅ all pass |
| sentrycs-sim | 110 | ✅ all pass |
| uds | 83 | ✅ all pass |
| echoshield-sim | 74 | ✅ all pass |
| map-sim | 107 | ✅ all pass |
