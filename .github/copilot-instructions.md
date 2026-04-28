<!-- SPECKIT START -->
Active feature plan: `specs/005-cot-gateway/plan.md` (CoT Gateway —
fuses EchoShield radar TCP JSON :9000 + Sentrycs C-UAS HTTP :7070 into
MIL-STD-2525C CoT 2.0 XML, pushed to TAK Server over TCP+SSL :8089
with newline-delimited framing).
Related artifacts: `specs/005-cot-gateway/spec.md`,
`specs/005-cot-gateway/research.md`,
`specs/005-cot-gateway/data-model.md`,
`specs/005-cot-gateway/contracts/cot-xml.md`,
`specs/005-cot-gateway/contracts/echodyne-wire.md`,
`specs/005-cot-gateway/contracts/sentrycs-poller.md`,
`specs/005-cot-gateway/contracts/tak-uplink.md`,
`specs/005-cot-gateway/quickstart.md`.
Tech stack: Python 3.11+, asyncio (TCP client for EchoShield + TCP+SSL
client for TAK + 5 concurrent coroutines: echodyne_adapter /
sentrycs_adapter / process_loop / ttl_loop / tak_sender), aiohttp
(HTTP client only, polling Sentrycs at 1 Hz; Gateway does NOT open any
HTTP port), stdlib `ssl` + `cryptography` for `gateway.p12` → PEM
loading (PoC `verify_mode=CERT_NONE`), stdlib `xml.etree.ElementTree`
for CoT XML (no lxml), pydantic v2 for `GatewayConfig` YAML, structlog
JSON logs; tests with pytest + pytest-asyncio + freezegun. Service
lives under `services/cot-gateway/` (hyphen), Python module
`cot_gateway`, symmetric to `services/uds/`, `services/map-sim/`,
`services/echoshield-sim/`, `services/sentrycs-sim/` (adds
`echoshield/`, `sentrycs/`, `correlate/`, `cot/`, `tak/` sub-packages).
Key contract notes: CoT `type` is source-bound and fixed over the
source lifetime (`ECHOSHIELD`/`SENTRYCS` → `a-u-A-M-F-Q-r` gray,
`FUSED` → `a-h-A-M-F-Q-r` red); status differences (DETECTED /
MITIGATING / NEUTRALIZED / Lost) encoded ONLY via `<remarks>` and
3-tier `stale` (Lost = `time` / NEUTRALIZED = `time + 30s` / others =
`time + 11s`). UID prefix switches (ECHO-/SENTRYCS-/FUSED-) MUST emit
a 2-message transition: old-uid `stale=time` clear + new-uid first CoT
(FR-GW-014). TrackCorrelator uses Haversine ≤ 50 m and |Δt| ≤ 3 s,
no one-to-many, closest-wins; TTL 10 s → Lost. EchoShield reconnect:
unlimited retries at 5 s interval. TAK reconnect: exponential backoff
1→60 s capped, max_retries=5 → non-zero exit. `cot_queue` maxsize=500
drop-newest on overflow. All timestamps UTC aware; CoT `time` from
`datetime.now(timezone.utc)` with ms precision ISO 8601 (`Z` suffix).
Upstream features (implemented): `specs/001-uds/`, `specs/002-map-sim/`,
`specs/003-echoshield-sim/` (wire schema reused via
`contracts/echodyne-wire.md`), `specs/004-sentrycs-sim/` (HTTP API
reused via `contracts/sentrycs-poller.md`). Downstream: TAK Server
container (Feature 001 infrastructure) on `:8089`.
<!-- SPECKIT END -->
