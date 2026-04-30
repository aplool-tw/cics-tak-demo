# Feature Specification: CoT Gateway Perimeter Guard

**Feature ID**: `011`  
**Feature Branch**: `feature/011-cot-gw-perimeter`  
**Created**: 2026-05-11  
**Status**: Draft

---

## Background

This feature resolves five root causes (RC1–RC5) that degrade the Taiwan anti-drone TAK PoC demo experience and misplace architectural responsibility:

| RC | Root Cause | Impact |
|----|-----------|--------|
| RC1 | Browser caches GET `/tracks` — track positions freeze on map | Demo shows static drone |
| RC2 | `clearLayers()` fires before fetch — sensor marker blinks on every refresh | Operator trust broken |
| RC3 | Perimeter guard lives in sentrycs-sim instead of cot-gateway | Wrong service owns takeover; cot-gateway is already the fusion authority |
| RC4 | sentrycs `detection_radius_m` is 8 000 m; should be 2 000 m | Unrealistic coverage; demo timing wrong |
| RC5 | Track shows no visual feedback after PerimeterGuard fires | Operator cannot confirm takeover has been issued |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Live Track Position Updates Without Page Reload (Priority: P1)

A demo operator opens the CoT Gateway tactical map at `http://localhost:8092/map` and watches the drone icon advance across the screen as the scenario progresses.  Today, the browser silently returns the cached first-seen position for every `fetch('/tracks')` call, so the drone appears frozen from the operator's perspective even though the underlying data is updating correctly.

**Why this priority**: A frozen drone makes the demo narrative impossible — the presenter cannot say "watch the drone cross the ring" if nothing moves.  This is the most damaging visible defect.

**Independent Test**: Open the map, confirm the drone icon moves between consecutive 2-second refresh cycles without a hard reload, and verify the browser DevTools network panel shows `Cache-Control: no-store` in the `/tracks` response headers.

**Acceptance Scenarios**:

1. **Given** the demo scenario is running, **When** the browser calls `GET /tracks`, **Then** the HTTP response includes a `Cache-Control: no-store` header and the track position reflects the latest known state on each call.
2. **Given** the browser has previously cached a `/tracks` response, **When** `refreshTracks()` fires on the next 2-second interval, **Then** the browser does not serve the stale cached entry and the drone marker position advances on the map.
3. **Given** a test client calls `GET /tracks` twice within 500 ms with the drone moving between calls, **Then** each response body contains distinct coordinate values.

---

### User Story 2 — Sensor Marker Stays Visible During Map Refresh (Priority: P1)

A TAK stakeholder is watching the EchoShield and Sentrycs sensor overlays during a live demo.  Every 30 seconds — when `refreshSites()` fires — both sensor markers and their range circles briefly disappear and then reappear.  If the fetch is slow or fails, the layers stay empty for the remainder of the demo, leaving a blank map where sensors should be.

**Why this priority**: The sensor markers anchor the entire spatial narrative.  A blinking or permanently-missing sensor icon destroys the operator's situational awareness and forces the presenter to explain a bug mid-demo.

**Independent Test**: Throttle the `/sites` endpoint to 800 ms, observe that sensor markers remain continuously visible during a `refreshSites()` call, and confirm layers are only updated after a successful response.

**Acceptance Scenarios**:

1. **Given** sensor markers are visible on the map, **When** `refreshSites()` begins a fetch, **Then** the existing sensor markers and range circles remain visible until the fetch resolves successfully.
2. **Given** a `GET /sites` fetch fails (network error or non-OK status), **When** the error is caught, **Then** the previously-rendered sensor markers and range circles remain on the map unchanged.
3. **Given** a `GET /sites` fetch succeeds, **When** the new data arrives, **Then** the layers are rebuilt atomically with the new sensor positions — no intermediate empty state is visible.
4. **Given** `GET /sites` returns an unreachable sentinel for a sensor, **When** the layers are rebuilt, **Then** the status legend shows the sensor as "unreachable" but other visible sensors remain on the map.

---

### User Story 3 — CoT Gateway Issues Takeover When Drone Enters SP Perimeter (Priority: P1)

A C-UAS supervisor needs the system to automatically command a drone takeover the moment the detected threat crosses a configurable exclusion perimeter around the Strategic Point (SP), without relying on an arbitrary elapsed-time countdown that breaks whenever scenario speed or start distance changes.  After Feature 011, this responsibility belongs to the CoT Gateway, which is already the authoritative fusion consumer of all track data and holds the SP coordinates.

**Why this priority**: This is the headline capability of Feature 011.  Moving the perimeter guard to cot-gateway gives it access to all fused tracks regardless of sensor source, aligns architectural responsibility, and makes the trigger geometry-correct.

**Independent Test**: Configure `perimeter.radius_m: 1000.0` in `cot-gateway/config/demo.yaml`, run the full demo scenario, and confirm (via structured logs) that exactly one UDS `POST /command/takeover` is dispatched when the drone's haversine distance to the SP first drops below 1 000 m.

**Acceptance Scenarios**:

1. **Given** `perimeter.radius_m` is configured in cot-gateway, **When** a DETECTED or MITIGATING track's distance to the SP drops below `radius_m`, **Then** the CoT Gateway dispatches exactly one `POST /command/takeover` to the UDS and emits a `perimeter_breach` structured log event.
2. **Given** a takeover has already been issued for a track, **When** subsequent ticks process that same track at the same or closer distance, **Then** no additional UDS call is made for that track in the same lifecycle.
3. **Given** `perimeter.radius_m` is absent or null in the cot-gateway config, **When** the gateway starts, **Then** no perimeter guard is active and no UDS calls originate from cot-gateway.
4. **Given** multiple fused tracks are active simultaneously, **When** track A enters the SP perimeter, **Then** only track A receives a takeover command; other tracks are evaluated independently.
5. **Given** a track enters the perimeter and is subsequently lost (TTL expiry), **When** a new track with the same entity key later re-enters, **Then** the idempotency latch does not prevent a fresh takeover for the new lifecycle.

---

### User Story 4 — Sentrycs Detection Coverage Limited to 2 000 m (Priority: P2)

A scenario designer reviews the Sentrycs simulation configuration and expects the `detection_radius_m` value to match the realistic 2 km RF detection range used in the demo narrative.  The current value of 8 000 m is three to four times too large, causing Sentrycs to detect the drone almost as soon as it appears on the Map Simulator, undermining the sensor-fusion storyline.

**Why this priority**: The 8 000 m radius renders the EchoShield-only phase effectively nonexistent in the demo, removing the dramatic "EchoShield alone → Fused handoff" moment that justifies the architecture.

**Independent Test**: Read `services/sentrycs-sim/config/demo.yaml`, confirm `detection_radius_m: 2000.0`, and confirm the Sentrycs RF range circle drawn on the tactical map has a radius of 2 000 m.

**Acceptance Scenarios**:

1. **Given** `detection_radius_m: 2000.0` is set, **When** the drone is at a distance greater than 2 000 m from the sensor, **Then** Sentrycs does not detect it and no SENTRYCS or FUSED track appears on the map.
2. **Given** the drone enters the 2 000 m Sentrycs range while EchoShield is already tracking it, **When** correlation fires, **Then** the track source transitions from ECHOSHIELD to FUSED.
3. **Given** the updated `demo.yaml`, **When** a developer reads the comment header, **Then** documented event timestamps (first EchoShield detection, first Sentrycs correlation, perimeter breach, neutralized) are consistent with the 35 m/s drone speed and 2 000 m Sentrycs radius.
4. **Given** `detection_radius_m` is now explicitly set in `demo.yaml`, **When** an engineer reads the file, **Then** no code-default is being silently relied upon.

---

### User Story 5 — Map Shows Orange "TAKEOVER" State for Intercepted Drones (Priority: P2)

After the CoT Gateway PerimeterGuard fires and dispatches a takeover command, a TAK operator needs the drone icon on the tactical map to change to an orange color and display "TAKEOVER" in the track panel — confirming to the operator that the intercept command has been issued without needing to consult logs.

**Why this priority**: Visual confirmation of the takeover state closes the operator feedback loop; without it the demo presenter must narrate an invisible event, which breaks the story.

**Independent Test**: Run the full demo scenario to takeover time; confirm the drone icon color changes to orange (`#FF9800`) on the tactical map and the side panel track entry shows `[TAKEOVER]` when `takeover_issued: true` is present in the `/tracks` response.

**Acceptance Scenarios**:

1. **Given** the PerimeterGuard has dispatched a takeover for a track, **When** the `/tracks` endpoint is polled, **Then** the serialized track includes `"takeover_issued": true`.
2. **Given** `takeover_issued` is `true` in a `/tracks` response, **When** `refreshTracks()` renders the track, **Then** the drone icon is drawn in orange (`#FF9800`) regardless of track source, and the side panel shows a `[TAKEOVER]` badge next to the track ID.
3. **Given** a track has `takeover_issued: false` or the field is absent, **When** the track is rendered, **Then** the icon color follows the existing `SRC_COLOR` mapping (unchanged behavior).
4. **Given** a takeover-issued track subsequently becomes "Lost" (TTL), **When** it is rendered, **Then** the lost-drone dimming still applies but the orange base color is preserved.

---

### Edge Cases

- **Drone already inside SP perimeter at first detection**: The PerimeterGuard evaluates distance on every `process_loop` tick; a drone first seen already within `radius_m` receives a takeover on its very first processed update.
- **SP coordinates not loaded** (sites file missing or empty): If the SP position cannot be determined at gateway startup, PerimeterGuard must refuse to activate and log a `perimeter_guard_disabled` warning; no silent fallback to (0, 0).
- **UDS unreachable at takeover time**: The `takeover_issued` flag in TrackStore is set only after a successful UDS dispatch (HTTP 200 or 409); a transport failure (`FAILED_TRANSPORT`) must not set the flag, allowing the next tick to retry — consistent with the existing takeover-caller contract.
- **`perimeter.radius_m` set to 0 or negative**: Config validation must reject values ≤ 0 at startup with a clear validation error.
- **Multiple tracks with same entity key** (e.g., EchoShield UID replaced by Fused UID): The idempotency latch lives on the entity key, not the CoT UID; a source-switch must not create a second takeover for the same physical drone.
- **`detection_radius_m: 2000` combined with `perimeter.radius_m: 1000`**: With a 35 m/s drone starting 3 500 m away, Sentrycs detects the drone at ≈ 2 000 m and the perimeter fires at ≈ 1 000 m; the scenario designer must verify the `detected_at_s` comment in `demo.yaml` matches these geometries.
- **Browser cache for `/sites`**: RC1 fix (`Cache-Control: no-store`) must be applied to both `/tracks` **and** `/sites` to prevent sensor positions from also freezing after the first successful fetch.
- **`clearLayers()` race during simultaneous SP and track refresh**: Because `refreshSites()` and `refreshTracks()` run on different timers (30 s vs 2 s), their asyncio callbacks are independent; the fix must not introduce cross-timer dependencies.

---

## Requirements *(mandatory)*

### Functional Requirements

#### RC1 — HTTP Cache Headers

- **FR-011-001**: The `/tracks` HTTP endpoint MUST return a `Cache-Control: no-store` response header on every response, preventing browser and intermediate-proxy caching of track coordinates.
- **FR-011-002**: The `/sites` HTTP endpoint MUST return a `Cache-Control: no-store` response header on every response.
- **FR-011-003**: The `/health` endpoint MAY omit `Cache-Control`; it is excluded from this requirement.

#### RC2 — Sensor Marker Flicker Fix

- **FR-011-004**: The `refreshSites()` JavaScript function MUST NOT call `siteLayer.clearLayers()` or `sensorLayer.clearLayers()` before `fetch('/sites')` resolves successfully.
- **FR-011-005**: Layer clearing and re-population MUST occur atomically within the `try` block after a successful (`r.ok`) response, using the newly-received data.
- **FR-011-006**: On any fetch failure (network error, non-OK status), `refreshSites()` MUST leave the existing site and sensor layers untouched and silently continue (current `catch` log behavior preserved).

#### RC3 — PerimeterGuard in CoT Gateway

- **FR-011-007**: A new `PerimeterGuardConfig` Pydantic model MUST be added to `cot_gateway.config` with fields: `enabled: bool` (default `False`), `radius_m: float` (required when enabled, `> 0`), `sp_lat: float`, `sp_lon: float`, and `uds_url: str` (the UDS endpoint base URL).
- **FR-011-008**: `GatewayConfig` MUST include a `perimeter: PerimeterGuardConfig` field (default-disabled).
- **FR-011-009**: A new Python package `cot_gateway.perimeter` MUST be created containing a `PerimeterGuard` class.
- **FR-011-010**: `PerimeterGuard` MUST use `cot_gateway.correlate.haversine.haversine_m` for all SP-to-track distance calculations; no new geo utilities or third-party packages may be introduced.
- **FR-011-011**: `PerimeterGuard.check(tracks)` MUST iterate all serialized tracks, compute the haversine distance from the SP to each track with `detection_status` of `DETECTED` or `MITIGATING`, and dispatch a UDS takeover when the distance is strictly less than `radius_m`.
- **FR-011-012**: The takeover idempotency latch in `PerimeterGuard` MUST be keyed on the track's entity key (combination of `radar_track_id` and/or `rf_track_id` as applicable) to survive CoT UID source-switches.
- **FR-011-013**: `PerimeterGuard` MUST emit a `perimeter_breach` structured log event containing `uid`, `dist_m`, and `radius_m` before dispatching the UDS call.
- **FR-011-014**: `GatewayMain.process_loop` MUST invoke `PerimeterGuard.check()` after each track update when `perimeter.enabled` is `True`.
- **FR-011-015**: The `cot-gateway/config/demo.yaml` MUST include a `perimeter:` section with `enabled: true`, `radius_m: 1000.0`, `sp_lat`, `sp_lon`, and `uds_url` set to the local UDS endpoint.

#### RC3 — sentrycs-sim Cleanup

- **FR-011-016**: The `SentrycsConfig` schema MUST remove the `defense_radius_m` field entirely; the field MUST NOT appear in any sentrycs-sim config file, schema, or test fixture after this feature.
- **FR-011-017**: `sentrycs_sim.loop.LoopRunner.run_one_tick` MUST remove the position-based perimeter check block (lines that read `self.config.defense_radius_m`), the `haversine_m` distance computation, and the `perimeter_breach` log event.
- **FR-011-018**: The `sentrycs-sim` service MUST NOT make any UDS `POST /command/takeover` calls after this feature; the `UdsClient` dependency and `_ensure_takeover_task` method MAY be retained if still exercised by other code paths, but MUST NOT be invoked by the main tick.
- **FR-011-019**: The `sentrycs-sim/config/demo.yaml` MUST NOT contain a `defense_radius_m` key after this feature.

#### RC4 — Sentrycs Detection Radius

- **FR-011-020**: The `sentrycs-sim/config/demo.yaml` MUST set `detection_radius_m: 2000.0`.
- **FR-011-021**: The comment header in `sentrycs-sim/config/demo.yaml` MUST document revised event timestamps consistent with a 35 m/s drone speed and a 2 000 m Sentrycs detection radius, including: first EchoShield detection (~`t=9 s`), first Sentrycs correlation distance, SP perimeter breach at 1 000 m, and estimated neutralized time.

#### RC5 — TAKEOVER Visual State

- **FR-011-022**: `TrackStore` MUST maintain a per-UID `takeover_issued: bool` flag (default `False`) alongside each stored `UnifiedTrack`.
- **FR-011-023**: `PerimeterGuard` MUST call `TrackStore.set_takeover_issued(uid)` after a successful UDS dispatch (HTTP 200 or 409); it MUST NOT set the flag on `FAILED_TRANSPORT`.
- **FR-011-024**: `TrackStore.get_all()` MUST include a `"takeover_issued": bool` field in each serialized track dictionary.
- **FR-011-025**: In the `/map` page JavaScript, `droneIcon()` MUST render a drone marker in orange (`#FF9800`) when `t.takeover_issued === true`, overriding the normal `SRC_COLOR` mapping.
- **FR-011-026**: When `takeover_issued` is `true`, the track panel entry MUST display a `[TAKEOVER]` badge next to the track ID.
- **FR-011-027**: The `SRC_COLOR` table and `SRC_BORDER` table in the map page JavaScript MUST NOT be modified; the TAKEOVER color override is applied only through the `takeover_issued` flag.

### Key Entities

- **PerimeterGuard**: A cot-gateway component that observes the TrackStore on every processing tick and dispatches a single UDS takeover command when a detected track enters the SP exclusion perimeter (radius `< radius_m`).
- **PerimeterGuardConfig**: Pydantic configuration sub-model attached to `GatewayConfig`; holds `enabled`, `radius_m`, `sp_lat`, `sp_lon`, `uds_url`.
- **SP Exclusion Perimeter**: A circular zone of radius `perimeter.radius_m` metres centred on the Strategic Point (`sp_lat`, `sp_lon`); crossing it inward (strictly `<`) triggers automatic takeover.
- **TrackStore (extended)**: In-memory asyncio store extended with a `takeover_issued` boolean flag per UID; flag is set when PerimeterGuard successfully dispatches a UDS call for that UID.
- **UDS Takeover Call (from cot-gateway)**: `POST {uds_url}/command/takeover` with a 4-field body identical to the existing sentrycs-sim contract (`drone_id`, `target_lat`, `target_lon`, `target_alt_m`); no `descent_speed_ms` is sent.
- **Entity Key (idempotency)**: A composite key formed from the track's `radar_track_id` and/or `rf_track_id`; used by PerimeterGuard to prevent double-takeover across CoT UID source switches.
- **Idempotency Latch**: An in-memory set within PerimeterGuard keyed on entity key; once an entry is added, no further UDS calls are made for that physical drone until the latch is cleared (on TTL expiry of all related UIDs).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-011-001**: In an end-to-end demo run, the drone icon on the tactical map moves a visually perceptible distance (≥ 70 m) between every 2-second refresh, with no position-frozen frames, as confirmed by browser DevTools network inspection showing `Cache-Control: no-store` on every `/tracks` response.
- **SC-011-002**: The EchoShield and Sentrycs sensor markers remain continuously visible throughout a 5-minute demo run with no blink, disappearance, or empty-map intervals, even under artificially-throttled network conditions (≥ 500 ms `/sites` latency).
- **SC-011-003**: The PerimeterGuard `perimeter_breach` log event appears in the cot-gateway structured log within one `process_loop` tick (≤ 250 ms) of the drone's distance to the SP first dropping below `radius_m`, as verified by log timestamp comparison.
- **SC-011-004**: Zero UDS `POST /command/takeover` calls originate from the sentrycs-sim service after Feature 011, confirmed by mock-UDS request capture in integration test.
- **SC-011-005**: For a single-drone scenario, exactly one UDS takeover call is made across the entire scenario lifecycle, regardless of how many ticks execute after the perimeter is first breached.
- **SC-011-006**: The Sentrycs RF range circle on the tactical map has a radius of 2 000 m, and the demo comment header documents timestamps consistent with a 35 m/s drone and 2 000 m detection range, verified by reading `demo.yaml`.
- **SC-011-007**: Within one map refresh cycle (≤ 2 s) of the PerimeterGuard firing, the drone icon on the tactical map turns orange and the side panel shows `[TAKEOVER]`, providing instant operator feedback without page reload.
- **SC-011-008**: Running `pytest` across `services/cot-gateway` and `services/sentrycs-sim` produces zero regressions against the pre-011 baseline (cot-gateway: ≥ 95 tests; sentrycs-sim: ≥ 117 tests) plus all new Feature 011 tests pass.
- **SC-011-009**: `ruff check` and `black --check` report zero violations across all modified Python files.

---

## Assumptions

- The PerimeterGuard SP coordinates (`sp_lat`, `sp_lon`) are explicitly set in `cot-gateway/config/demo.yaml` under the `perimeter:` section; they need not be auto-derived from `sites.yaml` (this keeps the guard independent of the sites file at runtime, though values will match).
- The UDS endpoint called by PerimeterGuard is the same `POST /command/takeover` used by sentrycs-sim; the frozen wire contract (G2) is not changed and `descent_speed_ms` is not sent.
- The takeover target coordinates sent to UDS from PerimeterGuard are the Holding Point coordinates hardcoded in `demo.yaml` (same `takeover_target_lat / lon / alt_m` pattern used by the existing sentrycs-sim scenario), not the drone's real-time position.
- `cot_gateway.correlate.haversine.haversine_m` is the authoritative geo-distance function; no new Python dependencies are added (G7).
- The `DroneRegistry`, `StateMachine`, and `_ensure_takeover_task` machinery in sentrycs-sim are retained to support future test and simulation scenarios; only the UDS call path from the main tick is removed.
- `takeover_issued` in TrackStore is a per-UID flag, not per-entity-key; the entity-key idempotency is the concern of PerimeterGuard, not TrackStore.
- Feature 011 does not change the CoT XML format, the TAK transmitter, the EchoShield adapter, or the correlator logic.
- The `mitigating_at_s` field remains in `DroneScenario` schema as a required backward-compatibility field; it continues to trigger the sentrycs-sim state transition to `MITIGATING` status (which is distinct from the takeover dispatch, now owned by cot-gateway).
- Sentrycs detection radius change (RC4) affects only the demo scenario `demo.yaml`; the `SentrycsConfig.detection_radius_m` default of 8 000 m in the Pydantic model is **not** changed (only the demo file value changes), keeping the default safe for other deployments.
- The `[TAKEOVER]` badge color (`#FF9800`) is consistent with the existing "lost-drone orange" (`#FF9800`) already referenced in the Feature 010 color palette, providing a coherent visual language: orange = degraded/intercepted.

---

## Clarifications *(pre-resolved)*

The following questions were identified during analysis and resolved based on the feature description and codebase inspection:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Should PerimeterGuard measure distance from the **SP** or from the **sensor**? | From the SP — cot-gateway owns SP coordinates and the perimeter is a "no-fly zone around the strategic point", not a sensor range. sentrycs-sim measured from sensor because it was the wrong service for this job. |
| 2 | Should `takeover_issued` flag survive a CoT UID source-switch (EchoShield→Fused)? | PerimeterGuard idempotency is keyed on entity key (not CoT UID); TrackStore flag is per-UID only. When a source-switch replaces one UID with another for the same physical drone, PerimeterGuard's entity-key latch prevents a second dispatch even though the TrackStore entry is new. |
| 3 | Does sentrycs-sim need a new config field to communicate detection events to cot-gateway? | No — cot-gateway already polls sentrycs-sim's `/detections` endpoint via `SentrycsAdapter`; no new IPC is needed. PerimeterGuard reads the already-available `detection_status` field on each `UnifiedTrack`. |
| 4 | Should the `UdsClient` in sentrycs-sim be deleted or just deactivated? | Retained — it is still exercised by existing contract tests and may be re-enabled for multi-gateway topologies. The main-tick call path is removed; the class itself is kept. |
