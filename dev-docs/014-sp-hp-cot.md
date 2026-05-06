# 014 — SP/HP CoT Broadcasting

**Feature branch**: `feature/014-sp-hp-cot`  
**Spec**: `specs/014-sp-hp-cot/`  
**Date**: 2026-05-06  
**Status**: ✅ Complete — merged to `develop`

---

## Summary

Implemented periodic broadcasting of Strategic Point (SP) and Holding Point (HP) CoT
markers — including multi-layer defense rings — into the existing `cot-gateway` TAK
uplink.  Real TAK clients (ATAK / WinTAK) now receive SP/HP positions and three
annotated range rings (1 km / 2 km / 3 km) every 30 seconds, keeping them continuously
visible without any polling from the client side.

---

## What Changed

### New file: `src/cot_gateway/cot/site_broadcaster.py`

Three pure CoT XML generator functions (stdlib `ElementTree`) + `SitesBroadcaster` class:

| Symbol | CoT type | UID |
|--------|----------|-----|
| `generate_sp_cot()` | `a-f-G-U-C` (Friendly Ground Unit — Command Post) | `CICS-014-SP` |
| `generate_hp_cot()` | `a-f-G-U-C` | `CICS-014-HP` |
| `generate_ring_cot()` | `u-d-c` (drawing circle) | `CICS-014-SP-RING-{r}m` |

Stale time for all three: `now + 2 × interval_s` — keeps markers alive between re-broadcasts.

`SitesBroadcaster.run()` is an `asyncio` coroutine: emits once immediately on start, then
re-emits every `interval_s` using `asyncio.wait_for(stop_event, timeout=interval_s)` —
the same pattern used by `ttl_loop()` in `loop.py`.

### Modified: `src/cot_gateway/config.py`

New `BroadcastConfig` Pydantic v2 model with `extra="forbid"`:

```yaml
broadcast:
  enabled: false          # flip to true to activate
  sp_lat: 24.725806
  sp_lon: 121.033750
  sp_alt_m: 50.0
  sp_name: "Strategic Point"
  hp_lat: 24.735344
  hp_lon: 121.044252
  hp_alt_m: 0.0
  hp_name: "Holding Point"
  defense_rings_m: [1000, 2000, 3000]   # metres; validated > 0
  interval_s: 30.0                       # re-broadcast period
```

`GatewayConfig` gains `broadcast: BroadcastConfig = Field(default_factory=BroadcastConfig)`.
Existing configs without a `broadcast:` key continue to work unchanged (disabled by default).

### Modified: `src/cot_gateway/loop.py`

`GatewayMain.__init__` creates `self._broadcaster` when `config.broadcast.enabled`.
`GatewayMain.run()` appends `self._broadcaster.run()` to the coroutine list if set.
A broadcaster crash is isolated by the existing `done/pending` supervisor — it logs
`coroutine_exited_unexpectedly` and keeps drone CoT running (G6 crash isolation).

### Modified: `config/gateway.yaml` + `config/demo.yaml`

Both configs now have a documented `broadcast:` section.  `gateway.yaml` ships with
`enabled: false` (production default); `demo.yaml` ships with `enabled: true` so the
full SP/HP/ring broadcast is active in the local dev demo.

---

## CoT XML Design Decisions

### SP / HP point markers — `a-f-G-U-C`

`a-f-G-U-C` maps to **Friendly Ground Unit — Command Post** in MIL-STD-2525C.  
On ATAK, this renders as a filled friendly (blue) ground icon — clearly visible as an
infrastructure anchor distinct from drone tracks (`a-u-*` grey / `a-h-*` red).

Both SP and HP use the same type; they are distinguished by UID (`CICS-014-SP` /
`CICS-014-HP`), callsign, and coordinates.  The `remarks` text reads `"Site: SP"` /
`"Site: HP"` for human readability in the CoT detail panel.

### Defense rings — `u-d-c` with `<shape><ellipse .../></shape>`

`u-d-c` is ATAK's native **drawing circle** type.  The `<detail>` contains a `<shape>`
element with an `<ellipse minor="{r}" major="{r}" angle="0"/>` where `minor` = `major` =
ring radius in metres — an equal-axis ellipse is a circle.

This format renders as an annotated circle overlay on the ATAK / WinTAK map without
requiring any plugins.  Alternative CoT types (`a-r-*`, `a-u-*` area types) were
researched but are less portable or require additional `<sensor>` sub-elements not
needed here (see `specs/014-sp-hp-cot/research.md` §1 for full comparison).

---

## Test Coverage

| File | Tests | Coverage |
|------|-------|---------|
| `tests/unit/test_broadcast_config.py` | 10 | `BroadcastConfig` model validation, `load_config()` YAML integration |
| `tests/unit/test_site_broadcaster.py` | 21 | XML generators (SP, HP, ring), `SitesBroadcaster` loop behaviour |

Total new tests: **31**. All 180 tests (149 baseline + 31 new) pass.

---

## Known Issues / Gotchas

1. **Integer ring UIDs**: `_ring_uid(2500.5)` → `"CICS-014-SP-RING-2500"` (truncates via
   `int()`). This is intentional — the UID must be stable across identical config across
   restarts, and floating-point noise could create duplicate rings.  The ellipse semi-axes
   retain full float precision.

2. **Queue full behaviour**: `_broadcast_once` uses `put_nowait` and logs `broadcast_queue_full`
   WARNING if the queue is saturated.  This is non-blocking and does not disrupt drone CoT.
   In practice, the 500-slot `cot_queue` would require >100 unacknowledged broadcast cycles
   to saturate.

3. **First emission at t=0**: Clients that connect after the first cycle (but before the
   second) still receive the queued messages from t=0 via the TAK transmitter's queue
   backlog — stale = t0 + 2×interval_s, so they remain valid for two full intervals.

4. **Broadcaster not in `seen_uids`**: SP/HP/ring UIDs are never added to `seen_uids` in
   `GatewayMain` (that set tracks drone tracks only).  This is correct — SP/HP are not
   drone tracks and should not affect TTL or source-switch logic.

---

## File Change Summary

```
services/cot-gateway/
  src/cot_gateway/
    config.py                          # Added BroadcastConfig + GatewayConfig.broadcast
    cot/site_broadcaster.py            # NEW — generators + SitesBroadcaster
    loop.py                            # Wired SitesBroadcaster into run()
  config/
    gateway.yaml                       # Added broadcast: section (enabled: false)
    demo.yaml                          # Added broadcast: section (enabled: true)
  tests/unit/
    test_broadcast_config.py           # NEW — 10 config model tests
    test_site_broadcaster.py           # NEW — 21 XML + broadcaster tests
specs/014-sp-hp-cot/
  spec.md plan.md research.md data-model.md tasks.md quickstart.md
  checklists/requirements.md
```
