<!-- SPECKIT START -->
Active feature plan: `specs/002-map-sim/plan.md` (Map Simulator — Central Object Registry, :8090).
Related artifacts: `specs/002-map-sim/spec.md`, `specs/002-map-sim/research.md`,
`specs/002-map-sim/data-model.md`, `specs/002-map-sim/contracts/rest-api.md`,
`specs/002-map-sim/quickstart.md`.
Tech stack: Python 3.11+, asyncio, aiohttp (server only), pydantic v2
(`extra="ignore"` for lenient update payloads), structlog, pytest +
pytest-asyncio + freezegun. Source lives under `services/map-sim/`,
symmetric to `services/uds/`.
Key contract notes (Clarification Q1, 2026-04-24): `GET /objects`
response `objects[].status` MUST retain the original UDS FlightState
value and MUST NEVER be overwritten by TTL state. TTL state is conveyed
by the independent boolean field `objects[].is_lost` (always explicit:
`true` iff `last_seen_s >= ttl_warn_s`, else `false`).
Upstream feature (already implemented): `specs/001-uds/` (UDS). UDS push
payload is the frozen 8-field body (`drone_id / lat / lon / alt_m /
speed_ms / heading_deg / status / timestamp`); Map Sim MUST silently
ignore extra fields (e.g. `model`, `operator_lat`, `operator_lon`) and
never reject them with 400.
<!-- SPECKIT END -->
