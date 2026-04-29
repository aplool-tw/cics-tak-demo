# Feature 007 – E2E Simulation Scenarios

**Branch:** `feature/007-e2e-scenarios`  
**Spec:** `specs/007-scenario/`  
**Status:** Implemented

---

## 1. Overview

Feature 007 provides two end-to-end simulation scenarios validating the entire drone-intercept pipeline:

| Scenario | Drones | Speed | Route |
|---|---|---|---|
| **Single drone (Sc-1)** | TRK-E01 | 15 m/s | 5 km north → SP |
| **Multi-drone (Sc-2)** | TRK-E0A/B/C | 12 m/s | N/W/NE staggered 0/30/60 s |

Strategic Point (SP): 24.725806°N, 121.033750°E  
Holding Point (HP): 24.725806°N, 121.071889°E (~3.86 km east)

---

## 2. Key Decisions

### 2.1 EchoShield track_id = drone_id (CRITICAL fix)

Pre-existing bug: `_new_track_id()` generated `echo-{uuid4().hex[:8]}` — random UIDs.  
Contract spec (`specs/003-echoshield-sim/contracts/echodyne-wire.md`) required `track_id = drone_id`.  
Fix: `_new_track_id(drone_id: str) → str: return drone_id`

Impact on CoT Gateway UIDs:
- Before fix: `ECHO-echo-a1b2c3d4` (wrong)
- After fix: `ECHO-TRK-E01` (correct)

Six test files updated; `test_scenario_c_new_track_id_after_lost` renamed and assertion inverted (track_id is now stable across Lost→re-appear cycles).

### 2.2 EchoShield sensor placement

Sensor placed at SP (24.725806°N, 121.033750°E) with `max_range_m=3200`.  
This ensures the M2 milestone ("drone enters 3 km detection range") triggers reliably with ±5 m position noise.

### 2.3 Sentrycs timing calculation

Milestones computed from Haversine start-distance at given speed:

```
Sc-1 (TRK-E01, d=8988m, v=15m/s):
  M3 detected_at_s  = 460  s  (drone ≈2 km from SP)
  M4 mitigating_at_s = 525 s  (drone ≈1 km from SP → takeover → HP)
  neutralized_at_s   = 565 s

Sc-2 (TRK-E0A, d=8988m, v=12m/s, t_start=0):
  detected_at_s=580, mitigating_at_s=666, neutralized_at_s=706
Sc-2 (TRK-E0B, d=7223m, v=12m/s, t_start=30):
  detected_at_s=406, mitigating_at_s=489, neutralized_at_s=519
Sc-2 (TRK-E0C, d=8485m, v=12m/s, t_start=60):
  detected_at_s=600, mitigating_at_s=684, neutralized_at_s=716
```

### 2.4 dev-launcher `--echoshield-config`

New flag: load sensor lat/lon/range from a YAML file, while `map_sim_url / feed_host / feed_port` are always injected dynamically. This allows pinning the sensor to SP for e2e runs.

---

## 3. Files Created / Modified

### New YAML scenario files
| File | Purpose |
|---|---|
| `services/uds/scenarios/e2e_single_drone.yaml` | UDS single-drone scenario (TRK-E01) |
| `services/uds/scenarios/e2e_multi_drone.yaml` | UDS multi-drone scenario (TRK-E0A/B/C) |
| `services/sentrycs-sim/config/e2e_single_drone.yaml` | Sentrycs Sc-1 timing |
| `services/sentrycs-sim/config/e2e_multi_drone.yaml` | Sentrycs Sc-2 timing |
| `services/echoshield-sim/config/e2e_scenario.yaml` | EchoShield sensor at SP |

### New validation scripts
| File | Purpose |
|---|---|
| `specs/007-scenario/scripts/validate_scenario.py` | Validates UDS / Sentrycs / EchoShield YAML |
| `specs/007-scenario/scripts/validate_cot.py` | Validates CoT XML type, UID prefix, stale rules |
| `specs/007-scenario/scripts/test_validate_scenario.py` | 20 pytest tests (TDD first) |
| `specs/007-scenario/scripts/test_validate_cot.py` | 16 pytest tests (TDD first) |

### Modified
| File | Change |
|---|---|
| `services/echoshield-sim/src/echoshield_sim/models/lifecycle.py` | `_new_track_id(drone_id)` → returns drone_id |
| `services/echoshield-sim/src/echoshield_sim/models/track.py` | `track_id` pattern relaxed to `min_length=1` |
| 6 echoshield-sim test files | Updated to use `TRK-E01` format track IDs |
| `scripts/dev-launcher.sh` | Added `--echoshield-config` flag |
| `scripts/dev-launcher.example.conf` | Documented `ECHOSHIELD_CONFIG` |

---

## 4. Test Results

| Suite | Tests | Result |
|---|---|---|
| echoshield-sim | 74 | ✅ Pass |
| cot-gateway | 94 | ✅ Pass |
| scenario validation | 31 | ✅ Pass |

---

## 5. Launch Commands

### Scenario 1 (single drone)
```bash
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_single_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml
```

### Scenario 2 (multi drone)
```bash
scripts/dev-launcher.sh \
  --uds-scenario services/uds/scenarios/e2e_multi_drone.yaml \
  --sentrycs-scenario services/sentrycs-sim/config/e2e_multi_drone.yaml \
  --echoshield-config services/echoshield-sim/config/e2e_scenario.yaml
```

### Validate scenario YAML (offline check)
```bash
python3 specs/007-scenario/scripts/validate_scenario.py \
  --uds   services/uds/scenarios/e2e_single_drone.yaml \
  --sntr  services/sentrycs-sim/config/e2e_single_drone.yaml \
  --echo  services/echoshield-sim/config/e2e_scenario.yaml
```

### Validate a CoT XML stream (pipe from tak-client-sim)
```bash
# Capture tak-client-sim stdout, then validate
python3 specs/007-scenario/scripts/validate_cot.py --file /tmp/cot_capture.ndjson
```

---

## 6. Expected TAK Console Output (Sc-1 excerpt)

```
[ECHO-TRK-E01]  type=a-u-A-M-F-Q-r  lat=24.790  lon=121.034  hae=150.0  remarks=status=Active
...
[SENTRYCS-TRK-E01] type=a-u-A-M-F-Q-r  remarks=status=DETECTED
[FUSED-TRK-E01]    type=a-h-A-M-F-Q-r  remarks=status=DETECTED
...
[SENTRYCS-TRK-E01] type=a-u-A-M-F-Q-r  remarks=status=MITIGATING
[FUSED-TRK-E01]    type=a-h-A-M-F-Q-r  remarks=status=MITIGATING
...
[SENTRYCS-TRK-E01] type=a-u-A-M-F-Q-r  remarks=status=NEUTRALIZED  stale=+30s
```
