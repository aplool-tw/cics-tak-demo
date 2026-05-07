# tak-connection

Shared TAK connection helpers for services that need a TLS client `SSLContext`.

## Install

```bash
pip install -e libs/tak-connection --break-system-packages
```

## TakConnectionConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | TAK server hostname or IP address. |
| `port` | `int` | `8089` | TAK server TCP port. |
| `use_ssl` | `bool` | `true` | Enables TLS for the connection. |
| `use_ssl_verify` | `bool` | `false` | Enables server certificate verification. |
| `cert_file` | `str \| None` | `None` | Client certificate path (`.pem`, `.crt`, or `.p12`). |
| `cert_password` | `str \| None` | `None` | Password for encrypted PEM/P12 material. Empty string becomes `None`. |
| `ca_bundle` | `str \| None` | `None` | CA bundle PEM path used when verification is enabled. |

## build_ssl_context examples

### CA-only TLS

```python
from tak_connection import TakConnectionConfig, build_ssl_context

cfg = TakConnectionConfig(
    host="tak.example.com",
    use_ssl=True,
    use_ssl_verify=True,
    ca_bundle="config/certs/ca-bundle.pem",
    cert_file=None,
)
ctx = build_ssl_context(cfg)
```

### PEM certificate

```python
cfg = TakConnectionConfig(
    host="tak.example.com",
    cert_file="config/certs/client.pem",
)
ctx = build_ssl_context(cfg)
```

### P12 certificate

```python
cfg = TakConnectionConfig(
    host="tak.example.com",
    cert_file="config/certs/gateway.p12",
    cert_password="secret",
)
ctx = build_ssl_context(cfg)
```

## Notes

- Dependencies stay minimal: `pydantic>=2.6` and `cryptography` only.
- The library uses stdlib `logging` only; `structlog` remains service-owned.
