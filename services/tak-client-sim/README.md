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

## Configuration

Configuration can be provided via YAML file (`--config path/to/config.yaml`) or CLI flags. CLI flags override YAML.

```yaml
# config.yaml example
host: tak-server
port: 8089
use_ssl_verify: false      # PoC default; set true with ca_bundle in production
max_retries: 5             # 0 = unlimited
filter_prefix: ""          # e.g. "FUSED" or "ECHO"
log_file: "/tmp/tak.jsonl" # optional structured JSONL log
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
config.py  (pydantic v2 ClientConfig)
models.py  (frozen dataclass CotEvent, ConnectionStats)
```

See [`specs/006-006-tak-client-sim/`](../../specs/006-006-tak-client-sim/) for full specification.
