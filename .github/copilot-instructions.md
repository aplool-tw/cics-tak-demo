<!-- SPECKIT START -->
Active feature plan: `specs/010-perimeter-defense/plan.md` (010-perimeter-defense —
Perimeter defense for Taiwan anti-drone TAK PoC. Four items: (1) fix
tactical map legend with 3 pastel defense ring entries + tooltips;
(2) increase drone speed 20→35 m/s; (3) verify TrackSource enum matches
JS SRC_COLOR + add entity_key to source_switch log; (4) add
position-based perimeter takeover to sentrycs-sim via defense_radius_m).
Related artifacts: `specs/010-perimeter-defense/spec.md`,
`specs/010-perimeter-defense/research.md`,
`specs/010-perimeter-defense/quickstart.md`.
Key coords: SP=(24.725806, 121.033750), HP=(24.725806, 121.071889).
Ring colors: 1km=#80deea, 2km=#ffcc80, 3km=#ef9a9a (pastel, no conflicts).
Speed: 35 m/s → 105 m/refresh at zoom 13; defense_radius_m: 1000.0 m.
At 35 m/s: EchoShield entry≈9s, 2km≈43s, 1km≈71s, detected_at_s=75s.
haversine_m from sentrycs_sim.geo.wgs84 (G7 no new deps). G2: no
wire/REST contract changes; defense_radius_m is YAML-only internal config.
<!-- SPECKIT END -->
