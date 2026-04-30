# Feature Specification: Perimeter Defense

**Feature ID**: `010`
**Feature Branch**: `010-perimeter-defense`
**Created**: 2026-04-30
**Status**: Draft

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Defense Ring Visibility on Tactical Map (Priority: P1)

A TAK operator opens the CoT Gateway tactical map during an exercise.  They immediately need to know how far a drone is from the Strategic Point (SP) and which colored dashed ring it has crossed, so they can gauge threat proximity without counting pixels.  Today the map draws three concentric dashed circles around the SP (at 1 km, 2 km, and 3 km radius) but the legend does not mention them and two ring colors clash with the EchoShield radar-range circle and the Sentrycs track dot color, making it impossible to distinguish rings from sensor overlays at a glance.

**Why this priority**: The legend is the operator's key to reading the map.  An unexplained, color-conflicting ring is a trust-breaking visual noise source; fixing it is a prerequisite for any meaningful demo.

**Independent Test**: Load the `/map` page of the CoT Gateway, confirm the legend panel shows three dashed-line entries labeled "1 km defense ring", "2 km defense ring", and "3 km defense ring", confirm their colors differ from the EchoShield (#00BFFF) and Sentrycs (#FFD700) palette entries, and hover each SP ring circle to confirm its tooltip reads the correct distance label.

**Acceptance Scenarios**:

1. **Given** the tactical map is open and the demo scenario is running, **When** an operator reads the legend panel, **Then** they see exactly three dashed-line legend entries for SP range rings labeled "1 km / 2 km / 3 km defense ring" with pastel colors distinct from all sensor-range and track-dot colors.
2. **Given** any of the three dashed SP range circles is visible, **When** the operator hovers over it, **Then** a tooltip appears reading "1 km defense ring", "2 km defense ring", or "3 km defense ring" respectively.
3. **Given** EchoShield radar range and Sentrycs RF range circles are both visible, **When** an operator compares them with the SP rings, **Then** no two visible lines share the same color at a glance.

---

### User Story 2 — Perceptible Drone Movement During Demo (Priority: P2)

A product presenter runs the end-to-end demo to show a TAK stakeholder how the drone threat evolves over time.  With the current speed setting the drone moves approximately 40 m every 3 s refresh cycle at zoom level 13, which is visually imperceptible — the stakeholder sees a static dot rather than an advancing threat.

**Why this priority**: A demo where the threat appears stationary destroys narrative flow and makes the sensor detection timeline meaningless.

**Independent Test**: Start the demo scenario (`demo_single_drone.yaml`), open the map at zoom 13, and observe that the drone marker moves a clearly visible distance between two consecutive 3-second map refreshes.

**Acceptance Scenarios**:

1. **Given** the demo scenario is running at zoom 13, **When** the map refreshes every 3 seconds, **Then** the drone marker moves at least 80 m between refreshes, producing a clearly visible displacement.
2. **Given** the updated scenario speed, **When** reviewing the Sentrycs demo config comment header, **Then** the documented event timestamps (first detection, first mitigation, neutralized) are consistent with the new speed value.

---

### User Story 3 — FUSED Track Appears on Tactical Map (Priority: P2)

A sensor-fusion engineer watches the tactical map as the demo scenario progresses.  They expect to see the track dot change from blue (EchoShield) to red (Fused) when Sentrycs correlates with EchoShield, and then remain visible after the drone flies beyond EchoShield range.  Currently the fused track sometimes does not appear, and the Sentrycs detection radius is implicit rather than explicit in the demo configuration, making troubleshooting difficult.

**Why this priority**: The fused track is the centerpiece of the C-UAS sensor-fusion narrative; it must be reliably visible for the demo to tell its story.

**Independent Test**: Run the full demo scenario end-to-end; at t ≈ 75 s confirm a blue EchoShield dot; at t ≈ 125 s confirm the dot switches to red (Fused); confirm the fused track persists even after the drone travels beyond the 3 200 m EchoShield range.

**Acceptance Scenarios**:

1. **Given** only EchoShield detects the drone, **When** the track is polled from `/tracks`, **Then** the `source` field reads `"ECHOSHIELD"` and the dot appears blue on the map.
2. **Given** Sentrycs correlates with EchoShield, **When** the track is polled, **Then** the `source` field reads `"FUSED"`, the dot appears red, and the old EchoShield-keyed entry no longer appears.
3. **Given** the drone has exited EchoShield range but remains within Sentrycs detection range, **When** the map refreshes, **Then** the Fused track remains visible and its coordinates continue to update.
4. **Given** the Sentrycs simulation configuration, **When** an engineer reads `demo.yaml`, **Then** `detection_radius_m` is explicitly stated (not relying on a code default) and a structured log event is emitted whenever source correlation changes.

---

### User Story 4 — Automatic Perimeter-Based Drone Takeover (Priority: P1)

A C-UAS operator needs the system to automatically issue a takeover-to-holding-point command the moment a detected drone crosses a configurable defense perimeter around the sensor, rather than relying on a hardcoded elapsed-time threshold.  Time-based triggers break whenever the demo scenario speed or start distance is adjusted; a position-based trigger remains correct regardless of those parameters.

**Why this priority**: This is the headline new capability of Feature 010.  It makes the system operationally coherent — the defense response is proportional to physical proximity rather than an arbitrary timer — and directly underpins the name "perimeter defense".

**Independent Test**: Configure `defense_radius_m: 1000.0` in the Sentrycs demo config, run the demo scenario, and confirm the UDS takeover API call fires when and only when the drone's great-circle distance to the sensor falls below 1 000 m for the first time.  Also confirm that setting `defense_radius_m` to `null` (omitted) keeps the pre-existing time-based takeover behavior unchanged.

**Acceptance Scenarios**:

1. **Given** `defense_radius_m` is configured (e.g., 1 000 m), **When** a DETECTED drone's distance to the sensor drops below that threshold, **Then** exactly one takeover command is issued to the UDS and the track transitions to MITIGATING.
2. **Given** `defense_radius_m` is configured and the drone is already within the perimeter at the moment it is first detected, **When** the first tick processes it, **Then** the takeover is issued immediately (no wait).
3. **Given** `defense_radius_m` is configured, **When** the same drone's takeover has already been issued, **Then** no duplicate takeover command is sent on subsequent ticks.
4. **Given** `defense_radius_m` is absent or null in the config, **When** the scenario runs, **Then** the takeover is triggered by the pre-existing `mitigating_at_s` time-based rule, with no behavioral change.
5. **Given** multiple drones are tracked simultaneously, **When** drone A enters the perimeter, **Then** only drone A receives a takeover command; drone B is unaffected until it also crosses the threshold.
6. **Given** the defense perimeter feature is active and the demo config is loaded, **When** an engineer inspects `demo.yaml`, **Then** `defense_radius_m: 1000.0` is present and its purpose is clear from context.

---

### Edge Cases

- What happens when `defense_radius_m` equals exactly the distance to the drone (floating-point boundary)?  The trigger condition uses strictly-less-than (`<`), so equality does not trigger.
- What if Map Sim is temporarily unreachable and drone position is stale?  The loop skips position-based checking for that tick; no spurious takeover is issued.
- What if `defense_radius_m` is set to a value larger than `detection_radius_m`?  The drone will never reach the defense perimeter before leaving detection range; the feature is effectively disabled for that drone.  No error is raised; the config is valid.
- What if the SP ring colors are changed to pastels that happen to match future sensor overlay colors?  The colors must remain distinct from EchoShield (#00BFFF), Sentrycs (#FFD700), active-drone blue (#2196F3), lost-drone orange (#FF9800), and fused red (#FF4444).
- What if a drone disappears (DETECTED → IDLE rollback) before triggering the perimeter threshold?  The `takeover_sent` flag is only set on a successful trigger; no command is issued after removal.

---

## Requirements *(mandatory)*

### Functional Requirements

**Map Legend & Ring Colors**

- **FR-010-001**: The tactical map legend MUST include one dashed-line entry for each of the three SP defense rings, labeled "1 km defense ring", "2 km defense ring", and "3 km defense ring".
- **FR-010-002**: The three SP ring colors MUST be visually distinct from each other and from all of: EchoShield radar range (#00BFFF), Sentrycs RF range (#FFD700), active track blue (#2196F3), lost track orange (#FF9800), and fused track red (#FF4444).
- **FR-010-003**: Each SP range circle drawn on the map MUST carry a hover tooltip whose text identifies the ring distance (e.g. "1 km defense ring").
- **FR-010-004**: The existing `.leg-line` CSS class (border-top: 2px dashed) MUST be reused for the ring legend entries; no new CSS classes may be introduced solely for this purpose.

**Demo Drone Speed**

- **FR-010-005**: The UDS demo scenario MUST configure the drone's cruising speed at 35 m/s (increased from 20 m/s), producing at least 80 m of map displacement per 3-second refresh cycle at zoom 13.
- **FR-010-006**: The Sentrycs demo config comment header MUST document adjusted event timestamps consistent with the 35 m/s speed so that demo facilitators can narrate timing accurately.

**FUSED Track Reliability**

- **FR-010-007**: The `TrackSource` enum string values (`ECHOSHIELD`, `SENTRYCS`, `FUSED`) MUST match the corresponding keys in the tactical map's `SRC_COLOR` table; this match MUST be verified and confirmed in this feature.
- **FR-010-008**: The Sentrycs simulation demo config MUST explicitly declare `detection_radius_m` (8 000 m) rather than relying on the code default, so that the detection boundary is self-documenting.
- **FR-010-009**: The CoT Gateway MUST emit a structured log event whenever a source correlation change is detected (e.g., EchoShield → Fused transition), including the old UID, new UID, and entity key.

**Perimeter-Based Takeover**

- **FR-010-010**: The `SentrycsConfig` schema MUST accept an optional `defense_radius_m` field (floating-point, metres, no minimum enforced at schema level, `None` by default).
- **FR-010-011**: When `defense_radius_m` is set, the sentrycs-sim loop MUST compute the great-circle distance from the sensor position to each DETECTED drone on every tick.
- **FR-010-012**: When `defense_radius_m` is set and a DETECTED drone's distance to the sensor is strictly less than `defense_radius_m` and no takeover has been issued for that drone, the loop MUST schedule a takeover command to the UDS immediately.
- **FR-010-013**: When `defense_radius_m` is set, the pre-existing time-based takeover trigger (`mitigating_at_s`) MUST be bypassed; the scenario `mitigating_at_s` field remains in the config schema for backward compatibility but is not evaluated as a trigger.
- **FR-010-014**: When `defense_radius_m` is absent or `None`, the system MUST continue to behave exactly as before Feature 010: takeover is triggered when scenario elapsed time reaches `mitigating_at_s`.
- **FR-010-015**: The Sentrycs simulation demo config MUST set `defense_radius_m: 1000.0` to exercise the new feature end-to-end in the standard demo.
- **FR-010-016**: The perimeter takeover check MUST be idempotent: once `takeover_sent` is set for a drone, no further takeover command is issued for that drone within the same lifecycle.

### Key Entities

- **Strategic Point (SP)**: Fixed geographic coordinate that acts as the protection objective; the origin for all defense ring radii.
- **Defense Ring**: A dashed circle of fixed radius (1 km, 2 km, 3 km) drawn around the SP on the tactical map; represents threat proximity zones.
- **Defense Perimeter**: A configurable range sphere (radius = `defense_radius_m`) centered on the sensor position; crossing it inward triggers automatic takeover.
- **Detected Drone Track**: A drone observed by Sentrycs-sim with status `DETECTED`; subject to perimeter-breach evaluation each tick.
- **Takeover Command**: A UDS API call directing the drone to fly to the Holding Point (HP); issued at most once per drone lifecycle.
- **Fused Track**: A `UnifiedTrack` with `source = FUSED`, formed when Sentrycs correlates with EchoShield; replaces the EchoShield track in the store and on the map.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-010-001**: A demo facilitator can narrate "the drone has crossed the 1 km / 2 km / 3 km ring" by reading the map legend in under 5 seconds without consulting any documentation.
- **SC-010-002**: At zoom level 13, the drone marker moves a perceptibly visible distance (≥ 80 m) between two consecutive map refreshes, confirming the speed increase is effective.
- **SC-010-003**: During a complete end-to-end demo run, the Fused track appears on the tactical map and remains continuously visible from the point of first correlation until the drone is neutralized, with zero dropouts.
- **SC-010-004**: When `defense_radius_m` is configured, the takeover command fires within one tick period (≤ 0.5 s) of the drone first crossing the threshold, as confirmed by structured logs.
- **SC-010-005**: With `defense_radius_m` absent, the end-to-end demo timeline (DETECTED at t ≈ 75 s, MITIGATING at t ≈ 125 s) is preserved exactly as before Feature 010.
- **SC-010-006**: No duplicate takeover commands are issued for a single drone instance across any number of ticks after the initial takeover fires.
- **SC-010-007**: All three ring legend entries and all three ring tooltips display the correct distance labels in a fresh browser session, verified without any cached state.
- **SC-010-008**: Running `pytest` across all affected services produces zero regressions compared to the pre-010 baseline.

---

## Assumptions

- The three SP ring radii (1 km, 2 km, 3 km) are fixed for Feature 010; making them configurable via the `/sites` API is out of scope.
- Pastel colors for the rings are chosen from the Material Design 200-shade palette (e.g., Cyan 200 `#80deea`, Orange 200 `#ffcc80`, Red 200 `#ef9a9a`) unless a more suitable palette is identified during implementation; final values must pass the color-conflict check in FR-010-002.
- `detection_radius_m` defaults to 8 000 m in `SentrycsConfig`; the demo simply makes this explicit.  No change to the default value is required.
- The defense perimeter is computed from the **sensor** position (not from the SP position), consistent with how `detection_radius_m` is already applied in `_fetch_with_backoff`.
- `haversine_m` is already implemented in `sentrycs_sim.geo.wgs84` and is the correct function to reuse; no new geo utilities need to be written.
- The `mitigating_at_s` field remains **required** in `DroneScenario` for backward compatibility with existing test fixtures; it is ignored as a trigger when `defense_radius_m` is set.
- Feature 010 does not change the CoT Gateway correlator, the EchoShield adapter, the UDS takeover API, or the TAK transmitter.
- The structured correlation-change log event (FR-010-009) is added to the CoT Gateway `_emit_for_track` method, not to the sentrycs-sim.

---

## Clarifications *(pre-resolved)*

The following questions were identified during analysis and resolved based on the feature requirements document:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Should the defense perimeter be measured from the **sensor** or from the **SP**? | From the sensor position — consistent with `detection_radius_m` semantics already in `loop.py`. |
| 2 | Should `mitigating_at_s` remain required when `defense_radius_m` is set? | Yes, the field stays required in the schema for backward compatibility with existing test fixtures; it is simply not evaluated as a trigger when `defense_radius_m` is set. |
| 3 | Are `TrackSource` enum values confirmed to match JS `SRC_COLOR` keys? | Yes, confirmed: `TrackSource.ECHOSHIELD.value == "ECHOSHIELD"`, `.SENTRYCS == "SENTRYCS"`, `.FUSED == "FUSED"` — all match the JS map. No code change needed; this is a verification item. |
| 4 | Which specific pastel colors to use for the three SP rings? | Implementation should choose colors from pastel/200-shade palette satisfying FR-010-002 color-conflict rules; suggested starting point: `#80deea` / `#ffcc80` / `#ef9a9a`. Final values confirmed during implementation. |
