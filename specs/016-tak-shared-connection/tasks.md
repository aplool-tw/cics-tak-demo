---
description: "Task list for feature 016-tak-shared-connection"
feature: "016-tak-shared-connection"
spec: "specs/016-tak-shared-connection/spec.md"
plan: "specs/016-tak-shared-connection/plan.md"
---

# Tasks: TAK Shared Connection (016)

**Feature**: `feature/016-tak-shared-connection`
**Input**: `specs/016-tak-shared-connection/plan.md`, `specs/016-tak-shared-connection/spec.md`, `specs/016-tak-shared-connection/research.md`, `specs/016-tak-shared-connection/quickstart.md`
**Output**: `specs/016-tak-shared-connection/tasks.md`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[US1]**: US-016-01 — Single-Point TAK Server Configuration (P1)
- **[US2]**: US-016-02 — Shared TAK Connection Library (P2)
- **[US3]**: US-016-03 — Documentation Update (P3)

> **G1 Test-First Note**: All tasks in Phase 2 must produce a **100% RED** pytest run before Phase 3
> begins. Tests fail initially because the `tak_connection` module does not yet exist (ImportError).
> Record the failure output before advancing. This is a hard gate.

> **Implementation Order Note**: Although US-016-02 (library) is priority P2 and US-016-01
> (config/scripts) is P1, the library is a **technical prerequisite** for the demo-script work.
> Both `cot-gateway` and `tak-client-sim` must adopt the shared library before the demo scripts
> can be validated end-to-end. Phases 2–6 implement US2 first, then US1, then US3.

---

## Phase 1: Setup — Library Scaffold

**Purpose**: Create the `libs/tak-connection/` directory structure and build configuration so test
files can be authored in Phase 2.

- [X] T001 Create libs/tak-connection/ directory tree: `mkdir -p libs/tak-connection/src/tak_connection libs/tak-connection/tests/unit libs/tak-connection/tests/integration`
- [X] T002 [P] Create libs/tak-connection/pyproject.toml: `[project]` name="tak-connection" version="0.1.0" requires-python=">=3.11" dependencies=["pydantic>=2.6","cryptography"]; `[build-system]` setuptools; `[tool.ruff]` line-length=100 target-version="py311"; `[tool.black]` line-length=100; `[tool.pytest.ini_options]` testpaths=["tests"] pythonpath=["src"]
- [X] T003 [P] Create empty libs/tak-connection/src/tak_connection/__init__.py (intentionally empty — all test imports will raise ImportError, confirming the G1 gate in Phase 2)
- [X] T004 [P] Create empty libs/tak-connection/tests/unit/__init__.py and empty libs/tak-connection/tests/integration/__init__.py
- [X] T005 Create libs/tak-connection/tests/conftest.py with three pytest fixtures: `tmp_pem_cert(tmp_path)` — generates a self-signed PEM cert+key using `cryptography` (RSA 2048, 1-day validity), writes `cert.pem` and `key.pem` to `tmp_path`, returns `(cert_path, key_path)`; `tmp_p12_cert(tmp_path)` — generates a P12 archive from the same cert+key with password=b"test", writes `cert.p12` to `tmp_path`, returns `(p12_path, "test")`; `tmp_malformed_p12(tmp_path)` — writes 64 bytes of random garbage to `malformed.p12` in `tmp_path`, returns `p12_path` (causes ValueError in P12 decode)

---

## Phase 2: Write Failing Tests — libs/tak-connection [US2] 🔴 (G1 Gate)

**Goal**: Write the complete unit test suite for `libs/tak-connection` **before any implementation
exists**. All tests must FAIL when run after this phase.

> ⚠️ **G1 CRITICAL**: After T010, run `pytest libs/tak-connection/ -v` and confirm **100% FAIL**
> (all tests raise `ImportError` from `from tak_connection import ...`). Record the failure count.
> **Do NOT proceed to Phase 3 until all tests are RED.**

**Independent Test**: `pytest libs/tak-connection/ -v` — all tests pass after Phase 3.

- [X] T006 [US2] Write libs/tak-connection/tests/unit/test_tak_connection.py — model validation tests: `test_valid_config_all_fields` (construct with all 7 fields → succeeds), `test_valid_config_defaults` (only `host` provided → port=8089, use_ssl=True, others None/False), `test_missing_host_raises` (no host arg → ValidationError), `test_extra_field_raises` (unknown key → ValidationError because extra="forbid"), `test_empty_host_raises` (host="" → ValidationError), `test_port_zero_raises` (port=0 → ValidationError ge=1), `test_port_65536_raises` (port=65536 → ValidationError le=65535), `test_frozen_raises` (assign cfg.host="other" after construction → ValidationError/TypeError), `test_empty_cert_password_becomes_none` (TakConnectionConfig(host="h", cert_password="") → cfg.cert_password is None — M2 fix) — confirm test FAILS before proceeding to implementation
- [X] T007 [US2] Add to libs/tak-connection/tests/unit/test_tak_connection.py — PEM cert path tests using `tmp_pem_cert` fixture: `test_pem_no_verify` (use_ssl_verify=False → returns `ssl.SSLContext`, verify_mode==ssl.CERT_NONE, check_hostname==False), `test_pem_with_verify` (use_ssl_verify=True + ca_bundle pointing to valid CA PEM → returns `ssl.SSLContext`, verify_mode==ssl.CERT_REQUIRED) — confirm tests FAIL before proceeding to implementation
- [X] T008 [US2] Add to libs/tak-connection/tests/unit/test_tak_connection.py — CA-only and missing-cert tests: `test_cert_file_none_returns_ssl_context` (cert_file=None + use_ssl=True → `isinstance(result, ssl.SSLContext)` and no exception raised — CA-only TLS path, R3), `test_missing_cert_file_raises_file_not_found` (cert_file="/nonexistent/path.p12" → FileNotFoundError whose message includes the missing path) — confirm tests FAIL before proceeding to implementation
- [X] T009 [P] [US2] Add to libs/tak-connection/tests/unit/test_tak_connection.py — P12 tests using `tmp_p12_cert` and `tmp_malformed_p12` fixtures: `test_p12_valid_returns_ssl_context` (valid P12 path + password → `isinstance(result, ssl.SSLContext)`), `test_p12_malformed_raises_value_error` (malformed P12 path → ValueError), `test_p12_cert_none_raises_value_error` (use `unittest.mock.patch("tak_connection.ssl_context.pkcs12.load_key_and_certificates", return_value=(None, None, []))` to simulate P12 that has no cert/key → expect `ValueError("p12 missing cert or key")` — H1 fix: covers the explicit `cert is None or key is None` guard branch for 100% branch coverage); create libs/tak-connection/tests/integration/test_ssl_integration.py with one real-cert round-trip test decorated `@pytest.mark.skipif(not os.getenv("INTEGRATION_CERTS"), reason="real certs not available — set INTEGRATION_CERTS=1")` — confirm tests FAIL before proceeding to implementation
- [X] T010 [US2] Run `pytest libs/tak-connection/ -v` — confirm ALL tests FAIL (100% RED, expect ImportError on every test); record exact failure count and error message; **[G1 Gate]: do NOT proceed to T011 until all tests are RED and failure is documented**

**Checkpoint**: All unit tests written and confirmed 100% RED — implementation phase may begin ✅

---

## Phase 3: Implement libs/tak-connection [US2] 🟢

**Goal**: Implement `TakConnectionConfig` and `build_ssl_context` until all tests from Phase 2 pass
with 100% branch coverage.

**Independent Test**: Install `libs/tak-connection` in isolation (`pip install -e libs/tak-connection`)
and run `pytest libs/tak-connection/ -v` — all tests pass, `--cov-branch` shows 100% for `build_ssl_context`.

- [X] T011 [P] [US2] Create libs/tak-connection/src/tak_connection/config.py with `TakConnectionConfig` Pydantic v2 model: `from __future__ import annotations`; `model_config = ConfigDict(extra="forbid", frozen=True)`; fields: `host: str` (no default), `port: int = Field(8089, ge=1, le=65535)`, `use_ssl: bool = True`, `use_ssl_verify: bool = False`, `cert_file: str | None = None`, `cert_password: str | None = None`, `ca_bundle: str | None = None`; add `@field_validator("host")` that raises ValueError when value is empty string; add `@field_validator("cert_password")` that converts empty-string `""` to None (preserving cot-gateway behaviour — spec edge case)
- [X] T012 [US2] Create libs/tak-connection/src/tak_connection/ssl_context.py — implement `build_ssl_context(cfg: TakConnectionConfig) -> ssl.SSLContext`: (1) create `ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`; (2) if `use_ssl_verify=False` → `ctx.check_hostname=False`, `ctx.verify_mode=ssl.CERT_NONE`; (3) if `use_ssl_verify=True` and `ca_bundle` non-None → `ctx.load_verify_locations(cfg.ca_bundle)`; (4) **early return `ctx`** when `cert_file is None` (CA-only TLS — no client cert, no error, R3); (5) raise `FileNotFoundError(f"cert_file not found: {cfg.cert_file}")` when `cfg.cert_file` is non-None and `not os.path.exists(cfg.cert_file)`; (6) if suffix `.pem` or `.crt` → `ctx.load_cert_chain(cfg.cert_file, password=cfg.cert_password)`; (7) else P12: `data=open(cfg.cert_file,"rb").read()`; `pwd=cfg.cert_password.encode() if cfg.cert_password else None`; `key, cert, _ = pkcs12.load_key_and_certificates(data, pwd)`; raise `ValueError("p12 missing cert or key")` if cert is None or key is None; write cert PEM and key PEM to `NamedTemporaryFile(delete=False, suffix=".pem")` and `suffix=".key"`; `os.chmod` both to 0o600; `ctx.load_cert_chain(cert_tmp, keyfile=key_tmp)` inside `try` block; `finally: os.unlink(cert_tmp); os.unlink(key_tmp)` (R8 temp-file cleanup fix); use `logging.getLogger(__name__)` for debug logs — NOT structlog (FR-016-021)
- [X] T013 [US2] Update libs/tak-connection/src/tak_connection/__init__.py: add `from tak_connection.config import TakConnectionConfig`, `from tak_connection.ssl_context import build_ssl_context`, and `__all__ = ["TakConnectionConfig", "build_ssl_context"]`
- [X] T014 [US2] Run `pip install -e libs/tak-connection` — verify editable install succeeds; run smoke test: `python3 -c "from tak_connection import TakConnectionConfig, build_ssl_context; cfg = TakConnectionConfig(host='192.168.1.100'); print('OK', cfg.host, cfg.port)"` — confirm output is `OK 192.168.1.100 8089`
- [X] T015 [US2] Run `pytest libs/tak-connection/tests/unit/ -v` — confirm ALL unit tests PASS (100% green); record exact pass count; **G1 gate verified — tests were RED before implementation, GREEN after**
- [X] T016 [P] [US2] Run `pytest libs/tak-connection/ --cov=tak_connection --cov-branch -v` from libs/tak-connection/ — confirm 100% branch coverage of `build_ssl_context` (PEM path, P12 path, cert_file=None path, missing-cert path, verify-on path, verify-off path); fix any uncovered branch before proceeding (SC-016-04)
- [X] T017 [P] [US2] Run `ruff check src tests` and `black --check src tests` from libs/tak-connection/ — resolve all lint warnings and formatting issues in config.py and ssl_context.py; re-run until both commands exit 0 (SC-016-05)
- [X] T018 [P] [US2] Create libs/tak-connection/README.md: include TakConnectionConfig fields reference table (field/type/default/description for all 7 fields), `build_ssl_context` usage examples (CA-only TLS with cert_file=None, PEM cert, P12 cert with password), install command (`pip install -e libs/tak-connection`), dependencies note (pydantic>=2.6 + cryptography only — G7), structlog-exclusion note (FR-016-021)
- [X] T019 [P] [US2] Quick validator smoke test: `python3 -c "from tak_connection import TakConnectionConfig; from pydantic import ValidationError; [print('OK', label) for label, fn in [('empty host', lambda: TakConnectionConfig(host='')), ('port 0', lambda: TakConnectionConfig(host='h', port=0)), ('extra field', lambda: TakConnectionConfig(host='h', extra=1))] if [None for _ in [1] if (lambda e: True)(None)] or True]"` — or run equivalent manual checks; confirm each raises ValidationError
- [X] T020 [US2] Verify transitive install path: from repo root run `pip show tak-connection` to confirm the editable install is registered; run `python3 -c "import tak_connection; import pathlib; print(pathlib.Path(tak_connection.__file__).parent)"` — confirm path is under `libs/tak-connection/src/`; this pre-flight verifies the `file://` dep in service pyproject.toml files will resolve correctly in T022 and T032

**Checkpoint**: `libs/tak-connection` fully implemented, unit-tested (100% branch coverage), installed, and lint-clean — US2 library phase complete ✅

---

## Phase 4: Update cot-gateway [US2]

**Goal**: Replace `cot-gateway`'s local SSL context logic with a thin wrapper that delegates to
`libs/tak-connection` using composition (no inheritance — G2 Contract Freeze).

**Independent Test**: `pytest services/cot-gateway/ -q` — all 209 tests pass unchanged; `config/demo.yaml` loads without error; G2 contract freeze verified.

- [X] T021 [US2] Add tak-connection local dependency to services/cot-gateway/pyproject.toml: insert `"tak-connection @ file://../../../libs/tak-connection"` into the `[project] dependencies` list (after existing deps); do NOT change any other field
- [X] T022 [US2] Run `pip install -e services/cot-gateway` from repo root — confirm tak-connection dep resolves via `file://` reference; verify with `python3 -c "from tak_connection import TakConnectionConfig; print('cot-gateway tak-connection import OK')"`
- [X] T023 [US2] Replace services/cot-gateway/src/cot_gateway/tak/ssl_context.py with thin delegation wrapper: module docstring `"""TAK SSL context — thin wrapper delegating to libs/tak-connection."""`; `import ssl`; `from cot_gateway.config import TakServerConfig`; `from tak_connection.config import TakConnectionConfig`; `from tak_connection.ssl_context import build_ssl_context as _build`; public function `build_ssl_context(cfg: TakServerConfig) -> ssl.SSLContext` that constructs `TakConnectionConfig(host=cfg.host, port=cfg.port, use_ssl=cfg.use_ssl, use_ssl_verify=cfg.use_ssl_verify, cert_file=cfg.cert_file, cert_password=cfg.cert_password, ca_bundle=cfg.ca_bundle)` and returns `_build(tak_cfg)` — note: `TakServerConfig.cert_file` is `str` (not Optional), always a valid path when `use_ssl=True` due to `GatewayConfig._check_cert_file` validator
- [X] T024 [US2] Run `pytest services/cot-gateway/ -v` — confirm all 209 tests PASS; G2 contract freeze verified (TakServerConfig field names unchanged, config/demo.yaml schema unchanged)
- [X] T025 [P] [US2] Verify no SSL duplication remains in cot-gateway: `grep -rn "load_cert_chain\|load_key_and_certificates\|cryptography.hazmat" services/cot-gateway/src/` — expect zero matches outside the import line in tak/ssl_context.py (SC-016-02 — single implementation)
- [X] T026 [P] [US2] Verify composition (not inheritance) in cot-gateway: `python3 -c "from cot_gateway.config import TakServerConfig; from tak_connection import TakConnectionConfig; assert not issubclass(TakServerConfig, TakConnectionConfig), 'ERROR: inheritance detected'; print('G2 composition OK')"` from services/cot-gateway/
- [X] T027 [P] [US2] Verify cot-gateway config/demo.yaml loads correctly after refactor: `python3 -c "from cot_gateway.config import GatewayConfig; import yaml; cfg = GatewayConfig.model_validate(yaml.safe_load(open('config/demo.yaml'))); print('G2 demo.yaml OK', cfg.tak_server.host)"` from services/cot-gateway/ — confirms G2 contract freeze (no YAML field renames)
- [X] T028 [P] [US2] Run `ruff check src tests` and `black --check src tests` from services/cot-gateway/ — confirm clean lint/format after ssl_context.py replacement; fix any issues (SC-016-05)
- [X] T029 [P] [US2] Confirm cot-gateway's ssl_context.py no longer imports `cryptography`, `tempfile`, or calls `os.unlink` directly: `grep -n "import cryptography\|import tempfile\|os.unlink" services/cot-gateway/src/cot_gateway/tak/ssl_context.py` — expect zero matches (those operations now live inside tak_connection.ssl_context)
- [X] T030 [US2] Record cot-gateway baseline: `pytest services/cot-gateway/ --tb=short -q` — document total pass count (must be 209); **cot-gateway US2 integration checkpoint complete** ✅

**Checkpoint**: cot-gateway delegates SSL to shared library; 209 tests green; lint clean ✅

---

## Phase 5: Update tak-client-sim [US2]

**Goal**: Replace `tak-client-sim`'s local SSL context logic with a thin wrapper that delegates to
`libs/tak-connection`. Always passes `cert_file=None` (CA-only TLS — tak-client-sim is a
read-only subscriber with no client certificate, per R3).

**Independent Test**: `pytest services/tak-client-sim/ -q` — all 99 tests pass unchanged; G2 contract freeze verified; `cert_file=None` explicitly set in wrapper.

- [X] T031 [US2] Add tak-connection and cryptography deps to services/tak-client-sim/pyproject.toml: insert `"tak-connection @ file://../../../libs/tak-connection"` and `"cryptography"` into `[project] dependencies` list (cryptography was previously only in cot-gateway — G7 pre-approved)
- [X] T032 [US2] Run `pip install -e services/tak-client-sim` from repo root — confirm tak-connection and cryptography deps resolve; verify with `python3 -c "from tak_connection import TakConnectionConfig, build_ssl_context; print('tak-client-sim tak-connection import OK')"`
- [X] T033 [US2] Refactor services/tak-client-sim/src/tak_client_sim/connection.py: remove the local `build_ssl_context` implementation and any direct `cryptography`, `tempfile`, `ssl` imports that were part of it; add `from tak_connection.config import TakConnectionConfig` and `from tak_connection.ssl_context import build_ssl_context as _build`; keep the **public function signature unchanged** `build_ssl_context(config: ClientConfig) -> ssl.SSLContext`; inside: construct `TakConnectionConfig(host=config.host, port=config.port, use_ssl=config.use_ssl, use_ssl_verify=config.use_ssl_verify, ca_bundle=config.ca_bundle, cert_file=None)` — `cert_file=None` is **intentional and explicit** (tak-client-sim has no cert_file in ClientConfig and presents no client certificate per R3); return `_build(tak_cfg)`
- [X] T034 [US2] Run `pytest services/tak-client-sim/ -v` — confirm all 99 tests PASS; G2 contract freeze verified (ClientConfig flat YAML keys unchanged, config/demo.yaml schema unchanged)
- [X] T035 [P] [US2] Verify no SSL duplication remains in tak-client-sim: `grep -rn "load_cert_chain\|load_key_and_certificates\|cryptography.hazmat" services/tak-client-sim/src/` — expect zero matches (SC-016-02)
- [X] T036 [P] [US2] Verify composition (not inheritance) in tak-client-sim: `python3 -c "from tak_client_sim.config import ClientConfig; from tak_connection import TakConnectionConfig; assert not issubclass(ClientConfig, TakConnectionConfig), 'ERROR: inheritance detected'; print('G2 composition OK')"` from services/tak-client-sim/
- [X] T037 [P] [US2] Verify tak-client-sim config/demo.yaml loads correctly after refactor: parse ClientConfig from services/tak-client-sim/ — confirm all flat YAML keys (host, port, use_ssl, filter_prefix, etc.) still valid; G2 contract freeze confirmed
- [X] T038 [P] [US2] Run `ruff check src tests` and `black --check src tests` from services/tak-client-sim/ — confirm clean lint/format after connection.py refactor (SC-016-05)
- [X] T039 [P] [US2] Confirm `cert_file=None` is explicitly set in tak-client-sim's TakConnectionConfig constructor: `grep -n "cert_file" services/tak-client-sim/src/tak_client_sim/connection.py` — expect `cert_file=None` in the constructor call (CA-only TLS for subscriber, R3 compliance)
- [X] T040 [US2] Run combined US2 test suite: `pytest libs/tak-connection/ services/cot-gateway/ services/tak-client-sim/ -q` — confirm all pass (libs unit + 209 cot-gateway + 99 tak-client-sim); **US2 completion checkpoint — all shared library adoption complete** ✅

**Checkpoint**: Both services delegate SSL to shared library; combined test suite green; SC-016-02 verified ✅

---

## Phase 6: Root Config & Demo Scripts [US1] 🎯 MVP

**Goal**: Replace per-service `config/remote-tak.yaml` files with a single `config/remote-tak.yaml`
at repo root; refactor both demo scripts to detect remote mode by file existence instead of env vars.

**Independent Test**: (1) Place `config/remote-tak.yaml` at repo root — run demo script — confirm
remote mode activates and YAML-parsed host/port/SSL values are passed to both services via CLI
args. (2) Rename/remove the file — confirm local mode (REMOTE_TAK_MODE=false). (3) Corrupt YAML
— confirm script exits with clear error message, not silent fallback.

- [X] T041 [US1] Create `config/` directory at repo root and `config/certs/.gitkeep` placeholder: `mkdir -p config/certs && touch config/certs/.gitkeep` — the `certs/` sub-directory will hold real P12/PEM cert files (gitignored)
- [X] T042 [P] [US1] Update .gitignore at repo root: add `config/certs/` on its own line so that any `.p12`, `.pem`, `.key` files placed under `config/certs/` are gitignored; `config/certs/.gitkeep` should remain committed (it's a file, not matching the directory pattern)
- [X] T043 [US1] Create config/remote-tak.yaml with `tak_server:` block only (NOT a full gateway config): host="192.168.1.100" (placeholder IP), port=8089, use_ssl=true, use_ssl_verify=false, cert_file="config/certs/gateway.p12", cert_password=null (leave null for unencrypted P12 or to omit client certificate — do NOT use ${ENV_VAR} here, YAML does not expand env vars), ca_bundle=null; include clear operator comments above each field explaining its purpose and valid values; include certificate placement comment: `# Place your P12 client certificate at config/certs/gateway.p12` and `# Place your CA bundle PEM at config/certs/ca-bundle.pem (if use_ssl_verify: true)`; file header comment: `# Absence of this file = local demo mode (tak-relay started locally)` (FR-016-005, M3 fix: no ${TAK_CERT_PASSWORD} env-var reference)
- [X] T044 [US1] Refactor scripts/demo-1drone-remote-tak.sh: remove the `TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` env-var detection block (FR-016-006); replace with YAML-file detection block: declare `REMOTE_CONFIG="${ROOT_DIR}/config/remote-tak.yaml"`; initialize `REMOTE_TAK_MODE=false TAK_HOST="" TAK_PORT="8089" TAK_USE_SSL="true"`; when `[[ -f "${REMOTE_CONFIG}" ]]` parse `TAK_HOST` via `python3 -c "import yaml, sys; ..."` with `|| die "Cannot parse config/remote-tak.yaml — check YAML syntax"`; parse `TAK_PORT` and `TAK_USE_SSL` similarly; set `REMOTE_TAK_MODE=true` only when file exists AND TAK_HOST is non-empty (FR-016-002, FR-016-003)
- [X] T045 [US1] Update scripts/demo-1drone-remote-tak.sh `launch_services()` remote-mode branch: add `--host "${TAK_HOST}" --port "${TAK_PORT}"` CLI args to the tak-client-sim invocation; add `--no-ssl` flag when `TAK_USE_SSL == "false"`; update inline comment above the remote-mode tak-client-sim launch to reference `config/remote-tak.yaml` instead of `TAK_HOST` env var (FR-016-034)
- [X] T046 [US1] Refactor scripts/demo-3drone-remote-tak.sh: apply the identical env-var-to-YAML-file detection changes as T044 (remove TAK_HOST/TAK_PORT/TAK_USE_SSL env-var block, add REMOTE_CONFIG YAML-file block with same error-handling pattern) (FR-016-006)
- [X] T047 [US1] Update scripts/demo-3drone-remote-tak.sh `launch_services()` remote-mode branch: apply the same `--host`/`--port`/`--no-ssl` CLI arg changes as T045 for the **single tak-client-sim invocation** in demo-3drone-remote-tak.sh (note: "3-drone" refers to 3 UDS drone scenarios — there is only ONE tak-client-sim instance regardless of drone count); update inline comments (FR-016-034, H2 fix)
- [X] T048 [US1] Remove per-service remote-tak config files: `git rm services/cot-gateway/config/remote-tak.yaml services/tak-client-sim/config/remote-tak.yaml`; run `git status` to confirm both deletions are staged; verify neither path exists under `services/` anymore (FR-016-004)
- [X] T049 [P] [US1] Verify local mode (no config file): temporarily rename `config/remote-tak.yaml` to `config/remote-tak.yaml.disabled`; run `bash -n scripts/demo-1drone-remote-tak.sh` to syntax-check; also `source` just the detection block in a subshell and assert `REMOTE_TAK_MODE` == false; restore the file — confirms acceptance scenario 1 from US-016-01
- [X] T050 [US1] Verify remote YAML parsing end-to-end: `python3 -c "import yaml; cfg=yaml.safe_load(open('config/remote-tak.yaml')); print(cfg['tak_server']['host'], cfg['tak_server']['port'])"` — expect `192.168.1.100 8089`; test error path by temporarily inserting a YAML syntax error and confirm the demo script `|| die` branch exits with non-zero status and a readable error message (acceptance scenario from edge-case: "bad YAML must exit with clear error")

**Checkpoint**: Single `config/remote-tak.yaml` activates remote mode; per-service files removed; local mode still works — US1 complete ✅

---

## Phase 7: Documentation [US3]

**Goal**: Root README, service READMEs, and a new dev-docs entry reflect the new library,
single config file, and removal of env-var–based remote mode. No reference to `TAK_HOST`/
`TAK_PORT`/`TAK_USE_SSL` env vars should remain outside of the "Before" description in dev-docs.

**Independent Test**: Follow only the updated root README "Remote TAK Server" section — confirm
every step references only `config/remote-tak.yaml`; no step requires per-service file edits or
setting env vars (SC-016-06).

- [X] T051 [P] [US3] Create dev-docs/016-tak-shared-connection.md with sections: **Motivation** (two duplicate `build_ssl_context` implementations + two per-service `config/remote-tak.yaml` files causing config drift); **Before Architecture** (diagram/description: `cot-gateway/tak/ssl_context.py` + `tak-client-sim/connection.py` each with SSL logic + `services/*/config/remote-tak.yaml` + `TAK_HOST`/`TAK_PORT` env vars in scripts); **After Architecture** (`libs/tak-connection` with `TakConnectionConfig` and `build_ssl_context`; single `config/remote-tak.yaml`; demo scripts read YAML); **Migration Guide** (steps for future services to adopt `libs/tak-connection`: add `file://` dep, replace local SSL code with thin wrapper); **G2 Contract Freeze Rationale** (composition vs inheritance decision from R1, why YAML field names are unchanged); **G7 Minimal Deps** (only pydantic>=2.6 + cryptography); **Temp-File Cleanup Fix** (R8 — original cot-gateway never called os.unlink, new library does via try/finally) (FR-016-030)
- [X] T052 [US3] Update root README.md "Remote TAK Server" section: remove all `TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` env-var instructions and replace with file-based workflow — (1) edit `config/remote-tak.yaml` and set `tak_server.host` to TAK server IP; (2) optionally copy cert to `config/certs/gateway.p12`; (3) run demo script — no env vars needed; reference the quickstart at `specs/016-tak-shared-connection/quickstart.md` for detailed usage (FR-016-031)
- [X] T053 [P] [US3] Update services/cot-gateway/README.md: add "Shared Library Dependencies" subsection listing `libs/tak-connection`; describe that `tak/ssl_context.py` is now a thin delegation wrapper (SSL logic removed); note G2 contract freeze (no YAML field name changes in config/demo.yaml); note that `TakServerConfig` uses composition, not inheritance, to construct `TakConnectionConfig` before calling `build_ssl_context` (FR-016-032)
- [X] T054 [P] [US3] Update services/tak-client-sim/README.md: add "Shared Library Dependencies" subsection listing `libs/tak-connection`; describe that `connection.py`'s local `build_ssl_context` has been removed and delegated; note `cert_file=None` is intentional (tak-client-sim is a CA-only subscriber that presents no client certificate); note G2 contract freeze (flat YAML keys in config/demo.yaml unchanged) (FR-016-033)
- [X] T055 [P] [US3] Verify root README.md contains no `TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` references: `grep -n "TAK_HOST\|TAK_PORT\|TAK_USE_SSL" README.md` — expect zero matches (SC-016-06 prerequisite — operator must be able to configure remote TAK without env vars)
- [X] T056 [P] [US3] Verify both demo scripts contain no `TAK_HOST`/`TAK_PORT`/`TAK_USE_SSL` env-var check paths: `grep -n "TAK_HOST\|TAK_PORT\|TAK_USE_SSL" scripts/demo-1drone-remote-tak.sh scripts/demo-3drone-remote-tak.sh` — expect zero matches in both files (FR-016-006)
- [X] T057 [P] [US3] Verify config/remote-tak.yaml contains operator comments for all 7 fields and the cert placement note: `grep -c "#" config/remote-tak.yaml` — expect ≥6 comment lines; manually verify cert placement comment is present (FR-016-005)
- [X] T058 [P] [US3] Verify dev-docs/016-tak-shared-connection.md covers all required topics: `grep -c "Motivation\|Before\|After\|Migration\|G2\|G7" dev-docs/016-tak-shared-connection.md` — expect all 6 terms present; confirm no surviving reference to `TAK_HOST` env var outside the "Before" section (FR-016-030)

**Checkpoint**: Documentation updated; no env-var references in README or demo scripts — US3 complete ✅

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation sweep across all changed components.

- [X] T059 Run full combined test suite: `pytest libs/tak-connection/ services/cot-gateway/ services/tak-client-sim/ -v --tb=short` — confirm all pass; record total test count (SC-016-03 — all existing 209 + 99 service tests pass after refactor; plus new library tests)
- [X] T060 [P] Final repo-wide lint pass: `ruff check libs/tak-connection/src services/cot-gateway/src services/tak-client-sim/src` — expect clean output for all three packages; run `black --check libs/tak-connection/src services/cot-gateway/src services/tak-client-sim/src` — expect clean (SC-016-05)

---

## Dependencies & Execution Order

### Phase Dependencies

| Phase | Depends On | Notes |
|-------|-----------|-------|
| Phase 1 (Setup) | — | Start immediately |
| Phase 2 (Failing Tests) | Phase 1 complete | Needs scaffold for test files to be created |
| Phase 3 (Implement Library) | Phase 2 — G1 gate: 100% RED confirmed | **Hard gate**: do NOT start T011 until T010 shows 100% FAIL |
| Phase 4 (cot-gateway) | Phase 3 complete + library installed | tak-connection must be installed and tested |
| Phase 5 (tak-client-sim) | Phase 3 complete + library installed | Can run **in parallel with Phase 4** (different service) |
| Phase 6 (Config/Scripts) | Phases 4 **and** 5 complete | Both services must use shared library before demo scripts are validated |
| Phase 7 (Docs) | Phase 6 complete | Documents the final state |
| Phase 8 (Polish) | Phases 1–7 complete | Final validation sweep |

### User Story Dependencies

- **US2 (P2) — Shared Library** (Phases 2–5): Implemented first despite lower spec priority — technical prerequisite for US1
- **US1 (P1) — Config/Scripts** (Phase 6): Depends on US2 — both services must delegate to shared library before demo-script validation is meaningful
- **US3 (P3) — Documentation** (Phase 7): Depends on US1 and US2 — documents the fully completed state

### Within Each Phase

- Tests (Phase 2) MUST be written and confirmed FAIL before implementation (Phase 3) — G1 non-negotiable
- T011 (config.py) and T012 (ssl_context.py) are different files — can be written in parallel [P]
- T013 (__init__.py re-exports) depends on both T011 and T012 being present
- Verification/lint tasks within a phase that are marked [P] can run in parallel after the main implementation task

### Parallel Execution Summary

```
Phase 1:  T001 → (T002 ‖ T003 ‖ T004) → T005
Phase 2:  T006 → T007 → T008 → (T009 ‖ T008 sequential) → T010  [G1 gate at T010]
Phase 3:  (T011 ‖ T012) → T013 → T014 → T015 → (T016 ‖ T017 ‖ T018 ‖ T019) → T020
Phase 4:  T021 → T022 → T023 → T024 → (T025 ‖ T026 ‖ T027 ‖ T028 ‖ T029) → T030
Phase 5:  T031 → T032 → T033 → T034 → (T035 ‖ T036 ‖ T037 ‖ T038 ‖ T039) → T040
          [Phases 4 and 5 can run in parallel after T020]
Phase 6:  T041 → (T042 ‖ T043) → T044 → T045 → T046 → T047 → T048 → (T049 ‖ T050)
Phase 7:  (T051 ‖ T052 ‖ T053 ‖ T054) → (T055 ‖ T056 ‖ T057 ‖ T058)
Phase 8:  T059 → T060
```

---

## Parallel Example: US2 Library Implementation (Phase 3)

```bash
# After T010 gate (100% RED confirmed), run T011 and T012 in parallel:
Task T011: "Create config.py with TakConnectionConfig in libs/tak-connection/src/tak_connection/config.py"
Task T012: "Create ssl_context.py with build_ssl_context in libs/tak-connection/src/tak_connection/ssl_context.py"
# T013 (update __init__.py) depends on both — run after T011 and T012 complete

# After T015 (tests pass), run verification tasks in parallel:
Task T016: "Run pytest --cov-branch to verify 100% branch coverage"
Task T017: "Run ruff check + black --check for libs/tak-connection"
Task T018: "Create libs/tak-connection/README.md"
Task T019: "Run validator smoke tests"
```

## Parallel Example: US2 Service Integration (Phases 4 & 5)

```bash
# After T020 (library installed and verified), run Phase 4 and Phase 5 in parallel:
Phase 4 tasks (T021–T030): "Update cot-gateway to delegate to libs/tak-connection"
Phase 5 tasks (T031–T040): "Update tak-client-sim to delegate to libs/tak-connection"
# T041 (create config/ directory) depends on both Phase 4 and Phase 5 completing
```

---

## Implementation Strategy

### MVP First (US2 → US1)

1. Complete Phase 1: Setup (scaffold — ~15 min)
2. Complete Phase 2: Write failing tests — run `pytest libs/tak-connection/` — confirm **100% RED** (G1 gate — critical)
3. Complete Phase 3: Implement library — run `pytest libs/tak-connection/` — confirm **100% GREEN** + 100% branch coverage
4. Complete Phases 4 + 5 in parallel: Integrate cot-gateway + tak-client-sim
5. **VALIDATE**: `pytest libs/tak-connection/ services/cot-gateway/ services/tak-client-sim/ -q` — all pass (SC-016-02 + SC-016-03)
6. Complete Phase 6: Root config + demo scripts (US1 MVP)
7. **DEMO**: Run `bash scripts/demo-1drone-remote-tak.sh` with and without `config/remote-tak.yaml` — verify both modes work
8. Complete Phase 7: Documentation (US3)
9. Complete Phase 8: Final polish

### Success Criteria Mapping

| SC | Verified At |
|----|-------------|
| SC-016-01: Single file activates remote mode | T050 |
| SC-016-02: Single SSL implementation in repo | T025, T035 (grep confirms) |
| SC-016-03: All existing tests pass after refactor | T040, T059 |
| SC-016-04: 100% branch coverage of build_ssl_context | T016 |
| SC-016-05: ruff + black clean for all three packages | T017, T028, T038, T060 |
| SC-016-06: Developer onboards from README alone | T055 (no env-var refs) |

### Notes

- [P] tasks = different files, no incomplete dependencies — safe to run in parallel
- G1 gate at T010: document failure output before implementing T011 (hard requirement, not advisory)
- G2 contract freeze: verified at T024 (209 cot-gateway tests green) and T034 (99 tak-client-sim tests green)
- G7 minimal deps: `libs/tak-connection` depends only on `pydantic>=2.6` + `cryptography`
- R3 (cert_file=None): verified by grep at T039 — `cert_file=None` must be explicit in tak-client-sim wrapper
- R8 (temp-file cleanup): verified by code review of ssl_context.py — `try/finally os.unlink` required (fixes resource leak vs original cot-gateway implementation)
