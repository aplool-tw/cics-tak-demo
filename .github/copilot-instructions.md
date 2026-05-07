<!-- SPECKIT START -->
Active feature plan: `specs/016-tak-shared-connection/plan.md` (016-tak-shared-connection —
TAK Shared Connection Library + Unified Remote Config).
RC1: New Python package libs/tak-connection with TakConnectionConfig (Pydantic v2, frozen,
extra=forbid, 7 fields: host/port/use_ssl/use_ssl_verify/cert_file/cert_password/ca_bundle)
and build_ssl_context(cfg) → ssl.SSLContext (PEM direct load + P12→temp PEM via cryptography,
cert_file=None → CA-only TLS, temp file cleanup via try/finally fix).
RC2: cot-gateway tak/ssl_context.py → thin wrapper constructing TakConnectionConfig from
TakServerConfig fields, delegating to tak_connection.ssl_context.build_ssl_context(). Add
tak-connection @ file://../../../libs/tak-connection to cot-gateway pyproject.toml.
RC3: tak-client-sim connection.py → wrapper constructing TakConnectionConfig with
cert_file=None (no client cert), delegating to tak_connection.build_ssl_context(). Add
tak-connection + cryptography deps to tak-client-sim pyproject.toml.
RC4: New config/remote-tak.yaml at repo root (committed, tak_server block only, placeholder
IP 192.168.1.100). Remove services/cot-gateway/config/remote-tak.yaml and
services/tak-client-sim/config/remote-tak.yaml.
RC5: Refactor demo-1drone-remote-tak.sh and demo-3drone-remote-tak.sh: replace TAK_HOST
env-var detection with config/remote-tak.yaml file-existence check + python3 YAML parse.
Pass --host/--port to tak-client-sim in remote mode. Remove TAK_HOST/TAK_PORT/TAK_USE_SSL
env-var code paths.
G1 TDD: libs/tak-connection tests written BEFORE implementation, confirmed FAIL. G2: Both
TakServerConfig and ClientConfig retain exact YAML field names/defaults. G7: only pydantic +
cryptography (both pre-approved). 209 cot-gateway + 99 tak-client-sim tests must stay green.
Related artifacts: `specs/016-tak-shared-connection/spec.md`,
`specs/016-tak-shared-connection/research.md`, `specs/016-tak-shared-connection/quickstart.md`.
<!-- SPECKIT END -->
