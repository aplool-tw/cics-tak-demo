<!-- SPECKIT START -->
Active feature plan: `specs/011-cot-gw-perimeter/plan.md` (011-cot-gw-perimeter —
CoT Gateway Perimeter Guard for Taiwan anti-drone TAK PoC. Five RC fixes:
RC1 Cache-Control no-store on /tracks+/sites; RC2 clearLayers() moved
inside refreshSites() success branch; RC3 new PerimeterGuard module in
cot_gateway/perimeter/ fires UDS POST /command/takeover when DETECTED or
MITIGATING track crosses SP exclusion radius (haversine from
cot_gateway.correlate.haversine); RC4 sentrycs detection_radius_m 8000→2000;
RC5 takeover_issued flag in TrackStore + orange #FF9800 drone icon + [TAKEOVER]
badge. sentrycs-sim defense_radius_m removed; time-based DETECTED→MITIGATING
transition replaces UDS call in loop step 4. No new dependencies (aiohttp
already present). G2: UDS wire unchanged {drone_id,target_lat,target_lon,
target_alt_m}; takeover_issued additive in /tracks response.
Key coords: SP=(24.725806, 121.033750), HP=(24.725806, 121.071889).
Timeline at 35 m/s from 3500m: EchoShield≈9s, Sentrycs≈43s, breach≈71s.
Related artifacts: `specs/011-cot-gw-perimeter/spec.md`,
`specs/011-cot-gw-perimeter/research.md`,
`specs/011-cot-gw-perimeter/quickstart.md`.
<!-- SPECKIT END -->
