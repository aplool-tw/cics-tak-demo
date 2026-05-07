# Quickstart: Feature 010 — Perimeter Defense

**Branch**: `010-perimeter-defense`  
**Demo scenario**: drone at 3 500 m, 35 m/s → 1 km takeover perimeter

---

## Prerequisites

```bash
git checkout 010-perimeter-defense
# Confirm services are installed (run once per venv):
cd services/sentrycs-sim && pip install -e ".[dev]" -q
cd services/cot-gateway  && pip install -e ".[dev]" -q
cd services/uds          && pip install -e ".[dev]" -q
```

---

## Run the Demo (all-in-one)

```bash
# Terminal 1 — UDS (drone command target + map sim)
cd services/uds
python -m uds --scenario scenarios/demo_single_drone.yaml

# Terminal 2 — Sentrycs sim (detection + perimeter takeover)
cd services/sentrycs-sim
python -m sentrycs_sim config/demo.yaml

# Terminal 3 — EchoShield sim (radar track source)
cd services/echoshield-sim
python -m echoshield_sim config/local.yaml    # or e2e_scenario.yaml

# Terminal 4 — CoT Gateway (correlator + tactical map)
cd services/cot-gateway
python -m cot_gateway
```

Open the tactical map: **http://localhost:18080/map**

---

## What to Observe

### Legend panel (Item 1)
- The side panel shows three new dashed-line entries:
  - `─ ─ ─  1km defense ring` (pastel cyan `#80deea`)
  - `─ ─ ─  2km defense ring` (pastel orange `#ffcc80`)
  - `─ ─ ─  3km defense ring` (pastel red `#ef9a9a`)
- Hover any of the three dashed concentric circles → tooltip shows the matching label.
- Colors do **not** match EchoShield blue (`#00BFFF`) or Sentrycs yellow (`#FFD700`).

### Drone movement (Item 2)
- At zoom 13, the drone marker moves a clearly visible distance every 3 seconds (≈ 105 m/refresh).
- Previous speed was 20 m/s (≈ 60 m/refresh — imperceptible).

### Fused track (Item 3)
- Blue `◆` (EchoShield) appears around t ≈ 9 s.
- Switches to red `✈` (Fused) when Sentrycs correlates (around detection threshold).
- Structured log in cot-gateway confirms `source_switch` event with `entity_key`.

### Perimeter takeover (Item 4)

Expected timeline with `defense_radius_m: 1000.0` at 35 m/s:

| Time | Event |
|---|---|
| t ≈ 0 s | Scenario starts, drone 3 500 m north of sensor |
| t ≈ 9 s | Enters EchoShield 3 200 m radar range |
| t ≈ 43 s | Crosses 2 km ring |
| t ≈ 71 s | Crosses 1 km defense perimeter (physics) |
| t = 75 s | `detected_at_s` fires → Sentrycs DETECTED |
| t = 75 s+ | First tick: drone already at ≈ 875 m → takeover fires immediately |
| t ≈ 165 s | NEUTRALIZED |

Watch the Sentrycs-sim log:
```
# Should appear around t=75s
{"event": "takeover_scheduled", "uid": "TRK-E01", ...}
```

---

## Verify Tests Pass

```bash
cd services/cot-gateway  && pytest -q --tb=short
cd services/sentrycs-sim && pytest -q --tb=short
cd services/uds          && pytest -q --tb=short
```

All should report **0 failures**.

---

## Verify Lint Clean

```bash
cd services/cot-gateway  && ruff check . && black --check . && echo "OK"
cd services/sentrycs-sim && ruff check . && black --check . && echo "OK"
```

---

## Fallback: Test Time-Based Mode (No Perimeter)

Remove (or comment out) `defense_radius_m` from `services/sentrycs-sim/config/demo.yaml`, then re-run. The takeover should fire at `t = 125 s` (scenario `mitigating_at_s`), confirming backward compatibility (FR-010-014).

---

## Key Files

| Purpose | Path |
|---|---|
| Tactical map + legend JS | `services/cot-gateway/src/cot_gateway/web/server.py` |
| TrackSource enum | `services/cot-gateway/src/cot_gateway/models/track.py` |
| Source-switch log | `services/cot-gateway/src/cot_gateway/loop.py` |
| Drone speed scenario | `services/uds/scenarios/demo_single_drone.yaml` |
| Sentrycs demo config | `services/sentrycs-sim/config/demo.yaml` |
| Sentrycs config schema | `services/sentrycs-sim/src/sentrycs_sim/config.py` |
| Takeover loop | `services/sentrycs-sim/src/sentrycs_sim/loop.py` |
| haversine_m | `services/sentrycs-sim/src/sentrycs_sim/geo/wgs84.py` |
