# 006 — TAK Server Docker stack & PoC PKI

## Scope

Provide a self-contained TAK Server tier so developers can exercise the full
sensor → CoT Gateway → TAK uplink loop without a TAK.gov account or external
licensing. Includes a swap path to the real TAK Server image for production.

This work is **infra-only**. It does not touch any wire contract, service
behavior, or test suite of features 001-005.

## Deliverables

| Path                                       | Purpose                                                   |
| ------------------------------------------ | --------------------------------------------------------- |
| `infra/tak-server/Dockerfile`              | python:3.12-slim image; no third-party deps               |
| `infra/tak-server/stub_server.py`          | asyncio TLS CoT collector on :8089 (stdlib only)          |
| `infra/tak-server/docker-compose.yaml`     | `stub` profile (default) + commented `prod` profile       |
| `infra/tak-server/README.md`               | Operator quickstart, file reference, troubleshooting      |
| `scripts/gen-certs.sh`                     | openssl-based CA + server cert + gateway p12 generator    |
| `docs/tak-server-deployment.md`            | Full ops guide (stub & production swap)                   |
| `scripts/dev-launcher.sh` (updated)        | New `--tak-cert-dir`, `--tak-p12-password` flags;          |
|                                            | mirrors certs into gateway runtime when `--tak-use-ssl`   |
| `.gitignore` (updated)                     | Excludes `infra/certs/` (private keys, p12)               |

## PKI design

`scripts/gen-certs.sh` generates a small chain in `infra/certs/`:

```
ca.crt (CICS-TAK-PoC-CA)
├── takserver.crt   CN=takserver, SAN=localhost,127.0.0.1, EKU=server+client
└── gateway.crt     CN=cot-gateway, EKU=clientAuth
                    └── gateway.p12 (cert + key + CA, password=${TAK_P12_PASSWORD:-takpoc})
truststore.pem  copy of ca.crt for ssl.SSLContext.load_verify_locations()
```

Filenames are conventional: production swap means dropping in real CA-issued
certs with the same names. Idempotent by default (refuses overwrite without
`--force`). Private keys are chmod 600.

## Stub TAK Server design

- Stdlib-only Python (asyncio + ssl + logging + json). **G7 compliant.**
- Listens on :8089 TLS, validates client cert against `ca.crt`
  (`CERT_OPTIONAL`; mTLS upgradable via `--require-client-cert`).
- Logs each connection / received CoT line / disconnect as JSON to stdout
  (G3-compatible structlog-shaped events).
- Optionally appends each CoT to `cot.ndjson` for replay.
- Healthcheck: TCP probe on `${TAK_PORT}`.

The stub is **not** a TAK Server; it is the smallest thing that proves the
CoT Gateway's TLS uplink path is wired correctly. It does not federate, has
no SA fan-out, no web console, no DB.

## Production swap

`docker-compose.yaml` ships the production stanza commented out. To switch:

1. `docker load` the official TAK Server image from TAK.gov.
2. Set `TAK_IMAGE` and `DB_PASSWORD` in `.env`.
3. Drop production certs into `infra/certs/` (same filenames).
4. Uncomment the `tak-server` + `tak-db` services.
5. `docker compose --profile prod up -d`.

The CoT Gateway is profile-agnostic — it just reads `gateway.p12`.

## dev-launcher integration

When invoked with `--tak-use-ssl`, the launcher now:

1. Reads certs from `--tak-cert-dir` (default `infra/certs/`).
2. Mirrors `gateway.p12` and `truststore.pem` into
   `services/cot-gateway/config/certs/` so the relative path in
   `gateway.yaml` resolves.
3. Exports `TAK_P12_PASSWORD` (CLI flag → env → `takpoc` fallback).
4. Emits `cert_file` / `cert_password` lines into the generated gateway YAML.

## Verification

| Check                                                      | Result    |
| ---------------------------------------------------------- | --------- |
| `bash -n` on `gen-certs.sh` and updated `dev-launcher.sh`  | OK        |
| `gen-certs.sh` produces valid chain (`openssl verify`)     | OK        |
| `gateway.p12` opens with declared password                 | OK        |
| Stub accepts TLS, logs valid client cert subject + cipher  | OK        |
| Manual CoT sent via `openssl s_client` reaches stub        | OK        |
| `dev-launcher --services cot-gateway --tak-use-ssl`        | OK        |
|   → gateway logs `tak_connected attempt:1`                 |           |
|   → stub logs `client_connected` with mTLS cipher          |           |

## Out of scope

- Real TAK Server image bundling (closed-source, license-restricted).
- ATAK client p12 generation (atak-tablet.p12, atak-phone.p12). Document the
  pattern (gateway.p12) but don't ship phone/tablet bundles unprompted.
- Federation, SA UDP, web console — all features of the real TAK Server only.

## Notes for future work

- If the team adopts FreeTAKServer or another open TAK implementation, it
  can replace the stub with a third profile (`free-tak`) without touching
  the gateway, certs, or dev-launcher contract.
- For multi-machine demos, regenerate certs with
  `scripts/gen-certs.sh --tak-host <fqdn> --tak-ip <ip> --force` and
  redistribute `gateway.p12` + `truststore.pem` to each gateway host.
