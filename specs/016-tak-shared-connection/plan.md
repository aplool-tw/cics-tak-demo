# Implementation Plan: TAK Shared Connection Library

**Branch**: `feature/016-tak-shared-connection` | **Date**: 2025-01-24 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/016-tak-shared-connection/spec.md`

## Summary

Extract duplicated SSL context logic from `cot-gateway` and `tak-client-sim` into a new
shared Python package `libs/tak-connection` containing `TakConnectionConfig` (Pydantic v2
frozen model) and `build_ssl_context()` (pure function, PEM + P12 → `ssl.SSLContext`).
Unify TAK server configuration for demo mode to a single `config/remote-tak.yaml` at repo
root; refactor both demo scripts to detect remote mode by file existence rather than the
`TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` env-var trio. Both services retain their exact current
YAML field names and defaults (G2 Contract Freeze).

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `pydantic>=2.6`, `cryptography` (both already in `cot-gateway`; adding to `tak-client-sim`)  
**Storage**: N/A — library is a pure utility; `build_ssl_context` creates temp PEM files that are cleaned up before return  
**Testing**: `pytest>=8.0`, `pytest-asyncio>=0.23`, `ruff>=0.4`, `black>=24.3`  
**Target Platform**: Linux (same environment as both services)  
**Project Type**: Shared library (`libs/tak-connection`) + refactor of two existing services + shell script updates  
**Performance Goals**: N/A — `build_ssl_context` is called once at service startup; no latency constraint  
**Constraints**: G2 (no YAML field renames in demo.yaml), G7 (only `pydantic` + `cryptography` as new deps), 209 cot-gateway tests + 99 tak-client-sim tests must stay green  
**Scale/Scope**: 3 Python files in the new library; ~15 file changes across services and scripts

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

> Note: `.specify/memory/constitution.md` is an unfilled template. Gates below are derived
> from the project-specific guards stated in the spec (G1–G7).

| Gate | Requirement | Status |
|------|-------------|--------|
| **G1 Test-First** | Tests written and confirmed FAIL before any source change | ✅ Plan enforces TDD ordering: test files created first in Step 1 |
| **G2 Contract Freeze** | `TakServerConfig` and `ClientConfig` YAML field names/defaults unchanged | ✅ Confirmed — both classes use composition, not inheritance; no field renames |
| **G5 Layout Mirror** | `libs/tak-connection/` mirrors services layout (`src/`, `tests/{unit,integration}/`, `pyproject.toml`, `README.md`) | ✅ Confirmed — layout spec'd below |
| **G7 Minimal Deps** | Only `pydantic>=2.6` + `cryptography` added (both already present in repo) | ✅ Confirmed — `tak-client-sim` adds `cryptography` which is pre-approved |

**Post-Phase-1 re-check**: `TakConnectionConfig` exposes exactly 7 fields (`host`, `port`,
`use_ssl`, `use_ssl_verify`, `cert_file`, `cert_password`, `ca_bundle`). Service-specific
fields (`xml_declaration`, `max_retries`, `backoff_*`, `queue_maxsize`, `filter_prefix`) are
intentionally excluded from the shared model; they remain in their respective service config
models. This is correct per FR-016-012 and the Assumptions section of the spec.

## Project Structure

### Documentation (this feature)

```text
specs/016-tak-shared-connection/
├── plan.md              ← this file
├── research.md          ← Phase 0 output (generated)
├── quickstart.md        ← Phase 1 output (generated)
└── tasks.md             ← Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
libs/tak-connection/                        ← NEW package (G5: mirrors services layout)
├── src/
│   └── tak_connection/
│       ├── __init__.py                     ← re-export TakConnectionConfig, build_ssl_context
│       ├── config.py                       ← TakConnectionConfig Pydantic v2 model
│       └── ssl_context.py                  ← build_ssl_context(cfg) → ssl.SSLContext
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_tak_connection.py          ← G1: written FIRST, confirmed FAIL
│   └── integration/
│       ├── __init__.py
│       └── test_ssl_integration.py         ← real cert loading (skipped in CI)
├── pyproject.toml
└── README.md

config/                                     ← NEW directory at repo root
├── remote-tak.yaml                         ← committed, placeholder IP 192.168.1.100
└── certs/
    └── .gitkeep                            ← placeholder; certs/ added to .gitignore

services/cot-gateway/
├── src/cot_gateway/tak/ssl_context.py      ← MODIFIED: thin wrapper → tak_connection
└── pyproject.toml                          ← MODIFIED: add tak-connection local dep

services/tak-client-sim/
├── src/tak_client_sim/connection.py        ← MODIFIED: delegate to tak_connection
└── pyproject.toml                          ← MODIFIED: add tak-connection + cryptography

scripts/
├── demo-1drone-remote-tak.sh               ← MODIFIED: YAML-file remote detection
└── demo-3drone-remote-tak.sh               ← MODIFIED: YAML-file remote detection

dev-docs/016-tak-shared-connection.md       ← NEW: architecture doc
README.md                                   ← MODIFIED: Remote TAK Server section
services/cot-gateway/README.md              ← MODIFIED: tak-connection dep note
services/tak-client-sim/README.md           ← MODIFIED: tak-connection dep note
.gitignore                                  ← MODIFIED: add config/certs/

DELETED:
  services/cot-gateway/config/remote-tak.yaml
  services/tak-client-sim/config/remote-tak.yaml
```

**Structure Decision**: New library at `libs/tak-connection/` uses the `src/` layout
convention matching `services/*`. No monorepo root `src/` — each project has its own. The
`config/` directory at repo root is new; it holds demo-mode YAML consumed only by shell
scripts (not loaded by any service directly).

## Implementation Phases

### Phase 1 — `libs/tak-connection` (TDD: tests first, implementation second)

**Step 1a — Write failing tests** (G1):
- Create `libs/tak-connection/tests/unit/test_tak_connection.py` with tests that import
  from `tak_connection` (which doesn't exist yet → all tests ImportError / FAIL).
- Cover: model validation (valid input, missing `host`, extra field, empty `host`,
  `port` out-of-range), `build_ssl_context` with PEM cert, with P12 cert, missing cert
  file (`FileNotFoundError`), `cert_file=None` + `use_ssl=True` (CA-only, no error),
  `use_ssl_verify=True/False`, P12 missing cert/key (`ValueError`).
- Run `pytest libs/tak-connection/` → confirm all tests FAIL (100% red).

**Step 1b — Create package scaffold**:
```
libs/tak-connection/
├── pyproject.toml     (name="tak-connection", deps=[pydantic>=2.6, cryptography])
├── README.md
└── src/tak_connection/
    ├── __init__.py
    ├── config.py
    └── ssl_context.py
```

**Step 1c — Implement**:

`config.py` — `TakConnectionConfig`:
```python
from pydantic import BaseModel, ConfigDict, Field

class TakConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    host: str                            # required, no default
    port: int = Field(default=8089, ge=1, le=65535)
    use_ssl: bool = True
    use_ssl_verify: bool = False
    cert_file: str | None = None
    cert_password: str | None = None
    ca_bundle: str | None = None
```

`ssl_context.py` — `build_ssl_context(cfg: TakConnectionConfig) → ssl.SSLContext`:
- Sets `check_hostname` / `verify_mode` from `use_ssl_verify`.
- Loads `ca_bundle` only when `use_ssl_verify=True` and `ca_bundle` is non-None.
- **Early return** when `cert_file is None`: returns the context as-is (CA-only TLS).
- When `cert_file` is a non-None path that does not exist → `FileNotFoundError`.
- `.pem`/`.crt` suffix → `ctx.load_cert_chain()` directly.
- Any other suffix → P12 decode via `cryptography.hazmat`; write temp PEM/key files;
  `ctx.load_cert_chain()`; **clean up temp files in `try/finally`** (fixes a leak in
  the original cot-gateway implementation which never calls `os.unlink`).
- `cert is None or key is None` after P12 decode → `ValueError("p12 missing cert or key")`.
- Uses `logging.getLogger(__name__)` for diagnostics (NOT `structlog`, per FR-016-021).

**Step 1d — Run tests green**: `pytest libs/tak-connection/` → 100% pass.

---

### Phase 2 — Refactor `cot-gateway`

**Step 2a** — Add dep to `services/cot-gateway/pyproject.toml`:
```toml
"tak-connection @ file://../../../libs/tak-connection",
```

**Step 2b** — Replace `services/cot-gateway/src/cot_gateway/tak/ssl_context.py` with thin
wrapper:
```python
"""TAK SSL context — thin wrapper delegating to libs/tak-connection."""
from cot_gateway.config import TakServerConfig
from tak_connection.config import TakConnectionConfig
from tak_connection.ssl_context import build_ssl_context as _build

def build_ssl_context(cfg: TakServerConfig) -> ssl.SSLContext:
    tak_cfg = TakConnectionConfig(
        host=cfg.host,
        port=cfg.port,
        use_ssl=cfg.use_ssl,
        use_ssl_verify=cfg.use_ssl_verify,
        cert_file=cfg.cert_file,          # str (not None) in TakServerConfig
        cert_password=cfg.cert_password,
        ca_bundle=cfg.ca_bundle,
    )
    return _build(tak_cfg)
```
Note: `TakServerConfig.cert_file` is `str` (not Optional) with default
`"config/certs/gateway.p12"`. The existing `GatewayConfig._check_cert_file` validator
ensures the file exists when `use_ssl=True`, so `cert_file` is always a valid path here.

**Step 2c** — Run cot-gateway tests: `pytest services/cot-gateway/` → 209 green.

---

### Phase 3 — Refactor `tak-client-sim`

**Step 3a** — Add deps to `services/tak-client-sim/pyproject.toml`:
```toml
"tak-connection @ file://../../../libs/tak-connection",
"cryptography",
```

**Step 3b** — Refactor `services/tak-client-sim/src/tak_client_sim/connection.py`:
Replace local `build_ssl_context(config: ClientConfig)` with a wrapper that:
1. Constructs `TakConnectionConfig(host=..., port=..., use_ssl=..., use_ssl_verify=...,
   ca_bundle=..., cert_file=None)` — `ClientConfig` has no `cert_file`; always `None`.
2. Calls `tak_connection.ssl_context.build_ssl_context(tak_cfg)`.
3. Keeps the public signature `build_ssl_context(config: ClientConfig) → ssl.SSLContext`
   so existing `test_connection.py` tests pass without modification.

**Step 3c** — Run tak-client-sim tests: `pytest services/tak-client-sim/` → 99 green.

---

### Phase 4 — Root config + demo scripts

**Step 4a** — Create `config/remote-tak.yaml` (committed, placeholder `192.168.1.100`):
```yaml
# config/remote-tak.yaml — Shared TAK Server connection settings for remote demo mode.
# Create this file to activate remote mode in demo scripts.
# Absence of this file = local mode (tak-relay started locally).
#
# Certificate placement:
#   Place your P12 client certificate at config/certs/gateway.p12
#   Place your CA bundle PEM at config/certs/ca-bundle.pem (if use_ssl_verify: true)
tak_server:
  host: "192.168.1.100"       # REQUIRED: set to your TAK server IP or hostname
  port: 8089                   # Default TAK CoT TCP port
  use_ssl: true                # Mutual TLS for real TAK servers
  use_ssl_verify: false        # Set true + ca_bundle for CA-verified TLS (production)
  cert_file: "config/certs/gateway.p12"       # P12 client certificate
  cert_password: null          # P12 password; or "${TAK_CERT_PASSWORD}" to use env var
  ca_bundle: null              # Path to CA bundle PEM; only used when use_ssl_verify: true
```

**Step 4b** — Create `config/certs/.gitkeep`; add `config/certs/` to `.gitignore`.

**Step 4c** — Refactor both demo scripts (`demo-1drone-remote-tak.sh`,
`demo-3drone-remote-tak.sh`):

Replace env-var detection block:
```bash
# OLD (remove):
REMOTE_TAK_MODE=false
if [[ -n "${TAK_HOST:-}" ]]; then REMOTE_TAK_MODE=true; fi
TAK_PORT="${TAK_PORT:-8089}"
TAK_USE_SSL="${TAK_USE_SSL:-true}"
```
With YAML-file detection:
```bash
# NEW:
REMOTE_CONFIG="${ROOT_DIR}/config/remote-tak.yaml"
REMOTE_TAK_MODE=false
TAK_HOST=""
TAK_PORT="8089"
TAK_USE_SSL="true"

if [[ -f "${REMOTE_CONFIG}" ]]; then
    TAK_HOST="$(python3 -c "
import yaml, sys
try:
    cfg = yaml.safe_load(open('${REMOTE_CONFIG}'))
    print(cfg['tak_server']['host'])
except Exception as e:
    sys.stderr.write(f'ERROR: cannot parse ${REMOTE_CONFIG}: {e}\n')
    sys.exit(1)
" 2>&1)" || die "Cannot parse ${REMOTE_CONFIG} — check YAML syntax"
    TAK_PORT="$(python3 -c "import yaml; cfg=yaml.safe_load(open('${REMOTE_CONFIG}')); print(cfg['tak_server'].get('port', 8089))")"
    TAK_USE_SSL="$(python3 -c "import yaml; cfg=yaml.safe_load(open('${REMOTE_CONFIG}')); print(str(cfg['tak_server'].get('use_ssl', True)).lower())")"
    [[ -n "${TAK_HOST}" ]] && REMOTE_TAK_MODE=true
fi
```

Also update `launch_services()` remote-mode branch to pass `--host`/`--port` to
`tak-client-sim`:
```bash
# Add to remote-mode tak-client-sim launch:
local sim_extra_args="--host ${TAK_HOST} --port ${TAK_PORT}"
if [[ "${TAK_USE_SSL}" == "false" ]]; then
    sim_extra_args="${sim_extra_args} --no-ssl"
fi
# shellcheck disable=SC2086
(cd "${ROOT_DIR}/services/tak-client-sim" && \
  exec python3 -m tak_client_sim --config "${TAK_CLIENT_CONFIG}" ${sim_extra_args}) \
  >>"${LOG_DIR}/tak-client-sim.log" 2>&1 &
```

**Step 4d** — Remove per-service remote-tak configs:
```bash
git rm services/cot-gateway/config/remote-tak.yaml
git rm services/tak-client-sim/config/remote-tak.yaml
```

---

### Phase 5 — Documentation

**Step 5a** — Create `dev-docs/016-tak-shared-connection.md` (architecture + migration guide).

**Step 5b** — Update `README.md` "Remote TAK Server" section: remove `TAK_HOST`/`TAK_PORT`
env-var instructions; reference only `config/remote-tak.yaml`.

**Step 5c** — Update `services/cot-gateway/README.md`: note `libs/tak-connection` dep;
note removal of local `ssl_context.py` SSL duplication.

**Step 5d** — Update `services/tak-client-sim/README.md`: note `libs/tak-connection` dep;
note removal of local `build_ssl_context`.

---

## Key Design Decisions

### Composition over inheritance
`TakServerConfig` and `ClientConfig` both contain service-specific fields that have no
place in a generic connection model (`xml_declaration`, `max_retries`, `backoff_*`,
`queue_maxsize`, `filter_prefix`, `web_*`). Inheritance would force either polluting
`TakConnectionConfig` with those fields or creating awkward split models. Composition
keeps both contracts frozen (G2) and the library dependency-free from service code.

### `TakConnectionConfig` field scope (7 fields only)
FR-016-012 explicitly lists 7 fields. Fields from the early design-decision note
(`xml_declaration`, `max_retries`, `backoff_*`) are NOT included: they are service-specific
concerns, and including them would make the library aware of wire-format and retry policy
decisions that belong to each service. This aligns with the Assumptions section of the spec.

### `cert_file=None` → CA-only TLS (no error)
`tak-client-sim` is a read-only subscriber that does not present a client certificate.
Setting `cert_file=None` (the default) causes `build_ssl_context` to skip client-cert
loading and return an SSL context that only verifies the server (or skips verification when
`use_ssl_verify=False`). This is the common subscriber pattern for TAK networks.

### Temp PEM cleanup fix
The original `cot-gateway/tak/ssl_context.py` creates temp PEM files with `delete=False`
but never calls `os.unlink()`. The new library adds `try/finally` cleanup. This is a
deliberate improvement, not a behaviour change from the calling service's perspective.

### Demo script: YAML detection, not env-var
File-existence checks (`[[ -f "${REMOTE_CONFIG}" ]]`) are idempotent and CI-friendly.
Removing env-var detection reduces surprise when running scripts in environments that
happen to have `TAK_HOST` set for unrelated purposes.

## Complexity Tracking

No constitution violations to justify. All gates pass.
