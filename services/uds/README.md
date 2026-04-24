# Unified Drone Simulator (UDS)

Single-source-of-truth simulator for drone positions in the anti-drone TAK PoC.

- Feature spec: [`specs/001-uds/spec.md`](../../specs/001-uds/spec.md)
- Plan: [`specs/001-uds/plan.md`](../../specs/001-uds/plan.md)
- Quickstart: [`specs/001-uds/quickstart.md`](../../specs/001-uds/quickstart.md)
- REST API contract: [`specs/001-uds/contracts/rest-api.md`](../../specs/001-uds/contracts/rest-api.md)

## Install (dev)

```bash
cd services/uds
pip install -e .[dev]
```

## Run

```bash
python -m uds --scenario scenarios/single_drone_invasion.yaml
```

Add `--debug` to expose `GET /status/{drone_id}` and `GET /drones` (non-contract).

## Failure semantics

UDS does **not** maintain a retry queue for the Map Simulator push path.
Any single-tick failure (`5xx`, timeout, connection refused) is logged
(`push.server_error` / `push.timeout` / `push.conn_error`), and the next tick
naturally re-pushes with the **freshest** drone state. This keeps the pipeline
self-healing without accumulating stale payloads, and satisfies FR-UDS-014 and
SC-007 (30 s Map Simulator outage ⇒ UDS keeps ticking, recovers on first
successful response).

## Tests

```bash
pytest
```
