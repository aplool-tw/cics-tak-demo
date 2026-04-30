# Data Model: Feature 012 — CoT Gateway Track Update Fix

**Date**: 2026-04-30
**Status**: Final
**Scope**: `services/cot-gateway`

---

## Overview

Feature 012 is a bug-fix. No new domain entities or persistent storage are introduced. The data
model changes are:

1. **`/tracks` JSON response** — additive `uid` field (RC1/RC3)
2. **`detect_source_switch` return type** — `tuple[Optional[str], str]` → `tuple[list[str], str]` (RC2)
3. **`TrackStore._serialize` signature** — adds `uid: str` parameter (RC3)
4. **JS `droneMarkers` object** — new module-level client-side marker registry (RC1)
5. **`_within_match` local variables** — `ts_radar`, `ts_rf` normalisation copies (RC4)

All `UnifiedTrack` fields and the `TrackSource` / `TrackStatus` / `DetectionStatus` types are
**unchanged**.

---

## §1 — `/tracks` HTTP Response Schema

**Endpoint**: `GET /tracks`
**Handler**: `web/server.py::build_web_app._tracks` → `track_store.get_all()`
**Contract tier**: Internal UI endpoint (not a frozen G2 wire contract)

### Before (Feature 011 baseline) — 18 fields

```json
{
  "source":           "ECHOSHIELD | SENTRYCS | FUSED",
  "track_id":         "string",
  "lat":              "number (float)",
  "lon":              "number (float)",
  "alt_m":            "number (float)",
  "azimuth_deg":      "number (float)",
  "velocity_ms":      "number (float)",
  "elevation_deg":    "number (float)",
  "track_status":     "Active | Lost",
  "detection_status": "DETECTED | MITIGATING | NEUTRALIZED | null",
  "classification":   "string",
  "drone_model":      "string | null",
  "radar_track_id":   "string | null",
  "rf_track_id":      "string | null",
  "operator_lat":     "number | null",
  "operator_lon":     "number | null",
  "timestamp":        "ISO 8601 UTC string (e.g. 2026-04-30T12:34:56.789000+00:00)",
  "last_updated":     "ISO 8601 UTC string",
  "takeover_issued":  "boolean"
}
```

### After (Feature 012) — 19 fields (additive)

```json
{
  "uid":              "string",         ← NEW: CoT uid (TrackStore key)
  "source":           "ECHOSHIELD | SENTRYCS | FUSED",
  "track_id":         "string",
  "lat":              "number (float)",
  "lon":              "number (float)",
  "alt_m":            "number (float)",
  "azimuth_deg":      "number (float)",
  "velocity_ms":      "number (float)",
  "elevation_deg":    "number (float)",
  "track_status":     "Active | Lost",
  "detection_status": "DETECTED | MITIGATING | NEUTRALIZED | null",
  "classification":   "string",
  "drone_model":      "string | null",
  "radar_track_id":   "string | null",
  "rf_track_id":      "string | null",
  "operator_lat":     "number | null",
  "operator_lon":     "number | null",
  "timestamp":        "ISO 8601 UTC string",
  "last_updated":     "ISO 8601 UTC string",
  "takeover_issued":  "boolean"
}
```

### `uid` Field Specification

| Attribute | Value |
|-----------|-------|
| Type | `string` |
| Source | TrackStore dict key (set by `_emit_for_track` via `upsert(new_uid, track)`) |
| Prefix convention | `ECHO-{radar_track_id}` · `SENTRYCS-{rf_track_id}` · `FUSED-{rf_track_id}` |
| Example values | `ECHO-TRK-001`, `SENTRYCS-DRN-001`, `FUSED-DRN-001` |
| Guaranteed unique | Yes — one entry per uid in the TrackStore dict |
| Guaranteed present | Yes — every entry in the response array includes this field |

### Field Position in `_serialize` Return Dict

`uid` is the **first** key in the dict, making it immediately visible in JSON responses for
debugging. All 18 pre-existing fields follow in their existing order.

---

## §2 — `detect_source_switch` Function (RC2)

**Module**: `cot_gateway.cot.uid`

### Signature Change

| | Before | After |
|-|--------|-------|
| Return type | `tuple[Optional[str], str]` | `tuple[list[str], str]` |
| Import added | — | `from __future__ import annotations` already present; `Optional` import can be removed |
| `None` sentinel | Used for no-switch case | Replaced by `[]` (empty list) |

### Return Value Semantics

| Scenario | Before | After |
|----------|--------|-------|
| No prior mapping (first emission) | `(None, "ECHO-TRK-001")` | `([], "ECHO-TRK-001")` |
| Single-source switch (ECHO→FUSED) | `("ECHO-TRK-001", "FUSED-DRN-001")` | `(["ECHO-TRK-001"], "FUSED-DRN-001")` |
| Dual-source switch (both ECHO+SENTRYCS→FUSED) | `("ECHO-TRK-001", "FUSED-DRN-001")` ← **BUG: only first** | `(["ECHO-TRK-001", "SENTRYCS-DRN-001"], "FUSED-DRN-001")` ← **fixed** |
| Dedup: two entity keys → same old uid | `("FUSED-DRN-001", "ECHO-TRK-001")` | `(["FUSED-DRN-001"], "ECHO-TRK-001")` |
| No switch (uid unchanged) | `(None, "ECHO-TRK-001")` | `([], "ECHO-TRK-001")` |

### Algorithm (After)

```
new_uid = uid_for(track)
old_uids = []
seen = set()
for key in entity_keys_for(track):
    prev = prev_uid_by_entity_key.get(key)
    if prev is not None and prev != new_uid and prev not in seen:
        old_uids.append(prev)
        seen.add(prev)
return old_uids, new_uid
```

### Deduplication Invariant

If both `radar:TRK-001` and `rf:DRN-001` map to the same old uid (e.g., `FUSED-DRN-001`), the
returned list contains that uid **exactly once**. The `seen` set enforces this without sorting.

---

## §3 — `TrackStore._serialize` Signature (RC3)

**Module**: `cot_gateway.web.track_store`

### Signature Change

```python
# Before
def _serialize(track: UnifiedTrack, takeover_issued: bool = False) -> dict[str, Any]:

# After
def _serialize(track: UnifiedTrack, uid: str, takeover_issued: bool = False) -> dict[str, Any]:
```

### Call-Site Change in `get_all()`

```python
# Before
return [_serialize(t, uid in self._takeover_set) for uid, t in self._data.items()]

# After
return [_serialize(t, uid, uid in self._takeover_set) for uid, t in self._data.items()]
```

### Notes

- `_serialize` is a module-level private function; it is not part of any public API or external
  wire contract.
- The only call site is `get_all()`. No other module calls `_serialize` directly.
- The function signature change is non-breaking from an external API perspective.

---

## §4 — JS `droneMarkers` Client-Side State (RC1)

**Location**: `refreshTracks()` function in `cot_gateway.web.server._HTML_TEMPLATE` (JS section)

### Object Schema

```javascript
// Module-level declaration (once, at page-load)
const droneMarkers = {};   // { [uid: string]: L.Marker }
```

| Attribute | Value |
|-----------|-------|
| Type | Plain JavaScript object (property bag) |
| Key | CoT uid string (e.g., `"ECHO-TRK-001"`) |
| Value | Active Leaflet `L.Marker` instance |
| Lifecycle | Initialised as `{}` at page-load; persisted across all `refreshTracks()` calls; reset only on browser page reload |
| Invariant | After each successful `refreshTracks()`, `Object.keys(droneMarkers)` equals the set of uids in the last `/tracks` response |

### Incremental Update Logic (Pseudocode)

```javascript
async function refreshTracks() {
  const r = await fetch('/tracks', {cache: 'no-store'});
  if (!r.ok) return;
  const tracks = await r.json();

  // Step 1: upsert / create markers
  const currentUids = new Set();
  for (const t of tracks) {
    currentUids.add(t.uid);
    const lost = t.track_status === 'Lost';
    if (droneMarkers[t.uid]) {
      // Update existing marker in-place
      droneMarkers[t.uid].setLatLng([t.lat, t.lon]);
      droneMarkers[t.uid].setIcon(droneIcon(t, lost));
      droneMarkers[t.uid].bindTooltip(/* tooltip html */);
      if (droneMarkers[t.uid].getPopup()) {
        droneMarkers[t.uid].setPopupContent(/* popup html */);
      }
    } else {
      // Create and register new marker
      const m = L.marker([t.lat, t.lon], {icon: droneIcon(t, lost), zIndexOffset: 500});
      m.bindTooltip(/* tooltip html */, {className: 'leaflet-tooltip-gw'});
      m.addTo(trackLayer);
      droneMarkers[t.uid] = m;
    }
    // Velocity arrow lines are still full-rebuild (stateless)
    if (!lost && t.velocity_ms > 0.5) {
      arrowLine(t.lat, t.lon, t.azimuth_deg, SRC_COLOR[t.source] || '#888').addTo(trackLayer);
    }
  }

  // Step 2: remove stale markers
  for (const uid of Object.keys(droneMarkers)) {
    if (!currentUids.has(uid)) {
      trackLayer.removeLayer(droneMarkers[uid]);
      delete droneMarkers[uid];
    }
  }

  // Step 3: rebuild panel list (FR-012-008 — panel MAY be full-rebuilt)
  // ... #track-list HTML rebuild unchanged ...
}
```

### Arrow Lines Note

Velocity arrow `L.polyline` objects remain stateless (created fresh each cycle, added directly to
`trackLayer`). They do not need uid-keyed tracking because they are directional decorators, not
the primary drone position marker. Stale arrow lines are implicitly cleaned up when `trackLayer`
is cleared of non-marker polylines.

> **Implementation Note**: Since arrow lines still call `addTo(trackLayer)` each cycle without
> `clearLayers()`, stale arrow lines from previous cycles will accumulate if the number of tracks
> changes. The simplest solution is to maintain a separate `arrowLayer` (or `arrowLines[]` array)
> and clear only that on each cycle, while leaving `trackLayer` markers managed via `droneMarkers`.
> Alternatively, arrow lines can be stored as a property of the marker (e.g., `droneMarkers[uid].arrowLine`)
> and removed/re-added on each update. Either approach is acceptable; the task file should specify
> the chosen pattern.

---

## §5 — `_within_match` Normalisation Variables (RC4)

**Module**: `cot_gateway.correlate.correlator`
**Method**: `TrackCorrelator._within_match`

### Before

```python
def _within_match(self, radar: UnifiedTrack, rf: UnifiedTrack) -> bool:
    if haversine_m(radar.lat, radar.lon, rf.lat, rf.lon) > self.distance_threshold_m:
        return False
    dt = abs((radar.timestamp - rf.timestamp).total_seconds())  # ← TypeError if mixed tz
    return dt <= self.time_window_s
```

### After

```python
def _within_match(self, radar: UnifiedTrack, rf: UnifiedTrack) -> bool:
    if haversine_m(radar.lat, radar.lon, rf.lat, rf.lon) > self.distance_threshold_m:
        return False
    ts_radar = (
        radar.timestamp if radar.timestamp.tzinfo is not None
        else radar.timestamp.replace(tzinfo=timezone.utc)
    )
    ts_rf = (
        rf.timestamp if rf.timestamp.tzinfo is not None
        else rf.timestamp.replace(tzinfo=timezone.utc)
    )
    dt = abs((ts_radar - ts_rf).total_seconds())
    return dt <= self.time_window_s
```

### Timezone Combination Matrix

| `radar.timestamp.tzinfo` | `rf.timestamp.tzinfo` | Before | After |
|--------------------------|----------------------|--------|-------|
| `timezone.utc` (aware) | `timezone.utc` (aware) | ✅ OK | ✅ OK (no change) |
| `timezone.utc` (aware) | `None` (naïve) | ❌ `TypeError` | ✅ naïve treated as UTC |
| `None` (naïve) | `timezone.utc` (aware) | ❌ `TypeError` | ✅ naïve treated as UTC |
| `None` (naïve) | `None` (naïve) | ✅ OK (both naïve) | ✅ both treated as UTC |

### Invariant

`UnifiedTrack.timestamp` fields are **never mutated**. `ts_radar` and `ts_rf` are local variables
within `_within_match` only. The normalised copies are used solely for the subtraction.

---

## §6 — Frozen Wire Contracts (G2 — Unchanged)

> Feature 012 does not modify any external schema. The following are declared immutable.

| Wire | Owner module | Format | Status |
|------|-------------|--------|--------|
| EchoShield TCP JSON | `echoshield/adapter.py` | `{track_id, latitude, longitude, altitude_m, velocity_ms, azimuth_deg, elevation_deg, timestamp}` | ✅ Unchanged |
| Sentrycs `/detections` JSON | `sentrycs/adapter.py` | `{detections: [{drone_id, lat, lon, …}]}` | ✅ Unchanged |
| TAK CoT XML | `cot/generator.py` | CoT 2.0 `<event>` XML | ✅ Unchanged |
| UDS `/command/takeover` body | `perimeter/guard.py` | `{drone_id, target_lat, target_lon, target_alt_m}` | ✅ Unchanged |
