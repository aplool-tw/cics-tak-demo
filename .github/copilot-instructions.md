<!-- SPECKIT START -->
Active feature plan: `specs/004-sentrycs-sim/plan.md` (Sentrycs Simulator —
passive RF C-UAS sensor + active takeover trigger, HTTP JSON Status API
on :7070).
Related artifacts: `specs/004-sentrycs-sim/spec.md`,
`specs/004-sentrycs-sim/research.md`,
`specs/004-sentrycs-sim/data-model.md`,
`specs/004-sentrycs-sim/contracts/http-status-api.md`,
`specs/004-sentrycs-sim/contracts/takeover-caller.md`,
`specs/004-sentrycs-sim/quickstart.md`.
Tech stack: Python 3.11+, asyncio, aiohttp (dual-use: HTTP client for
Map Sim `GET /objects` + UDS `POST /command/takeover`, AND aiohttp.web
server for :7070 Status API), pydantic v2 (`extra="forbid"` on scenario
YAML and wire schema), structlog (JSON), pyyaml; tests with pytest +
pytest-asyncio + freezegun + jsonschema. Service lives under
`services/sentrycs-sim/`, symmetric to `services/uds/`,
`services/map-sim/`, and `services/echoshield-sim/` (adds `uds/`,
`state/`, `api/` sub-packages).
Key contract notes: `GET /detections` returns an array of non-IDLE
DroneTrack (IDLE excluded; empty → `[]` with HTTP 200, never 404);
`GET /detection/{uid}` returns a single object or 404; `GET /health` for
liveness. 14 required fields per detection (FR-SC-016) including
`operator_lat/lon/distance_m/bearing_deg`. `model` is NOT from Map Sim —
it is looked up from scenario YAML `drones[*].model` via a `uid → model`
table built at startup; unknown uid outputs `"Unknown"` + error log and
MUST NOT block. Operator position is computed ONCE via WGS84 destination
formula when a DroneTrack is created, then frozen for the whole scenario
(SC-SC-004 zero jitter). Map Sim poll runs at 2 Hz (0.5s) with
exponential backoff 1/2/4/10s; non-IDLE state MUST NOT regress during
Map Sim outage. UDS takeover: exactly once per drone (FR-SC-010); HTTP
200 and 409 both transition to MITIGATING; 400/404 latch
`takeover_sent=True` with no retry; timeout/5xx/connection error allows
next-tick retry only. Graceful shutdown in ≤ 3s on SIGINT/SIGTERM.
Upstream features (implemented): `specs/001-uds/` (UDS),
`specs/002-map-sim/` (Map Simulator), `specs/003-echoshield-sim/`
(EchoShield). Sentrycs consumes Map Sim
`GET /objects?lat&lon&radius_m=8000` filtering out `is_lost=true`
(FR-SC-007, passive RF cannot locate lost targets); calls UDS
`POST /command/takeover` per `specs/001-uds/contracts/rest-api.md §1`
with exactly 4 fields (`drone_id`, `target_lat`, `target_lon`,
`target_alt_m=0.0`).
<!-- SPECKIT END -->
