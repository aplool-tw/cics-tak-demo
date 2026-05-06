# CoT Gateway

Fuse EchoShield radar + Sentrycs RF tracks into CoT 2.0 XML and push to TAK Server over TCP+TLS.

See `specs/005-cot-gateway/` for full spec / plan / quickstart.

## Install

```bash
python3 -m pip install --break-system-packages -e '.[dev]'
```

## Run

```bash
python3 -m cot_gateway --config config/gateway.yaml
```

## Web Map Viewer

The built-in Leaflet.js map at `http://127.0.0.1:8092/map` shows all active CoT tracks:

- Live drone markers with MIL-STD-2525C tactical symbols
- `a-h-*` (hostile/fused) → red diamond; `a-u-*` (unknown/single-source) → grey circle
- Stale markers dimmed at opacity 0.45
- SP / HP range rings; event list panel with source badges and distance to SP

```bash
# Start gateway, then open browser
python3 -m cot_gateway --config config/gateway.yaml
open http://127.0.0.1:8092/map
```

For a full demo with all services and 3 map viewers simultaneously, use the demo scripts at repo root:

```bash
scripts/demo-1drone.sh   # 1-drone scenario
scripts/demo-3drone.sh   # 3-drone scenario
```

## Test

```bash
pytest
pytest tests/unit/
pytest tests/contract/
pytest tests/integration/
```

## Configuration

See `config/gateway.yaml` for the full schema (four sections: echoshield / sentrycs / correlator /
tak_server, plus `logging`). Environment variable expansion is supported via `${VAR}`; typical use is
`tak_server.cert_password: "${TAK_P12_PASSWORD}"`.

## Certificates

Place `gateway.p12` at `config/certs/gateway.p12` (password via `TAK_P12_PASSWORD` env).
Alternative: offline convert to PEM with `openssl pkcs12 -in gateway.p12 -out gateway.pem -nodes`
and point `cert_file` at the `.pem`. See `config/certs/README.md`.

## Troubleshooting

- `ValidationError` on startup → check `config/gateway.yaml` (missing field / bad value / cert file
  not found).
- `tak_max_retries_exceeded` → verify TAK Server reachable on `tak_server.host:port`; Gateway exits
  with non-zero after 5 retries.
- `echoshield_disconnected` warnings → Gateway auto-reconnects every 5 s; no action needed.
- `queue_full_drop` warnings → TAK transmitter cannot keep up; usually transient during reconnect.
