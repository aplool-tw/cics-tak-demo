<!-- SPECKIT START -->
Active feature plan: `specs/006-006-tak-client-sim/plan.md` (TAK Client
Simulator — lightweight asyncio Python service acting as a passive TAK
client, receiving Newline-delimited CoT XML over TCP+SSL from TAK Server
:8089, parsing with stdlib xml.etree.ElementTree, and outputting
human-readable lines to stdout + structlog JSON to stderr/log-file).
Related artifacts: `specs/006-006-tak-client-sim/spec.md`,
`specs/006-006-tak-client-sim/research.md`,
`specs/006-006-tak-client-sim/data-model.md`,
`specs/006-006-tak-client-sim/contracts/tak-downlink.md`,
`specs/006-006-tak-client-sim/quickstart.md`.
Tech stack: Python 3.11+, asyncio (single TCP+SSL connection:
asyncio.open_connection + StreamReader.readuntil(b'\n', limit=65536)),
stdlib `ssl` (PoC: CERT_NONE+check_hostname=False; NO cryptography dep —
client does not need p12/client-cert), stdlib `xml.etree.ElementTree`
(no lxml), pydantic v2 `ClientConfig` (extra=forbid, frozen=True),
structlog JSON logs, pyyaml (optional --config); tests with pytest +
pytest-asyncio + freezegun. Service lives under `services/tak-client-sim/`
(hyphen), Python module `tak_client_sim` (underscore), G5-symmetric to
`services/cot-gateway/`. Key modules: connection.py (TakConnection +
exponential backoff reconnect: min(1×2^(n-1), 60)s, max_retries=0
means unlimited), parser.py (parse_cot_xml → CotEvent frozen dataclass;
source: ECHO-/SENTRYCS-/FUSED-/UNKNOWN; color: a-u-→GREY/a-h-→RED;
delta_s=max(0,round(stale-time)); oversized→cot_oversized warning,
invalid XML→cot_parse_error warning), formatter.py (format_event +
[STALE] if now-stale>30s; print() allowed here only), runner.py
(receive_loop + signal handler + graceful shutdown → session_summary).
Upstream: `specs/005-cot-gateway/` (CoT Gateway sends uplink on :8089;
frozen contracts: tak-uplink.md, cot-xml.md §7 compliance matrix 8
scenarios). Exit codes: 0=graceful, 1=max_retries exceeded, 2=config
error. G6: no persistence; G7: no cryptography/lxml/geopy.
<!-- SPECKIT END -->
