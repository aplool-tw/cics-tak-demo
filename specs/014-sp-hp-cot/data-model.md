# Data Model: SP/HP CoT Broadcasting (Feature 014)

---

## 1. `BroadcastConfig` — Pydantic Model

**Module**: `services/cot-gateway/src/cot_gateway/config.py`  
**Constraints**: `extra="forbid"`, all fields optional with defaults

| Field | Python type | Default | Pydantic constraint | Description |
|---|---|---|---|---|
| `enabled` | `bool` | `False` | — | Master switch; `False` → no CoT emitted |
| `interval_s` | `float` | `30.0` | `gt=0.0` | Rebroadcast cadence (seconds) |
| `sp_lat` | `float` | `24.725806` | `ge=-90.0, le=90.0` | SP latitude (WGS-84) |
| `sp_lon` | `float` | `121.033750` | `ge=-180.0, le=180.0` | SP longitude (WGS-84) |
| `sp_alt_m` | `float` | `50.0` | `ge=0.0` | SP altitude MSL (metres HAE) |
| `sp_name` | `str` | `"Strategic Point"` | — | SP callsign on TAK maps |
| `sp_rings_m` | `list[float]` | `[1000.0, 2000.0, 3000.0]` | each element `> 0` via `@model_validator` | Defense ring radii (metres) |
| `hp_lat` | `float` | `24.735344` | `ge=-90.0, le=90.0` | HP latitude (WGS-84) |
| `hp_lon` | `float` | `121.044252` | `ge=-180.0, le=180.0` | HP longitude (WGS-84) |
| `hp_alt_m` | `float` | `0.0` | `ge=0.0` | HP altitude MSL (metres HAE) |
| `hp_name` | `str` | `"Holding Point"` | — | HP callsign on TAK maps |

**`@model_validator`** (after): iterates `sp_rings_m`; raises `ValueError` for any `r <= 0`.

**`GatewayConfig` field**:
```python
broadcast: BroadcastConfig = Field(default_factory=BroadcastConfig)
```
Not `Optional` — always present; `enabled=False` by default. No `None`-guard needed.

---

## 2. `SitesBroadcaster` — Class Interface

**Module**: `services/cot-gateway/src/cot_gateway/cot/site_broadcaster.py`

```python
class SitesBroadcaster:
    """Periodic broadcaster of SP/HP point markers and SP defense rings to the CoT queue."""

    def __init__(
        self,
        cfg: BroadcastConfig,
        cot_queue: asyncio.Queue[str],
        stop_event: asyncio.Event,
    ) -> None:
        self._cfg = cfg
        self._queue = cot_queue
        self._stop = stop_event
        self._log = get_logger("cot_gateway.broadcast")

    def _broadcast_once(self, now: datetime) -> None:
        """Enqueue SP + HP + all ring CoT messages (non-blocking put_nowait).
        
        Silently drops messages if cot_queue is full (QueueFull logged at WARNING).
        """
        ...

    async def run(self) -> None:
        """Emit immediately on call, then re-emit every cfg.interval_s seconds.
        
        Returns when stop_event is set. Does not suppress exceptions — caller
        (GatewayMain.sp_hp_broadcast_loop) is responsible for error handling.
        """
        ...
```

**Standalone generator functions** (module-level, not methods — allows unit testing without a `SitesBroadcaster` instance):

```python
def generate_sp_cot(cfg: BroadcastConfig, now: datetime) -> str:
    """Build SP point-marker CoT XML string."""
    ...

def generate_hp_cot(cfg: BroadcastConfig, now: datetime) -> str:
    """Build HP point-marker CoT XML string."""
    ...

def generate_ring_cot(cfg: BroadcastConfig, radius_m: float, now: datetime) -> str:
    """Build one SP defense-ring (u-d-c) CoT XML string for the given radius."""
    ...
```

**UID constants** (module-level):
```python
SP_UID = "CICS-014-SP"
HP_UID = "CICS-014-HP"

def _ring_uid(radius_m: float) -> str:
    return f"CICS-014-SP-RING-{int(radius_m)}"
```

---

## 3. CoT XML Examples

### 3.1 SP Point Marker (`a-f-G-U-C`)

Config: `sp_lat=24.725806`, `sp_lon=121.033750`, `sp_alt_m=50.0`, `sp_name="Strategic Point"`, `interval_s=30.0`  
`now = 2026-05-06T10:00:00.000Z`  → `stale = 2026-05-06T10:01:00.000Z` (now + 60 s)

```xml
<event version="2.0"
       uid="CICS-014-SP"
       type="a-f-G-U-C"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0" ce="10.0" le="5.0" />
  <detail>
    <contact callsign="Strategic Point" />
    <remarks>Site: SP</remarks>
  </detail>
</event>
```

### 3.2 HP Point Marker (`a-f-G-U-C`)

Config: `hp_lat=24.735344`, `hp_lon=121.044252`, `hp_alt_m=0.0`, `hp_name="Holding Point"`, `interval_s=30.0`  
`now = 2026-05-06T10:00:00.000Z`  → `stale = 2026-05-06T10:01:00.000Z`

```xml
<event version="2.0"
       uid="CICS-014-HP"
       type="a-f-G-U-C"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.735344" lon="121.044252" hae="0.0" ce="10.0" le="5.0" />
  <detail>
    <contact callsign="Holding Point" />
    <remarks>Site: HP</remarks>
  </detail>
</event>
```

### 3.3 SP Defense Ring — 1 km (`u-d-c`)

Config: `sp_lat=24.725806`, `sp_lon=121.033750`, `sp_alt_m=50.0`, `interval_s=30.0`  
`radius_m=1000.0`, `now = 2026-05-06T10:00:00.000Z`  → `stale = 2026-05-06T10:01:00.000Z`

```xml
<event version="2.0"
       uid="CICS-014-SP-RING-1000"
       type="u-d-c"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0" ce="9999999.0" le="9999999.0" />
  <detail>
    <shape>
      <ellipse minor="1000.0" major="1000.0" angle="0" />
    </shape>
  </detail>
</event>
```

### 3.4 SP Defense Ring — 2 km (`u-d-c`)

`radius_m=2000.0`

```xml
<event version="2.0"
       uid="CICS-014-SP-RING-2000"
       type="u-d-c"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0" ce="9999999.0" le="9999999.0" />
  <detail>
    <shape>
      <ellipse minor="2000.0" major="2000.0" angle="0" />
    </shape>
  </detail>
</event>
```

### 3.5 SP Defense Ring — 3 km (`u-d-c`)

`radius_m=3000.0`

```xml
<event version="2.0"
       uid="CICS-014-SP-RING-3000"
       type="u-d-c"
       time="2026-05-06T10:00:00.000Z"
       start="2026-05-06T10:00:00.000Z"
       stale="2026-05-06T10:01:00.000Z"
       how="h-e">
  <point lat="24.725806" lon="121.033750" hae="50.0" ce="9999999.0" le="9999999.0" />
  <detail>
    <shape>
      <ellipse minor="3000.0" major="3000.0" angle="0" />
    </shape>
  </detail>
</event>
```

---

## 4. Stale Time Formula

```
stale_dt = now + timedelta(seconds=2 * cfg.interval_s)
stale     = _iso_ms(stale_dt)   # reuse existing _iso_ms() from cot/generator.py
```

Where `_iso_ms(dt)` → ISO 8601 UTC with milliseconds, Z suffix (e.g. `"2026-05-06T10:01:00.000Z"`).

**Import `_iso_ms`** by defining a local copy in `site_broadcaster.py` (or by importing it from `cot.generator` if made semi-public with a leading underscore). Prefer a local copy to avoid coupling to `generator.py`'s internals — the function is three lines.

---

## 5. Message Count Per Broadcast Cycle

| Config | SP | HP | Rings | Total |
|---|---|---|---|---|
| `sp_rings_m: []` | 1 | 1 | 0 | **2** |
| `sp_rings_m: [1000]` | 1 | 1 | 1 | **3** |
| `sp_rings_m: [1000, 2000, 3000]` (default) | 1 | 1 | 3 | **5** |
| `sp_rings_m: [500, 1000, 1500, 2000, 2500, 3000]` | 1 | 1 | 6 | **8** |

At `interval_s=30`, the default config produces **5 messages per 30 seconds** — approximately 0.17 msg/s, negligible against the `queue_maxsize=500` TAK transmit queue.

---

## 6. Logger

```python
_log = get_logger("cot_gateway.broadcast")
```

Structured log fields emitted on each successful broadcast cycle (FR-014-024):
```python
_log.info(
    "broadcast_cycle",
    sp_uid=SP_UID,
    hp_uid=HP_UID,
    ring_count=len(cfg.sp_rings_m),
    interval_s=cfg.interval_s,
)
```
