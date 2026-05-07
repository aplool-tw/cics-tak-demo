# Feature Specification: TAK Shared Connection

**Feature Branch**: `feature/016-tak-shared-connection`
**Created**: 2025-01-24
**Status**: Draft
**Feature ID**: 016

---

## User Scenarios & Testing *(mandatory)*

### User Story US-016-01 — Single-Point TAK Server Configuration (Priority: P1)

As a **demo operator**, I want to configure the TAK server address and SSL settings in one place so that I can switch between local and remote TAK mode without editing multiple files or setting multiple environment variables.

**Why this priority**: The root cause of current friction is duplicated config entry points (`TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` env vars AND per-service `config/remote-tak.yaml` templates). Unifying them into a single `config/remote-tak.yaml` at the repo root is the highest-value change and is a prerequisite for all downstream work.

**Independent Test**: Place a `config/remote-tak.yaml` at the repo root, run either demo script without setting `TAK_HOST` env var, and confirm the script detects remote mode and passes the correct host/port/SSL settings to both `cot-gateway` and `tak-client-sim`.

**Acceptance Scenarios**:

1. **Given** `config/remote-tak.yaml` does not exist, **When** a demo script is run, **Then** the script starts in local mode (includes `tak-relay`, skips remote TAK settings).
2. **Given** `config/remote-tak.yaml` exists with a valid `tak_server.host`, **When** a demo script is run, **Then** the script starts in remote mode — reads `host`, `port`, `use_ssl` from the YAML file and applies them to both services.
3. **Given** `config/remote-tak.yaml` exists, **When** `TAK_HOST` env var is also set, **Then** the YAML file settings take precedence (env-var override path is removed).
4. **Given** `config/remote-tak.yaml` exists with `use_ssl: false`, **When** a demo script is run, **Then** both services start without TLS enabled.

---

### User Story US-016-02 — Shared TAK Connection Library (Priority: P2)

As a **developer**, I want a single Python package (`libs/tak-connection`) that provides both the TAK connection configuration model and the SSL context builder so that neither `cot-gateway` nor `tak-client-sim` contains duplicated SSL logic or disconnected configuration models.

**Why this priority**: Duplicate `build_ssl_context` implementations across both services mean any SSL bug or new cert format must be fixed in two places. Extracting a shared library eliminates drift and enforces a single contract.

**Independent Test**: Install `libs/tak-connection` in isolation (no service dependencies), construct a `TakConnectionConfig` from a YAML dict, call `build_ssl_context`, and confirm the correct `ssl.SSLContext` is returned. Then confirm both `cot-gateway` and `tak-client-sim` unit tests pass against the shared implementation.

**Acceptance Scenarios**:

1. **Given** a dict with TAK connection fields, **When** `TakConnectionConfig.model_validate(...)` is called, **Then** a valid frozen model is returned; extra fields raise a validation error.
2. **Given** `TakConnectionConfig` with `use_ssl=True` and a PEM cert path, **When** `build_ssl_context(cfg)` is called, **Then** an `ssl.SSLContext` is returned with hostname verification matching `use_ssl_verify`.
3. **Given** `TakConnectionConfig` with a P12 cert path and password, **When** `build_ssl_context(cfg)` is called, **Then** P12 is decoded via `cryptography`, temp PEM files are written, and an `ssl.SSLContext` is returned.
4. **Given** `TakConnectionConfig` with a cert path that does not exist, **When** `build_ssl_context(cfg)` is called, **Then** a `FileNotFoundError` is raised with the missing path.
5. **Given** `cot-gateway` is configured via its existing `config/demo.yaml`, **When** `cot-gateway` starts, **Then** it operates identically to before the refactor (G2 Contract Freeze: no YAML field name changes).
6. **Given** `tak-client-sim` is configured via its existing `config/demo.yaml`, **When** `tak-client-sim` starts, **Then** it operates identically to before the refactor.
7. **Given** `TakConnectionConfig` with `use_ssl=True` and `cert_file=None`, **When** `build_ssl_context(cfg)` is called, **Then** an `ssl.SSLContext` is returned without loading a client certificate (CA-only / server-verify TLS); no error is raised.

---

### User Story US-016-03 — Documentation Update (Priority: P3)

As a **developer or new contributor**, I want updated README files and a dev-docs entry that explain the shared config file, the new library, and the removal of per-service remote-tak templates so that I can configure a real TAK integration in under five minutes without reading source code.

**Why this priority**: Documentation is essential for PoC handoff and future contributors but does not block system function; it follows correct implementations.

**Independent Test**: Follow only the updated root README instructions to connect to a real TAK server; confirm no step requires editing per-service files or setting env vars.

**Acceptance Scenarios**:

1. **Given** the root `README.md`, **When** a reader follows the "Remote TAK Server" section, **Then** they are directed only to `config/remote-tak.yaml` (no reference to `TAK_HOST`/`TAK_PORT` env vars).
2. **Given** `services/cot-gateway/README.md`, **When** read, **Then** it accurately describes that TAK connection settings are shared via `libs/tak-connection` and `config/remote-tak.yaml`.
3. **Given** `dev-docs/016-tak-shared-connection.md`, **When** read, **Then** it explains the before/after architecture, migration steps, and the G2 contract freeze rationale.

---

### Edge Cases

- **`cert_file=None` with `use_ssl=True`**: `TakConnectionConfig` with `use_ssl: true` and `cert_file: null/None` — `build_ssl_context` MUST skip client-certificate loading and proceed with CA-only (server-verify) TLS. This is valid for read-only subscribers (e.g., `tak-client-sim`) that do not present a client certificate. No error is raised.
- **Empty `cert_password`**: An empty string `""` in YAML for `cert_password` must be treated as `null`/`None` (preserving current cot-gateway behaviour).
- **Unreadable `config/remote-tak.yaml`**: If the file exists but cannot be parsed (bad YAML), the demo script must exit with a clear error message, not silently fall back to local mode.
- **`host` is empty string**: YAML `tak_server.host: ""` must cause validation failure, not silently connect to `""`.
- **P12 missing cert or key**: If the P12 archive decodes but contains no certificate or private key, `build_ssl_context` must raise a `ValueError` (not an opaque `AttributeError`).
- **CA bundle path when `use_ssl_verify: false`**: If `ca_bundle` is set but `use_ssl_verify` is `false`, the CA bundle is silently ignored (current behaviour preserved).
- **`tak-client-sim` does not use `cert_file`**: The shared model's `cert_file` field is optional; `tak-client-sim` config YAML has no `cert_file` key, so absence must be valid (no extra-field error).
- **Concurrent library import**: Both services run in separate processes; there is no shared state in the library.

---

## Requirements *(mandatory)*

### Functional Requirements

#### RC1 — Shared Remote TAK Config File

- **FR-016-001**: A single `config/remote-tak.yaml` file at the repository root MUST hold all TAK server connection settings for demo mode (`tak_server.host`, `tak_server.port`, `tak_server.use_ssl`, `tak_server.use_ssl_verify`, `tak_server.cert_file`, `tak_server.cert_password`, `tak_server.ca_bundle`).
- **FR-016-002**: The demo scripts (`scripts/demo-1drone-remote-tak.sh`, `scripts/demo-3drone-remote-tak.sh`) MUST detect remote mode by checking whether `config/remote-tak.yaml` **exists** (not by checking the `TAK_HOST` env var).
- **FR-016-003**: The demo scripts MUST read `config/remote-tak.yaml` using `python3 -c "import yaml; ..."` to extract `tak_server.host`, `tak_server.port`, and `tak_server.use_ssl` and pass them to both `cot-gateway` and `tak-client-sim`.
- **FR-016-004**: The per-service `config/remote-tak.yaml` files (`services/cot-gateway/config/remote-tak.yaml` and `services/tak-client-sim/config/remote-tak.yaml`) MUST be removed.
- **FR-016-005**: `config/remote-tak.yaml` MUST include clear operator comments documenting each field and the certificate placement path (preserving the documentation quality of the files it replaces).
- **FR-016-006**: The `TAK_HOST`, `TAK_PORT`, and `TAK_USE_SSL` env-var code paths in both demo scripts MUST be removed.

#### RC2 — Shared TAK Connection Library

- **FR-016-010**: A Python package at `libs/tak-connection/` MUST be created following the same directory layout convention as services (`src/`, `tests/{unit,integration}/`, `pyproject.toml`, `README.md`).
- **FR-016-011**: The package MUST expose a `TakConnectionConfig` Pydantic v2 model with `model_config = ConfigDict(extra="forbid", frozen=True)`.
- **FR-016-012**: `TakConnectionConfig` MUST define the following fields (all names identical to existing YAML keys — G2 Contract Freeze):
  - `host: str` (no default; required)
  - `port: int` (default `8089`, validated `1–65535`)
  - `use_ssl: bool` (default `True`)
  - `use_ssl_verify: bool` (default `False`)
  - `cert_file: str | None` (default `None`)
  - `cert_password: str | None` (default `None`)
  - `ca_bundle: str | None` (default `None`)
- **FR-016-013**: The package MUST expose `build_ssl_context(cfg: TakConnectionConfig) -> ssl.SSLContext` that reproduces the full p12→PEM→SSLContext path currently in `services/cot-gateway/src/cot_gateway/tak/ssl_context.py`.
- **FR-016-014**: `build_ssl_context` MUST support both PEM/CRT direct load (no `cryptography` dep needed) and P12 decode via `cryptography`.
- **FR-016-015**: `build_ssl_context` MUST raise `FileNotFoundError` only when `cert_file` is a **non-`None`** path that does not exist on disk. When `cert_file` is `None`, client-certificate loading is skipped; the function proceeds with CA-only (server-verify) TLS and MUST NOT raise an error.
- **FR-016-016**: The package MUST depend only on Python stdlib, `pydantic` (v2), and `cryptography` (G7 Minimal Dependencies).
- **FR-016-017**: `cot-gateway` MUST import `TakConnectionConfig` and `build_ssl_context` from `libs/tak-connection` and MUST remove its own `tak/ssl_context.py` SSL-context duplication.
- **FR-016-018**: `tak-client-sim` MUST import `TakConnectionConfig` and `build_ssl_context` from `libs/tak-connection` and MUST remove its own `connection.py` SSL-context duplication.
- **FR-016-019**: `cot-gateway`'s `TakServerConfig` MUST use **composition/delegation** (NOT inheritance) to pass SSL connection fields to `TakConnectionConfig`. `TakServerConfig` retains its exact current field names and defaults so `config/demo.yaml` works unchanged (G2 Contract Freeze). Internally, it constructs a `TakConnectionConfig` instance to pass to `build_ssl_context()`.
- **FR-016-020**: `tak-client-sim`'s `ClientConfig` MUST use **composition/delegation** (NOT inheritance) to construct a `TakConnectionConfig` before calling `build_ssl_context()`. The flat YAML keys (`host`, `port`, `use_ssl`, etc.) in `config/demo.yaml` MUST remain unchanged (G2 Contract Freeze).
- **FR-016-021**: The shared `libs/tak-connection` library MUST use Python's **stdlib `logging`** module (or raise exceptions) for any diagnostic output — NOT `structlog`. `structlog` is only required in service code (`cot-gateway`, `tak-client-sim`). This keeps `libs/tak-connection` a pure utility with minimal dependencies (G7 Minimal Deps).
- **FR-016-022**: Tests for `libs/tak-connection` MUST be written **before** implementation and confirmed to FAIL (G1 Test-First). Tests MUST cover: model validation (valid + invalid inputs), `build_ssl_context` with PEM cert, with P12 cert, with missing cert file (`FileNotFoundError`), with `cert_file=None` + `use_ssl=True` (CA-only TLS, no error), and with `use_ssl_verify=True/False`.

#### RC3 — Documentation

- **FR-016-030**: `dev-docs/016-tak-shared-connection.md` MUST be created documenting: motivation, before/after architecture, migration guide (for future services), and G2 contract freeze notes.
- **FR-016-031**: Root `README.md` "Remote TAK Server" section MUST be updated to reference `config/remote-tak.yaml` only (no `TAK_HOST`/`TAK_PORT` env var instructions).
- **FR-016-032**: `services/cot-gateway/README.md` MUST be updated to describe the dependency on `libs/tak-connection` and removal of local `ssl_context.py`.
- **FR-016-033**: `services/tak-client-sim/README.md` MUST be updated to describe the dependency on `libs/tak-connection` and removal of local SSL context logic.
- **FR-016-034**: Demo script inline comments for remote TAK mode MUST be updated to reference `config/remote-tak.yaml` as the activation mechanism.

---

### Key Entities

- **`TakConnectionConfig`** (new, in `libs/tak-connection`): Pydantic v2 frozen model representing a TAK server TCP+TLS endpoint. Fields: `host`, `port`, `use_ssl`, `use_ssl_verify`, `cert_file`, `cert_password`, `ca_bundle`. This is the canonical representation of a TAK connection across all services in the repo.

- **`build_ssl_context`** (new, in `libs/tak-connection`): Pure function — takes a `TakConnectionConfig`, returns an `ssl.SSLContext`. Supports PEM/CRT direct load and P12-to-PEM conversion via `cryptography`. No side effects beyond temp file creation (cleaned up before return).

- **Root `config/remote-tak.yaml`** (new, replaces two per-service files): Committed YAML file at repo root with a placeholder host (`192.168.1.100`). Contains ONLY the `tak_server:` block (not a full gateway config). Demo scripts read `tak_server.host`, `tak_server.port`, `tak_server.use_ssl` from it and pass them as CLI args to both services. Absence of this file signals "local demo mode."

- **`TakServerConfig`** (existing, in `cot-gateway`): Retains its exact current shape (all same field names, same defaults) so `config/demo.yaml` works unchanged. Does NOT inherit from `TakConnectionConfig`. Internally constructs a `TakConnectionConfig` instance to pass to `build_ssl_context()` (composition/delegation). No YAML field renames.

- **`ClientConfig`** (existing, in `tak-client-sim`): Retains its exact current shape (flat YAML keys). Does NOT inherit from `TakConnectionConfig`. Internally constructs a `TakConnectionConfig` instance to pass to `build_ssl_context()` (composition/delegation). No YAML field renames.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-016-01**: An operator can activate remote TAK mode for both demo scripts by creating or editing a **single file** (`config/remote-tak.yaml`) — no environment variables required.
- **SC-016-02**: The shared SSL context builder (`build_ssl_context`) is the **only** implementation in the repository; both services reference it directly with no local copies.
- **SC-016-03**: All existing `cot-gateway` and `tak-client-sim` pytest tests pass without modification after the refactor (G2 Contract Freeze verified).
- **SC-016-04**: `libs/tak-connection` unit tests achieve 100% branch coverage of `build_ssl_context` (PEM path, P12 path, missing cert path, verify-on/off paths).
- **SC-016-05**: `ruff check .` and `black --check src tests` pass clean for `libs/tak-connection`, `cot-gateway`, and `tak-client-sim` after the change.
- **SC-016-06**: A developer following only the updated root `README.md` can configure and launch a remote TAK demo in under 5 minutes without consulting per-service READMEs.

---

## Assumptions

- `cot-gateway`'s `TakServerConfig` keeps its exact current field names and defaults (no inheritance from `TakConnectionConfig`); it constructs a `TakConnectionConfig` instance internally when calling `build_ssl_context()`. The existing YAML schema `tak_server.host`, `tak_server.port`, … is preserved without introducing a new YAML nesting level.
- `tak-client-sim`'s flat YAML keys (`host`, `port`, `use_ssl`, …) remain at the top level of the config file; `TakConnectionConfig` fields are re-exposed at the same YAML level, not nested under `tak_server:`.
- `libs/tak-connection` is installed as a local editable dependency (`pip install -e libs/tak-connection`) in both service `pyproject.toml` files; it is not published to PyPI.
- The shared library does not handle retry or backoff logic — those remain service-specific (`max_retries`, `backoff_initial_s`, `backoff_cap_s` stay in per-service config models).
- Temp PEM files created by `build_ssl_context` during P12 decoding are cleaned up via `os.unlink` after `ctx.load_cert_chain` succeeds (preserving current behaviour).
- The root `config/remote-tak.yaml` is **committed** with a placeholder IP (`192.168.1.100`). Users edit the file to switch to their TAK server. The file MUST NOT be gitignored. The `config/certs/` directory (which may contain real P12 files) IS added to `.gitignore`; a `config/certs/.gitkeep` placeholder is committed instead.
- No existing contract between services changes: EchoShield NDJSON, Sentrycs HTTP, CoT XML wire format are unaffected.

---

## Out of Scope

- Changing any wire protocol (CoT XML framing, NDJSON format, HTTP API schemas).
- Adding new configuration fields to `TakConnectionConfig` beyond those already present in both service config models.
- Implementing certificate rotation, dynamic config reload, or hot-reload of `config/remote-tak.yaml` at runtime.
- Publishing `libs/tak-connection` as a standalone PyPI package.
- Adding retry or backoff logic to the shared library (remains service-specific).
- Modifying `config/demo.yaml` for either service.
- Changes to any service other than `cot-gateway` and `tak-client-sim`.

---

## Clarifications

### Session 2026-05-07

- Q: What should `build_ssl_context` do when `cert_file=None` and `use_ssl=True`? → A: Skip client-cert loading; connect with CA-only (server-verify) TLS. Raise `FileNotFoundError` only when `cert_file` is a non-`None` path that doesn't exist on disk. This is intentional: `tak-client-sim` is a read-only subscriber that does NOT present a client certificate.
- Q: Should `TakServerConfig` and `ClientConfig` inherit from `TakConnectionConfig` or use composition/delegation? → A: Composition/delegation only. Neither config class inherits from `TakConnectionConfig`. Both retain their exact current field shapes (G2 Contract Freeze) and construct a `TakConnectionConfig` internally before calling `build_ssl_context()`.
- Q: Does the root `config/remote-tak.yaml` contain only a `tak_server` block, or is it a full gateway config? → A: It contains ONLY the `tak_server` block. Demo scripts read `tak_server.host`, `tak_server.port`, `tak_server.use_ssl` from it to decide remote mode and set CLI args for both services.
- Q: Should `config/remote-tak.yaml` be committed or gitignored? → A: Committed, with a placeholder IP `192.168.1.100`. The file itself is NOT gitignored. The `config/certs/` directory (containing real P12 files) IS gitignored.
- Q: How do demo scripts pass TAK server settings to `tak-client-sim` in remote mode? → A: Via CLI args (`--host HOST --port PORT`), the same pattern already used for `cot-gateway` (`--tak-host HOST --tak-port PORT`). `tak-client-sim/config.py`'s `load_config()` already supports `args.host` and `args.port` overrides.
- Q: Should the shared `libs/tak-connection` library use `structlog`? → A: No. The library is a pure utility with no I/O or running service. It MUST use Python's stdlib `logging` (or raise exceptions). `structlog` is only required in service code (`cot-gateway`, `tak-client-sim`). FR-016-021 updated accordingly.
