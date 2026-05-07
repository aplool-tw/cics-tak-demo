# TAK Server Deployment Guide

This is the **operational guide** for the TAK Server tier of the CICS
Anti-Drone TAK PoC. It complements the formal specification in
[`docs/system-docs/07-tak-server-deployment-spec.md`](system-docs/07-tak-server-deployment-spec.md)
(which defines the *what*) by documenting the *how* in this repo.

The repo ships **two interchangeable TAK Server profiles** behind a single
docker-compose stack:

1. **Stub profile (default)** — a bundled Python TLS CoT collector. No
   TAK.gov account required. Sufficient for sensor → gateway → TAK end-to-end
   smoke tests. Does **not** federate, does **not** distribute SA, does
   **not** provide a web console. See `infra/tak-server/stub_server.py`.

2. **Production profile** — the real TAK Server image obtained from
   <https://tak.gov>. The stack is pre-wired (commented out in
   `docker-compose.yaml`); you supply the image, `CoreConfig.xml`, and a
   PostGIS database password.

The CoT Gateway is **profile-agnostic**: it consumes `infra/certs/gateway.p12`
regardless of which profile is running. To swap profiles you swap certs
and uncomment one stanza.

---

## 1. Cert layout

`scripts/gen-certs.sh` produces a self-contained PKI suitable for the stub
profile and as a placeholder for the production profile:

```
infra/certs/
├── ca.crt                # Root CA (public)
├── ca.key                # Root CA private key (KEEP SAFE / do not commit)
├── takserver.crt         # Server cert (CN=takserver, SAN=localhost,127.0.0.1)
├── takserver.key         # Server key
├── gateway.crt           # Client cert (CN=cot-gateway)
├── gateway.key           # Client key
├── gateway.p12           # PKCS#12 bundle: gateway cert/key + CA chain
├── truststore.pem        # Copy of ca.crt for Python ssl context
└── cert.env              # Convenience snippet: TAK_P12_PASSWORD, TAK_CERT_DIR
```

All filenames are **conventional**: production swap simply means replacing
the contents while keeping the names.

### gen-certs.sh options

```bash
scripts/gen-certs.sh --help
```

Common invocations:

| Goal                                    | Command                                                                |
| --------------------------------------- | ---------------------------------------------------------------------- |
| Default dev certs (`localhost`)         | `scripts/gen-certs.sh`                                                 |
| Fresh regenerate                        | `scripts/gen-certs.sh --force`                                         |
| Custom server hostname / IP             | `scripts/gen-certs.sh --tak-host tak.lab --tak-ip 10.0.0.5 --force`    |
| Random p12 password                     | `scripts/gen-certs.sh --p12-password "$(openssl rand -hex 16)" --force` |
| Custom output directory                 | `scripts/gen-certs.sh --output /etc/cics-tak/certs`                    |

The script refuses to overwrite without `--force` to protect production
artifacts from accidental clobber. Set `TAK_P12_PASSWORD` before running
to control the gateway p12 password (otherwise `takpoc` is used).

---

## 2. Stub profile (default)

```bash
# (one-time) certs
./scripts/gen-certs.sh

# bring up
cd infra/tak-server
docker compose up -d

# logs
docker compose logs -f tak-server-stub
```

Behavior:

- Listens on `:18089` (override with `TAK_PORT` env var).
- Requires TLS; client certs are validated against `ca.crt` (mTLS
  optional — defaults to `CERT_OPTIONAL`).
- Logs every connection / received CoT line / disconnect as JSON to stdout.
- Appends each CoT to `/var/log/tak-stub/cot.ndjson` inside the container
  (volume `tak_stub_logs`, persists across restarts until `docker compose down -v`).

Wire it to the gateway:

```bash
export TAK_P12_PASSWORD=takpoc          # match gen-certs.sh password
./scripts/dev-launcher.sh --services cot-gateway,sentrycs-sim,echoshield-sim,uds,map-sim \
    --tak-host localhost --tak-port 18089 --tak-use-ssl
```

The gateway picks up `services/cot-gateway/config/certs/gateway.p12` (which
should be a symlink/copy of `infra/certs/gateway.p12` — see
"Wiring certs into the gateway" below).

---

## 3. Production profile

### 3.1 Prerequisites

- A TAK.gov account and a downloaded TAK Server Docker image (`takserver-docker-*.zip`).
- An x86_64 host with Docker ≥ 24, ≥ 4 GB RAM, ≥ 20 GB disk.
- Production-grade certs from your own CA (or TAK.gov-issued).
- A PostGIS instance (provided in `docker-compose.yaml` as `tak-db`) or
  external Postgres reachable from the TAK container.

### 3.2 Steps

1. Load the image:
   ```bash
   cd ~
   unzip takserver-docker-*.zip
   docker load -i takserver-*.tar.gz
   docker images | grep tak     # note the tag, e.g. takserver:5.4
   ```

2. Edit `infra/tak-server/.env` (create if missing):
   ```bash
   TAK_IMAGE=takserver:5.4
   DB_PASSWORD=<strong password>
   TAK_PORT=8089
   ```

3. Drop your production certs into `infra/certs/`, **keeping the
   stub-profile filenames**:
   - `ca.crt` (CA chain)
   - `takserver.crt` / `takserver.key` (server cert)
   - `gateway.p12` (CoT Gateway client; password = `$TAK_P12_PASSWORD`)
   - `truststore.pem` (CA chain — usually identical to `ca.crt`)

4. Provide a `CoreConfig.xml` next to `docker-compose.yaml` (TAK Server
   convention; copy the example from your TAK Server distribution and
   adjust DB host/port and federation settings).

5. Uncomment the `tak-server` and `tak-db` services in `docker-compose.yaml`,
   then:
   ```bash
   cd infra/tak-server
   docker compose --profile prod up -d
   ```

6. Verify:
   ```bash
   docker compose --profile prod ps
   curl -k https://localhost:8443/    # web console banner
   ```

### 3.3 Cutover with no gateway downtime

Because both profiles use `infra/certs/gateway.p12`, you can prepare the
production certs, swap them in, and bounce only the gateway:

```bash
# 1. Place prod certs in infra/certs/  (overwrites stub certs)
# 2. Bring stub down, prod up
docker compose down
docker compose --profile prod up -d
# 3. Restart only the gateway so it reloads the new p12
./scripts/dev-launcher.sh --services cot-gateway --tak-host <prod-host> --tak-use-ssl
```

---

## 4. Wiring certs into the gateway

`services/cot-gateway/config/gateway.yaml` references
`config/certs/gateway.p12` (relative to the gateway's working directory).

For development the dev-launcher script already mirrors `infra/certs/` into
the gateway's runtime config directory. If you run the gateway manually:

```bash
mkdir -p services/cot-gateway/config/certs
cp infra/certs/gateway.p12      services/cot-gateway/config/certs/
cp infra/certs/truststore.pem   services/cot-gateway/config/certs/
export TAK_P12_PASSWORD=takpoc
cd services/cot-gateway && python3 -m cot_gateway
```

The gateway reads the p12 via `cryptography.hazmat.primitives.serialization`
and constructs a stdlib `ssl.SSLContext`; no changes are needed when swapping
between stub and production profiles, only the cert files differ.

---

## 5. Troubleshooting

| Symptom                                                        | Resolution                                                                                        |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `wrong password` reading `gateway.p12`                         | `TAK_P12_PASSWORD` mismatch. Re-run `gen-certs.sh --p12-password <pwd>` or fix the env var.       |
| `certificate verify failed: hostname mismatch`                 | Add the right SAN: `gen-certs.sh --tak-host <fqdn> --tak-ip <ip> --force`.                        |
| Gateway logs `tak_connect_failed` repeatedly                   | Check `docker compose logs tak-server-stub`; check port `${TAK_PORT}` is exposed on the host.     |
| Stub logs `ssl_error: TLSV1_ALERT_UNKNOWN_CA`                  | Gateway's truststore is stale. Copy fresh `truststore.pem` to gateway config certs dir.           |
| Real TAK Server rejects gateway client cert                    | Production TAK Server must trust the issuing CA. Re-issue `gateway.p12` from the production CA.   |
| Stub doesn't see any CoT despite gateway "up"                  | Gateway likely buffered on a non-existent path. Verify `cert_file` in `gateway.yaml` and re-run.  |

---

## 6. Security notes

- `infra/certs/` is `.gitignore`d. **Never** commit `*.key`, `*.p12`, or
  `ca.key`. The repo treats anything in this directory as developer-local
  or production-secret.
- The default p12 password (`takpoc`) is for development convenience only.
  Always override `TAK_P12_PASSWORD` in any non-dev environment.
- `verify_mode=CERT_OPTIONAL` in the stub is intentional — many ATAK
  client onboardings need looser server policies during enrollment. The
  real TAK Server enforces `CERT_REQUIRED` per its own configuration.
- Root CA private key (`ca.key`) is generated locally and never leaves the
  developer's machine. The stub trusts only its sibling CA. There is no
  shared trust between developers' stubs.
