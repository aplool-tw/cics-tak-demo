# Quickstart: Feature 015 — CoT XML Compliance + Remote TAK Server Support

**Feature Branch**: `feature/015-cot-xml-compliance`  
**Plan**: [`specs/015-cot-xml-compliance/plan.md`](plan.md)  
**Spec**: [`specs/015-cot-xml-compliance/spec.md`](spec.md)

This guide covers the developer workflow for implementing and deploying Feature 015 end-to-end.

---

## 1. Prerequisites

```bash
# Install cot-gateway in dev mode (once)
pip install -e "services/cot-gateway[dev]" --break-system-packages

# Install tak-client-sim in dev mode (once)
pip install -e "services/tak-client-sim[dev]" --break-system-packages

# Verify existing tests are green before making any change
cd services/cot-gateway && python3 -m pytest -q  # expect 180 passed
cd services/tak-client-sim && python3 -m pytest -q  # expect 99 passed
```

---

## 2. TDD Workflow (G1 — Test First)

Create the test files **before touching any source code**.  Confirm they fail (red).

```bash
# Step 1: create test files (see implementation scope in plan.md)
#   services/cot-gateway/tests/unit/test_generator_xml_decl.py
#   services/cot-gateway/tests/unit/test_config_xml_decl.py

# Step 2: run new tests — they MUST fail before implementation
cd services/cot-gateway
python3 -m pytest tests/unit/test_generator_xml_decl.py tests/unit/test_config_xml_decl.py -v
# Expected: all FAIL (AttributeError / AssertionError)

# Step 3: implement (see §4 below)

# Step 4: confirm tests are now green
python3 -m pytest tests/unit/test_generator_xml_decl.py tests/unit/test_config_xml_decl.py -v
# Expected: all PASS

# Step 5: confirm no regressions
python3 -m pytest -q  # must stay at 180+ passed
```

---

## 3. Key Test Cases (what the test files must cover)

### `test_generator_xml_decl.py`

| Test ID | Scenario | Assertion |
|---------|----------|-----------|
| `test_uid_droid_present` | Default `generate_cot()` call | `<uid Droid="…"/>` present in output |
| `test_uid_droid_equals_event_uid` | Any track | `uid Droid` attribute value equals `event uid` attribute |
| `test_uid_droid_is_first_detail_child` | Parse output with ET | `detail[0].tag == "uid"` |
| `test_xml_decl_true` | `generate_cot(track, xml_declaration=True)` | Output starts with `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>` |
| `test_xml_decl_false_default` | `generate_cot(track)` (default) | Output starts with `<event` |
| `test_xml_decl_false_explicit` | `generate_cot(track, xml_declaration=False)` | Output starts with `<event` |
| `test_existing_elements_unchanged` | Compare before/after | `<contact>`, `<remarks>`, `<track>` unchanged |
| `test_compliance_matrix_all_8_scenarios` | 8 source × status combinations from `cot-xml.md §7` | `<uid Droid>` present in all 8; existing assertions still pass |
| `test_uid_droid_special_chars_escaped` | Callsign with `<>&"'` chars | ET auto-escapes via attribute assignment |

### `test_config_xml_decl.py`

| Test ID | Scenario | Assertion |
|---------|----------|-----------|
| `test_xml_declaration_field_default` | `TakServerConfig()` | `xml_declaration == False` |
| `test_xml_declaration_field_true` | `TakServerConfig(xml_declaration=True)` | `xml_declaration == True` |
| `test_xml_declaration_roundtrip_yaml` | Load YAML with `xml_declaration: true` | Field parsed correctly |
| `test_ca_bundle_field_default` | `TakServerConfig()` | `ca_bundle is None` |
| `test_ca_bundle_field_set` | `TakServerConfig(ca_bundle="certs/ca.pem")` | `ca_bundle == "certs/ca.pem"` |
| `test_cli_tak_host_override` | Pass `--tak-host 10.0.0.5` via `main(argv=[…])` | `cfg.tak_server.host == "10.0.0.5"` |
| `test_cli_tak_port_override` | Pass `--tak-port 9099` via `main(argv=[…])` | `cfg.tak_server.port == 9099` |
| `test_cli_partial_override_host_only` | Only `--tak-host` provided | Port unchanged from YAML |
| `test_cli_partial_override_port_only` | Only `--tak-port` provided | Host unchanged from YAML |
| `test_extra_field_still_forbidden` | `TakServerConfig(unknown_field=1)` | `ValidationError` raised |

---

## 4. Implementation Steps (RC1 — CoT XML Compliance)

### 4a. `services/cot-gateway/src/cot_gateway/config.py`

Add two fields to `TakServerConfig` (after `cert_password`, before `max_retries`):

```python
ca_bundle: str | None = None           # Path to CA bundle PEM for TLS peer verification
xml_declaration: bool = False          # Prepend <?xml ...?> to every CoT event string
```

### 4b. `services/cot-gateway/src/cot_gateway/cot/generator.py`

1. Add `xml_declaration: bool = False` keyword-only parameter to `generate_cot()`.
2. Add `<uid Droid>` as first child of `<detail>` (before `<contact>`):
   ```python
   detail = ET.SubElement(event, "detail")
   ET.SubElement(detail, "uid", {"Droid": uid})    # ← first child
   ET.SubElement(detail, "contact", {"callsign": uid})
   ...
   ```
3. Apply declaration prefix at the end:
   ```python
   xml = ET.tostring(event, encoding="unicode")
   if xml_declaration:
       xml = "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + xml
   return xml
   ```

### 4c. `services/cot-gateway/src/cot_gateway/loop.py`

Three `generate_cot()` call sites (lines ~134, ~148, ~189) must pass the config flag:

```python
# Example (repeat for all 3 call sites)
xml = generate_cot(track, now=now, xml_declaration=self.config.tak_server.xml_declaration)
```

### 4d. `services/cot-gateway/src/cot_gateway/cli.py`

Add two optional arguments to `_parse_args()`:

```python
p.add_argument("--tak-host", metavar="HOST", help="TAK Server hostname or IP override")
p.add_argument("--tak-port", type=int, metavar="PORT", help="TAK Server port override")
```

Apply overrides in `main()` after the web-override block (same `model_copy` pattern):

```python
tak_overrides: dict = {}
if getattr(args, "tak_host", None):
    tak_overrides["host"] = args.tak_host
if getattr(args, "tak_port", None):
    tak_overrides["port"] = args.tak_port
if tak_overrides:
    cfg = cfg.model_copy(
        update={"tak_server": cfg.tak_server.model_copy(update=tak_overrides)}
    )
```

---

## 5. Implementation Steps (RC2 — Config Examples)

### `services/cot-gateway/config/remote-tak.yaml`

```yaml
# Remote TAK Server example configuration
# Copy to my-tak.yaml and fill in your environment values before use.
#
# Usage:
#   python3 -m cot_gateway --config config/remote-tak.yaml
#   python3 -m cot_gateway --config config/remote-tak.yaml --tak-host 192.0.2.10 --tak-port 8089
#
# Certificates:
#   cert_file  : PKCS#12 (.p12) client certificate issued by your TAK Server CA.
#                Generate with: scripts/gen-certs.sh  or export from FreeTAKServer UI.
#   cert_password: passphrase for the .p12 file (leave blank if unset; use ${TAK_CERT_PASSWORD})
#   ca_bundle  : PEM CA bundle to verify the TAK Server's TLS certificate.
#                Not required when use_ssl_verify: false (PoC default).

tak_server:
  host: "${TAK_HOST}"            # e.g. 192.0.2.10 or tak.example.com
  port: 8089
  use_ssl: true
  use_ssl_verify: false          # set true + provide ca_bundle for production
  cert_file: "config/certs/gateway.p12"
  cert_password: "${TAK_CERT_PASSWORD}"
  ca_bundle: null                # e.g. "config/certs/ca.pem"
  xml_declaration: true          # many real TAK servers require the XML declaration header
  max_retries: 5

echoshield:
  host: "127.0.0.1"
  port: 9000

sentrycs:
  enabled: true
  host: "127.0.0.1"
  port: 7070

logging:
  level: "INFO"
  json: true

web:
  enabled: false
```

### `services/tak-client-sim/config/remote-tak.yaml`

```yaml
# Remote TAK Server example configuration for tak-client-sim
# Copy to my-tak-client.yaml and fill in your environment values before use.
#
# Usage:
#   python3 -m tak_client_sim --config config/remote-tak.yaml
#
# ca_bundle: Path to PEM CA bundle for verifying the TAK Server certificate.
#            Required only when use_ssl_verify: true.

host: "${TAK_HOST}"              # e.g. 192.0.2.10 or tak.example.com
port: 8089
use_ssl: true
use_ssl_verify: false
ca_bundle: null                  # e.g. "config/certs/ca.pem"
max_retries: 0
```

---

## 6. Implementation Steps (RC3 — Demo Scripts)

### `scripts/demo-1drone-remote-tak.sh` — branching skeleton

```bash
#!/usr/bin/env bash
# demo-1drone-remote-tak.sh — 1-drone pipeline with optional remote TAK server.
# Set TAK_HOST (and optionally TAK_PORT, TAK_USE_SSL) to route to a real TAK server.
# Without TAK_HOST, falls back to local tak_relay.py mode.
set -euo pipefail
# ... (inherit helper functions from demo-1drone.sh) ...

if [[ -n "${TAK_HOST:-}" ]]; then
    # ── Remote TAK mode ──────────────────────────────────────────────────────
    warn "TAK_HOST=${TAK_HOST} — routing to remote TAK server (no local relay)"
    GW_EXTRA_ARGS="--tak-host ${TAK_HOST} --tak-port ${TAK_PORT:-8089}"
    # launch all services EXCEPT tak-relay; pass GW_EXTRA_ARGS to cot-gateway
else
    # ── Local relay fallback mode ─────────────────────────────────────────────
    warn "TAK_HOST not set — falling back to local tak_relay.py mode"
    # identical to demo-1drone.sh launch_services()
fi
```

> The 3-drone variant (`demo-3drone-remote-tak.sh`) is identical except it uses
> `demo_three_drones.yaml` scenarios and 3-drone banner text.

---

## 7. Implementation Steps (RC4 — Documentation)

### `specs/005-cot-gateway/contracts/cot-xml.md`

- **§1 Wire format**: Replace *"單筆事件結構：[…] **不含** `<?xml?>` 宣告頭"* with:  
  *"XML declaration controlled by `tak_server.xml_declaration` config flag (default `false` = no declaration; set `true` for TAK Server compatibility)."*
- **§2 XML Schema**: Add `<uid Droid="{UID}"/>` as the first child of `<detail>` in the example block; add a row to the field table.

### `services/cot-gateway/README.md`

Add two sections:
1. **"Connecting to a Real TAK Server"** — reference `config/remote-tak.yaml`, describe cert placement, show `--tak-host`/`--tak-port` usage.
2. **"Logging"** note: *"Service logs are structured JSON (structlog); the wire protocol sent to TAK Server is CoT XML — the two formats are independent."*

### `services/tak-client-sim/README.md`

Mirror the above two sections adapted for the client simulator.

### `AGENTS.md`

In the logging / CoT-XML sections, add:
> ⚠️ Log format ≠ wire format: `cot-gateway` and `tak-client-sim` emit **structlog JSON** to
> stdout/files; the bytes transmitted over TCP to the TAK Server are **CoT XML**.  Do not confuse
> the two.

---

## 8. Lint & Format Gate

```bash
# Run after each implementation step before committing
cd services/cot-gateway
ruff check . && black --check src tests

cd ../tak-client-sim
ruff check . && black --check src tests
```

---

## 9. Commit Sequence (conventional commits)

```
test(015-cot-xml-compliance): add failing unit tests for xml_declaration and uid Droid (G1)
feat(015-cot-xml-compliance): add xml_declaration and ca_bundle fields to TakServerConfig
feat(015-cot-xml-compliance): add <uid Droid> element and xml_declaration param to generator
feat(015-cot-xml-compliance): thread xml_declaration config flag through loop.py call sites
feat(015-cot-xml-compliance): add --tak-host and --tak-port CLI overrides to cot-gateway
feat(015-cot-xml-compliance): add remote-tak.yaml example configs for gateway and client-sim
feat(015-cot-xml-compliance): add demo-1drone-remote-tak.sh and demo-3drone-remote-tak.sh
docs(015-cot-xml-compliance): update cot-xml.md contract with <uid Droid> addition
docs(015-cot-xml-compliance): add Remote TAK Server and log-vs-wire sections to READMEs
docs(015-cot-xml-compliance): add log!=wire note to AGENTS.md
```

Each commit must include the trailer:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```
