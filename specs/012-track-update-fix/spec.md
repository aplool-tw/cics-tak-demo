# Feature Specification: CoT Gateway Track Update Fix

**Feature ID**: `012`  
**Feature Branch**: `feature/012-track-update-fix`  
**Created**: 2026-04-30  
**Status**: Draft

---

## Background

This feature resolves four root causes (RC1–RC4) that produce incorrect map display and orphaned ATAK icons when the CoT Gateway handles EchoShield-to-FUSED source transitions and simultaneous multi-source tracking:

| RC | Root Cause | Impact |
|----|-----------|--------|
| RC1 | JS map uses destructive `clearLayers()` on every refresh cycle instead of a uid-keyed incremental strategy | EchoShield drone position appears frozen at first-seen value before Sentrycs engages; all markers blink on every 2-second refresh |
| RC2 | `detect_source_switch` returns only the *first* differing old uid; `_emit_for_track` removes only one stale uid from TrackStore | When FUSED supersedes both an ECHO and a SENTRYCS uid, the second orphan icon persists on ATAK indefinitely instead of being cleared |
| RC3 | `TrackStore._serialize` omits the CoT uid from the `/tracks` payload | JS cannot identify which marker corresponds to which track; uid-keyed incremental updates are impossible without this field |
| RC4 | `TrackCorrelator._within_match` subtracts `radar.timestamp − rf.timestamp` without normalising timezone-awareness | If one timestamp is naïve and the other UTC-aware, Python raises `TypeError`, silently suppressing the fusion match |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — EchoShield Drone Moves Continuously Before Sentrycs Engages (Priority: P1)

A demo operator opens the CoT Gateway tactical map at `http://localhost:8092/map` and watches the drone icon advance smoothly from the moment EchoShield detects it — well before Sentrycs comes into RF range. Today the JS layer calls `trackLayer.clearLayers()` on every 2-second poll and rebuilds all markers from scratch. Because the `/tracks` payload carries no uid field, the browser has no stable per-marker identity; on each refresh the old marker object is destroyed and a new one is placed at the just-fetched position. Under any network jitter this creates a visible snap or freeze at the first-seen coordinate and a recurring blink as the layer goes momentarily empty.

**Why this priority**: The EchoShield-only phase is the opening act of the demo narrative — "watch the radar pick up the drone". A frozen or snapping icon destroys operator trust and forces the presenter to explain a rendering artefact mid-demo. This is the most immediately visible defect.

**Independent Test**: With only EchoShield Simulator running (Sentrycs disabled), observe the drone icon on the tactical map for 30 seconds. The icon must advance continuously with no freeze, blink, or snap. Browser DevTools must show no `clearLayers()` equivalent destructive reset per poll, and each `/tracks` JSON entry must include a `uid` field.

**Acceptance Scenarios**:

1. **Given** EchoShield is tracking a drone and Sentrycs is disabled, **When** `refreshTracks()` fires on the 2-second interval, **Then** the drone marker updates its position in place (lat/lon change) without being destroyed and re-created; no flicker or disappearance occurs between consecutive refreshes.
2. **Given** the JS `droneMarkers` object already holds a marker for `uid=ECHO-TRK-001`, **When** a new `/tracks` response arrives with the same uid at updated coordinates, **Then** the existing Leaflet marker is repositioned to the new coordinates rather than a new marker being inserted.
3. **Given** a uid present in the previous `refreshTracks()` cycle is absent from the current `/tracks` response, **When** the JS processes the response, **Then** the corresponding Leaflet marker is removed from `trackLayer` and deleted from `droneMarkers`.
4. **Given** the `/tracks` HTTP response body, **When** its JSON is parsed, **Then** each track entry includes a `uid` string field whose value follows the CoT UID prefix convention (`ECHO-*`, `SENTRYCS-*`, or `FUSED-*`).

---

### User Story 2 — FUSED Track Appears and All Single-Source Ghost Icons Disappear (Priority: P1)

A TAK operator monitoring the ATAK client expects a single authoritative red FUSED icon to appear when EchoShield and Sentrycs simultaneously track the same drone, with every earlier single-source grey icon simultaneously vanishing. Currently, `detect_source_switch` returns only the *first* differing old uid it finds. If both a `radar:` and an `rf:` entity key had prior uid mappings — for example, after a brief Sentrycs-only phase before EchoShield caught up — only one stale CoT is emitted. The second orphan uid stays in TrackStore and ATAK continues showing a ghost grey icon beside the correct red FUSED icon for up to 10 seconds (until TTL expiry).

**Why this priority**: The ECHO→FUSED icon transition is the visual centrepiece of the sensor-fusion story. A ghost grey icon lingering next to the red FUSED icon directly contradicts the fusion narrative and confuses the operator about which track is authoritative.

**Independent Test**: Run the dual-sensor scenario (EchoShield first, then Sentrycs enters range). Capture all CoT XML emitted to a mock TAK Server. At the source-switch event, confirm that a `stale=time` CoT is emitted for **each** previously active single-source uid (potentially two), all before the first live FUSED CoT. Verify the `/tracks` response no longer contains entries for any superseded single-source uid immediately after the switch.

**Acceptance Scenarios**:

1. **Given** `prev_uid_by_entity_key` maps both `radar:TRK-001 → ECHO-TRK-001` and `rf:DRN-001 → SENTRYCS-DRN-001`, **When** `detect_source_switch` is called with a FUSED track (`radar_track_id=TRK-001`, `rf_track_id=DRN-001`), **Then** it returns a list containing both `ECHO-TRK-001` and `SENTRYCS-DRN-001` as old uids (order may vary) and `FUSED-DRN-001` as the new uid.
2. **Given** two old uids are identified for a source switch, **When** `_emit_for_track` processes the transition, **Then** a stale CoT with `stale=time` is enqueued for **each** old uid, each old uid is removed from `TrackStore`, and both stale CoTs appear in the transmitter queue before the first live FUSED CoT.
3. **Given** EchoShield and Sentrycs simultaneously track the same drone with positions ≤ 50 m apart and timestamps within 3 s, **When** `TrackCorrelator.correlate()` returns the FUSED track and `_emit_for_track` completes, **Then** the `/tracks` response contains an entry for `uid=FUSED-DRN-001` and contains no entries for `ECHO-TRK-001` or `SENTRYCS-DRN-001`.
4. **Given** only one old uid existed (typical ECHO→FUSED transition with no prior SENTRYCS entry), **When** `detect_source_switch` is called, **Then** it returns a list containing exactly that one old uid — the single-old-uid path is not regressed.
5. **Given** two entity keys of the same track both map to the **same** old uid in `prev_uid_by_entity_key`, **When** `detect_source_switch` collects old uids, **Then** the returned list contains that uid exactly once (deduplication enforced).

---

### User Story 3 — Correlation Succeeds Regardless of Sensor Timestamp Timezone Format (Priority: P2)

A system integrator connects a production EchoShield sensor whose driver produces naïve `datetime` objects (no timezone info attached) rather than the UTC-aware datetimes the simulator emits. The CoT Gateway's `TrackCorrelator._within_match` performs a direct subtraction between the radar and RF timestamps. When one timestamp is timezone-aware (UTC) and the other naïve, Python raises a `TypeError`, silently suppressing the fusion match. The operator sees separate grey EchoShield and Sentrycs icons instead of the expected red FUSED icon, with no error surfaced in the log.

**Why this priority**: The EchoShield and Sentrycs adapters each own their timestamp parsing independently. A library update, a production sensor swap, or a test fixture using naïve datetimes can introduce this inconsistency at any time without any code change. The correlator must be defensively timezone-safe.

**Independent Test**: Unit-inject a track pair where `radar.timestamp` is naïve and `rf.timestamp` is UTC-aware (and vice versa) into `_within_match`. Confirm no exception is raised and the time-window comparison returns the correct boolean result.

**Acceptance Scenarios**:

1. **Given** `radar.timestamp` is a UTC-aware `datetime` and `rf.timestamp` is a naïve `datetime` representing the same wall-clock instant, **When** `_within_match` computes the time delta, **Then** no `TypeError` is raised and the result is `True` (within window).
2. **Given** `radar.timestamp` is naïve and `rf.timestamp` is UTC-aware, **When** `_within_match` computes the time delta, **Then** the same timezone-safe result is produced.
3. **Given** both timestamps are already UTC-aware, **When** `_within_match` computes the time delta, **Then** the result is identical to the pre-fix behaviour (no regression).
4. **Given** both timestamps are naïve, **When** `_within_match` computes the time delta, **Then** they are both treated as UTC and the subtraction succeeds without exception.

---

### Edge Cases

- What happens if `detect_source_switch` finds the same old uid stored under two different entity keys (e.g., a prior FUSED uid is stored for both `radar:` and `rf:` keys)? → The returned list MUST deduplicate: the uid appears only once regardless of how many keys pointed to it.
- What happens if a uid is already absent from `TrackStore` when `_emit_for_track` attempts to remove it during a multi-uid source switch (e.g., TTL removal raced the source switch)? → `TrackStore.remove` is already idempotent (no-op if absent); no error may be raised.
- What happens if the JS `refreshTracks()` receives a brand-new uid not in `droneMarkers`? → A new Leaflet marker is created and inserted into both `trackLayer` and `droneMarkers`.
- What happens when `_within_match` receives two naïve datetimes? → Both are assumed UTC and treated as equivalent to two UTC-aware datetimes; the subtraction succeeds without exception.
- What happens if the Sentrycs adapter is disabled and only EchoShield is running? → `detect_source_switch` will only ever return an empty old-uid list (no source switches); the `_emit_for_track` loop over old uids is a no-op with no observable effect.

---

## Requirements *(mandatory)*

### Functional Requirements

#### RC1 & RC3 — Uid Field in `/tracks` Payload

- **FR-012-001**: `TrackStore._serialize` MUST accept the CoT uid as an additional argument and include `"uid": <uid_string>` in the returned dictionary, at the same level as `"source"`, `"lat"`, `"lon"`, and all other existing fields.
- **FR-012-002**: `TrackStore.get_all()` MUST pass the dict key (the CoT uid under which each track is stored) into `_serialize`, so the serialized payload for each track carries its authoritative uid.
- **FR-012-003**: The `/tracks` HTTP endpoint MUST reflect the updated `get_all()` output such that every JSON entry in the array includes a `"uid"` string field; no other field in the response schema may be removed or renamed (constraint G2: frozen wire contracts apply to upstream sensors and TAK, not the internal `/tracks` UI endpoint, but no regression to existing fields is permitted).

#### RC1 — Uid-Keyed Incremental Map Marker Updates

- **FR-012-004**: The `refreshTracks()` JavaScript function MUST maintain a module-level `droneMarkers` object keyed by CoT uid, initialised once at page-load time as an empty object and persisted across all subsequent `refreshTracks()` calls within the same browser session.
- **FR-012-005**: `refreshTracks()` MUST NOT call `trackLayer.clearLayers()` at any point during or before the incremental update loop.
- **FR-012-006**: On each `refreshTracks()` call, for every track entry in the `/tracks` response, the JS MUST: (a) if the uid already exists in `droneMarkers`, update the existing marker's position, icon, tooltip, and popup content in place using Leaflet marker mutation APIs (`setLatLng`, `setIcon`, `setPopupContent`, or equivalent); (b) if the uid does not exist in `droneMarkers`, create a new Leaflet marker, add it to `trackLayer`, and store it in `droneMarkers[uid]`.
- **FR-012-007**: On each `refreshTracks()` call, for every uid present in `droneMarkers` that is **absent** from the current `/tracks` response, the JS MUST remove the corresponding marker from `trackLayer` (via `trackLayer.removeLayer()` or equivalent) and delete the entry from `droneMarkers`.
- **FR-012-008**: The `track_panel` side-list (`#track-list`) MAY continue to be fully rebuilt on each refresh cycle; incremental uid-keyed update is required only for the Leaflet marker layer.

#### RC2 — Source-Switch Multi-Uid Cleanup

- **FR-012-009**: `detect_source_switch(track, prev_uid_by_entity_key)` MUST return a 2-tuple of type `(list[str], str)` — a list of all distinct old uids and the new uid — replacing the current `(Optional[str], str)` signature.
- **FR-012-010**: The old-uid list MUST contain every uid found in `prev_uid_by_entity_key` under any entity key of the track that differs from `new_uid`, with duplicates removed; each distinct old uid MUST appear at most once.
- **FR-012-011**: When no prior uid differs from `new_uid` (or the track has no prior mapping), `detect_source_switch` MUST return `([], new_uid)` — an empty list rather than `None`.
- **FR-012-012**: `GatewayMain._emit_for_track` MUST iterate the full old-uid list; for **each** old uid it MUST: (a) enqueue a final stale CoT with `force_stale_eq_time=True` and `override_uid=old_uid`; (b) call `await self._track_store.remove(old_uid)` (when TrackStore is available); (c) discard the old uid from `self.seen_uids`; and (d) emit one `source_switch` structured log event per old uid.
- **FR-012-013**: All stale CoTs for old uids MUST be enqueued before the live CoT for the new uid is enqueued; transmission order MUST reflect: stale-CoT-1 … stale-CoT-N → live-CoT-new.
- **FR-012-014**: All existing call sites that unpack `detect_source_switch`'s return value (including `_emit_for_track` and all test files) MUST be updated to the `(old_uids, new_uid)` pattern; no compatibility shim for the old `Optional[str]` return is provided.

#### RC4 — Timezone-Safe Timestamp Comparison

- **FR-012-015**: `TrackCorrelator._within_match` MUST normalise both `radar.timestamp` and `rf.timestamp` to UTC-aware `datetime` objects before computing the absolute time delta; a naïve `datetime` (one whose `tzinfo` is `None`) MUST be treated as UTC by calling `.replace(tzinfo=timezone.utc)`.
- **FR-012-016**: The normalisation MUST operate on local variables only; `UnifiedTrack.timestamp` fields MUST NOT be mutated; no adapter, model, or other module is changed.
- **FR-012-017**: No new third-party packages or standard-library imports beyond `datetime.timezone` (already used in `correlator.py`) may be introduced to implement this normalisation (constraint G7).

#### Testing Requirements

- **FR-012-018**: All existing test cases in `test_uid_source_switch.py` that assert on the return value of `detect_source_switch` MUST be updated to unpack and assert against the new `(list[str], str)` signature.
- **FR-012-019**: A new unit test MUST verify that `detect_source_switch` returns **both** `ECHO-TRK-001` and `SENTRYCS-DRN-001` in the old-uid list when both `radar:TRK-001` and `rf:DRN-001` previously mapped to distinct single-source uids.
- **FR-012-020**: A new unit test MUST verify that when two entity keys of the same track both map to the same old uid, the returned list contains that uid exactly once.
- **FR-012-021**: A new integration or unit test MUST verify the `_emit_for_track` multi-uid source-switch path: given two old uids, both stale CoTs appear in the transmitter queue before the live CoT, and both old uids are absent from `TrackStore` and `seen_uids` afterwards.
- **FR-012-022**: A new unit test for `TrackCorrelator._within_match` MUST cover all four timezone combinations (aware/aware, aware/naïve, naïve/aware, naïve/naïve) and confirm no exception is raised and the correct within-window boolean is returned in each case.
- **FR-012-023**: The contract test suite (`tests/contract/`) MUST pass without modification to any contract fixture file, confirming that the EchoShield TCP wire, Sentrycs `/detections` wire, TAK CoT XML format, and UDS `/command/takeover` body remain unchanged (constraints G2 and G7).

### Key Entities

- **`droneMarkers` (JS module-level object)**: A persistent JavaScript object keyed by CoT uid, holding references to live Leaflet `Marker` instances for each active drone track; populated and maintained incrementally across `refreshTracks()` calls instead of being rebuilt from scratch each cycle.
- **`TrackStore._serialize` (extended)**: The per-track serialization helper, updated to accept and embed the `uid` key so the `/tracks` response carries the authoritative CoT uid for each entry.
- **`detect_source_switch` (updated signature)**: Returns `(list[str], str)` — all distinct old uids whose prior mappings differ from the new uid, deduplicated — enabling multi-uid stale CoT emission on a single source-switch event.
- **`GatewayMain._emit_for_track` (updated)**: Iterates all old uids from the source-switch list; for each, emits a stale CoT, removes the uid from TrackStore and `seen_uids`, and logs a `source_switch` event; then emits the single live CoT for the new uid.
- **Timezone Normalizer (inline in `_within_match`)**: A two-line guard pattern applied to both timestamps before subtraction, converting naïve datetimes to UTC-aware without mutating track objects.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-012-001**: During the EchoShield-only phase of the demo scenario, the drone marker advances by a visually perceptible distance (≥ 70 m) between every 2-second refresh cycle with no freeze, snap, or marker disappearance, confirmed by manual inspection and absence of `clearLayers()` calls in `refreshTracks()`.
- **SC-012-002**: When EchoShield and Sentrycs simultaneously track the same drone and a FUSED track is established, the mock-TAK-Server CoT capture shows exactly one stale CoT (`stale=time`) for **every** superseded single-source uid, and all such stale CoTs precede the first live FUSED CoT in transmission order.
- **SC-012-003**: Every entry in the `/tracks` JSON response includes a `"uid"` field matching the `ECHO-*`, `SENTRYCS-*`, or `FUSED-*` prefix convention; verified by a test client polling the endpoint during a live scenario.
- **SC-012-004**: Unit tests for `detect_source_switch` cover the zero, one, and two old-uid cases; all pass, and no test raises an exception due to the signature change.
- **SC-012-005**: `TrackCorrelator._within_match` raises no exception across all four naïve/aware timestamp combinations; confirmed by the new unit test covering all four cases.
- **SC-012-006**: Running `pytest` across `services/cot-gateway` produces zero regressions against the pre-012 baseline plus all new Feature 012 tests pass; `ruff check` and `black --check` report zero violations across all modified files.
- **SC-012-007**: No existing wire contract fixture files (EchoShield TCP JSON, Sentrycs `/detections`, TAK CoT XML, UDS `/command/takeover`) are modified; the contract test suite passes without any fixture changes, confirming constraints G2 and G7 are preserved.

---

## Assumptions

- The `uid` field added to the `/tracks` payload is used exclusively by the JS map layer for incremental marker management; it does not affect CoT XML generation, ATAK display, PerimeterGuard logic, or any other server-side component.
- Naïve `datetime` objects appearing in sensor timestamps are assumed to represent UTC; no DST or local-timezone interpretation is applied. This assumption aligns with the existing adapter convention of always producing UTC-aware datetimes; the normalisation in `_within_match` acts as a defensive guard, not a conversion.
- The `droneMarkers` JS object is initialised once at page-load time as `{}` and persists across `refreshTracks()` calls within the same browser session; a full page reload resets it, which is acceptable behaviour for a demo map.
- `detect_source_switch` callers outside `_emit_for_track` — primarily the test file `test_uid_source_switch.py` — must update their unpack patterns as part of this feature; no backwards-compatibility shim for the old `Optional[str]` return value is provided.
- `TrackStore._serialize` currently receives the track object only; passing the uid as a second argument is a minimal, non-breaking change to the helper's internal call signature (it is a module-level private function, not part of any public API or wire contract).
- Feature 012 does not change the CoT XML format, the TAK transmitter, the EchoShield adapter, the Sentrycs adapter, the PerimeterGuard, or the `TrackStore` class public API (`upsert`, `remove`, `mark_takeover`, `get_all`).
- No new Python runtime dependencies are introduced; `datetime.timezone` from the standard library is sufficient for timezone normalisation (constraint G7).
- The frozen wire contracts (constraint G2) — UDS `/command/takeover` body schema, EchoShield TCP JSON format, Sentrycs `/detections` JSON format, TAK CoT XML format — remain unmodified by this feature.

---

## Clarifications *(pre-resolved)*

### Session 2026-04-30

- No additional clarifications required. A full ambiguity scan across all taxonomy categories (Functional Scope, Domain & Data Model, Interaction & UX Flow, Non-Functional Quality Attributes, Integration & External Dependencies, Edge Cases & Failure Handling, Constraints & Tradeoffs, Terminology, Completion Signals, Misc/Placeholders) found every category **Clear**. All root causes (RC1–RC4), acceptance scenarios, success criteria, out-of-scope declarations, wire-contract constraints (G2, G7), and edge cases are sufficiently specified. No scope changes were made.

The following questions were identified during codebase analysis and resolved prior to spec completion:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Should the `uid` field in `/tracks` use the TrackStore dict key or be re-derived from the track object? | Use the TrackStore key passed into `_serialize` from `get_all()`'s `self._data.items()` iteration. This is the authoritative uid already stored and guaranteed to match the CoT uid emitted to ATAK; re-deriving would risk divergence if the track object's fields are stale. |
| 2 | Should `detect_source_switch` return `(list[str], str)` breaking the old `(Optional[str], str)` contract? | Yes — the return type changes to `(list[str], str)`. The only production call site is `_emit_for_track` (one file) and the only test call site is `test_uid_source_switch.py`; both are within the scope of this feature. An empty list replaces `None`, making the iteration pattern uniform. |
| 3 | Should `_within_match` normalisation mutate `UnifiedTrack.timestamp` or use local copies? | Local copies only. Two-line inline guard: `ts = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t` applied to both timestamps before subtraction. `UnifiedTrack` objects MUST NOT be mutated by the correlator. |
| 4 | Does the uid-keyed JS approach require changes to `refreshSites()` or sensor marker logic? | No. The sensor layer flicker fix (moving `clearLayers()` after successful fetch) was delivered in Feature 011. Only `refreshTracks()` and the drone `trackLayer` are in scope for this feature. |
| 5 | Does adding `uid` to `/tracks` break the Feature 011 takeover visual or the `/map` page panel? | No. The panel rendering loop reads existing fields (`t.source`, `t.lat`, `t.lon`, `t.takeover_issued`, etc.); adding a new `uid` field is additive and does not affect any existing panel or icon logic. |
