# Feature Specification: SP/HP CoT Broadcasting

**Feature ID**: 014  
**Feature Branch**: `feature/014-sp-hp-cot`  
**Created**: 2026-05-06  
**Status**: Draft  
**Short Name**: `sp-hp-cot`

---

## Summary

Add periodic Cursor-on-Target (CoT) broadcasting of the Strategic Point (SP) and Holding Point
(HP) site markers — and the SP's layered defense rings — to `cot-gateway`, so that real TAK
clients (ATAK / WinTAK) connected to the TAK Server see these fixed annotations on their
operational maps without any manual input.

Broadcasting is governed by a new, additive `broadcast` section in `gateway.yaml`.  All existing
configuration files that omit the `broadcast` key continue to work unchanged.

---

## Background

The Taiwan anti-drone TAK PoC scenario operates around two fixed ground sites defined in
`config/sites.yaml`:

| Site | Role | Significance |
|------|------|--------------|
| SP   | Strategic Point — collocated radar site (EchoShield + Sentrycs) | Origin of all drone detections; has three defense-ring radii (1 km / 2 km / 3 km) |
| HP   | Holding / Landing Point — designated drone intercept landing zone | Destination assigned to a neutralised drone |

Today, the web-map viewer (`:8092`) renders both sites in the browser, but real TAK clients
(**ATAK**, **WinTAK**) that connect directly to the TAK Server (`:8089`) receive **no** SP / HP
CoT events.  Operators using field devices therefore see drone tracks arriving without any map
context — they cannot identify the radar site, the defense perimeter rings, or the intended
landing zone.

This feature closes that gap by broadcasting three CoT event types from `cot-gateway`:

1. **SP point marker** — identifies the radar / strategic site on TAK maps.
2. **HP point marker** — identifies the holding / landing zone on TAK maps.
3. **SP defense-ring overlays** — one circular CoT event per configured ring radius, centred on
   the SP, rendered by ATAK / WinTAK as a visible circle.

---

## Clarifications

### Session 2026-05-06

- Q: Config source for SP/HP — new `broadcast:` section in gateway.yaml vs reusing `web.sp_lat/sp_lon` and `perimeter.holding_lat/lon`? → A: Introduce a new **top-level `broadcast:` section** in `gateway.yaml`. `BroadcastConfig` reads SP/HP coordinates directly, with defaults matching existing values in `demo.yaml`. Existing configs without the `broadcast:` key work unchanged via pydantic default. No coupling to `web` or `perimeter` subsections.
- Q: CoT type for SP point marker? → A: **`a-f-G-U-C`** (Friendly Ground Unit — Command Post). Renders as a starred/filled friendly symbol in ATAK; standard TAK convention for ground command/control infrastructure.
- Q: CoT type for HP marker? → A: **`a-f-G-U-C`** (Friendly Ground Unit — Command Post). Both SP and HP use the same type for consistency; they are distinguished by their stable UIDs and callsigns (`sp_name` / `hp_name`).
- Q: CoT circle/ring format — `u-d-c` vs `a-r-*`? → A: Use **`u-d-c`** (drawing circle) with `<shape><ellipse minor="R" major="R" angle="0"/></shape>` inside `<detail>`, where R is the ring radius in metres. `<point>` is at the SP centre. `minor` and `major` are semi-axes in metres (equal for a circle). This is the format ATAK uses for circle drawing overlays.
- Q: Broadcaster integration — coroutine or separate task? → A: Add as a new **`asyncio.Task`** launched in `GatewayMain.run()` alongside existing coroutines. The method is named **`sp_hp_broadcast_loop()`** on `GatewayMain`. It is NOT a separate module outside GatewayMain.

---

## User Scenarios & Testing

### US-001 — TAK Operator Sees SP and Defense Rings on Map (Priority: P1)

A TAK operator opens ATAK on a field device connected to the TAK Server.  Without any manual
input, they can see the Strategic Point site marker and three concentric defense-ring overlays
(1 km, 2 km, 3 km) centred on that marker.  When drone tracks arrive on their map they can
immediately judge which ring the drone has entered.

**Why this priority**: Without SP/ring context, field operators have no spatial reference to
evaluate incoming drone alerts — this is the highest-value outcome of the feature.

**Independent Test**: With only `broadcast.enabled: true` and valid SP coordinates in
`gateway.yaml`, connect a TAK client and confirm that, within two broadcast intervals, the SP
point marker and all three ring overlays appear on the map.

**Acceptance Scenarios**:

1. **Given** `cot-gateway` starts with `broadcast.enabled: true` and SP coordinates set,
   **When** a TAK client connects to the TAK Server,
   **Then** the SP point marker appears on the client map within `2 × broadcast_interval_s`
   seconds of connection.

2. **Given** the broadcaster is running,
   **When** `broadcast_interval_s` seconds elapse,
   **Then** the SP point marker and all configured ring overlays are re-broadcast, refreshing
   their stale timer on connected TAK clients.

3. **Given** a TAK client is already connected,
   **When** the SP ring CoT events arrive,
   **Then** the client renders each ring as a visible circular overlay concentric with the SP
   marker, at the correct radii.

4. **Given** the operator views the ATAK map during a live drone incursion,
   **When** the drone track CoT arrives alongside the SP/ring overlays,
   **Then** the operator can visually determine which defense ring the drone has entered.

---

### US-002 — TAK Operator Sees HP Marker on Map (Priority: P2)

A TAK operator can identify the Holding Point (HP) — the designated drone landing zone — as a
named map marker on their TAK client, so they know where a neutralised drone is being guided.

**Why this priority**: The HP is actionable only when an intercept is in progress.  SP ring
awareness (US-001) must exist first; HP context is the next most important operational overlay.

**Independent Test**: With `broadcast.enabled: true` and HP coordinates set, verify the HP
point marker appears on a connected TAK client within `2 × broadcast_interval_s` seconds.

**Acceptance Scenarios**:

1. **Given** `cot-gateway` starts with `broadcast.enabled: true` and HP coordinates configured,
   **When** a TAK client connects,
   **Then** the HP point marker appears on the client map with the correct label and position
   within `2 × broadcast_interval_s` seconds.

2. **Given** the perimeter-guard system redirects a drone toward the HP,
   **When** the TAK operator views their map,
   **Then** both the incoming drone track and the HP destination marker are visible
   simultaneously, allowing the operator to confirm the drone is heading to the correct site.

---

### US-003 — Operator Reconfigures SP/HP Positions Without Code Change (Priority: P3)

A system operator can update SP or HP coordinates, ring radii, or broadcast interval by editing
`gateway.yaml` and restarting `cot-gateway` — no source-code change or container rebuild
required.

**Why this priority**: Operational site coordinates may change between exercises.  Externalising
the configuration avoids error-prone code changes in the field.

**Independent Test**: Modify `broadcast.sp_lat` / `broadcast.sp_lon` and ring radii in
`gateway.yaml`, restart the gateway, and verify the updated SP position and rings appear on the
TAK client.

**Acceptance Scenarios**:

1. **Given** default SP coordinates are set in `gateway.yaml`,
   **When** an operator changes `broadcast.sp_lat` / `broadcast.sp_lon` and restarts the
   gateway,
   **Then** the SP marker and ring overlays appear at the new coordinates on TAK clients.

2. **Given** default ring radii are `[1000, 2000, 3000]` metres,
   **When** an operator changes `broadcast.sp_rings_m` to `[500, 1500]` and restarts,
   **Then** only two ring overlays appear on TAK clients; the three-ring overlays are no longer
   refreshed and expire after their stale time.

3. **Given** an existing `gateway.yaml` that has **no** `broadcast` section,
   **When** the gateway starts,
   **Then** it uses built-in defaults and starts successfully without errors — no existing
   config is broken by this change.

---

## Edge Cases

- **`broadcast.enabled: false` (default)**: No SP, HP, or ring CoT events are enqueued or
  sent.  The broadcaster coroutine exits immediately without logging repetitive skip messages.

- **Empty `sp_rings_m: []`**: No ring CoT events are emitted; only the SP point marker is
  broadcast.  This is valid and must not cause an error.

- **TAK Server unavailable at startup**: The broadcaster enqueues CoT events normally; the
  existing TAK transmitter retry/backoff logic handles delivery once the server reconnects.
  The broadcaster does not need its own retry path.

- **Gateway restart mid-interval**: TAK clients retain the previous SP/HP/ring CoT until their
  stale time expires (`now + 2 × interval_s`).  After restart, the broadcaster re-emits within
  one interval, so the gap seen by clients is at most `2 × interval_s`.

- **Ring radius of 0 m or negative**: Must be rejected at config-load time with a clear
  validation error.  The gateway must not start.

- **SP and HP coordinates identical**: Permitted — both CoT events are emitted with distinct
  UIDs and callsigns; no deduplication logic is applied.

- **Very short `broadcast_interval_s` (e.g., 1 s)**: Permitted by config.  The broadcaster
  re-enqueues on that cadence.  Operators should use values ≥ 10 s in production to avoid
  saturating the TAK queue.

- **Broadcast coroutine crash**: The existing `GatewayMain.run()` supervision must log the
  error but must not terminate the gateway — drone CoT broadcasting (the primary function) must
  continue unaffected.

---

## Requirements

### Functional Requirements

#### Configuration

- **FR-014-001**: The system MUST accept a new top-level `broadcast` section in `gateway.yaml`
  with the following sub-fields, all optional (fall back to defaults when absent):

  | Field | Type | Default | Description |
  |-------|------|---------|-------------|
  | `enabled` | bool | `false` | Master switch for SP/HP/ring broadcasting |
  | `interval_s` | float > 0 | `30.0` | Rebroadcast cadence in seconds |
  | `sp_lat` | float [-90, 90] | `24.725806` | SP latitude |
  | `sp_lon` | float [-180, 180] | `121.033750` | SP longitude |
  | `sp_alt_m` | float ≥ 0 | `50.0` | SP altitude (metres HAE) |
  | `sp_name` | string | `"Strategic Point"` | SP callsign / label |
  | `sp_rings_m` | list[float > 0] | `[1000.0, 2000.0, 3000.0]` | Defense ring radii |
  | `hp_lat` | float [-90, 90] | `24.735344` | HP latitude |
  | `hp_lon` | float [-180, 180] | `121.044252` | HP longitude |
  | `hp_alt_m` | float ≥ 0 | `0.0` | HP altitude (metres HAE) |
  | `hp_name` | string | `"Holding Point"` | HP callsign / label |

- **FR-014-002**: A `gateway.yaml` that contains **no** `broadcast` key MUST load successfully
  with all defaults; no validation error or startup failure is permitted.

- **FR-014-003**: Individual fields within the `broadcast` section MAY be omitted; each absent
  field MUST fall back to its documented default independently.

- **FR-014-004**: The system MUST reject a `broadcast` section that contains any ring radius
  ≤ 0 with a validation error that names the offending value, and MUST NOT start.

- **FR-014-005**: The system MUST reject `interval_s ≤ 0` with a validation error.

#### SP Point Marker Broadcasting

- **FR-014-006**: When `broadcast.enabled` is `true`, the system MUST periodically emit a CoT
  point-marker event for the SP at the coordinates and altitude defined in `broadcast.sp_lat /
  sp_lon / sp_alt_m`.

- **FR-014-007**: The SP CoT event MUST carry a stable, deterministic UID (e.g., derived from
  the string `"SP"` and feature ID `014`) so that TAK clients update the existing marker rather
  than creating a duplicate each broadcast cycle.

- **FR-014-008**: The SP CoT event MUST carry the `sp_name` value as the operator-visible
  callsign / label on TAK client maps.

- **FR-014-009**: The SP CoT event `stale` timestamp MUST be set to
  `now + 2 × broadcast.interval_s` so the marker remains visible between re-broadcasts and
  expires automatically if the gateway stops.

#### HP Point Marker Broadcasting

- **FR-014-010**: When `broadcast.enabled` is `true`, the system MUST periodically emit a CoT
  point-marker event for the HP at the coordinates and altitude defined in `broadcast.hp_lat /
  hp_lon / hp_alt_m`.

- **FR-014-011**: The HP CoT event MUST carry a stable, deterministic UID (distinct from the SP
  UID), carrying `hp_name` as the callsign / label.

- **FR-014-012**: The HP CoT `stale` timestamp MUST follow the same `now + 2 × interval_s`
  rule as the SP.

#### Defense Ring Broadcasting

- **FR-014-013**: When `broadcast.enabled` is `true`, the system MUST emit one CoT circle-type
  event per entry in `broadcast.sp_rings_m`, centred on the SP coordinates, with a radius equal
  to the configured value.

- **FR-014-014**: Each ring CoT event MUST carry a stable, deterministic UID that encodes both
  the SP identity and the ring radius (e.g., `"SP-RING-1000"`), so repeated broadcasts update
  the existing circle rather than creating duplicates on TAK clients.

- **FR-014-015**: Ring CoT events MUST use the CoT circle-drawing type (`u-d-c`) that ATAK and
  WinTAK render as a visible circular area overlay on the map.

- **FR-014-016**: Ring CoT events MUST NOT be emitted when `sp_rings_m` is empty; this MUST NOT
  produce an error.

- **FR-014-017**: Each ring's `stale` timestamp MUST follow the same `now + 2 × interval_s`
  rule.

#### Broadcast Timing & Lifecycle

- **FR-014-018**: The broadcaster MUST emit the first round of SP, HP, and ring CoT events
  immediately on startup (before the first interval elapses), so that TAK clients that connect
  shortly after gateway startup do not have to wait a full interval.

- **FR-014-019**: After the initial emission, the broadcaster MUST re-emit all events every
  `broadcast.interval_s` seconds until the gateway stops.

- **FR-014-020**: The broadcaster MUST run as a dedicated asyncio coroutine supervised by
  `GatewayMain`, started alongside the existing drone-track coroutines.

- **FR-014-021**: All SP, HP, and ring CoT events MUST be enqueued onto the existing CoT
  transmit queue so they are delivered through the same TAK TCP connection as drone tracks.

#### Code Integrity

- **FR-014-022**: The `generate_cot()` function in `cot/generator.py` MUST NOT be modified;
  SP/HP/ring XML generation MUST be implemented in a new module.

- **FR-014-023**: All CoT XML for SP, HP, and rings MUST be built using Python's stdlib
  `xml.etree.ElementTree`; no third-party XML library (e.g., lxml) is permitted.

#### Observability

- **FR-014-024**: The broadcaster MUST emit a structured `structlog` JSON log event at `INFO`
  level each time it completes a broadcast cycle, including: `sp_uid`, `hp_uid`, `ring_count`,
  `interval_s`.

- **FR-014-025**: Validation errors in the `broadcast` config section MUST produce a structured
  `structlog` JSON log event at `ERROR` level with `field` and `reason` keys before the gateway
  exits.

- **FR-014-026**: If the broadcaster coroutine exits unexpectedly, `GatewayMain` MUST log a
  `WARNING`-level structured event and MUST NOT propagate the exception to other coroutines.

#### Testing

- **FR-014-027**: All new broadcaster logic MUST be covered by unit tests written before the
  implementation (TDD: tests confirmed failing first, then implementation makes them pass).

- **FR-014-028**: Unit tests MUST cover: correct UID generation, correct stale calculation,
  correct ring count for various `sp_rings_m` lengths (including empty), config-load with no
  `broadcast` section, and config rejection for invalid ring radii.

---

### Key Entities

#### Configuration Models

- **`BroadcastConfig`** (new Pydantic model in `config.py`): Holds all broadcast-related
  fields — `enabled`, `interval_s`, `sp_lat/lon/alt_m/name`, `sp_rings_m`, `hp_lat/lon/alt_m/name`.
  Optional at the `GatewayConfig` level; defaults to a disabled instance when absent from YAML.

- **`GatewayConfig.broadcast`** (new field): The single entry point for all broadcast
  settings, wired into `GatewayConfig` with `Field(default_factory=BroadcastConfig)` where
  the default `BroadcastConfig` has `enabled: false`. No `Optional` or `None` needed —
  the field always exists, just disabled by default.

#### Modules

- **`cot/site_broadcaster.py`** (new module): Contains the broadcaster coroutine and CoT XML
  generation functions for SP point, HP point, and ring (`u-d-c`) events.  Depends on
  `BroadcastConfig` and the transmit `cot_queue`.

- **`cot/generator.py`** (unchanged): Drone CoT generation — MUST NOT be modified.

- **`loop.py`** (`GatewayMain`): Wires the new broadcaster coroutine into the coroutine list
  when `broadcast.enabled` is `true`. The broadcaster method is named **`sp_hp_broadcast_loop()`**
  and is launched as a dedicated `asyncio.Task` in `GatewayMain.run()`, alongside the existing
  drone-track coroutines.

#### CoT Event Shapes

- **SP CoT event**: `<event type="a-f-G-U-C" ...>` (Friendly Ground Unit — Command Post) with a
  `<point>` at SP coordinates and `<detail>` containing `<contact callsign="..."/>` and
  `<remarks>`. Renders as a starred/filled friendly symbol in ATAK.

- **HP CoT event**: `<event type="a-f-G-U-C" ...>` (Friendly Ground Unit — Command Post) with a
  `<point>` at HP coordinates and `<detail>` containing `<contact callsign="..."/>`. Distinguished
  from the SP event by its UID and the `hp_name` callsign value.

- **Ring CoT event**: `<event type="u-d-c" ...>` (user-drawn circle) with a `<point>` at SP
  coordinates and a `<detail>` containing `<shape><ellipse minor="{r}" major="{r}" angle="0"/></shape>`
  so ATAK renders it as a filled/stroked circle of the given radius.

  > **Note for implementation**: The `u-d-c` type with `<shape><ellipse>` (where `minor ==
  > major == radius_m`) is the CoT representation that ATAK renders as a circle overlay.
  > `angle="0"` means no rotation.  This is the correct approach — confirmed by TAK developer
  > documentation and ATAK field testing.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Within `2 × broadcast_interval_s` seconds of a TAK client connecting to the TAK
  Server, the SP point marker appears on the client map at the correct coordinates.

- **SC-002**: Within `2 × broadcast_interval_s` seconds of a TAK client connecting, the HP
  point marker appears on the client map at the correct coordinates.

- **SC-003**: Within `2 × broadcast_interval_s` seconds of a TAK client connecting, all
  configured SP defense rings appear as circular overlays centred on the SP, at the correct
  radii.

- **SC-004**: SP, HP, and ring markers remain continuously visible on TAK clients for as long
  as the gateway is running (i.e., they never expire during normal operation).

- **SC-005**: After a gateway restart, TAK clients see refreshed SP/HP/ring markers within one
  broadcast interval — the gap in visibility is less than `2 × interval_s` seconds.

- **SC-006**: Changing SP/HP coordinates or ring radii in `gateway.yaml` and restarting the
  gateway causes TAK clients to see the updated positions/rings within one broadcast interval,
  with no manual TAK client action required.

- **SC-007**: An existing `gateway.yaml` with no `broadcast` section starts the gateway without
  errors and continues to deliver drone CoT events normally — zero regression.

- **SC-008**: All new broadcaster code paths are covered by automated unit tests; the test suite
  passes without modification to any existing test.

- **SC-009**: The broadcaster adds no observable latency to drone-track CoT delivery; drone
  tracks continue to appear on TAK clients within the existing latency budget.

---

## Assumptions

- TAK clients (ATAK / WinTAK) support the `u-d-c` CoT type with `<shape><ellipse>` for
  circle rendering; this is standard TAK protocol behaviour.
- The existing TAK transmit queue (`queue_maxsize: 500`) provides sufficient headroom for the
  additional SP/HP/ring events (at most `2 + len(sp_rings_m)` events per interval — typically
  5 events per 30 s, negligible versus drone-track volume).
- Site coordinates are stable within a running session; no hot-reload of coordinates without
  restart is required.
- The `cot-gateway` already manages the TCP connection to the TAK Server; the broadcaster
  reuses this connection transparently via the existing CoT transmit queue.
- The `perimeter` section in `gateway.yaml` continues to hold the holding-point coordinates for
  the UDS perimeter-guard subsystem; the new `broadcast.hp_*` fields are a separate copy for
  TAK broadcasting and do not replace or alias the `perimeter.holding_*` fields.

---

## Out of Scope

- **Hot-reload of broadcast config**: Coordinate or interval changes require a gateway restart.
- **SP/HP CoT on the web-map viewer**: The web map already renders SP/HP from `sites.yaml`
  independently; this feature targets only the TAK-Server / ATAK / WinTAK path.
- **Dynamic SP/HP positions**: SP and HP are fixed ground sites; moving-target broadcasting is
  not part of this feature.
- **Per-ring styling** (colour, fill, opacity): CoT styling is controlled by the TAK client's
  local preferences; the gateway emits standard `u-d-c` events only.
- **Modifying `generate_cot()`**: Drone CoT generation is unchanged.
- **Persistence across restarts**: All state is in-memory; a restart re-broadcasts cleanly
  from scratch.
- **Broadcasting other `sites.yaml` entries** beyond SP (type `strategic_point`) and HP
  (type `holding_point`).
