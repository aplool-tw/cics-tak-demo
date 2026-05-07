# Contract: `/tracks` HTTP Endpoint

**Service**: CoT Gateway (`services/cot-gateway`)
**Endpoint**: `GET /tracks`
**Contract Tier**: Internal UI endpoint (not a frozen G2 external wire contract)
**Updated by**: Feature 012 — CoT Gateway Track Update Fix
**Date**: 2026-04-30

---

## Overview

The `/tracks` endpoint exposes the live contents of the in-memory `TrackStore` as a JSON array.
It is consumed exclusively by the `refreshTracks()` JavaScript function in the `/map` browser page.
No external system (ATAK, EchoShield, Sentrycs, UDS) reads this endpoint.

Feature 012 adds one field (`uid`) to the response. All 18 pre-existing fields are preserved
unchanged in name, type, and position.

---

## Request

```
GET /tracks HTTP/1.1
Host: <gateway-host>:18092
Cache-Control: no-store
```

| Attribute | Value |
|-----------|-------|
| Method | `GET` |
| Path | `/tracks` |
| Authentication | None (internal demo network) |
| Request body | None |
| Cache | `no-store` (client enforces via `fetch('/tracks', {cache: 'no-store'})`) |

---

## Response (Success)

### HTTP Status

`200 OK`

### Response Headers

```
Content-Type: application/json
Cache-Control: no-store, no-cache
Pragma: no-cache
```

### Response Body

A JSON array of track objects. May be empty (`[]`) when no tracks are active.

```json
[
  {
    "uid":              "ECHO-TRK-001",
    "source":           "ECHOSHIELD",
    "track_id":         "TRK-001",
    "lat":              24.7501,
    "lon":              121.0452,
    "alt_m":            123.4,
    "azimuth_deg":      87.5,
    "velocity_ms":      35.2,
    "elevation_deg":    3.1,
    "track_status":     "Active",
    "detection_status": null,
    "classification":   "UNKNOWN",
    "drone_model":      null,
    "radar_track_id":   "TRK-001",
    "rf_track_id":      null,
    "operator_lat":     null,
    "operator_lon":     null,
    "timestamp":        "2026-04-30T12:34:56.789000+00:00",
    "last_updated":     "2026-04-30T12:34:56.800000+00:00",
    "takeover_issued":  false
  },
  {
    "uid":              "FUSED-DRN-001",
    "source":           "FUSED",
    "track_id":         "FUSED-DRN-001",
    "lat":              24.7490,
    "lon":              121.0440,
    "alt_m":            118.0,
    "azimuth_deg":      89.0,
    "velocity_ms":      34.8,
    "elevation_deg":    2.9,
    "track_status":     "Active",
    "detection_status": "DETECTED",
    "classification":   "DRONE",
    "drone_model":      "DJI Phantom",
    "radar_track_id":   "TRK-001",
    "rf_track_id":      "DRN-001",
    "operator_lat":     24.710,
    "operator_lon":     121.020,
    "timestamp":        "2026-04-30T12:34:57.100000+00:00",
    "last_updated":     "2026-04-30T12:34:57.110000+00:00",
    "takeover_issued":  true
  }
]
```

---

## Field Reference

| Field | Type | Nullable | Added | Description |
|-------|------|----------|-------|-------------|
| `uid` | `string` | No | **Feature 012** | CoT uid — TrackStore dict key; matches the uid emitted to ATAK |
| `source` | `string` | No | pre-012 | Track source: `ECHOSHIELD`, `SENTRYCS`, or `FUSED` |
| `track_id` | `string` | No | pre-012 | Canonical track identifier (`TRK-*`, `DRN-*`, `FUSED-*`) |
| `lat` | `number` | No | pre-012 | Latitude (WGS-84, decimal degrees) |
| `lon` | `number` | No | pre-012 | Longitude (WGS-84, decimal degrees) |
| `alt_m` | `number` | No | pre-012 | Altitude (metres above MSL) |
| `azimuth_deg` | `number` | No | pre-012 | Heading azimuth (degrees, 0–360) |
| `velocity_ms` | `number` | No | pre-012 | Ground speed (m/s) |
| `elevation_deg` | `number` | No | pre-012 | Elevation angle (degrees) |
| `track_status` | `string` | No | pre-012 | `Active` or `Lost` |
| `detection_status` | `string\|null` | Yes | pre-012 | `DETECTED`, `MITIGATING`, `NEUTRALIZED`, or `null` (ECHOSHIELD tracks) |
| `classification` | `string` | No | pre-012 | Target classification label (e.g., `UNKNOWN`, `DRONE`) |
| `drone_model` | `string\|null` | Yes | pre-012 | Drone model reported by Sentrycs RF sensor, or `null` |
| `radar_track_id` | `string\|null` | Yes | pre-012 | EchoShield radar track ID, or `null` for SENTRYCS-only tracks |
| `rf_track_id` | `string\|null` | Yes | pre-012 | Sentrycs RF track ID, or `null` for ECHOSHIELD-only tracks |
| `operator_lat` | `number\|null` | Yes | pre-012 | Drone operator latitude reported by Sentrycs, or `null` |
| `operator_lon` | `number\|null` | Yes | pre-012 | Drone operator longitude reported by Sentrycs, or `null` |
| `timestamp` | `string` | No | pre-012 | ISO 8601 UTC timestamp of the track observation |
| `last_updated` | `string` | No | pre-012 | ISO 8601 UTC timestamp of last `TrackStore.upsert()` call |
| `takeover_issued` | `boolean` | No | pre-012 | `true` if PerimeterGuard issued UDS takeover for this uid |

---

## `uid` Field — uid Prefix Convention

| Source | Pattern | Example |
|--------|---------|---------|
| `ECHOSHIELD` | `ECHO-{radar_track_id}` | `ECHO-TRK-001` |
| `SENTRYCS` | `SENTRYCS-{rf_track_id}` | `SENTRYCS-DRN-001` |
| `FUSED` | `FUSED-{rf_track_id}` | `FUSED-DRN-001` |

The `uid` value is the same string ATAK receives in the CoT `<event uid="…">` attribute,
enabling end-to-end correlation from ATAK icon to `/tracks` entry to `TrackStore` key.

---

## Response (Error)

The endpoint does not return structured error bodies. On internal errors, aiohttp returns a
standard `500 Internal Server Error`. The JS client treats any non-`200` response as a no-op
(`if (!r.ok) return;`).

---

## Versioning and Stability

| Version | Change |
|---------|--------|
| Feature 011 baseline | 18 fields (no `uid`); `takeover_issued` field added |
| **Feature 012** | **19 fields; `uid` added as first field** |

The `/tracks` endpoint is **not** a frozen G2 contract. It is consumed only by the embedded
browser JS (`refreshTracks()` in `/map`). Additive field additions are permitted; removals or
renames require updating both `track_store.py` and `server.py` JS together.

---

## Consumer Behaviour (JS `refreshTracks()`)

After Feature 012, the JS consumer:

1. Reads `t.uid` as the stable identifier for incremental marker management
2. Reads `t.lat`, `t.lon` for `marker.setLatLng()`
3. Reads `t.source`, `t.takeover_issued`, `t.track_status` for `droneIcon(t, lost)` rendering
4. Reads `t.track_id`, `t.detection_status`, `t.velocity_ms`, `t.azimuth_deg`, `t.alt_m` for
   tooltip and popup content
5. Reads `t.source`, `t.track_id`, `t.lat`, `t.lon`, `t.alt_m`, `t.velocity_ms`,
   `t.takeover_issued`, `t.detection_status` for the `#track-list` panel HTML

All reads are by **named field** — additional fields are silently ignored by the JS consumer.

---

## Frozen External Contracts (Not This Document)

The following external wire contracts are managed separately and are **not modified** by Feature 012:

| Contract | Document reference |
|----------|--------------------|
| EchoShield TCP JSON wire | `tests/contract/test_echodyne_wire.py` |
| Sentrycs `/detections` JSON | `tests/contract/test_sentrycs_poller.py` |
| TAK CoT XML | `tests/contract/test_cot_xml_schema.py` |
| UDS `/command/takeover` body | `tests/contract/test_tak_uplink.py` |
