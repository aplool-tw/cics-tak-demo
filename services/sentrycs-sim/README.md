# Sentrycs Simulator

Anti-drone TAK PoC — detection status API + UDS takeover caller.

Mirrors `services/echoshield-sim/` layout; queries Map Sim `/objects` at 2 Hz,
runs per-drone state machines (`IDLE → DETECTED → MITIGATING → NEUTRALIZED`),
fires UDS `/command/takeover` exactly once per drone, and exposes an HTTP
Status API (`:7070`) consumed by the CoT Gateway `SentrycsAdapter`.

## Install

```bash
cd services/sentrycs-sim
pip install -e '.[dev]'
```

## Run

```bash
python -m sentrycs_sim --scenario config/local.yaml --verbose
# or
sentrycs-sim --scenario config/local.yaml --verbose
```

Endpoints (contract: `specs/004-sentrycs-sim/contracts/http-status-api.md`):

- `GET /detections` — non-IDLE drones, wire schema per FR-SC-016 (14 fields).
- `GET /detection/{uid}` — single, or 404 when IDLE / unknown.
- `GET /health` — `{status, uptime_s, tracked_drones, map_sim_reachable}`.

## CLI

| arg | default | notes |
| --- | --- | --- |
| `--scenario PATH` | *required* | YAML loaded via pydantic v2 (`extra="forbid"`). |
| `--api-port N` | `7070` | Overrides scenario `api_port`. |
| `--verbose` | off | Emits DEBUG-level structured logs. |

## Structured log events (normative; see `specs/004-sentrycs-sim/research.md` R10)

`startup`, `state_transition`, `mapsim_query`, `mapsim_unavailable`,
`takeover_request`, `takeover_response`, `operator_locked`,
`unregistered_uid`, `http_request`, `shutdown`.

## Tests

```bash
pytest -q                    # contract + unit + integration
pytest -q tests/contract     # schema contracts
pytest -q tests/unit         # state machine / config / geo / clients
pytest -q tests/integration  # end-to-end freeze_time + stubs
```

See `specs/004-sentrycs-sim/quickstart.md` for full walkthrough.
