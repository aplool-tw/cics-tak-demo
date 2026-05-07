# spec.md — 013-tak-client-sim-webmap

Feature ID : 013
Name       : tak-client-sim-webmap
Branch     : feature/013-tak-client-sim-webmap
Status     : Draft (Clarified 2026-05-06)

---

## Summary

Upgrade the `tak-client-sim` web map with MIL-STD-2525C-compliant SVG icons and
add two end-to-end demo shell scripts (`demo-1drone.sh`, `demo-3drone.sh`) that
start the complete pipeline — including the TAK relay (`scripts/tak_relay.py`)
and `tak-client-sim` — and open all three map viewers in the browser simultaneously.

---

## Background

The `tak-client-sim` service already has a Leaflet-based web map at `:18093/map`
that displays CoT events received from the TAK relay.  Current markers are plain
filled circles (blue for GREY targets, red for RED targets).  The project's CoT
type codes map directly onto MIL-STD-2525C affiliations, so proper symbology can
be derived deterministically without ambiguity.

The existing demo scripts (`demo-cot-gateway-map.sh`,
`demo-cot-gateway-map-3drones.sh`) do **not** start the TAK relay or
`tak-client-sim`, meaning the end-to-end TAK path has no single-command demo.
This feature closes that gap.

---

## Clarifications

### Session 2026-05-06

- Q: Which component provides the `:18089` endpoint in the demo scripts — `stub_server.py` (TLS) or `tak_relay.py` (plaintext TCP)? → A: `tak_relay.py`. `stub_server.py` only ingests and logs CoT XML from cot-gateway; it does not relay data to tak-client-sim. cot-gateway `demo.yaml` uses `use_ssl: false` (plaintext TCP) — incompatible with stub_server.py's TLS. `tak_relay.py` is the broadcast relay designed to connect both parties (known fact 3). FR-007 row 6 and the Assumptions section updated accordingly.

- Q: tak-client-sim `connection.py` always wraps connections with `ssl=ssl_ctx`. Since `tak_relay.py` is plaintext TCP, how does tak-client-sim connect? → A: Add `use_ssl: bool = True` to `ClientConfig`. When `false`, pass `ssl=None` to `asyncio.open_connection`. Set `use_ssl: false` in `demo.yaml`. This is now FR-014.

- Q: What is the correct map-sim browser URL — `http://127.0.0.1:18090/map` (as written in FR-008/US-002) or `http://127.0.0.1:18090/objects` (known fact 5)? → A: `http://127.0.0.1:18090/objects`. The `/map` route is served by cot-gateway (`:18092/map`) and tak-client-sim (`:18093/map`); map-sim exposes `/objects`. FR-008, US-002 table, and SC-004 updated.

- Q: FR-010 port pre-flight list (8089, 8090, 8092, 8093, 18080) omits sentrycs-sim `:17070`; Edge Cases mentions `:18091` which matches no service. What is the canonical list? → A: Canonical checked ports: **8089, 8090, 8092, 8093, 18080, 7070**. `:18091` in Edge Cases was a typo for `:18092` (cot-gateway); corrected. FR-010 updated.

- Q: FR-010 requires verifying Python modules are importable, but `tak_relay.py` is a standalone script (not a pip-installable module). How should the pre-flight check handle it? → A: Use a file-existence check (`[[ -f scripts/tak_relay.py ]]`) for the relay script instead of a Python import check. FR-010 item 4 added.

---

## User Stories

### US-001 — Operator views MIL-STD-2525C icons on the TAK client map (Priority: P1)

A demo operator opens the `tak-client-sim` map at `http://127.0.0.1:18093/map`
and sees track icons that match MIL-STD-2525C affiliation conventions:

- **Unknown / unclassified** targets (`a-u-*`) rendered as a **grey outlined
  circle with an interior cross** (MIL-STD-2525C Unknown symbol).
- **Hostile / fused** targets (`a-h-*`) rendered as a **red filled diamond**
  (MIL-STD-2525C Hostile symbol).

Stale targets are visually dimmed regardless of affiliation.  A course-heading
arrow is drawn inside the icon when `speed > 0.3 m/s`.

**Why this priority**: Correct military symbology is the primary differentiator
between the existing state and the demo-ready state required for the G2 contract
review.  It is the highest-visibility visible change.

**Independent Test**: Install `tak-client-sim`, start `scripts/tak_relay.py`,
inject a synthetic CoT XML event of type `a-u-A-M-F-Q-r` and one of type
`a-h-A-M-F-Q-r` via the relay.  Open `:18093/map` and confirm the icon shapes
match the expected MIL-STD-2525C symbols.

**Acceptance Scenarios**:

1. **Given** a live CoT event with `cot_type = "a-u-A-M-F-Q-r"` is present in
   the store, **When** the map refreshes, **Then** the marker is a grey
   outlined circle with an interior cross (Unknown affiliation symbol).
2. **Given** a live CoT event with `cot_type = "a-h-A-M-F-Q-r"` is present in
   the store, **When** the map refreshes, **Then** the marker is a red filled
   diamond (Hostile affiliation symbol).
3. **Given** any CoT event whose `stale` time has passed, **When** the map
   refreshes, **Then** the marker is dimmed (reduced opacity / grey fill)
   regardless of its affiliation.
4. **Given** a CoT event with `speed > 0.3 m/s`, **When** the icon is
   rendered, **Then** a directional arrow aligned to `course` is shown inside
   the icon body.
5. **Given** a CoT event with `speed ≤ 0.3 m/s`, **When** the icon is
   rendered, **Then** no directional arrow is shown.

---

### US-002 — Operator runs single-drone end-to-end demo with one command (Priority: P2)

An operator runs `scripts/demo-1drone.sh` from the repository root.  The script
starts **all** pipeline services in the correct order:

```
map-sim → UDS (demo_single_drone scenario) → echoshield-sim → sentrycs-sim
→ cot-gateway → TAK stub server → tak-client-sim
```

Health checks confirm all services are ready before the browser is opened.  The
script then opens **three browser tabs**:

| Tab | URL                             | Content                     |
|-----|---------------------------------|-----------------------------|
| 1   | `http://127.0.0.1:18090/objects` | Map Sim                     |
| 2   | `http://127.0.0.1:18092/map`     | CoT Gateway map viewer      |
| 3   | `http://127.0.0.1:18093/map`     | TAK Client Sim map viewer   |

`Ctrl-C` cleanly stops all services, including the TAK stub and
`tak-client-sim`.  A `--stop` flag stops any previously-started instance from a
separate shell.

**Why this priority**: Without this script the TAK relay + tak-client-sim leg of
the architecture is never exercised in a demo.  The second-highest priority after
the icon fix.

**Independent Test**: Run `scripts/demo-1drone.sh`; confirm all seven services
start, browser opens three tabs, drone track appears on all three maps, and
`Ctrl-C` exits cleanly.

**Acceptance Scenarios**:

1. **Given** all Python packages installed, **When** `scripts/demo-1drone.sh`
   is executed, **Then** all seven services start (map-sim, uds, echoshield-sim,
   sentrycs-sim, cot-gateway, TAK stub, tak-client-sim) without error.
2. **Given** all services healthy, **When** the health-check loop completes,
   **Then** three browser tabs open automatically.
3. **Given** the demo is running, **When** the drone track begins (t≈9s into
   the UDS scenario), **Then** a track icon appears on the TAK client map at
   `:18093/map`.
4. **Given** the demo is running, **When** `Ctrl-C` is pressed, **Then** all
   seven processes are terminated gracefully, no orphan processes remain.
5. **Given** a previously-running demo, **When**
   `scripts/demo-1drone.sh --stop` is executed, **Then** all services from the
   stored PID files are stopped.
6. **Given** a required Python package is not installed, **When** the script
   runs, **Then** it exits with an actionable error message naming the missing
   package.

---

### US-003 — Operator runs three-drone end-to-end demo with one command (Priority: P3)

An operator runs `scripts/demo-3drone.sh`.  It is identical in structure to
`demo-1drone.sh` but uses the three-drone scenario configs
(`demo_three_drones.yaml` for UDS and sentrycs-sim).  The same three browser
tabs open; all three drone tracks appear on every map viewer.

**Why this priority**: Extends the single-drone demo to the higher-complexity
scenario.  The implementation is nearly identical to US-002 (config swap only),
so it is a fast follow.

**Independent Test**: Run `scripts/demo-3drone.sh`; confirm three drone tracks
appear on all maps and the script stops cleanly.

**Acceptance Scenarios**:

1. **Given** all Python packages installed, **When** `scripts/demo-3drone.sh`
   is executed, **Then** all services start with the three-drone scenario
   configs.
2. **Given** the demo is running, **When** the scenario plays back, **Then**
   three distinct track UIDs appear on the TAK client map at `:18093/map`.
3. **Given** `Ctrl-C`, **Then** all services stop cleanly.

---

## Edge Cases

- **TAK stub not running**: `tak-client-sim` retries indefinitely
  (`max_retries: 9999`); the demo script must wait for the stub to be healthy
  before starting `tak-client-sim` to avoid a misleading connection-refused
  burst in the logs.
- **Port already in use**: If any of `:18089`, `:18090`, `:18092`, `:18093`, `:18080`, or `:17070`
  is already bound when the script starts, the script must detect the conflict
  and exit with a clear error message before spawning services.
- **Unknown `cot_type` prefix**: A CoT event whose type does not start with
  `a-u` or `a-h` must fall back to the existing UNKNOWN styling (grey/blue
  circle) without throwing a JavaScript error.
- **Stale events with course arrows**: A stale event with `speed > 0.3` should
  still render an arrow inside the dimmed icon so the last known heading is
  preserved.
- **Browser not available**: `xdg-open` / `open` failure must not abort the
  script; the URL must be printed to the terminal as a fallback.
- **Partial service failure**: If any service exits unexpectedly during the
  health-check phase, the script must detect the dead process, log which service
  failed, and trigger cleanup before exiting.
- **Three-drone overlap**: When three tracks are geographically close, icons
  must not obscure each other (Leaflet's default z-index stacking is acceptable;
  explicit click-to-front behaviour is out of scope).

---

## Functional Requirements

### FR-001 — MIL-STD-2525C Unknown icon

`web_server.py`'s `makeDroneIcon()` function MUST render a **grey outlined
circle with an interior diagonal cross** (×) for any CoT event whose
`cot_type` starts with `a-u`.  The SVG MUST be inline `L.divIcon` HTML, no
external image files.  Fill colour: `#90a4ae` (grey).  Stroke colour:
`#546e7a`.

### FR-002 — MIL-STD-2525C Hostile icon

`makeDroneIcon()` MUST render a **red filled diamond** (45°-rotated square) for
any CoT event whose `cot_type` starts with `a-h`.  Fill colour: `#ef5350`.
Stroke colour: `#b71c1c`.

### FR-003 — Stale icon dimming

When `is_stale` is `true`, the icon (regardless of shape) MUST use reduced
opacity (`opacity: 0.45`) and grey fill (`#546e7a`) so stale targets are
visually distinct without being invisible.

### FR-004 — Course arrow inside icon

When `speed > 0.3 m/s`, a white directional arrowhead MUST be rendered inside
the icon body (polygon rotated to `course` degrees clockwise from north), as
in the existing implementation.  The arrow MUST fit within the icon's
`viewBox` and not overflow the border.

### FR-005 — Legend update

The map legend in `web_server.py` MUST be updated to show:

- Unknown (grey circle+cross)
- Hostile (red diamond)
- Stale (dimmed version of either)

replacing the old "GREY (blue circle)" / "RED (red circle)" entries.

### FR-006 — No new Python runtime dependencies

The icon changes MUST be implemented using only inline SVG inside
`L.divIcon` HTML strings.  No additional Python packages or JavaScript
libraries may be introduced.  Existing CDN resources (Leaflet 1.9.4) are
unchanged.

### FR-007 — `demo-1drone.sh` — service startup order

`scripts/demo-1drone.sh` MUST start services in the following order with the
specified configs:

| # | Service         | Command / Config                                             | Health check                          |
|---|-----------------|--------------------------------------------------------------|---------------------------------------|
| 1 | map-sim         | `python3 -m map_sim --port 8090`                             | `GET /health` → 200                   |
| 2 | uds             | `python3 -m uds --scenario demo_single_drone.yaml ...`       | TCP connect `:18080`                  |
| 3 | echoshield-sim  | `python3 -m echoshield_sim --config demo.yaml`               | `GET /info` (`:19001`) → 200           |
| 4 | sentrycs-sim    | `python3 -m sentrycs_sim --scenario demo.yaml`               | `GET /health` (`:17070`) → 200         |
| 5 | cot-gateway     | `python3 -m cot_gateway --config demo.yaml`                  | `GET /health` (`:18092`) → 200         |
| 6 | TAK relay       | `python3 scripts/tak_relay.py --port 8089`                   | TCP connect `:18089`                   |
| 7 | tak-client-sim  | `python3 -m tak_client_sim --config services/tak-client-sim/config/demo.yaml` | `GET /health` (`:18093`) → 200 |

The script MUST wait up to 30 seconds for all services to become healthy before
proceeding.

### FR-008 — `demo-1drone.sh` — browser launch

After all health checks pass, the script MUST open three browser tabs:
`http://127.0.0.1:18090/objects`, `http://127.0.0.1:18092/map`,
`http://127.0.0.1:18093/map`.  Opening MUST be attempted via `xdg-open` (Linux)
and `open` (macOS) in that order; failure of both MUST be non-fatal (URLs
printed to stdout).

### FR-009 — `demo-1drone.sh` — cleanup

The script MUST register `trap cleanup INT TERM EXIT`.  On `Ctrl-C` or
unexpected exit, it MUST send `SIGTERM` then `SIGKILL` (after 1 s) to all
started PIDs.  PID files under `.dev-runtime/pids/` MUST be written for each
service (keys: `map-sim`, `uds`, `echoshield-sim`, `sentrycs-sim`,
`cot-gateway`, `tak-relay`, `tak-client-sim`).  A `--stop` flag MUST read those
PID files and terminate services without requiring the demo to still be
running in the same shell.

### FR-010 — `demo-1drone.sh` — pre-flight checks

Before starting any service, the script MUST verify:

1. All required scenario/config files exist.
2. `python3` is available in `PATH`.
3. Each required Python module (`map_sim`, `uds`, `echoshield_sim`,
   `sentrycs_sim`, `cot_gateway`, `tak_client_sim`) is importable.
4. `scripts/tak_relay.py` exists as a file (file-existence check, not Python
   import, since it is a standalone script).
5. None of the ports 8089, 8090, 8092, 8093, 18080, 7070 are already bound.

On failure it MUST print an actionable `ERROR:` message and exit non-zero.

### FR-011 — `demo-3drone.sh`

`scripts/demo-3drone.sh` MUST be structurally identical to `demo-1drone.sh`
with the following config substitutions:

| Service        | 1-drone config                        | 3-drone config                             |
|----------------|---------------------------------------|--------------------------------------------|
| uds            | `demo_single_drone.yaml`              | `demo_three_drones.yaml`                   |
| sentrycs-sim   | `config/demo.yaml`                    | `config/demo_three_drones.yaml`            |

All other services, health checks, browser URLs, and cleanup logic MUST be
identical to `demo-1drone.sh`.

### FR-012 — Structured logging (no `print()`)

`tak-client-sim` production Python code (`web_server.py`, `cot_store.py`,
`models.py` and any new files) MUST use `structlog` for all runtime output.
No `print()` calls are permitted in production modules.  Demo shell scripts
may use `echo`.

### FR-013 — No wire-contract changes

The CoT XML format, TCP framing (NDJSON: CoT XML followed by `\n`), and all
HTTP JSON APIs (`/events`, `/health`) MUST remain unchanged.

### FR-014 — tak-client-sim plaintext (no-SSL) connection mode

`ClientConfig` MUST gain a `use_ssl: bool = True` field.  When `use_ssl` is
`false`, `connection.py` MUST pass `ssl=None` to `asyncio.open_connection`
(plaintext TCP).  When `use_ssl` is `true` (default), existing SSL behaviour
is unchanged.  `services/tak-client-sim/config/demo.yaml` MUST set
`use_ssl: false` so the demo connects to `tak_relay.py` (plaintext TCP on
`:18089`) without a TLS handshake.  No new Python dependencies are required.

---

## Key Entities

| Entity            | Description                                                                                   |
|-------------------|-----------------------------------------------------------------------------------------------|
| `CotEvent`        | Immutable dataclass holding `uid`, `cot_type`, `color`, `source`, `lat/lon/hae`, `speed`, `course`, `stale`, `raw_xml`.  Drives both icon shape (via `cot_type`) and colour (via `color`/`is_stale`). |
| `ColorLabel`      | `Literal["GREY", "RED", "UNKNOWN"]` — existing classification, maps to MIL affiliation: GREY→Unknown, RED→Hostile. |
| `CotStore`        | In-memory store keyed by UID; provides the `GET /events` payload consumed by the map. |
| TAK Stub Server   | Python TCP server at `infra/tak-server/stub_server.py`; accepts SSL-wrapped CoT XML on `:18089`. Used for SSL validation scenarios; **not** used in demo scripts. |
| TAK Relay         | `scripts/tak_relay.py` — plaintext TCP broadcast relay on `:18089`; cot-gateway (publisher) and tak-client-sim (subscriber) both connect to it. Used in demo scripts. |
| Demo Script       | Bash script that orchestrates all services for a single- or three-drone scenario; owns PID lifecycle and browser launch. |

---

## Success Criteria

| ID     | Criterion                                                                                                                       |
|--------|---------------------------------------------------------------------------------------------------------------------------------|
| SC-001 | Unknown-affiliation tracks (`a-u-*`) appear as the MIL-STD-2525C Unknown symbol (grey circle + cross) on the TAK client map within 2 s of the event being received. |
| SC-002 | Hostile-affiliation tracks (`a-h-*`) appear as the MIL-STD-2525C Hostile symbol (red diamond) on the TAK client map within 2 s of the event being received. |
| SC-003 | `scripts/demo-1drone.sh` starts all 7 services from a cold state in under 30 s on a developer laptop and opens 3 browser tabs. |
| SC-004 | During the single-drone scenario the drone track is visible simultaneously on all three map viewers (`:18090/objects`, `:18092/map`, `:18093/map`) by t = 30 s after script start. |
| SC-005 | `Ctrl-C` during either demo script leaves zero orphan processes after 5 s. |
| SC-006 | `scripts/demo-3drone.sh` produces three distinct track UIDs on the TAK client map during the three-drone playback. |
| SC-007 | No new Python packages appear in any `pyproject.toml` or `requirements*.txt` file as a result of this feature. |
| SC-008 | The `/events` and `/health` JSON response shapes are byte-for-byte identical to the pre-feature responses for the same input (wire-contract regression). |

---

## Assumptions

- `tak_relay.py` is used as the TAK relay in both demo scripts.  It is a
  plaintext TCP broadcast relay: cot-gateway (publisher) and tak-client-sim
  (subscriber) both connect to it on `:18089`.  `stub_server.py` is the
  alternative for SSL scenarios (e.g., actual TAK Server validation) and is
  **not** used in the demo scripts — it does not relay data to downstream
  clients.
- `tak-client-sim` `demo.yaml` sets `use_ssl: false` (plaintext, no TLS
  handshake) for the relay connection, and `:18093` for the web map; these
  values are not changed by the demo scripts.
- The MIL-STD-2525C affiliation mapping is exhaustive for this project:
  all observed CoT types begin with either `a-u` (Unknown) or `a-h` (Hostile).
  Any other prefix falls back gracefully to the existing UNKNOWN style.
- Browser auto-open is a convenience feature; the demo is fully functional
  if the operator manually navigates to the three URLs.
- `tak-client-sim/config/demo.yaml` sets `use_ssl: false` (plaintext TCP); the demo
  scripts do not need to generate TLS certificates.

---

## Out of Scope

- ATAK (Android) client integration or certificate provisioning.
- MIL-STD-2525C icons for affiliations beyond Unknown (`a-u`) and Hostile
  (`a-h`) — e.g., Friendly (`a-f`) or Neutral (`a-n`) are not used in this
  project's CoT type codes.
- Persistent storage of CoT events across restarts.
- Multi-host / networked deployment of the demo (localhost only).
- Changes to `cot-gateway`'s web map or any other service's UI.
- Automated CI/CD tests for the demo scripts.
- Docker-compose orchestration for the full pipeline.
