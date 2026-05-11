# UDS CLI reference

`python -m uds` (or `uds` console script once installed) exposes these flags
per FR-UDS-011 / quickstart.md §2.2.

| Flag | Default | Description |
|------|---------|-------------|
| `--scenario <path>` | (required) | YAML scenario file |
| `--api-port <int>` | 18080 | REST API port (CLI > `scenario.servers.command_api_port` > 18080) |
| `--map-sim-url <url>` | `http://127.0.0.1:18090` | Map Simulator base URL |
| `--hz <int>` | 10 | Main loop frequency in Hz (1–20); CLI > `scenario.update_hz` > 10 |
| `--verbose` | off | Set log level to DEBUG |
| `--debug` | off | Register non-contract `GET /status/{drone_id}` and `GET /drones` |

## `--debug` caveat

Routes registered under `--debug` are intentionally **not** part of the UDS
public contract — their response schema may change between releases. Downstream
services (Sentrycs Simulator, Map Simulator, etc.) must **not** depend on them.
See `specs/001-uds/contracts/rest-api.md` §2.3.

If structured state queries become necessary, they should be introduced as a
new formal contract (e.g. `POST /query/state`), not by promoting the debug
endpoints.
