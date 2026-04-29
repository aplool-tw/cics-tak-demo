<!-- SPECKIT START -->
Active feature plan: `specs/007-scenario/plan.md` (007-e2e-scenarios —
End-to-end scenario validation with strategic coordinates for Taiwan
anti-drone TAK PoC. Delivers two scenario YAML sets (single-drone
invasion + three-drone multi-direction), EchoShield e2e config, and
validation scripts).
Related artifacts: `specs/007-scenario/spec.md`,
`specs/007-scenario/research.md`,
`specs/007-scenario/data-model.md`,
`specs/007-scenario/quickstart.md`,
`specs/007-scenario/contracts/scenario-yaml.md`,
`specs/007-scenario/contracts/sentrycs-yaml.md`.
Key coords: SP=(24.725806, 121.033750), HP=(24.725806, 121.071889).
Scenario 1: TRK-E01 (15m/s, N→S, 8.99km) milestones M3=460s, M4=525s.
Scenario 2: TRK-E0A/B/C (12m/s) M4 at 666/489/684s.
Critical finding: dev-launcher.sh echoshield sensor hardcoded at
(24.0, 121.0) — 80.9km from SP → Phase F adds --echoshield-config
param + `services/echoshield-sim/config/e2e_scenario.yaml`
(sensor at SP, max_range_m=3200). Validation: validate_scenario.py
(map-sim poll M1 + tak-client-sim log parse M2-M4) + validate_cot.py
(CoT type/stale/uid compliance). No new Python deps; Haversine
self-implemented (G7). G2: no frozen contract changes.
<!-- SPECKIT END -->
