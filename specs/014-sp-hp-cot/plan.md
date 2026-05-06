# Implementation Plan: SP/HP CoT Broadcasting (Feature 014)

**Feature Branch**: `feature/014-sp-hp-cot`  
**Spec**: `specs/014-sp-hp-cot/spec.md`  
**Status**: Ready for implementation  

---

## 1. Architecture

```
┌─────────────────────────── GatewayMain.run() ───────────────────────────────────┐
│                                                                                   │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────┐                    │
│  │ EchodyneAdapter│   │SentrycsAdapter │   │  ttl_loop()    │                    │
│  │     .run()     │   │     .run()     │   │                │                    │
│  └───────┬────────┘   └───────┬────────┘   └────────────────┘                    │
│          │track_queue         │                                                   │
│  ┌───────▼────────────────────▼──┐                                               │
│  │       process_loop()          │                                               │
│  │  (correlate → emit drone CoT) │                                               │
│  └───────────────┬───────────────┘                                               │
│                  │                 ┌─────────────────────────────────────┐       │
│                  │ cot_queue       │  sp_hp_broadcast_loop()  [NEW]       │       │
│                  │◄────────────────│  ↕ SitesBroadcaster                 │       │
│                  │                 │    generate_sp_cot()                 │       │
│  ┌───────────────▼───────────────┐ │    generate_hp_cot()                │       │
│  │      TakTransmitter.run()     │ │    generate_ring_cot()  (×N rings)  │       │
│  │  (TCP uplink to TAK Server)   │ └─────────────────────────────────────┘       │
│  └───────────────────────────────┘                                               │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

Config:
  GatewayConfig
    └── broadcast: BroadcastConfig   ← NEW (default_factory=BroadcastConfig, enabled=False)
```

The broadcaster is a **pure producer**: it writes into the existing `cot_queue` (`asyncio.Queue[str]`). No new transport, no new connection. The `TakTransmitter` consumes SP/HP/ring CoT messages identically to drone track messages.

---

## 2. Module Breakdown

### 2.1 `config.py` — `BroadcastConfig` (new Pydantic model)

Append after `PerimeterGuardConfig`, before `GatewayConfig`.

```python
class BroadcastConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    interval_s: float = Field(default=30.0, gt=0.0)
    sp_lat:   float = Field(default=24.725806, ge=-90.0, le=90.0)
    sp_lon:   float = Field(default=121.033750, ge=-180.0, le=180.0)
    sp_alt_m: float = Field(default=50.0, ge=0.0)
    sp_name:  str   = "Strategic Point"
    sp_rings_m: list[float] = Field(default_factory=lambda: [1000.0, 2000.0, 3000.0])
    hp_lat:   float = Field(default=24.735344, ge=-90.0, le=90.0)
    hp_lon:   float = Field(default=121.044252, ge=-180.0, le=180.0)
    hp_alt_m: float = Field(default=0.0, ge=0.0)
    hp_name:  str   = "Holding Point"

    @model_validator(mode="after")
    def _validate_rings(self) -> "BroadcastConfig":
        for r in self.sp_rings_m:
            if r <= 0:
                raise ValueError(f"sp_rings_m contains non-positive radius: {r}")
        return self
```

Wire into `GatewayConfig`:

```python
class GatewayConfig(BaseModel):
    ...
    broadcast: BroadcastConfig = Field(default_factory=BroadcastConfig)
```

Using `default_factory=BroadcastConfig` (not `Optional`) means a config file without a `broadcast:` key loads cleanly with `enabled=false` — no `None`-guard needed downstream.

---

### 2.2 `cot/site_broadcaster.py` — XML generators + `SitesBroadcaster` (new file)

**Location**: `services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py`

#### UID constants

```python
SP_UID   = "CICS-014-SP"
HP_UID   = "CICS-014-HP"
# Ring: "CICS-014-SP-RING-{int(radius_m)}"  — no decimals, radius truncated to int
```

#### `generate_sp_cot(cfg, now) -> str`

```
event  type="a-f-G-U-C"  uid="CICS-014-SP"  how="h-e"
  point  lat/lon/hae from cfg.sp_lat/lon/alt_m  ce="10.0"  le="5.0"
  detail
    contact  callsign=cfg.sp_name
    remarks  "Site: SP"
```

`stale = now + timedelta(seconds=2 * cfg.interval_s)`

#### `generate_hp_cot(cfg, now) -> str`

Same structure as SP but with `uid="CICS-014-HP"`, HP coordinates, `hp_name`, and remarks `"Site: HP"`.

#### `generate_ring_cot(cfg, radius_m, now) -> str`

```
event  type="u-d-c"  uid="CICS-014-SP-RING-{int(radius_m)}"  how="h-e"
  point  lat/lon = SP coords  hae=cfg.sp_alt_m  ce="9999999.0"  le="9999999.0"
  detail
    shape
      ellipse  minor="{radius_m:.1f}"  major="{radius_m:.1f}"  angle="0"
```

`stale = now + timedelta(seconds=2 * cfg.interval_s)`

#### `SitesBroadcaster`

```python
class SitesBroadcaster:
    def __init__(
        self,
        cfg: BroadcastConfig,
        cot_queue: asyncio.Queue[str],
        stop_event: asyncio.Event,
    ) -> None: ...

    def _broadcast_once(self, now: datetime) -> None:
        """Enqueue SP + HP + all ring CoT messages onto cot_queue (non-blocking put_nowait)."""
        ...

    async def run(self) -> None:
        """Emit immediately, then re-emit every cfg.interval_s until stop_event is set."""
        ...
```

`_broadcast_once` uses `cot_queue.put_nowait()` (raises `asyncio.QueueFull` if full; silently log and continue — do not block the broadcast loop).

`run()` pattern:
```python
async def run(self) -> None:
    self._broadcast_once(datetime.now(timezone.utc))   # immediate first emission
    self._log.info("broadcast_cycle", ...)
    while not self._stop.is_set():
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.interval_s)
            return   # stop requested
        except asyncio.TimeoutError:
            pass
        self._broadcast_once(datetime.now(timezone.utc))
        self._log.info("broadcast_cycle", ...)
```

`INFO` log fields per FR-014-024: `sp_uid`, `hp_uid`, `ring_count`, `interval_s`.

---

### 2.3 `loop.py` — `GatewayMain` wiring

**New method**:

```python
async def sp_hp_broadcast_loop(self) -> None:
    """Delegate to SitesBroadcaster.run() — errors caught here, not propagated."""
    from cot_gateway.cot.site_broadcaster import SitesBroadcaster
    broadcaster = SitesBroadcaster(
        cfg=self.config.broadcast,
        cot_queue=self.cot_queue,
        stop_event=self._stop,
    )
    await broadcaster.run()
```

**Wiring in `run()`** — add after the existing `sentrycs` conditional:

```python
if self.config.broadcast.enabled:
    coroutines.append(self.sp_hp_broadcast_loop())
```

**Crash isolation**: The existing `GatewayMain.run()` supervision loop already logs `coroutine_exited_unexpectedly` for non-fatal exceptions. The broadcaster will be supervised identically to the other coroutines — no additional try/except needed in `sp_hp_broadcast_loop()`. The gate is: the exception must NOT be a `ConnectionError` with "max retries" (only that triggers `exit_code = 1`).

---

## 3. Config Schema — new `broadcast:` YAML section

```yaml
broadcast:
  enabled: true
  interval_s: 30.0

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

All fields are optional — omitting `broadcast:` entirely works. Omitting individual fields falls back to defaults. Any `sp_rings_m` entry ≤ 0, or `interval_s` ≤ 0, causes a `ValidationError` at load time (gateway refuses to start).

---

## 4. Integration Points Summary

| Touch-point | Change | Risk |
|---|---|---|
| `config.py` | Add `BroadcastConfig`, add `broadcast` field to `GatewayConfig` | Low — additive; `extra="forbid"` catches typos |
| `cot/site_broadcaster.py` | New file | Zero risk to existing code |
| `loop.py` `__init__` | No changes | — |
| `loop.py` `run()` | Add 3-line broadcaster wiring | Low — behind `if broadcast.enabled` guard |
| `config/demo.yaml` | Add `broadcast: enabled: true` section | Optional — update after impl passes tests |
| `config/gateway.yaml` | No change needed (defaults satisfy prod) | Zero |

---

## 5. Testing Strategy (G1 TDD)

All tests live in `services/cot-gateway/tests/unit/test_site_broadcaster.py`.

**Tests MUST be written and confirmed FAILING before implementation begins.**

### 5.1 Config tests (follow `test_perimeter_config.py` pattern)

| Test ID | Scenario |
|---|---|
| T014-C01 | `BroadcastConfig()` defaults: `enabled=False`, `interval_s=30.0`, correct lat/lon/alt defaults |
| T014-C02 | `BroadcastConfig(enabled=True)` → `enabled is True` |
| T014-C03 | Ring radius ≤ 0 raises `ValidationError` |
| T014-C04 | Ring radius negative raises `ValidationError` |
| T014-C05 | `interval_s=0` raises `ValidationError` |
| T014-C06 | Extra fields raise `ValidationError` (extra="forbid") |
| T014-C07 | `load_config()` without `broadcast:` key → `cfg.broadcast.enabled is False` |
| T014-C08 | `load_config()` with full `broadcast:` section → all fields parsed correctly |
| T014-C09 | `load_config()` with invalid ring radius rejects at load time |
| T014-C10 | `sp_rings_m: []` is valid (empty list allowed) |

### 5.2 XML generator tests (follow `test_cot_generator.py` pattern)

| Test ID | Scenario |
|---|---|
| T014-X01 | `generate_sp_cot()` — UID is `"CICS-014-SP"` |
| T014-X02 | `generate_sp_cot()` — type is `"a-f-G-U-C"` |
| T014-X03 | `generate_sp_cot()` — callsign equals `cfg.sp_name` |
| T014-X04 | `generate_sp_cot()` — `stale == now + 2×interval_s` (millisecond precision) |
| T014-X05 | `generate_sp_cot()` — point lat/lon/hae match `cfg.sp_*` |
| T014-X06 | `generate_hp_cot()` — UID is `"CICS-014-HP"` (distinct from SP) |
| T014-X07 | `generate_hp_cot()` — type is `"a-f-G-U-C"`, callsign equals `cfg.hp_name` |
| T014-X08 | `generate_hp_cot()` — point lat/lon/hae match `cfg.hp_*` |
| T014-X09 | `generate_ring_cot(cfg, 1000.0, now)` — UID is `"CICS-014-SP-RING-1000"` |
| T014-X10 | `generate_ring_cot()` — type is `"u-d-c"` |
| T014-X11 | `generate_ring_cot(cfg, 1000.0, now)` — `<ellipse minor="1000.0" major="1000.0" angle="0"/>` |
| T014-X12 | `generate_ring_cot(cfg, 2500.5, now)` — UID is `"CICS-014-SP-RING-2500"`, ellipse semi-axes are `"2500.5"` |
| T014-X13 | `generate_ring_cot()` — point is at SP coordinates, not HP |
| T014-X14 | `generate_ring_cot()` — stale follows same `now + 2×interval_s` rule |
| T014-X15 | All three generators — output is valid XML (parse with `ET.fromstring` without error) |

### 5.3 Broadcaster loop tests

| Test ID | Scenario |
|---|---|
| T014-B01 | `SitesBroadcaster.run()` with `sp_rings_m=[]` — enqueues exactly 2 messages (SP + HP) |
| T014-B02 | `SitesBroadcaster.run()` with `sp_rings_m=[1000, 2000, 3000]` — enqueues exactly 5 messages on first cycle |
| T014-B03 | `SitesBroadcaster.run()` — first emission happens before any `await sleep` |
| T014-B04 | `SitesBroadcaster.run()` — stop_event set immediately after first cycle → only one batch queued |
| T014-B05 | `GatewayMain` with `broadcast.enabled=False` — `sp_hp_broadcast_loop` coroutine not in task list |

### 5.4 Test fixtures pattern

```python
import asyncio
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import pytest
from cot_gateway.config import BroadcastConfig
from cot_gateway.cot.site_broadcaster import (
    SitesBroadcaster, generate_sp_cot, generate_hp_cot, generate_ring_cot,
)

NOW = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

@pytest.fixture
def cfg():
    return BroadcastConfig(
        enabled=True, interval_s=30.0,
        sp_lat=24.725806, sp_lon=121.033750, sp_alt_m=50.0,
        sp_name="Strategic Point", sp_rings_m=[1000.0, 2000.0, 3000.0],
        hp_lat=24.735344, hp_lon=121.044252, hp_alt_m=0.0, hp_name="Holding Point",
    )
```

---

## 6. Constitution Check

| Gate | Status | Note |
|---|---|---|
| G1 TDD | ✅ Required | Tests in `test_site_broadcaster.py` written and confirmed failing before `site_broadcaster.py` exists |
| G2 Pydantic `extra="forbid"` | ✅ Required | `BroadcastConfig` must include `model_config = ConfigDict(extra="forbid")` |
| G3 structlog JSON | ✅ Required | `get_logger("cot_gateway.broadcast")`, no `print()`, no f-string logs |
| G4 stdlib ET only | ✅ Required | `from xml.etree import ElementTree as ET` — no lxml |
| G5 Additive config | ✅ Required | `GatewayConfig.broadcast = Field(default_factory=BroadcastConfig)` — missing key → disabled |
| G6 Crash isolation | ✅ Required | Broadcaster supervised by existing `GatewayMain.run()` error handler; exception logged as WARNING, gateway continues |
| G7 No `generate_cot()` mutation | ✅ Required | `cot/generator.py` MUST NOT be modified |

---

## 7. File Changelist

```
MODIFIED:
  services/cot-gateway/src/cot_gateway/config.py
  services/cot-gateway/src/cot_gateway/loop.py

NEW:
  services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py
  services/cot-gateway/tests/unit/test_site_broadcaster.py

OPTIONAL (post-impl):
  services/cot-gateway/config/demo.yaml   (add broadcast: enabled: true)
  specs/014-sp-hp-cot/plan.md             (this file)
```

---

## 8. Sequence: Broadcast Cycle

```
t=0   GatewayMain.run() starts
t=0   sp_hp_broadcast_loop() task created
t=0   SitesBroadcaster.__init__(cfg, cot_queue, stop_event)
t=0   SitesBroadcaster.run() called
t=0     _broadcast_once(now=t0)  → enqueues SP + HP + 3 rings (5 messages)
t=0     log INFO broadcast_cycle {sp_uid, hp_uid, ring_count=3, interval_s=30.0}
t=0     asyncio.wait_for(stop_event, timeout=30.0)
t=30  TimeoutError → loop continues
t=30    _broadcast_once(now=t30) → enqueues 5 more messages, stale = t30+60
t=60  → ...
t=N   stop_event.set() → asyncio.wait_for returns → SitesBroadcaster.run() returns
```

TAK clients that connect at t=15 receive the first batch (queued at t=0) from the TAK transmitter backlog. Their SP/HP/ring stale is t0+60, so markers remain visible until t=60 — well after the t=30 refresh.
