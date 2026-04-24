<!-- SPECKIT START -->
Active feature plan: `specs/003-echoshield-sim/plan.md` (EchoShield
Simulator — Radar sensor-layer simulator, TCP JSON feed on :9000).
Related artifacts: `specs/003-echoshield-sim/spec.md`,
`specs/003-echoshield-sim/research.md`,
`specs/003-echoshield-sim/data-model.md`,
`specs/003-echoshield-sim/contracts/tcp-feed.md`,
`specs/003-echoshield-sim/quickstart.md`.
Tech stack: Python 3.11+, asyncio (TCP server :9000), aiohttp (HTTP
client for Map Sim `GET /objects`, single-flight, 1.0s timeout),
pydantic v2 (`extra="forbid"` for config, `extra="ignore"` for MapSim
input), structlog (JSON), numpy (Gaussian noise via
`np.random.default_rng(seed)`), pytest + pytest-asyncio + freezegun.
Source lives under `services/echoshield-sim/`, symmetric to
`services/uds/` and `services/map-sim/`.
Key contract notes: TCP feed is newline-delimited compact JSON (UTF-8,
one RadarTrack per line, `\n`-terminated, no batch/keepalive). Quiet
mode: Simulator MUST NOT write any bytes when no tracks and no
due-this-tick Lost events. Grace window (`lost_grace_sec`, default
2.0s, wall-clock via `time.monotonic()`) absorbs Map Sim jitter: within
grace the original `track_id` is preserved; only on timeout is exactly
one `track_status:"Lost"` emitted and the mapping released (re-appearing
drone_id then gets a fresh `track_id`). Wire schema per spec §Key
Entities RadarTrack (authoritative over ICD-001: `latitude`/`longitude`
field names, `Active`/`Lost` status set).
Upstream features (implemented): `specs/001-uds/` (UDS),
`specs/002-map-sim/` (Map Simulator). EchoShield consumes Map Sim
`GET /objects?lat&lon&radius_m` WITHOUT `include_lost`, trusts the
server-side haversine radius filter, and MUST NOT use `objects[].status`
to influence output (radar sees "in response or not").
<!-- SPECKIT END -->
