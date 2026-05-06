# Quickstart: 013-tak-client-sim-webmap

How to run the end-to-end CICS TAK demo with MIL-STD-2525C map icons.

---

## Prerequisites

Install all services once (from the repository root):

```bash
pip install -e services/map-sim          --break-system-packages
pip install -e services/uds              --break-system-packages
pip install -e services/echoshield-sim   --break-system-packages
pip install -e services/sentrycs-sim     --break-system-packages
pip install -e services/cot-gateway      --break-system-packages
pip install -e services/tak-client-sim   --break-system-packages
```

Verify installations:

```bash
python3 -c "import map_sim, uds, echoshield_sim, sentrycs_sim, cot_gateway, tak_client_sim; print('All OK')"
```

---

## Single-drone demo

Starts 7 services and opens 3 browser tabs.

```bash
scripts/demo-1drone.sh
```

**What runs:**

| Service | Port | Role |
|---------|------|------|
| map-sim | :8090 | Receives drone positions from UDS |
| uds | :18080 | Plays back 1-drone invasion scenario |
| echoshield-sim | :9000/:9001 | Radar feed → CoT Gateway |
| sentrycs-sim | :7070 | RF detection API → CoT Gateway |
| cot-gateway | :8092 | Correlates tracks; web map viewer |
| tak_relay.py | :8089 | Plaintext TCP broadcast relay |
| tak-client-sim | :8093 | Receives CoT XML; TAK client map |

**Browser tabs opened automatically:**

| Tab | URL | Content |
|-----|-----|---------|
| 1 | http://127.0.0.1:8090/objects | Map Sim — raw UDS drone positions |
| 2 | http://127.0.0.1:8092/map | CoT Gateway — correlated tracks (EchoShield + Sentrycs) |
| 3 | http://127.0.0.1:8093/map | TAK Client Sim — MIL-STD-2525C icons |

**Scenario timeline (from script start, ~5 s startup):**

```
t=  9s   TRK-E01 enters EchoShield 3.2 km range → track appears (grey circle+cross = Unknown)
t= 43s   2 km from SP → Sentrycs DETECTED → fused track turns red (red diamond = Hostile)
t= 71s   1 km from SP → Sentrycs MITIGATING → UDS takeover to Holding Point
t=110s   NEUTRALIZED → drone redirected to HP (24.735344N, 121.044252E)
```

**Stop the demo:**

```bash
# Option A: Ctrl-C in the terminal running the script
^C

# Option B: from a separate shell
scripts/demo-1drone.sh --stop
```

---

## Three-drone demo

Identical to the single-drone demo but uses the 3-drone scenario:

```bash
scripts/demo-3drone.sh
```

Three tracks appear on all map viewers simultaneously. Ctrl-C or `--stop` to stop.

---

## TAK client map icons (MIL-STD-2525C)

| CoT type prefix | Symbol | Shape | Colour |
|-----------------|--------|-------|--------|
| `a-u-*` | Unknown | Grey outlined circle with interior × cross | Fill `#90a4ae`, stroke `#546e7a` |
| `a-h-*` | Hostile | Red filled diamond (45°-rotated square) | Fill `#ef5350`, stroke `#b71c1c` |
| Any other | Fallback Unknown | Grey circle | Same as Unknown |
| Stale (any) | Dimmed version | Same shape, grey fill | Fill `#546e7a`, opacity 0.45 |

A white directional arrow is drawn inside the icon when `speed > 0.3 m/s`, aligned to the `course` angle (degrees clockwise from north).

---

## Manual mode (without demo scripts)

Start each service individually for development:

```bash
# Terminal 1 — map-sim
cd services/map-sim && python3 -m map_sim --port 8090

# Terminal 2 — uds
cd services/uds && python3 -m uds \
    --scenario scenarios/demo_single_drone.yaml \
    --api-port 18080 --map-sim-url http://127.0.0.1:8090

# Terminal 3 — echoshield-sim
cd services/echoshield-sim && python3 -m echoshield_sim --config config/demo.yaml

# Terminal 4 — sentrycs-sim
cd services/sentrycs-sim && python3 -m sentrycs_sim --scenario config/demo.yaml

# Terminal 5 — cot-gateway
cd services/cot-gateway && python3 -m cot_gateway --config config/demo.yaml

# Terminal 6 — TAK relay
python3 scripts/tak_relay.py --port 8089

# Terminal 7 — tak-client-sim
python3 -m tak_client_sim --config services/tak-client-sim/config/demo.yaml
```

Open browsers:
- http://127.0.0.1:8090/objects
- http://127.0.0.1:8092/map
- http://127.0.0.1:8093/map

---

## Troubleshooting

### "Port XXXX is already in use"

Find and stop the conflicting process:

```bash
# Linux
ss -tlnp | grep ':8089\|:8090\|:8092\|:8093\|:18080\|:7070'
# macOS
lsof -i :8089 -i :8090 -i :8092 -i :8093
```

Or run `scripts/demo-1drone.sh --stop` first to clean up a previous run.

### "tak_client_sim not installed"

```bash
pip install -e services/tak-client-sim --break-system-packages
```

### "scripts/tak_relay.py not found"

Ensure you are running the script from the repository root:

```bash
cd /path/to/cics-tak-demo
scripts/demo-1drone.sh
```

### TAK client map shows no tracks

1. Verify cot-gateway is healthy: `curl http://127.0.0.1:8092/health`
2. Verify tak_relay.py is accepting connections: `bash -c "echo > /dev/tcp/127.0.0.1/8089" && echo "relay UP"`
3. Check logs: `.dev-runtime/logs/tak-client-sim.log`

### Icons still show as circles after update

Hard-refresh the browser (Ctrl+Shift+R / Cmd+Shift+R) to bypass the page cache.

---

## Log files

All service logs are written to `.dev-runtime/logs/` during a demo run:

```
.dev-runtime/logs/
├── map-sim.log
├── uds.log
├── echoshield-sim.log
├── sentrycs-sim.log
├── cot-gateway.log
├── tak-relay.log
└── tak-client-sim.log
```
