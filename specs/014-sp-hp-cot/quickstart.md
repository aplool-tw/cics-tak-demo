# Quickstart: SP/HP CoT Broadcasting (Feature 014)

---

## Prerequisites

```bash
cd services/cot-gateway
pip install -e ".[dev]"     # installs pytest, pytest-asyncio, etc.
```

Confirm the test suite is green before starting:

```bash
pytest tests/ -q
```

---

## 1. TDD Step 0 — Write Tests First (G1)

**Create the test file before implementing anything**:

```bash
touch tests/unit/test_site_broadcaster.py
```

Add the test stubs from `plan.md §5`. Run the suite — tests must FAIL (ImportError or assertion failures) because `cot/site_broadcaster.py` does not exist yet:

```bash
pytest tests/unit/test_site_broadcaster.py -v
# Expected: ERRORS / FAILED — "No module named 'cot_gateway.cot.site_broadcaster'"
```

Confirm the failures are the right failures (import errors or test assertion failures, not syntax errors), then proceed to implementation.

---

## 2. Implementation Order

1. **`config.py`** — add `BroadcastConfig` and `broadcast` field to `GatewayConfig`
2. **`cot/site_broadcaster.py`** — XML generators + `SitesBroadcaster`
3. **`loop.py`** — add `sp_hp_broadcast_loop()` method and wiring in `run()`

After each step, re-run:

```bash
pytest tests/unit/test_site_broadcaster.py -v
```

Target: all T014-C* pass after step 1, T014-X* pass after step 2, T014-B* pass after step 3.

Full suite after all steps:

```bash
pytest tests/ -q
# Expected: all existing tests still pass (zero regression)
```

---

## 3. Running the Gateway Locally with Broadcasting Enabled

### 3.1 Add broadcast config to `config/demo.yaml`

Append to the bottom of `config/demo.yaml`:

```yaml
broadcast:
  enabled: true
  interval_s: 10.0          # short interval for demo — 10 s instead of 30 s
  sp_lat: 24.725806
  sp_lon: 121.033750
  sp_alt_m: 50.0
  sp_name: "Strategic Point"
  sp_rings_m: [1000.0, 2000.0, 3000.0]
  hp_lat: 24.735344
  hp_lon: 121.044252
  hp_alt_m: 0.0
  hp_name: "Holding Point"
```

### 3.2 Start the gateway

```bash
python -m cot_gateway --config config/demo.yaml
```

You should see a structured JSON log line every 10 seconds:

```json
{"event": "broadcast_cycle", "sp_uid": "CICS-014-SP", "hp_uid": "CICS-014-HP", "ring_count": 3, "interval_s": 10.0, "level": "info", "logger": "cot_gateway.broadcast", "timestamp": "..."}
```

### 3.3 Verify config load without `broadcast:` key

```bash
python -m cot_gateway --config config/gateway.yaml
# Must start without errors — broadcast disabled by default
```

Expected: No `broadcast_cycle` log lines; gateway operates normally.

---

## 4. Verifying CoT XML Output

### 4.1 Capture raw CoT on the queue (unit test approach)

```python
import asyncio
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from cot_gateway.config import BroadcastConfig
from cot_gateway.cot.site_broadcaster import (
    SitesBroadcaster, generate_sp_cot, generate_hp_cot, generate_ring_cot,
)

cfg = BroadcastConfig(enabled=True)
now = datetime.now(timezone.utc)

# Inspect SP CoT
sp_xml = generate_sp_cot(cfg, now)
print(sp_xml)

# Validate it parses cleanly
root = ET.fromstring(sp_xml)
assert root.attrib["uid"] == "CICS-014-SP"
assert root.attrib["type"] == "a-f-G-U-C"

# Inspect ring CoT
ring_xml = generate_ring_cot(cfg, 1000.0, now)
print(ring_xml)
root = ET.fromstring(ring_xml)
assert root.attrib["type"] == "u-d-c"
ellipse = root.find("detail/shape/ellipse")
assert ellipse.attrib["minor"] == "1000.0"
```

### 4.2 Capture CoT TCP stream (integration)

If a local TAK server is running on `127.0.0.1:18089` (non-SSL, see `demo.yaml`):

```bash
# In a second terminal — listen for raw CoT XML on the TAK TCP port:
nc -l 8089 | grep --line-buffered "CICS-014"
```

Start the gateway (step 3.2). Within 10 seconds you should see the SP, HP, and ring CoT XML flowing through.

### 4.3 Verify with ATAK / WinTAK

1. Configure ATAK to connect to the TAK server that `cot-gateway` uplinks to.
2. Start `cot-gateway` with `broadcast.enabled: true`.
3. Within `2 × interval_s` seconds, confirm on the ATAK map:
   - A blue star symbol labelled **"Strategic Point"** at `24.7258°N, 121.0338°E`
   - A blue star symbol labelled **"Holding Point"** at `24.7353°N, 121.0443°E`
   - Three concentric circles centred on the SP at 1 km, 2 km, and 3 km radii

---

## 5. Config Validation Smoke Tests

### Ring radius ≤ 0 rejected

```yaml
# bad-broadcast.yaml (add to any config)
broadcast:
  enabled: true
  sp_rings_m: [1000.0, 0.0, 3000.0]   # 0.0 is invalid
```

```bash
python -m cot_gateway --config bad-broadcast.yaml
# Expected: ValidationError, gateway does not start
```

### `interval_s: 0` rejected

```yaml
broadcast:
  enabled: true
  interval_s: 0
```

```bash
python -m cot_gateway --config bad-interval.yaml
# Expected: ValidationError, gateway does not start
```

---

## 6. Running the Full Test Suite

```bash
# From services/cot-gateway/
pytest tests/ -q --tb=short

# With coverage:
pytest tests/ --cov=cot_gateway --cov-report=term-missing -q
```

New tests added by this feature:
- `tests/unit/test_site_broadcaster.py` — config, XML generators, broadcaster loop (T014-C*, T014-X*, T014-B*)

All existing tests must continue to pass with zero modification (SC-007, SC-008).

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `broadcast_cycle` log never appears | `broadcast.enabled: false` in config | Set `enabled: true` |
| SP/HP markers appear but rings do not | `sp_rings_m` is empty or missing | Add ring radii to config |
| Gateway exits immediately with `ValidationError` | Ring radius ≤ 0 or `interval_s` ≤ 0 | Fix config values |
| Markers appear once then never again | `stop_event` set prematurely (test environment) | Check test fixture teardown |
| `QueueFull` warnings in logs | TAK transmitter backlogged | Increase `queue_maxsize` or reduce broadcast frequency |
| Existing tests fail after implementation | Accidental mutation of `cot/generator.py` | Verify `generator.py` is unchanged (`git diff`) |
