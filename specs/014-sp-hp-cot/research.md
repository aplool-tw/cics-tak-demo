# Research: SP/HP CoT Broadcasting (Feature 014)

**Status**: Complete — all NEEDS CLARIFICATION resolved  
**Date**: 2026-05-06  

---

## 1. CoT `u-d-c` Circle Format

### Decision
Use CoT type `u-d-c` with `<shape><ellipse minor="{r}" major="{r}" angle="0"/></shape>` inside `<detail>`. Set `minor` and `major` equal to the ring radius in metres to produce a perfect circle.

### Rationale
`u-d-c` ("user-drawn circle") is the TAK standard for persistent circular area overlays. ATAK and WinTAK both render this type as a stroked circle on the map, centred on the `<point>` element, with the radius driven by the `ellipse` semi-axes (in metres). This is distinct from `a-r-*` (hostile range ring) and `u-d-r` (rectangle), which are different drawing primitives.

The `<ellipse>` element requires exactly three attributes:
- `minor`: semi-minor axis (metres) — for a circle, equals `major`
- `major`: semi-major axis (metres) — for a circle, equals `minor`
- `angle`: rotation in degrees from north — `"0"` for an unrotated circle

The `<point>` is placed at the **centre** of the circle (SP coordinates), not the circumference.

### Confirmed XML skeleton

```xml
<event version="2.0"
       uid="CICS-014-SP-RING-1000"
       type="u-d-c"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0"
         ce="9999999.0" le="9999999.0"/>
  <detail>
    <shape>
      <ellipse minor="1000.0" major="1000.0" angle="0"/>
    </shape>
  </detail>
</event>
```

**`ce`/`le` values for drawings**: Set to `9999999.0` (TAK convention for "unknown / not applicable") because circular-error and linear-error concepts do not apply to drawing overlays. Using the drone-track values (`ce="10.0"`, `le="5.0"`) would be misleading and may confuse ATAK's CoT accuracy display.

**`how` value**: `"h-e"` (human entered/estimated). TAK uses this for all operator-placed annotations. Alternative `"h-g-i-g-o"` (human-generated geospatial image overlay) is also used in some TAK implementations but `h-e` is the simpler, widely accepted choice for drawing overlays.

### Alternatives Considered
- `a-r-*` (range ring) — renders differently; requires hostile/friendly affiliation context; not appropriate for defensive perimeter overlays.
- KML/SHP import into TAK — out-of-band, not automatable from the gateway.
- Repeating the CoT as a `<sensor>` element — for sensor FOV overlays; wrong primitive.

---

## 2. `a-f-G-U-C` Point Marker Format

### Decision
Use CoT type `a-f-G-U-C` for both SP and HP point markers, with `<contact callsign="..."/>` in `<detail>` to set the operator-visible label.

### Rationale
`a-f-G-U-C` decodes as:
- `a` — atom (a physical entity)
- `f` — friendly (blue in ATAK's MIL-STD-2525 symbology)
- `G` — ground
- `U` — unit
- `C` — command post

This renders in ATAK as a **filled star in blue** — the standard MIL-STD-2525 symbol for a friendly command post. It is the correct TAK convention for ground infrastructure (radar sites, control points, landing zones) operated by the blue-force.

Both SP and HP use the same type; they are distinguished by their stable UIDs (`CICS-014-SP` / `CICS-014-HP`) and their `callsign` values.

### Confirmed XML skeleton

```xml
<event version="2.0"
       uid="CICS-014-SP"
       type="a-f-G-U-C"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0"
         ce="10.0" le="5.0"/>
  <detail>
    <contact callsign="Strategic Point"/>
    <remarks>Site: SP</remarks>
  </detail>
</event>
```

**`ce`/`le` for ground markers**: `ce="10.0"` and `le="5.0"` (metres) — same as drone track CoT. These are reasonable positional-accuracy values for fixed ground infrastructure surveyed to GPS accuracy.

**`<remarks>` content**: Short human-readable label (`"Site: SP"` / `"Site: HP"`). Used in the CoT detail pop-up in ATAK. Not required for rendering but adds operational clarity.

### Alternatives Considered
- `a-f-G-I` (friendly ground installation) — also valid but less common; `a-f-G-U-C` is more widely recognised in TAK deployments for COP markers.
- `b-m-p-w` (waypoint) — renders as a plain point, no MIL symbology; loses the "command post" semantic.
- `a-n-G-U-C` (neutral) — wrong affiliation; SP and HP are blue-force assets.

---

## 3. Stale Time Strategy

### Decision
`stale = now + 2 × broadcast_interval_s`

### Rationale
The stale time serves two purposes:
1. **Marker persistence**: The marker must remain visible on TAK clients between re-broadcast cycles. Setting `stale = now + 1 × interval_s` would cause the marker to expire exactly at the next re-broadcast, creating a visible flicker.
2. **Auto-expiry on gateway stop**: The marker should eventually disappear if the gateway goes offline permanently. `2 × interval_s` means the marker expires within one missed cycle.

At `interval_s = 30`:
- First broadcast at t=0: `stale = t0 + 60s`
- Second broadcast at t=30: `stale = t30 + 60s = t0 + 90s`
- The marker's stale refreshes from `t0+60` to `t0+90` at t=30 — well before expiry.
- If the gateway stops at t=30, the last-known stale is `t30+60 = t0+90s`, so clients see the marker for up to 60 more seconds before auto-expiry.

This is identical to the strategy used by ATAK itself for SA (Situational Awareness) tracks and is the TAK community consensus approach for periodic re-broadcast of persistent overlays.

### Alternatives Considered
- `stale = now + 1 × interval_s`: Risk of visible flicker; acceptable only if broadcast is rock-solid reliable (it is not when TAK server is temporarily unavailable).
- `stale = far future (e.g. +24h)`: Marker persists long after gateway shutdown; confusing for operators. Violates the auto-expiry requirement.
- Dynamic stale (extending on each re-broadcast): Equivalent to `now + 2×interval` in practice; adds implementation complexity for no benefit.

---

## 4. Why `xml.etree.ElementTree` Is Sufficient (G7 Constraint)

### Decision
Use `from xml.etree import ElementTree as ET` exclusively. No lxml, no minidom, no third-party XML library.

### Rationale

CoT 2.0 XML is a **shallow, flat structure** with at most three levels of nesting (event → detail → shape/contact/remarks). ElementTree's `ET.Element()` / `ET.SubElement()` / `ET.tostring()` API handles this structure directly without any XPath, XSLT, namespace management, or schema validation — none of which CoT requires.

Specific sufficiency evidence from existing codebase:
- `cot/generator.py` already uses `ET` for drone track CoT (the most complex CoT shape in the codebase) — the SP/HP/ring structures are simpler.
- The existing drone CoT test suite (`test_cot_generator.py`) validates XML correctness using `ET.fromstring()` — the same approach works for site broadcaster tests.
- CoT XML is ASCII-safe; no Unicode normalisation or encoding edge-cases arise.

`ET.tostring(event, encoding="unicode")` produces a compliant UTF-8 string without an XML declaration — correct for CoT messages injected into a TCP stream (TAK Server expects no XML declaration).

### Alternatives Considered
- **lxml**: Faster and more featureful, but an additional dependency (`pip install lxml`) that must be pinned and audited. Zero benefit for CoT's shallow structure. Violates the explicit G7 constraint.
- **`xml.dom.minidom`**: stdlib but verbose; `toprettyxml()` inserts whitespace that CoT parsers tolerate but that adds unnecessary bytes to the TCP stream.
- **`defusedxml`**: Adds XSS/XXE protection — relevant for parsing untrusted input, not for generating trusted output.

---

## 5. UID Scheme

### Decision
- SP marker UID: `"CICS-014-SP"`
- HP marker UID: `"CICS-014-HP"`
- Ring UIDs: `"CICS-014-SP-RING-{int(radius_m)}"` where `int()` truncates (not rounds) the radius

### Rationale
UIDs must be:
1. **Stable** — same value every broadcast cycle so TAK clients update the existing item rather than creating duplicates
2. **Deterministic** — derivable from config at startup without any persistent state
3. **Unique** — no collision with drone track UIDs (those use `ECHO-`, `SENTRYCS-`, `FUSED-` prefixes)

The `CICS-014-` prefix namespaces all site-broadcaster UIDs under the project (`CICS`) and feature ID (`014`). This avoids collisions with future features or other gateway instances.

For ring UIDs, using `int(radius_m)` means `1000.0` → `"CICS-014-SP-RING-1000"` and `2500.5` → `"CICS-014-SP-RING-2500"`. This is acceptable because: (a) ring radii are operator-configured round numbers in practice; (b) if radii do have decimals, the truncation is consistent across all broadcasts of the same config.

### Alternatives Considered
- UUID4: Non-deterministic; creates duplicates on every restart.
- Hash of coordinates: Opaque; harder to debug from TAK client CoT detail view.
- `"SP"` / `"HP"` (unqualified): Collision risk with other TAK Server users broadcasting their own SP/HP markers in multi-agency exercises.
