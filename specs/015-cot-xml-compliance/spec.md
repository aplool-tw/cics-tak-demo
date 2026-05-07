# Feature Specification: CoT XML Standard Format Compliance + Remote TAK Server Support

**Feature ID**: 015  
**Feature Branch**: `015-cot-xml-compliance`  
**Created**: 2025-07-14  
**Status**: Draft  
**Spec Directory**: `specs/015-cot-xml-compliance/`

---

## User Scenarios & Testing *(mandatory)*

### User Story US-015-01 — Operator Connects CoT Gateway to a Real TAK Server (Priority: P1)

An operator deploying the anti-drone system in a live exercise wants to connect `cot-gateway`
directly to a real TAK server (e.g., TAK Server CE/EUD) instead of the local `tak_relay.py`.
The real server requires mutual TLS with a P12 certificate, expects well-formed CoT 2.0 XML that
includes a `<uid Droid>` device-identification element, and optionally expects an XML declaration
header.  The operator should be able to point the gateway at the real server by editing a single
config YAML (or passing two CLI flags) and restarting the service — without touching any source
code.

**Why this priority**: Without this story the system is demo-only.  Real TAK integrations are
the primary business goal of the PoC.

**Independent Test**: Run `cot-gateway --config services/cot-gateway/config/remote-tak.yaml
--tak-host 192.0.2.10 --tak-port 8089` and confirm the gateway connects, sends CoT with
`<uid Droid>`, and the TAK Server displays the tracks.  Can be tested in isolation with a
stub TAK server that validates the received XML.

**Acceptance Scenarios**:

1. **Given** a `remote-tak.yaml` config with `tak_server.host`, `tak_server.port`, `use_ssl: true`,
   `cert_file` and `ca_bundle` populated,  
   **When** `cot-gateway` starts with `--config remote-tak.yaml`,  
   **Then** the gateway establishes a TLS connection to the remote TAK server and begins
   forwarding CoT XML events.

2. **Given** a gateway started without `--tak-host` / `--tak-port` flags,  
   **When** a track event is produced,  
   **Then** the CoT XML sent to the TAK server contains `<uid Droid="{callsign}"/>` inside
   `<detail>` and all existing contract elements (`<event>`, `<point>`, `<contact callsign>`,
   `<remarks>`, `<track>`) are unchanged.

3. **Given** `xml_declaration: true` in `TakServerConfig`,  
   **When** a CoT event is generated,  
   **Then** the output string starts with
   `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>`.

4. **Given** `xml_declaration: false` (default),  
   **When** a CoT event is generated,  
   **Then** the output string starts with `<event` (no XML declaration).

5. **Given** `--tak-host 10.0.0.5 --tak-port 8089` passed on the CLI,  
   **When** the gateway reads its config file,  
   **Then** the CLI values override `tak_server.host` and `tak_server.port` from the YAML.

---

### User Story US-015-02 — TAK Client Sim Operator Connects to Remote TAK Server (Priority: P2)

A TAK operator running `tak-client-sim` for end-to-end testing wants to point the simulator
at a real remote TAK server instead of `tak_relay`.  The same YAML config pattern used by
`cot-gateway` should be available for `tak-client-sim`.

**Why this priority**: Enables full end-to-end smoke-testing against a real TAK environment
without code changes.

**Independent Test**: Run `tak-client-sim --config services/tak-client-sim/config/remote-tak.yaml`
and confirm it connects to the remote server and logs received CoT events.

**Acceptance Scenarios**:

1. **Given** `services/tak-client-sim/config/remote-tak.yaml` exists and contains valid host,
   port, SSL, and `ca_bundle` fields,  
   **When** `tak-client-sim` is started with that config,  
   **Then** it connects to the remote TAK server and begins receiving/logging CoT events without
   any code change.

2. **Given** the `tak-client-sim` README,  
   **When** an operator reads the "Connecting to Real TAK Server" section,  
   **Then** they can follow the instructions end-to-end with no prior knowledge of the codebase.

---

### User Story US-015-03 — DevOps Operator Runs Remote-TAK Demo Scripts (Priority: P2)

A DevOps/field operator wants a single command to start the full 1-drone or 3-drone pipeline
with tracks flowing directly to a real TAK server, configured via environment variables, with
no code changes required.

**Why this priority**: Simplifies field deployment; removes need to edit config files at runtime.

**Independent Test**: Set `TAK_HOST=192.0.2.10 TAK_PORT=8089` and run
`./scripts/demo-1drone-remote-tak.sh`.  Confirm all services start, tracks appear on the real
TAK server, and the script exits cleanly on Ctrl-C.

**Acceptance Scenarios**:

1. **Given** `TAK_HOST`, `TAK_PORT`, and `TAK_USE_SSL` environment variables are set,  
   **When** `demo-1drone-remote-tak.sh` is executed,  
   **Then** the pipeline starts using the real TAK server instead of `tak_relay.py`.

2. **Given** `TAK_HOST` is not set (unset or empty),  
   **When** either remote-TAK demo script is executed,  
   **Then** the script falls back to local `tak_relay.py` mode and prints a warning.

3. **Given** the 3-drone scenario,  
   **When** `demo-3drone-remote-tak.sh` is executed with `TAK_HOST` set,  
   **Then** all three drone tracks reach the real TAK server with correct CoT XML.

---

### User Story US-015-04 — Developer Reads Logs and Understands Wire Format (Priority: P3)

A developer seeing structured JSON log output from `cot-gateway` or `tak-client-sim` should
clearly understand that logs are in structlog JSON format and that the CoT XML wire format is
separate — to avoid confusion between the two representations.

**Why this priority**: Documentation clarity prevents incorrect assumptions about the protocol;
low risk but corrects a known confusion point.

**Independent Test**: Read the READMEs and `AGENTS.md` and confirm a developer new to the project
would not confuse log output with wire-format CoT XML.

**Acceptance Scenarios**:

1. **Given** the `services/cot-gateway/README.md`,  
   **When** an operator reads the logging section,  
   **Then** they find an explicit note: "Service logs are structured JSON (structlog); the
   wire protocol sent to TAK Server is CoT XML."

2. **Given** `services/tak-client-sim/README.md`,  
   **When** a developer reads about received messages,  
   **Then** the same log-vs-wire clarification is present.

3. **Given** `AGENTS.md` logs section,  
   **When** a contributor reads the logging guidelines,  
   **Then** they see a note that log format does not equal wire format.

---

### Edge Cases

- **XML declaration + relay compatibility**: When `xml_declaration: false` (default), output is
  byte-identical to the current format; existing integration tests and `tak_relay.py` must not
  be affected.
- **`<uid Droid>` with special characters in callsign**: Callsigns like `ECHO-TRK-001` or
  `FUSED-DRN-001` are ASCII-safe; however `xml.etree.ElementTree` must set the attribute value
  via the API (not string concatenation) to guarantee XML-safe output.
- **CLI override with missing value**: `--tak-host` or `--tak-port` provided without the other
  must each apply independently; partial overrides are valid.
- **`remote-tak.yaml` cert paths**: Files may not exist on the developer's machine; the example
  config must clearly mark placeholder values and provide a comment explaining how to populate them.
- **`tak_relay.py` unmodified**: The fallback path in the remote-TAK scripts must not touch
  `tak_relay.py`; local relay mode must remain bit-for-bit identical to `demo-1drone.sh` /
  `demo-3drone.sh`.
- **Existing 180 + 99 tests**: Adding `xml_declaration` field and `<uid Droid>` element must not
  break any currently passing test.  New fields use defaults that preserve current behaviour.
- **`TakServerConfig` pydantic `extra="forbid"`**: Adding `xml_declaration` requires it to be
  declared as a proper model field, not injected at runtime.
- **Source-switch double-message compatibility**: The `<uid Droid>` addition must appear in
  both the "final CoT on old uid" and the "first CoT on new uid" messages.

---

## Requirements *(mandatory)*

### Functional Requirements

#### RC1 — CoT XML Format Compliance

- **FR-015-001**: The CoT generator MUST support an `xml_declaration` boolean field in
  `TakServerConfig` (default `False`).  When `True`, every generated CoT event string MUST
  be prefixed with `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>`.
  When `False`, no declaration is prepended (backward-compatible default).

- **FR-015-002**: The CoT generator MUST add a `<uid Droid="{callsign}"/>` child element to the
  `<detail>` block of every generated CoT event.  The `Droid` attribute value MUST equal the
  `uid` attribute on the `<event>` element (same value as `<contact callsign>`).

- **FR-015-003**: All existing `<detail>` child elements (`<contact callsign>`, `<remarks>`,
  `<track>`) MUST remain present and unchanged in position, attribute names, attribute values,
  and text content relative to the current contract (`specs/005-cot-gateway/contracts/cot-xml.md`).

- **FR-015-004**: All existing `<event>` attributes (`version`, `uid`, `type`, `time`, `start`,
  `stale`, `how`) and `<point>` attributes (`lat`, `lon`, `hae`, `ce`, `le`) MUST remain
  unchanged in name, value derivation, and serialisation format.

- **FR-015-005**: The `<uid Droid>` attribute value MUST be set via the `xml.etree.ElementTree`
  API (element attribute assignment), not by string concatenation, so that XML-special characters
  in callsigns are automatically escaped.

- **FR-015-006**: The updated contract example in `specs/005-cot-gateway/contracts/cot-xml.md`
  MUST reflect the addition of `<uid Droid>` in the `<detail>` block; all other contract rules
  remain frozen.

- **FR-015-007**: A dedicated test suite MUST exist that:
  (a) verifies `<uid Droid>` is present and equals the event `uid` for all 8 compliance-matrix
      scenarios from §7 of `cot-xml.md`;
  (b) verifies that `xml_declaration=True` produces output starting with the expected declaration;
  (c) verifies that `xml_declaration=False` produces output starting with `<event`;
  (d) verifies that all 8 existing compliance-matrix scenarios still pass (no regression).

#### RC2 — Remote TAK Server Config Examples & CLI Flags

- **FR-015-008**: A file `services/cot-gateway/config/remote-tak.yaml` MUST be created with
  clearly documented placeholder values for `tak_server.host`, `tak_server.port`,
  `tak_server.use_ssl`, `tak_server.cert_file`, and `tak_server.ca_bundle`.  Comments MUST
  explain each field and how to populate certificate paths.

- **FR-015-009**: A file `services/tak-client-sim/config/remote-tak.yaml` MUST be created
  with clearly documented placeholder values for `host`, `port`, `use_ssl`, and `ca_bundle`.

- **FR-015-010**: `cot-gateway/cli.py` MUST expose two new optional CLI flags:
  `--tak-host HOST` and `--tak-port PORT`.  These flags MUST override `tak_server.host` and
  `tak_server.port` respectively from the loaded config, following the same `model_copy` pattern
  used for `--web-host` / `--web-port`.

- **FR-015-011**: `services/cot-gateway/README.md` MUST include a "Connecting to Real TAK Server"
  section documenting: editing `remote-tak.yaml`, obtaining/placing certificates, and running
  the gateway with `--config` and optional `--tak-host` / `--tak-port` overrides.

- **FR-015-012**: `services/tak-client-sim/README.md` MUST include a "Connecting to Real TAK
  Server" section documenting analogous steps for the client simulator.

- **FR-015-013**: A test MUST verify that `--tak-host` and `--tak-port` CLI overrides are applied
  to the loaded `TakServerConfig` and that the underlying config object reflects the override
  values (not the YAML defaults).

#### RC3 — Demo Scripts Remote TAK Support

- **FR-015-014**: `scripts/demo-1drone-remote-tak.sh` MUST be created.  When `TAK_HOST` is set
  and non-empty, the script MUST start `cot-gateway` with `--tak-host "$TAK_HOST"
  --tak-port "${TAK_PORT:-8089}"` and skip starting `tak_relay.py`.  When `TAK_HOST` is unset
  or empty, the script MUST fall back to local `tak_relay.py` mode (identical to `demo-1drone.sh`)
  and print a warning.

- **FR-015-015**: `scripts/demo-3drone-remote-tak.sh` MUST be created with the same remote /
  fallback logic as FR-015-014 but based on `demo-3drone.sh`.

- **FR-015-016**: `scripts/tak_relay.py` MUST NOT be modified by this feature.

- **FR-015-017**: The remote-TAK scripts MUST accept `TAK_USE_SSL` as an optional environment
  variable (values `true` / `false`; default `true`).  When `false`, the scripts MUST pass
  configuration that disables TLS for the gateway connection to the TAK server.

#### RC4 — Log vs Wire Format Documentation

- **FR-015-018**: `services/cot-gateway/README.md` MUST contain an explicit note in its logging
  section stating that service logs are structured JSON (structlog format) and that the wire
  protocol sent to TAK Server is CoT XML — the two formats are independent.

- **FR-015-019**: `services/tak-client-sim/README.md` MUST contain the same log-vs-wire
  clarification in its logging section.

- **FR-015-020**: `AGENTS.md` logs section MUST be updated with a note that log format does not
  equal wire format (CoT XML).

---

### Key Entities

#### Config Fields

| Entity | Field | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `TakServerConfig` | `xml_declaration` | `bool` | `False` | Prepend XML declaration to every CoT event string |
| `TakServerConfig` | `ca_bundle` | `str \| None` | `None` | Path to CA bundle PEM for TLS peer verification (mirrors tak-client-sim pattern) |

#### CLI Flags (cot-gateway)

| Flag | Type | Overrides | Description |
|------|------|-----------|-------------|
| `--tak-host HOST` | `str` | `tak_server.host` | TAK Server hostname or IP override |
| `--tak-port PORT` | `int` | `tak_server.port` | TAK Server TCP port override |

#### New XML Element

| Element | Location | Attribute | Value | Rule |
|---------|----------|-----------|-------|------|
| `<uid/>` | `<detail>` child | `Droid` | `{callsign}` (equals event `uid`) | MUST appear as first child of `<detail>` before `<contact/>` |

#### Example Files (new)

| File | Purpose |
|------|---------|
| `services/cot-gateway/config/remote-tak.yaml` | Example gateway config for real TAK server |
| `services/tak-client-sim/config/remote-tak.yaml` | Example client-sim config for real TAK server |
| `scripts/demo-1drone-remote-tak.sh` | 1-drone pipeline demo with remote TAK support |
| `scripts/demo-3drone-remote-tak.sh` | 3-drone pipeline demo with remote TAK support |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-015-001**: All 180 existing `cot-gateway` tests and all 99 existing `tak-client-sim` tests
  continue to pass after all changes are merged; zero regressions.

- **SC-015-002**: The CoT gateway produces CoT XML that is accepted without errors by a
  real TAK Server (CE or EUD) when `xml_declaration: true` and a valid P12 certificate are
  configured — confirmed by tracks appearing in ATAK/WinTAK with correct callsigns and icons.

- **SC-015-003**: A developer new to the project can, following only the README documentation,
  connect both `cot-gateway` and `tak-client-sim` to a real TAK server within 30 minutes of
  first reading.

- **SC-015-004**: The `<uid Droid>` element is present and correct in 100% of generated CoT
  events across all 8 compliance-matrix scenarios (ECHOSHIELD/SENTRYCS/FUSED × Active/Lost/
  DETECTED/MITIGATING/NEUTRALIZED).

- **SC-015-005**: The remote-TAK demo scripts start the full pipeline end-to-end and route tracks
  to the real TAK server within 60 seconds of invocation when the `TAK_HOST` environment
  variable is set.

- **SC-015-006**: When `xml_declaration: false` (default), generated CoT XML is byte-identical
  in structure to the current output (only `<uid Droid>` is added; no other bytes change),
  confirmed by diff against existing contract test golden samples.

- **SC-015-007**: The `--tak-host` and `--tak-port` CLI flags successfully override config-file
  values, confirmed by automated tests that check the loaded config object and by an integration
  smoke test against a local stub server.

---

## Assumptions

- The project uses pydantic v2 with `model_config = ConfigDict(extra="forbid", frozen=True)` for
  all service config models; any new config field must be declared as a proper pydantic field
  with a default value.
- `xml.etree.ElementTree` (stdlib) is the only XML library in scope; no external XML/schema
  validation libraries will be added (constraint G7).
- `tak_relay.py` is a local development convenience tool only; it does not need SSL/cert support
  and will not be modified.
- Certificate files (P12, PEM CA bundle) are generated externally (e.g., via `scripts/gen-certs.sh`
  or provided by the TAK server administrator); this feature does not implement cert generation.
- `TakServerConfig` already has `use_ssl`, `use_ssl_verify`, and `cert_file` fields; `ca_bundle`
  is the only missing field needed for full remote-server TLS configuration.
- The `<uid Droid>` element placement as the first child of `<detail>` follows ATAK convention;
  TAK servers that do not use `<uid Droid>` will silently ignore it.
- Demo scripts are bash and rely on the same Python virtual-environment / process-management
  pattern established in `demo-1drone.sh` and `demo-3drone.sh`.
- All new log events introduced by this feature MUST use structlog JSON (constraint G3).
- Tests are written before implementation (constraint G1 test-first).

---

## Non-Goals

The following are explicitly **out of scope** for this feature:

- **No changes to existing `<event>` attributes** (`version`, `uid`, `type`, `time`, `start`,
  `stale`, `how`) — these are contract-frozen.
- **No changes to `<point>` attributes** — contract-frozen.
- **No changes to `<contact callsign>`, `<remarks>`, `<track>`** elements or their attributes —
  contract-frozen.
- **No certificate generation tooling** — `gen-certs.sh` is not in scope; only documentation of
  cert placement.
- **No TAK Server administration UI or API** — this feature is client-side only.
- **No changes to `tak_relay.py`** — the local relay must remain unmodified.
- **No mobile / ATAK plugin changes** — TAK client configuration is out of scope.
- **No changes to upstream data sources** (EchoShield, SentryCS, UDS, Map Sim) — only
  `cot-gateway`, `tak-client-sim`, and deployment scripts are in scope.
- **No new Python package dependencies** — all implementation uses stdlib and existing
  dependencies only (constraint G7).
- **No changes to the CoT stale/type/UID derivation logic** — only the serialisation layer
  gains `<uid Droid>` and optional XML declaration.
- **No multi-gateway or load-balanced deployment** — single-gateway topology only.

---

## References

- `specs/005-cot-gateway/contracts/cot-xml.md` — frozen CoT 2.0 XML contract (to be updated with `<uid Droid>`)
- `services/cot-gateway/src/cot_gateway/cot/generator.py` — XML generation implementation
- `services/cot-gateway/src/cot_gateway/config.py` — `TakServerConfig` pydantic v2 model
- `services/cot-gateway/src/cot_gateway/cli.py` — CLI entry point with `--web-host`/`--web-port` pattern
- `services/tak-client-sim/src/tak_client_sim/config.py` — `ClientConfig` pydantic v2 model
- `scripts/demo-1drone.sh` — baseline 1-drone demo script
- `scripts/demo-3drone.sh` — baseline 3-drone demo script
- `AGENTS.md` — project constraints G1–G7
