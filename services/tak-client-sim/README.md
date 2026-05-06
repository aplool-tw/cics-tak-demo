# tak-client-sim

TAK Client Simulator — receives newline-delimited CoT XML from TAK Server over TCP+SSL and prints formatted events to the console for end-to-end PoC scenario verification.

## Quick Start

```bash
pip install -e ".[dev]" --break-system-packages

# Connect to local TAK Server (no SSL verification, PoC mode)
python -m tak_client_sim --host localhost --port 8089

# Filter to FUSED events only
python -m tak_client_sim --host localhost --port 8089 --filter FUSED

# Write all events to a log file (JSONL)
python -m tak_client_sim --host localhost --port 8089 --log-file /tmp/tak-events.jsonl
```

## Web Map Viewer

The built-in Leaflet.js browser map displays CoT events received from the TAK server.

### Features
- Live drone track markers (ECHO / SENTRYCS / FUSED / UNKNOWN) with direction arrows
- SP (Strategic Point — EchoShield + Sentrycs radar stations) with 1 km / 2 km / 3 km range rings
- HP (Holding Point — designated drone landing site after takeover)
- Event list panel with source badges, stale indicators, and distance to SP
- `Cache-Control: no-store` on all dynamic endpoints (prevents stale data)

### Running the demo (recommended)

Use the full-stack demo scripts at repo root — they start all 7 services and open 3 browser tabs automatically:

```bash
# From repo root
scripts/demo-1drone.sh    # 1-drone scenario
scripts/demo-3drone.sh    # 3-drone scenario
scripts/demo-1drone.sh --stop   # stop all services
```

### Manual setup

```bash
# Terminal 1 — start the full pipeline (map-sim, uds, echoshield-sim, sentrycs-sim, cot-gateway)
scripts/dev-launcher.sh

# Terminal 2 — start the TCP relay (bridges cot-gateway → tak-client-sim over plaintext TCP)
python3 scripts/tak_relay.py

# Terminal 3 — start tak-client-sim with web viewer
python3 -m tak_client_sim --config services/tak-client-sim/config/demo.yaml

# Open browser
open http://127.0.0.1:8093/map
```

The relay (`scripts/tak_relay.py`) listens on `:8089` and broadcasts any CoT XML received from cot-gateway to all connected subscribers (including tak-client-sim).

## Configuration

Configuration can be provided via YAML file (`--config path/to/config.yaml`) or CLI flags. CLI flags override YAML.

```yaml
# config.yaml example
host: tak-server
port: 8089
use_ssl: true              # set false for local demo with tak_relay.py (plaintext TCP)
use_ssl_verify: false      # PoC default; set true with ca_bundle in production
max_retries: 5             # 0 = unlimited
filter_prefix: ""          # e.g. "FUSED" or "ECHO"
log_file: "/tmp/tak.jsonl" # optional structured JSONL log

# Web map viewer
web_enabled: true
web_host: 0.0.0.0
web_port: 8093             # default 8091; use 8093 to avoid conflict with cot-gateway (:8092)
sp_lat: 24.725806
sp_lon: 121.033750
hp_lat: 24.725806
hp_lon: 121.071889
```

CLI SSL flags:

```bash
python -m tak_client_sim --host localhost --port 8089 --no-ssl   # plaintext TCP (demo mode)
python -m tak_client_sim --host tak-server --port 8089 --ssl     # TLS (production)
```

## Console Output Format

```
[11:00:00.000Z] ECHO-TRK-001234  a-u-A-M-F-Q-r  ECHO   GREY  lat=25.06000 lon=121.56000 hae=100.0  status=Active
[11:00:01.000Z] [STALE] ECHO-TRK-001234  ...
```

## Running Tests

```bash
python3 -m pytest -q
ruff check . && black --check src tests
```

## Architecture

```
__main__.py → runner.py → connection.py (TCP+SSL)
                       → receive_loop   (readuntil \n, limit=64KB)
                       → parser.py      (stdlib ElementTree)
                       → formatter.py   (print_event)
                       → web_server.py  (optional Leaflet map, GET /map /events /health)
config.py  (pydantic v2 ClientConfig)
models.py  (frozen dataclass CotEvent, ConnectionStats)
cot_store.py (asyncio lock-based store, auto-evicts stale+60s events)
```

See [`specs/006-006-tak-client-sim/`](../../specs/006-006-tak-client-sim/) for full specification.
