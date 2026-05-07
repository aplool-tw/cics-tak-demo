# Dev Quickstart: TAK Shared Connection (016)

**Branch**: `feature/016-tak-shared-connection`  
**Prerequisite**: Python 3.11+, `pyyaml` installed system-wide (ships with service installs).

---

## 1. Set up `libs/tak-connection`

```bash
# From repo root
pip install -e libs/tak-connection
# Verify
python3 -c "from tak_connection import TakConnectionConfig, build_ssl_context; print('OK')"
```

---

## 2. Install updated services

```bash
pip install -e services/cot-gateway
pip install -e services/tak-client-sim
```

Both services now depend on `tak-connection` via `file://` references in their
`pyproject.toml`, so the above commands also pull in the shared library.

---

## 3. Run all tests

```bash
# New library (write tests first, confirm FAIL, then implement)
pytest libs/tak-connection/ -v

# Services (must stay green after refactor)
pytest services/cot-gateway/   # expect 209 pass
pytest services/tak-client-sim/ # expect 99 pass
```

---

## 4. Local demo mode (unchanged)

```bash
# No config/remote-tak.yaml → local mode (tak-relay included)
bash scripts/demo-1drone-remote-tak.sh
```

---

## 5. Remote TAK Server demo mode

```bash
# 1. Copy the committed placeholder and set your TAK server IP
cp config/remote-tak.yaml config/remote-tak.yaml.bak   # optional backup
# Edit config/remote-tak.yaml:
#   tak_server.host: "YOUR_TAK_IP"
#   tak_server.cert_file: "config/certs/gateway.p12"   (if using client cert)

# 2. Place your client certificate (if needed)
mkdir -p config/certs
cp /path/to/your/gateway.p12 config/certs/gateway.p12

# 3. Launch remote demo (no TAK_HOST env var needed)
bash scripts/demo-1drone-remote-tak.sh
# OR
bash scripts/demo-3drone-remote-tak.sh
```

The scripts read `config/remote-tak.yaml` automatically. If the file exists and
`tak_server.host` is non-empty, remote mode activates. If the file is absent or has a
bad host, local mode is used (or the script exits with an error if YAML is malformed).

---

## 6. Switching back to local mode

```bash
# Option A: Remove the file
mv config/remote-tak.yaml config/remote-tak.yaml.disabled

# Option B: Leave the file but set host to empty or localhost
# (empty host → local mode)
```

---

## 7. `TakConnectionConfig` quick reference

```python
from tak_connection import TakConnectionConfig, build_ssl_context
import ssl

# CA-only TLS (no client cert — tak-client-sim pattern)
cfg = TakConnectionConfig(host="192.168.1.100", use_ssl=True, use_ssl_verify=False)
ctx = build_ssl_context(cfg)   # ssl.SSLContext, no cert loaded
assert isinstance(ctx, ssl.SSLContext)

# Client cert TLS (PEM — cot-gateway pattern)
cfg = TakConnectionConfig(
    host="192.168.1.100",
    use_ssl=True,
    use_ssl_verify=False,
    cert_file="config/certs/gateway.pem",
)
ctx = build_ssl_context(cfg)   # loads client cert

# Client cert TLS (P12)
cfg = TakConnectionConfig(
    host="192.168.1.100",
    use_ssl=True,
    cert_file="config/certs/gateway.p12",
    cert_password="secret",
)
ctx = build_ssl_context(cfg)   # decodes P12, writes temp PEM, cleans up

# Missing cert → FileNotFoundError
cfg = TakConnectionConfig(host="h", cert_file="/missing.p12")
try:
    build_ssl_context(cfg)
except FileNotFoundError as e:
    print(e)   # "cert_file not found: /missing.p12"

# Extra field → ValidationError (extra="forbid")
from pydantic import ValidationError
try:
    TakConnectionConfig(host="h", unknown_field=1)
except ValidationError:
    pass   # expected

# Frozen model — no mutation
cfg = TakConnectionConfig(host="h")
try:
    cfg.host = "other"   # raises ValidationError
except ValidationError:
    pass
```

---

## 8. Lint & format

```bash
# From libs/tak-connection/
ruff check src tests
black --check src tests

# From services (no changes to lint conventions)
cd services/cot-gateway  && ruff check src tests && black --check src tests
cd services/tak-client-sim && ruff check src tests && black --check src tests
```

---

## 9. Directory map (post-feature)

```
libs/tak-connection/
├── src/tak_connection/
│   ├── __init__.py          ← from tak_connection import TakConnectionConfig, build_ssl_context
│   ├── config.py            ← TakConnectionConfig
│   └── ssl_context.py       ← build_ssl_context()
└── tests/
    ├── unit/test_tak_connection.py
    └── integration/test_ssl_integration.py   (skipped if no cert)

config/
├── remote-tak.yaml           ← committed; edit host to activate remote mode
└── certs/
    ├── .gitkeep
    └── gateway.p12           ← add your cert here (gitignored)

# Removed:
#   services/cot-gateway/config/remote-tak.yaml
#   services/tak-client-sim/config/remote-tak.yaml
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: tak_connection` | Library not installed | `pip install -e libs/tak-connection` |
| `FileNotFoundError: cert_file not found: config/certs/gateway.p12` | P12 not copied | Copy cert to `config/certs/gateway.p12` |
| Demo script exits "Cannot parse config/remote-tak.yaml" | Bad YAML syntax | Check indentation; run `python3 -c "import yaml; yaml.safe_load(open('config/remote-tak.yaml'))"` |
| `ValidationError: extra inputs are not permitted` | Old service config has unknown field | Check for typos in YAML key names |
| `ValueError: p12 missing cert or key` | P12 archive has no client cert | Obtain correct P12 from TAK server admin |
| `pydantic.ValidationError` on `tak_server.max_retries` | Using old cot-gateway with new remote-tak.yaml | `config/remote-tak.yaml` is NOT a full gateway config; services use `config/demo.yaml` |
