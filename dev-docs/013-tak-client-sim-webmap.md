# dev-docs/013-tak-client-sim-webmap.md

Feature ID : 013
Name       : tak-client-sim-webmap
Branch     : feature/013-tak-client-sim-webmap
Merged to  : develop
Status     : Complete

---

## Summary

This feature delivers three capabilities on top of the existing `tak-client-sim` web map viewer that was merged in the 013 cycle:

1. **MIL-STD-2525C SVG icons** — The map now renders proper tactical symbols based on CoT type affiliation, replacing the previous simple colored circles.
2. **Plaintext TCP mode** (`use_ssl: false`) — A new `use_ssl` config field allows tak-client-sim to connect to `scripts/tak_relay.py` (a plaintext TCP broadcast relay) instead of a TLS endpoint. This is the correct mode for local demo runs.
3. **Full-stack demo scripts** — `scripts/demo-1drone.sh` and `scripts/demo-3drone.sh` start all 7 services in the correct order and open 3 browser tabs simultaneously: Map Sim, CoT Gateway, and TAK Client Sim web maps.

---

## Key Technical Decisions

### 1. `use_ssl: bool = True` in `ClientConfig`

The existing `connection.py` always constructed an `ssl.SSLContext`. There was no way to disable TLS for local demo runs where `tak_relay.py` is used as the TAK endpoint (a plaintext TCP proxy).

**Decision**: Add `use_ssl: bool = True` to `ClientConfig` (placed after `port`, before `use_ssl_verify`). When `False`, `ssl=None` is passed to `asyncio.open_connection()`, establishing a plaintext TCP connection. The default `True` preserves backward compatibility with all existing configs.

**CLI**: `--ssl` / `--no-ssl` flags added to `__main__.py`.

### 2. MIL-STD-2525C icon dispatch in JavaScript

The existing `evtColors()` function mapped the Python-side `color` field (`"GREY"` / `"RED"`) to CSS colors. The new `makeIconHtml()` function dispatches directly on `cot_type`:

- `cot_type.startsWith('a-h')` → **Hostile**: red filled diamond (`<rect transform="rotate(45)"/>`)
- `cot_type.startsWith('a-u')` → **Unknown**: grey circle with diagonal crosshair (`<circle>` + two `<line>`)
- Anything else → Unknown fallback (graceful degradation per SC-005)
- Stale events: `style="opacity:0.45"` on the SVG root + grey `#546e7a` fill override

The `viewBox="-12 -12 24 24"` and `iconSize: [24, 24]` are preserved from the original implementation. The `<rect x="-8" y="-8" width="16" height="16">` dimensions were specifically chosen to keep vertices at ±11.3 px, leaving a 0.7 px margin inside the viewBox.

**Card color** (`event-uid` CSS color) was also updated to use `cotColor(cot_type)` instead of the old `evtColors(color).fill`.

### 3. TAK relay vs TAK stub server

The demo scripts use `scripts/tak_relay.py` (plaintext TCP broadcast relay on `:8089`), **not** `infra/tak-server/stub_server.py` (a TLS-only ingestion server). The distinction matters because:

- `cot-gateway/config/demo.yaml` has `use_ssl: false` — CoT Gateway connects to `:8089` in plaintext.
- `tak_relay.py` broadcasts every received CoT XML line to all connected subscribers.
- `stub_server.py` accepts TLS + logs CoT XML but does NOT relay to downstream clients.

### 4. Demo script architecture (7-service pipeline)

```
UDS(:18080) → Map Sim(:8090) ← EchoShield Sim(:9000/9001)
              Map Sim         ← Sentrycs Sim(:7070)
                                EchoShield Sim → CoT Gateway(:8092) → TAK Relay(:8089)
                                Sentrycs Sim   → CoT Gateway         ↑
                                                                TAK Client Sim(:8093)
```

Startup order (enforced by health-check loop before opening browser):
1. `map-sim` — `:8090/health`
2. `uds` — TCP `:18080`
3. `echoshield-sim` — `:9001/info`
4. `sentrycs-sim` — `:7070/health`
5. `cot-gateway` — `:8092/health`
6. `tak-relay` — TCP `:8089`
7. `tak-client-sim` — `:8093/health`

Browser tabs opened (after health checks pass):
- `http://127.0.0.1:8090/map` — Map Sim tactical map
- `http://127.0.0.1:8092/map` — CoT Gateway tactical map
- `http://127.0.0.1:8093/map` — TAK Client Sim tactical map

---

## File Change Summary

| File | Change |
|------|--------|
| `services/tak-client-sim/src/tak_client_sim/config.py` | Added `use_ssl: bool = True` field + `--ssl`/`--no-ssl` CLI handling |
| `services/tak-client-sim/src/tak_client_sim/__main__.py` | Added `--ssl` / `--no-ssl` argparse flags |
| `services/tak-client-sim/src/tak_client_sim/connection.py` | Conditional `ssl=None` when `use_ssl=False` |
| `services/tak-client-sim/src/tak_client_sim/web_server.py` | Replaced `evtColors()` with `makeIconHtml()` + MIL-STD-2525C shapes + legend update |
| `services/tak-client-sim/config/demo.yaml` | Added `use_ssl: false` |
| `scripts/demo-1drone.sh` | New: 7-service demo script, 3 browser tabs, single-drone scenario |
| `scripts/demo-3drone.sh` | New: same as above with three-drone scenario configs |
| `services/tak-client-sim/tests/unit/test_config_use_ssl.py` | New: 12 tests for `use_ssl` config field and CLI |
| `services/tak-client-sim/tests/unit/test_web_icon_logic.py` | New: 5 tests for MIL-STD-2525C SVG icon generation |
| `services/tak-client-sim/tests/unit/test_demo_scripts.py` | New: 2 tests for demo script correctness |
| `services/tak-client-sim/tests/unit/test_web_server.py` | Added wire-contract regression: `/events` JSON key set |

---

## Known Issues / Gotchas

### CoT Gateway `demo.yaml` does not forward CoT to TAK relay by default

The `cot-gateway/config/demo.yaml` must have `tak.enabled: true` pointing to `:8089` for data to flow from cot-gateway → tak_relay → tak-client-sim. Verify this before running the demo. If tak-client-sim shows no data, check cot-gateway logs for `tak_uplink_connected`.

### `tak_relay.py` TCP health check

The demo script health-checks the relay via `bash -c "echo > /dev/tcp/127.0.0.1/8089"` — this is a TCP connect test (not HTTP). On macOS the `/dev/tcp` built-in may require bash (not zsh). The scripts use `#!/usr/bin/env bash` explicitly.

### Browser open on Linux

Uses `xdg-open` — requires a desktop environment. On headless servers, the browser-open silently fails (non-fatal, URLs are printed to stdout). Install `xdg-utils` if needed.

### `shellcheck` not installed on this host

The `shellcheck` tool was not available during development, so the scripts were validated with `bash -n` (syntax check) instead. Run `apt install shellcheck` + `shellcheck -S warning scripts/demo-*.sh` after installation.

---

## Test Coverage

| Test file | Tests | What it covers |
|-----------|-------|----------------|
| `test_config_use_ssl.py` | 12 | `use_ssl` field default, config loading, CLI `--ssl`/`--no-ssl`, YAML loading |
| `test_web_icon_logic.py` | 5 | Hostile diamond SVG, Unknown circle SVG, stale dimming, course arrow, legend strings |
| `test_demo_scripts.py` | 2 | demo-1drone scenario path, demo-3drone scenario path |
| `test_web_server.py` (extended) | +3 | `/events` JSON key set wire-contract regression |

Total: **98 passing** (up from 61 pre-feature baseline).

---

## How to Run the Demo

### 1-drone scenario

```bash
# Install all services once
pip install -e services/map-sim services/uds services/echoshield-sim \
            services/sentrycs-sim services/cot-gateway services/tak-client-sim \
            --break-system-packages

# Run demo (starts 7 services, opens 3 browser tabs)
scripts/demo-1drone.sh

# Stop
scripts/demo-1drone.sh --stop
```

### 3-drone scenario

```bash
scripts/demo-3drone.sh
scripts/demo-3drone.sh --stop
```

### Watch the maps

| Map | URL | Content |
|-----|-----|---------|
| Map Sim | http://127.0.0.1:8090/map | Map Sim tactical map |
| CoT Gateway | http://127.0.0.1:8092/map | Correlated EchoShield + Sentrycs tracks |
| TAK Client Sim | http://127.0.0.1:8093/map | CoT XML received from TAK relay (MIL-STD-2525C icons) |

---

## Speckit Artifacts

All artifacts in `specs/013-tak-client-sim-webmap/`:
- `spec.md` — Feature specification with 14 FRs, 8 SCs, 3 user stories
- `plan.md` — Implementation plan (7 components)
- `data-model.md` — `use_ssl` field and `connection.py` changes
- `research.md` — MIL-STD-2525C SVG shapes, TLS-bypass approach
- `tasks.md` — 36 TDD-ordered tasks (all complete)
- `quickstart.md` — Developer quickstart guide
- `checklists/requirements.md` — Requirements traceability
