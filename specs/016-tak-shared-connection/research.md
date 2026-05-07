# Research: TAK Shared Connection Library

**Feature**: 016-tak-shared-connection  
**Branch**: `feature/016-tak-shared-connection`

---

## R1 — Composition vs Inheritance for Config Delegation

### Decision
Use **composition** (construct `TakConnectionConfig` inside `TakServerConfig`/`ClientConfig`
methods, do NOT inherit from it).

### Rationale
`TakServerConfig` and `ClientConfig` each contain service-specific fields that have no
meaning in a generic connection model:

| `TakServerConfig` extras | `ClientConfig` extras |
|--------------------------|----------------------|
| `xml_declaration` | `filter_prefix` |
| `max_retries` (ge=1) | `max_retries` (ge=0, different constraint) |
| `backoff_initial_s` | `backoff_initial_s` |
| `backoff_cap_s` | `backoff_cap_s` |
| `queue_maxsize` | `log_file` |
| (backoff cross-validator) | `web_enabled`, `web_host`, `web_port` |

Inheritance would require either:
- **Option A**: Add all service-specific fields to `TakConnectionConfig` (breaks G7 minimal
  deps, bloats the library, creates impossible cross-service constraints).
- **Option B**: Inherit and override `model_config = ConfigDict(extra="ignore")` (breaks
  G2 — the extra fields would silently vanish on serialisation/validation round-trips).

Composition keeps both YAML contracts frozen (G2), the library independent of both services,
and the mapping explicit and auditable (one `TakConnectionConfig(...)` call per service).

### Alternatives Considered
- **Pydantic mixin / abstract base model**: Rejected — same as inheritance for Pydantic v2;
  `model_config` does not compose cleanly across classes.
- **Protocol / structural typing**: Rejected — no runtime enforcement; still requires manual
  field-mapping at the call site.

---

## R2 — P12→PEM Conversion Flow

### Decision
Use `cryptography.hazmat.primitives.serialization.pkcs12.load_key_and_certificates()` for
P12 decoding. Write temp PEM/key files via `tempfile.NamedTemporaryFile(delete=False)`.
Clean up temp files in `try/finally` **after** `ctx.load_cert_chain()` returns.

### Rationale
`ssl.SSLContext.load_cert_chain()` requires paths to files (not in-memory bytes) in CPython's
standard library implementation. The `delete=False` + manual `os.unlink()` pattern is the
standard workaround on all platforms (including Linux where the file is still accessible
after unlink while the fd is open — but we unlink after `load_cert_chain` returns, so the
sequence is: write → chmod 0600 → load_cert_chain → unlink).

The original `cot-gateway/tak/ssl_context.py` omits `os.unlink()` — a resource leak
(temp files accumulate on disk). The new library fixes this with `try/finally`.

### P12 field validation
`pkcs12.load_key_and_certificates()` returns `(key, cert, additional_certs)`. Either `key`
or `cert` being `None` means the archive is malformed. Raise `ValueError("p12 missing cert
or key")` before writing any temp files to fail fast with a clear message.

### PEM path (no cryptography dep needed)
`.pem` / `.crt` suffix → `ssl.SSLContext.load_cert_chain()` directly. This path has no
dependency on `cryptography` and handles unencrypted or password-protected PEM certs.

### Password handling
- `cert_password=None` or `cert_password=""` → passed as `None` to `load_cert_chain()` and
  `pkcs12.load_key_and_certificates()`. Empty string treated as None matches the
  existing `cot-gateway` `load_config()` behaviour.
- For P12: `cfg.cert_password.encode()` only when non-None/non-empty.

### Alternatives Considered
- **`PyOpenSSL`**: Rejected — additional dep (violates G7); `cryptography` is already in
  the repo.
- **`subprocess` → `openssl pkcs12`**: Rejected — env dependency, shell injection risk,
  not portable to all CI environments.
- **In-memory chain loading via `ssl.SSLContext.load_verify_locations(cadata=...)`**: Only
  available for CA certs, not client cert+key pairs in the standard library.

---

## R3 — `cert_file=None` → CA-Only TLS (No Client Certificate)

### Decision
When `cert_file is None`, `build_ssl_context` returns the `ssl.SSLContext` after applying
`verify_mode` / `check_hostname` / CA bundle settings, **without** calling
`load_cert_chain()`. No error is raised.

### Rationale
`tak-client-sim` is a read-only subscriber (CoT XML receiver). TAK Server does not require
the subscriber to present a client certificate for read-only connections in most deployments.
This is the standard CA-only / server-verify TLS pattern.

The distinction from a missing-cert error is crucial:
- `cert_file=None` (explicit absence) → intentional CA-only TLS → no error.
- `cert_file="/path/to/cert.p12"` (path specified but file absent) → `FileNotFoundError`
  with the missing path.

### Alternatives Considered
- **Require `cert_file` always**: Rejected — would break `tak-client-sim` which does not
  and should not have a client certificate.
- **Separate `TAKSubscriberConfig` without `cert_file`**: Rejected — over-engineering;
  `cert_file: str | None = None` with a single code path is sufficient.

---

## R4 — Local Editable Dependency via `file://` Reference

### Decision
Use `"tak-connection @ file://../../../libs/tak-connection"` in both service
`pyproject.toml` dependency lists. Install with `pip install -e services/SERVICE --break-system-packages`
(or in virtualenv), which also installs the local `tak-connection` package in editable mode
because pip resolves `file://` references transitively.

### Rationale
The `@ file://` PEP 508 URL syntax is supported by `pip>=21.3` and `setuptools>=64`. It
references a relative path from the package being installed. Because both services sit at
`services/cot-gateway/` and `services/tak-client-sim/`, the relative path
`../../../libs/tak-connection` resolves correctly from each service's root.

The library is NOT published to PyPI (G7 / scope decision). Using a local reference is the
standard pattern for monorepo libraries that are not worth the publishing overhead.

### Install commands (developer workflow)
```bash
pip install -e libs/tak-connection
pip install -e services/cot-gateway
pip install -e services/tak-client-sim
```
Each service install transitively picks up `tak-connection` due to the `file://` dep.

### Alternatives Considered
- **Git submodule + `git+file://`**: Rejected — unnecessary complexity for a same-repo dep.
- **Path dependency in `pyproject.toml` tool.uv.sources`**: Rejected — requires `uv`;
  project uses `pip`/`setuptools`.
- **Symlink `libs/tak-connection` inside each service**: Rejected — fragile, not portable
  across clone strategies.

---

## R5 — `structlog` Exclusion from `libs/tak-connection`

### Decision
`libs/tak-connection` uses **Python stdlib `logging`** only (`logging.getLogger(__name__)`).
No `structlog` dependency.

### Rationale
`structlog` is a service-level concern: it formats log records for service operators running
in production. A shared library with `structlog` would force all consumers to configure
`structlog` processors (or see ugly default output). The library's only diagnostic output
is raising exceptions with clear messages; it has no I/O loop, no request handling, no
structured events to log. Any debug-level logging (e.g., "loading P12 cert") uses stdlib
`logging.debug()`, which is a no-op unless the caller configures a handler.

This also satisfies G7 (minimal dependencies).

### Alternatives Considered
- **Depend on `structlog` optionally**: Rejected — optional deps are confusing and create
  import-time branch complexity.
- **Pass a logger as a parameter**: Rejected — over-engineering for a library that emits
  at most one debug log.

---

## R6 — Demo Script YAML Parsing Pattern

### Decision
Parse `config/remote-tak.yaml` using inline `python3 -c "import yaml; ..."` in Bash.
Use `pyyaml` (already installed as a service dep). Detect remote mode by file existence
**and** non-empty `tak_server.host`.

### Rationale
The demo scripts already use `python3 -c "import ..."` for module-import preflight checks.
`pyyaml` is available in any environment that has the services installed. The three-line
parse approach (one python3 invocation per field) is explicit and auditable. An alternative
single call could extract all fields at once, but the current pattern matches the existing
script style.

**Error handling in Bash**:
```bash
TAK_HOST="$(python3 -c "..." 2>&1)" || die "Cannot parse config/remote-tak.yaml"
```
`set -euo pipefail` + `|| die` ensures the script exits immediately with a clear message
on YAML parse error, satisfying the edge case requirement.

**Local-host detection**: The spec does not require filtering `127.*` or `localhost` as
special cases; presence of the file and a non-empty `host` value is sufficient to trigger
remote mode.

### Alternatives Considered
- **`yq` CLI tool**: Rejected — external dependency not guaranteed on all developer machines.
- **`jq` + JSON conversion**: Rejected — adds `python3 -c` call for YAML→JSON conversion
  anyway; no benefit.
- **Bash-native YAML parser**: Rejected — no reliable lightweight parser exists for Bash.

---

## R7 — ruff / black Line-Length Convention for `libs/tak-connection`

### Decision
Use `line-length = 100` (matching `cot-gateway`). Target Python 3.11.

### Rationale
The repo has two line-length conventions (cot-gateway: 100, tak-client-sim: 120). As a new
shared library that is closer in nature to cot-gateway (it was extracted from cot-gateway's
SSL context), 100 is the more conservative choice and easier to read in diff views.

---

## R8 — Temp File Cleanup Order (Fix over Original)

### Decision
After `ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)`, unlink both files in
`try/finally`:
```python
try:
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
finally:
    os.unlink(cert_file)
    os.unlink(key_file)
```

### Rationale
The original `cot-gateway/tak/ssl_context.py` never calls `os.unlink()`. Each service
start with a P12 cert would leave two orphaned temp files (one `.pem`, one `.key`) in
`/tmp`. On long-running systems or CI environments with many test runs this accumulates.
Using `try/finally` ensures cleanup even if `load_cert_chain` raises an exception.

Note: `ssl.SSLContext.load_cert_chain()` reads the files immediately and does not hold
open file descriptors after return, so unlinking after the call is safe.

### Alternatives Considered
- **`tempfile.TemporaryFile(delete=True)`**: Cannot be used — `ssl.SSLContext` needs a
  filesystem path, not a file object.
- **`tempfile.TemporaryDirectory`**: Works but heavier than needed for two files.
