# Research: Feature 015 — CoT XML Standard Format Compliance + Remote TAK Server Support

**Phase**: 0 — Research (pre-implementation)  
**Date**: 2025-07-14  
**Plan**: [`specs/015-cot-xml-compliance/plan.md`](plan.md)

All NEEDS CLARIFICATION items from the Technical Context have been resolved below.

---

## R-001 — XML Declaration with `xml.etree.ElementTree` (stdlib)

**Question**: What is the correct approach to produce `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>` using only the stdlib `xml.etree.ElementTree` module?

**Decision**: Prepend the declaration string **manually** as a Python string prefix to the output of `ET.tostring(event, encoding="unicode")`.

**Rationale**:

1. `ET.tostring(event, encoding="unicode", xml_declaration=True)` raises `LookupError: unknown encoding: unicode` — the `xml_declaration` parameter is only honoured when `encoding` is a byte encoding (e.g., `"utf-8"`), not the special `"unicode"` sentinel.

2. `ET.tostring(event, encoding="utf-8", xml_declaration=True)` returns `bytes` prefixed with `b"<?xml version='1.0' encoding='utf-8'?>"` — lower-case encoding label, no `standalone` attribute, requires a `.decode("utf-8")` round-trip.  This does **not** match the ATAK-required form `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>`.

3. **Chosen approach**: When `xml_declaration=True`, the generator returns:
   ```python
   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + ET.tostring(event, encoding="unicode")
   ```
   This is a pure-string operation, zero-allocation beyond the prefix, consistent with G7 (stdlib only), and produces the exact byte sequence expected by real TAK servers.

**Alternatives considered**:

| Alternative | Why rejected |
|-------------|-------------|
| `ET.tostring(event, encoding="utf-8", xml_declaration=True).decode()` | Lowercase encoding name, no `standalone`, extra `.decode()` round-trip |
| `ElementTree.write()` into `io.StringIO` | File-oriented API; more complex and no benefit |
| Regex post-processing of ET output | Brittle; violates YAGNI |

**Implementation note**: The `generate_cot()` signature gains a keyword-only parameter:

```python
def generate_cot(
    track: UnifiedTrack,
    now: Optional[datetime] = None,
    *,
    force_stale_eq_time: bool = False,
    override_uid: Optional[str] = None,
    xml_declaration: bool = False,      # ← new
) -> str:
    ...
    xml = ET.tostring(event, encoding="unicode")
    if xml_declaration:
        xml = "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + xml
    return xml
```

---

## R-002 — `<uid Droid>` Placement Inside `<detail>`

**Question**: Where exactly should `<uid Droid>` appear in the `<detail>` block, and how should it be constructed?

**Decision**: Insert `<uid Droid="{callsign}"/>` as the **first child** of `<detail>`, before `<contact callsign>`.

**Rationale**:

- ATAK convention (observed in CivTAK / WinTAK CoT captures) places `<uid Droid>` first in `<detail>`.
- The spec `§Key Entities` table explicitly states: *"MUST appear as first child of `<detail>` before `<contact/>`"*.
- FR-015-005 requires the attribute value to be set via the ET API (attribute dict), not string concatenation, so that XML-special characters in callsigns are automatically escaped.
- `xml.etree.ElementTree` preserves insertion order; calling `ET.SubElement(detail, "uid", {"Droid": uid})` **before** `ET.SubElement(detail, "contact", ...)` guarantees position.

**Before** (current `generator.py`):

```xml
<detail>
  <contact callsign="ECHO-TRK-001"/>
  <remarks>Source: ECHOSHIELD | Speed: 35.0m/s | Alt: 120m</remarks>
  <track speed="35.0" course="180.0"/>
</detail>
```

**After** (with `<uid Droid>`):

```xml
<detail>
  <uid Droid="ECHO-TRK-001"/>
  <contact callsign="ECHO-TRK-001"/>
  <remarks>Source: ECHOSHIELD | Speed: 35.0m/s | Alt: 120m</remarks>
  <track speed="35.0" course="180.0"/>
</detail>
```

**Implementation note**:

```python
detail = ET.SubElement(event, "detail")
ET.SubElement(detail, "uid", {"Droid": uid})        # ← NEW: first child
ET.SubElement(detail, "contact", {"callsign": uid})
remarks = ET.SubElement(detail, "remarks")
remarks.text = _build_remarks(track)
ET.SubElement(detail, "track", {...})
```

**Contract impact**: `specs/005-cot-gateway/contracts/cot-xml.md`:
- §1 wire-format note: Remove the sentence "不含 `<?xml?>` 宣告頭"; replace with note that declaration is controlled by `xml_declaration` config flag (default off = no declaration).
- §2 XML schema example: Add `<uid Droid="{UID}"/>` as first `<detail>` child.
- SC-015-006 ensures `xml_declaration=False` output is byte-identical in structure to existing output (only `<uid Droid>` is added).

---

## R-003 — `ca_bundle` Field in `TakServerConfig`

**Question**: Does `TakServerConfig` need a `ca_bundle` field?  How does it relate to `use_ssl_verify`?

**Decision**: Add `ca_bundle: str | None = None` to `TakServerConfig`.

**Rationale**:

- The spec §Key Entities table lists `ca_bundle` as a new `TakServerConfig` field needed for full remote-server TLS configuration.
- FR-015-008 references `tak_server.ca_bundle` in the `remote-tak.yaml` example config.
- `tak-client-sim`'s `ClientConfig` already has `ca_bundle: Optional[str] = None` — structural symmetry (G5) requires the same in `TakServerConfig`.
- The SSL context builder (`services/cot-gateway/src/cot_gateway/tak/ssl_context.py`) currently uses `cert_file` for the client certificate.  `ca_bundle`, when set and `use_ssl_verify=True`, should be passed to `ssl.SSLContext.load_verify_locations()` to authenticate the TAK server's certificate.
- `TakServerConfig` uses `extra="forbid"`, so the field must be declared explicitly with a `None` default (backward-compatible).

**Alternatives considered**:

| Alternative | Why rejected |
|-------------|-------------|
| Reuse `cert_file` for CA bundle path | `cert_file` is a P12 client cert, not a CA bundle; mixing them breaks cert loading |
| `use_ssl_verify: bool` alone (already present) | Without a path, Python's `ssl` defaults to system CA store — insufficient for self-signed TAK server certs |

---

## R-004 — CLI Override Pattern (Frozen Pydantic Models)

**Question**: How should `--tak-host` and `--tak-port` CLI overrides be applied to the frozen `TakServerConfig` / `GatewayConfig`?

**Decision**: Use nested `model_copy(update=…)` following the exact pattern established for `--web-host`/`--web-port` in `cli.py`.

**Rationale**:

- `GatewayConfig` and `TakServerConfig` are `frozen=True`; direct field assignment raises `pydantic.ValidationError`.
- The existing web override pattern in `cli.py` (lines 56–67) already demonstrates the canonical approach:
  ```python
  cfg = cfg.model_copy(update={"web": cfg.web.model_copy(update=web_overrides)})
  ```
- The identical pattern applies for TAK overrides:
  ```python
  tak_overrides: dict = {}
  if args.tak_host:
      tak_overrides["host"] = args.tak_host
  if args.tak_port:
      tak_overrides["port"] = args.tak_port
  if tak_overrides:
      cfg = cfg.model_copy(update={"tak_server": cfg.tak_server.model_copy(update=tak_overrides)})
  ```
- `model_copy` re-validates field values through pydantic validators, so invalid port numbers are caught early.
- Partial overrides (only `--tak-host` without `--tak-port`) are valid — each flag applies independently.

**Alternatives considered**:

| Alternative | Why rejected |
|-------------|-------------|
| Mutate raw YAML dict before `GatewayConfig.model_validate()` | Bypasses field validators on nested models |
| `object.__setattr__` on frozen model | Circumvents pydantic's type safety; fragile |
| Add `model_config = ConfigDict(frozen=False)` override in subclass | Changes contract of all config objects; violates G2 |

---

## R-005 — Demo Script Remote-TAK Branching Logic

**Question**: What is the cleanest bash pattern for the remote-TAK demo scripts to branch between remote-TAK and local-relay modes?

**Decision**: Use a bash `[[ -n "${TAK_HOST:-}" ]]` guard.  When `TAK_HOST` is set and non-empty: launch `cot-gateway` with `--tak-host` / `--tak-port` flags, skip `tak_relay.py`.  When unset/empty: fall back to local relay (identical to `demo-1drone.sh`).

**Rationale**:

- FR-015-014 / FR-015-015 specify this exact branching logic.
- `${TAK_PORT:-8089}` default aligns with `TakServerConfig.port = 8089`.
- `${TAK_USE_SSL:-true}` default matches `TakServerConfig.use_ssl = True`.
- When `TAK_USE_SSL=false`, the script passes `--config` pointing to a config with `use_ssl: false`; no separate `--no-ssl` CLI flag needed (the YAML config file controls it).
- FR-015-016 mandates `tak_relay.py` is NOT modified.
- Script structure: reuse all helper functions (`preflight`, `cleanup`, `wait_for_health`) from the base demo scripts; only `launch_services()` and the `preflight` port-check set differ.
- When `TAK_HOST` is unset: print a yellow warning banner, then proceed with local relay exactly as `demo-1drone.sh` / `demo-3drone.sh` do.

**Port allocation in remote-TAK mode**:

| Port | Local mode | Remote-TAK mode |
|------|-----------|-----------------|
| 8089 | `tak_relay.py` listens | Remote TAK server (not local) — skip port-free check |
| 8090 | map-sim | map-sim (unchanged) |
| 8092 | cot-gateway web | cot-gateway web (unchanged) |
| 8093 | tak-client-sim web | tak-client-sim web (unchanged) |

**Health check in remote-TAK mode**: Skip the `tcp_ready 8089` relay check; replace with a brief
`nc` or `curl`-based connectivity probe to `${TAK_HOST}:${TAK_PORT:-8089}` (best-effort, non-fatal).

**Alternatives considered**:

| Alternative | Why rejected |
|-------------|-------------|
| Single combined script with `--mode local\|remote` flag | More complex to document; no env-var convenience |
| `TAK_HOST` default of `""` empty string | Same as unset; `[[ -n ]]` handles both correctly |
| Separate `--config` files for SSL-on and SSL-off | Unnecessary duplication; use `TAK_USE_SSL` env var to select config dynamically |
