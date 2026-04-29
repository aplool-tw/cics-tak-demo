# 006 — TAK Client Simulator

**Feature**: `006-tak-client-sim`
**Branch**: `feature/006-006-tak-client-sim`
**Service**: `services/tak-client-sim/`
**Module**: `tak_client_sim`

---

## Overview

The TAK Client Simulator (`tak-client-sim`) is a Python asyncio service that connects to a TAK Server over TCP+SSL, receives newline-delimited CoT 2.0 XML, parses each event, and prints formatted output to the console. It removes the need for a real Android ATAK client during PoC scenario verification.

---

## Architecture

```
__main__.py  →  runner.main()
                ├── config.py    (pydantic v2 ClientConfig, YAML + CLI merge)
                ├── connection.py (build_ssl_context, connect_with_retry, backoff)
                └── receive_loop
                    ├── parser.py    (parse_cot_xml, stdlib ET, derive_source/color)
                    └── formatter.py (format_event, is_stale_at_receive, print_event)
models.py    (CotEvent frozen dataclass, ConnectionStats)
```

Data flows: `TCP bytes → readuntil(b'\n', limit=64KB) → parse_cot_xml() → CotEvent → format_event() → print_event()`

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| No `cryptography` dependency | stdlib `ssl` only | Receiver needs no client cert; G7 minimal deps |
| `CotEvent` as frozen dataclass | not pydantic | Hot-path performance; parser runs on every CoT |
| `print()` in `connection.py` | FR-TCS-023 explicit exception | Reconnect progress needs to reach operator even if structlog not configured |
| `limit=65536` on `open_connection` | not on `readuntil()` | Python 3.12: `limit` is a constructor param, not method param |
| `use_ssl_verify = False` default | PoC mode | TAK Server uses self-signed cert; `--use-ssl-verify` to override |
| `asyncio_mode = "auto"` in pyproject.toml | pytest-asyncio | Eliminates per-test `@pytest.mark.asyncio` boilerplate |

---

## Implementation Notes

### Python 3.12 asyncio fix
`asyncio.StreamReader.readuntil()` does **not** accept a `limit=` keyword argument in Python 3.12. The buffer limit must be passed to `asyncio.open_connection(limit=65536)`. The `LimitOverrunError` is still raised automatically when the line exceeds the limit.

### Stub server in integration tests
Integration tests use `asyncio.start_server(..., host="127.0.0.1", port=0)` to get OS-assigned ports, avoiding port conflicts between tests. The `receive_loop` signature accepts an already-connected `StreamReader` so tests can inject connections without the SSL/reconnect machinery.

### Stale detection
`is_stale_at_receive(event)` compares `event.stale` against the current UTC time. `delta_s == 0` means the event was already stale at emission (Lost state). The formatter prefix `[STALE]` is cosmetic only — TAK Server manages actual persistence.

---

## Speckit Workflow Issues

- `speckit.tasks` agent got stuck after writing `tasks.md` (10+ min, fixed tool call count)
- `speckit.implement` agent got stuck before writing any files (same issue)
- Both recovered by: reading artifacts directly and implementing manually
- Workaround: keep implementation tasks small enough for a single-context agent pass

---

## Test Coverage

| Layer | File | Count |
|---|---|---|
| Contract | `tests/contract/test_tak_downlink.py` | 9 |
| Unit — parser | `tests/unit/test_parser.py` | 12 |
| Unit — formatter | `tests/unit/test_formatter.py` | 8 |
| Unit — config | `tests/unit/test_config.py` | 10 |
| Unit — connection | `tests/unit/test_connection.py` | 8 |
| Unit — oversized | `tests/unit/test_oversized.py` | 4 |
| Integration | `tests/integration/test_runner.py` | 8 |
| **Total** | | **59** |

All 59 tests pass, `ruff` + `black` clean.

---

## Commands

```bash
# Install
pip install -e "services/tak-client-sim[dev]" --break-system-packages

# Run (PoC, no SSL verify)
python -m tak_client_sim --host localhost --port 8089

# Tests
( cd services/tak-client-sim && python3 -m pytest -q )

# Lint
( cd services/tak-client-sim && ruff check . && black --check src tests )

# Smoke
services/tak-client-sim/scripts/smoke.sh localhost 8089
```
