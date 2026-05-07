# Dev-Docs: Feature 015 — CoT XML Standard Format Compliance + Remote TAK Server Support

**Feature ID**: 015  
**Branch**: `feature/015-cot-xml-compliance`  
**Merged into**: `develop`  
**Date**: 2025-07-14  
**Tests**: 209 cot-gateway + 99 tak-client-sim = 308 total, 0 failed  

---

## Overview

This feature prepares `cot-gateway` and `tak-client-sim` for integration with real TAK servers
(FreeTAKServer, TAK Server CE, WinTAK, ATAK) by:

1. **Adding `<uid Droid>` element** to every generated CoT XML event (required by many real TAK servers for device identification).
2. **Adding optional XML declaration** header (`<?xml version='1.0' encoding='UTF-8' standalone='yes'?>`) configurable per deployment.
3. **Adding `ca_bundle` SSL field** to cot-gateway's `TakServerConfig` and wiring it to `ssl_context.py` (G5 parity with tak-client-sim).
4. **Adding `--tak-host`, `--tak-port`, `--no-ssl` CLI flags** to cot-gateway for quick connection overrides.
5. **Remote TAK config examples** for both services.
6. **Remote-TAK demo scripts** (`demo-1drone-remote-tak.sh`, `demo-3drone-remote-tak.sh`).
7. **Clarifying log format vs wire format** in all READMEs and AGENTS.md.

---

## Key Technical Decisions

### Decision 1: XML Declaration as String Prefix (R-001)

Python's stdlib `xml.etree.ElementTree.tostring()` does not produce an XML declaration when `encoding="unicode"` (raises `LookupError` if `xml_declaration=True` is combined with unicode encoding). The simplest compliant approach:

```python
xml_str = ET.tostring(event, encoding="unicode")
if xml_declaration:
    return "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + xml_str
return xml_str
```

No new dependencies (`lxml` still prohibited per G7). The string prefix is the same declaration all real TAK servers expect.

### Decision 2: `<uid Droid>` Placement (G2 Contract Freeze)

`<uid Droid="{callsign}"/>` is inserted as the **first child** of `<detail>` — before the existing `<contact callsign>`, `<remarks>`, and `<track>` elements. This is a pure addition; no existing elements are moved, modified, or removed. All 8 scenario compliance matrix tests (from `cot-xml.md §7`) continue to pass.

### Decision 3: `ca_bundle` Only Wired When `use_ssl_verify=True` (C1 Fix)

The `ssl_context.py` `build_ssl_context()` function now calls `ctx.load_verify_locations(cafile=cfg.ca_bundle)` only when both conditions are true:
- `cfg.ca_bundle is not None`
- `cfg.use_ssl_verify is True`

This preserves the existing behavior for the default `use_ssl_verify=False` (certificate verification skipped, as expected in PoC mode). Operators who want CA-verified TLS for production must set both fields.

### Decision 4: `--no-ssl` CLI Flag (A1 Fix)

The `--no-ssl` flag was added to `cot-gateway/cli.py` to resolve the `TAK_USE_SSL=false` mechanism needed by the demo scripts. This mirrors the `--no-ssl` pattern already present in `tak-client-sim`. The demo scripts pass `--no-ssl` when `TAK_USE_SSL=false` is set in the environment.

### Decision 5: `xml_declaration: bool = False` Default (G2 Backward Compat)

Default is `False` to preserve byte-identical output for all existing tests, the local relay, and existing integration setups. The contract file `cot-xml.md §1` is updated to reflect this is now configurable.

---

## File Change Summary

### New Source Files
| File | Purpose |
|------|---------|
| `services/cot-gateway/tests/unit/test_generator_xml_decl.py` | 19 unit tests for xml_declaration, `<uid Droid>`, 8-scenario compliance, source-switch |
| `services/cot-gateway/tests/unit/test_config_xml_decl.py` | 13 unit tests for config fields, SSL wiring, CLI override patterns |

### Modified Source Files
| File | Change |
|------|--------|
| `services/cot-gateway/src/cot_gateway/config.py` | Added `ca_bundle: str | None = None` and `xml_declaration: bool = False` to `TakServerConfig` |
| `services/cot-gateway/src/cot_gateway/cot/generator.py` | Added `ET.SubElement(detail, "uid", {"Droid": uid})` as first `<detail>` child; added `xml_declaration: bool = False` keyword param |
| `services/cot-gateway/src/cot_gateway/loop.py` | Passed `xml_declaration=self.config.tak_server.xml_declaration` to all 3 `generate_cot()` call sites |
| `services/cot-gateway/src/cot_gateway/tak/ssl_context.py` | Added `ca_bundle` wiring: `ctx.load_verify_locations(cafile=cfg.ca_bundle)` when `use_ssl_verify=True` |
| `services/cot-gateway/src/cot_gateway/cli.py` | Added `--tak-host`, `--tak-port`, `--no-ssl` flags with `model_copy` override pattern |

### New Config / Script Files
| File | Purpose |
|------|---------|
| `services/cot-gateway/config/remote-tak.yaml` | Full template for connecting to real TAK server with documented cert/SSL fields |
| `services/tak-client-sim/config/remote-tak.yaml` | Client sim template for remote TAK server |
| `scripts/demo-1drone-remote-tak.sh` | Dual-mode demo (local relay or real TAK) for single-drone scenario |
| `scripts/demo-3drone-remote-tak.sh` | Dual-mode demo for three-drone scenario |

### Documentation Updates
| File | Change |
|------|--------|
| `specs/005-cot-gateway/contracts/cot-xml.md` | §1: xml_declaration config flag note; §2: `<uid Droid>` in schema and field table; §8: examples updated |
| `services/cot-gateway/README.md` | "Connecting to a Real TAK Server" section + log≠wire clarification |
| `services/tak-client-sim/README.md` | Same sections adapted for client sim |
| `AGENTS.md` | Log format ≠ wire format note added to §3.3 |

---

## Wire Format After This Feature

Default (local relay mode, `xml_declaration: false`):
```xml
<event version="2.0" uid="ECHO-TRK-001" type="a-u-A-M-F-Q-r" ...><point ... /><detail><uid Droid="ECHO-TRK-001" /><contact callsign="ECHO-TRK-001" /><remarks>...</remarks><track ... /></detail></event>\n
```

Real TAK server mode (`xml_declaration: true`):
```xml
<?xml version='1.0' encoding='UTF-8' standalone='yes'?><event ...>...<detail><uid Droid="ECHO-TRK-001" />...</detail></event>\n
```

---

## Quick Start: Connect to Real TAK Server

```bash
# 1. Copy and edit the remote config
cp services/cot-gateway/config/remote-tak.yaml services/cot-gateway/config/my-tak.yaml
# Edit my-tak.yaml: set tak_server.host, cert_file, cert_password

# 2. Start cot-gateway (CLI override for quick test)
export TAK_HOST=192.168.1.100
python3 -m cot_gateway \
  --config services/cot-gateway/config/remote-tak.yaml \
  --tak-host "${TAK_HOST}" --tak-port 18089

# 3. OR use the demo script
TAK_HOST=192.168.1.100 scripts/demo-1drone-remote-tak.sh
# TAK_USE_SSL=false for plain TCP TAK servers:
TAK_HOST=192.168.1.100 TAK_USE_SSL=false scripts/demo-1drone-remote-tak.sh
```

---

## Known Issues / Gotchas

1. **`use_ssl_verify: false` still needed for self-signed certs**: Real TAK servers often use self-signed or internal CA certificates. Set `use_ssl: true` + `use_ssl_verify: false` to enable TLS without CA verification (PoC mode). For production, set `use_ssl_verify: true` and provide `ca_bundle`.

2. **P12 password via env var**: `cert_password: "${TAK_CERT_PASSWORD}"` uses `${}` expansion. If the password contains YAML special characters, enclose it in quotes in the env var.

3. **`xml_declaration` and newline framing**: The XML declaration prefix does NOT affect the existing newline-terminated framing (`event_xml + "\n"`). The full wire frame is now: `"<?xml ...?><event ...>...</event>\n"` — still newline-delimited.

4. **`<uid Droid>` breaks byte-identity with pre-015 output**: Any system comparing raw CoT XML bytes (e.g., golden-sample snapshot tests) will need to update their expected output to include `<uid Droid>`. The contract tests have been updated accordingly.

5. **tak-client-sim `ca_bundle` was already wired**: The `tak-client-sim/connection.py` already called `ctx.load_verify_locations(ca_bundle)`. Feature 015 adds the same wiring to `cot-gateway/tak/ssl_context.py` for G5 parity.

---

## Test Coverage Summary

| Test File | Tests Added | What They Cover |
|-----------|-------------|-----------------|
| `test_generator_xml_decl.py` | 19 | xml_declaration param (default/true), `<uid Droid>` (presence, value, position, special chars), 8-scenario compliance matrix, source-switch final CoT |
| `test_config_xml_decl.py` | 13 | xml_declaration field (default/true/YAML roundtrip), ca_bundle field (default/set/SSL wiring), extra field still forbidden, CLI override model_copy patterns |
