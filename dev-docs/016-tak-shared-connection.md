# 016 — TAK Shared Connection

## Motivation

`cot-gateway` and `tak-client-sim` each carried their own `build_ssl_context` implementation, and
both services also kept separate `config/remote-tak.yaml` templates. That duplicated TLS logic,
caused remote-mode configuration drift, and left the original cot-gateway p12 path leaking temp
files.

## Before Architecture

Before this feature, `services/cot-gateway/src/cot_gateway/tak/ssl_context.py` implemented its own
P12/PEM handling while `services/tak-client-sim/src/tak_client_sim/connection.py` had a separate
CA-only TLS builder. Remote TAK usage also depended on per-service `config/remote-tak.yaml` files
plus demo-script environment variables such as `TAK_HOST`, `TAK_PORT`, and `TAK_USE_SSL`.

## After Architecture

`libs/tak-connection` now owns the shared TAK TLS primitives: `TakConnectionConfig` and
`build_ssl_context`. Both services keep their existing config schemas, compose a
`TakConnectionConfig`, and delegate TLS creation instead of embedding connection details locally.
Remote demo mode is now anchored on a single repo-root `config/remote-tak.yaml`, and the remote
demo scripts read that YAML instead of operator-set env vars.

## Migration Guide

1. Install or depend on `libs/tak-connection`.
2. Keep the service-specific config model unchanged for G2 compatibility.
3. Build a `TakConnectionConfig` from the service config by composition, not inheritance.
4. Delegate to `tak_connection.build_ssl_context`.
5. If the service needs remote demo support, read or merge the repo-root `config/remote-tak.yaml`
   instead of creating another service-local template.

## G2 Contract Freeze Rationale

`TakServerConfig` and `ClientConfig` do not inherit from `TakConnectionConfig`. Composition keeps
all existing YAML field names and loading paths stable, so `services/cot-gateway/config/demo.yaml`
and `services/tak-client-sim/config/demo.yaml` continue to validate without schema churn.

## G7 Minimal Deps

The shared library adds only `pydantic>=2.6` and `cryptography`. Logging stays on stdlib
`logging` inside `libs/tak-connection`; `structlog` remains service-owned.

## Temp-File Cleanup Fix

The old cot-gateway p12 flow wrote temporary PEM/key files and never removed them. The shared
library now wraps the temp-file path in `try/finally` cleanup so both generated files are unlinked
on every exit path.
