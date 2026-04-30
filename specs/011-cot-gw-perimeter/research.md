# Research: CoT Gateway Perimeter Guard (Feature 011)

**Feature**: `011-cot-gw-perimeter`  
**Phase**: Phase 0 — Dependency & Approach Confirmation  
**Date**: 2026-05-11

---

## Summary

Feature 011 introduces no new external dependencies. All required capabilities are already present in the codebase. This document confirms each technical area and records the decisions made.

---

## Decision Log

### D1 — HTTP client for UDS takeover dispatch

**Question**: Does `cot-gateway` already have an HTTP client available for use in `PerimeterGuard`?

**Decision**: Use `aiohttp.ClientSession` — the same library already used by `SentrycsAdapter` to poll the sentrycs-sim `/detections` endpoint and by `server.py` to fan-out sensor-info requests.

**Rationale**: `aiohttp` is listed in `AGENTS.md §3.2` as a required dependency (`aiohttp, pydantic v2, structlog, PyYAML`). It is already in `services/cot-gateway/pyproject.toml`. Introducing a separate HTTP client (e.g., `httpx`) would violate G7 (Minimal Dependencies).

**Session management**: `PerimeterGuard.__init__` receives an injected `aiohttp.ClientSession` (created once in `GatewayMain.__init__` alongside the perimeter guard). This avoids per-call session creation overhead and simplifies test injection.

**Alternatives considered**:
- `urllib.request` (stdlib): synchronous only; incompatible with asyncio event loop. Rejected.
- `httpx` with asyncio: adds a new dependency not needed elsewhere. Rejected per G7.

---

### D2 — Haversine distance function

**Question**: Does `cot-gateway` already have a haversine implementation? Can it be reused directly?

**Decision**: Reuse `cot_gateway.correlate.haversine.haversine_m(lat1, lon1, lat2, lon2) → float` exactly as specified in FR-011-010.

**Rationale**: The function at `services/cot-gateway/src/cot_gateway/correlate/haversine.py` implements the standard haversine formula with Earth radius `6_371_000 m` and returns distance in metres. It is already tested by the correlator unit tests. No wrapper or reimplementation is needed.

**Signature confirmed**:
```python
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float
```

**Alternatives considered**:
- `sentrycs_sim.geo.wgs84.haversine_m`: same formula, different module path. Not importable from cot-gateway (different service). Rejected — use the cot-gateway copy per FR-011-010.
- `geopy`: explicitly prohibited by G7 / AGENTS.md `§3.2`.

---

### D3 — Entity key for idempotency latch

**Question**: How should PerimeterGuard compute the entity key to detect source-switch scenarios?

**Decision**: Use `cot_gateway.cot.uid.entity_keys_for(track: UnifiedTrack) → list[str]` to obtain all entity keys for a given track, and add each returned key to `_triggered` upon successful dispatch.

**Rationale**: `entity_keys_for` already encodes the `(radar_track_id, rf_track_id)` composite logic used by `GatewayMain` to manage `prev_uid_by_entity_key`. Using the same function guarantees that the PerimeterGuard idempotency latch is consistent with the source-switch detection logic in the main loop. A FUSED track carries both `radar_track_id` and `rf_track_id`; an ECHOSHIELD track carries only `radar_track_id`. The latch covers all keys for a given track.

**Latch lifecycle**: Keys remain in `_triggered` for the service lifetime (G6 no persistence). They are not explicitly removed on TTL expiry from the correlator — this is intentional. If the same physical drone re-enters the perimeter after TTL expiry, the scenario requires a service restart to allow a fresh takeover (consistent with the PoC scope and SC-011-005 "single scenario lifecycle").

---

### D4 — UDS wire contract compatibility

**Question**: Does the frozen `POST /command/takeover` contract (AGENTS.md §4) match the parameters PerimeterGuard will send?

**Decision**: PerimeterGuard sends `{drone_id, target_lat, target_lon, target_alt_m}` — exactly the frozen four-field body. No `descent_speed_ms` is included (per spec Assumptions §5).

**Frozen contract confirmed** (from AGENTS.md §4):
```
POST /command/takeover
{drone_id, target_lat, target_lon, target_alt_m}
200 / 400 / 404 / 409; 409 treated as success
```

**Parameter mapping**:
| Wire field | Source in PerimeterGuard |
|------------|--------------------------|
| `drone_id` | `track.track_id` (same as sentrycs-sim's `DroneTrack.uid`) |
| `target_lat` | `config.perimeter.holding_lat` |
| `target_lon` | `config.perimeter.holding_lon` |
| `target_alt_m` | `config.perimeter.holding_alt_m` |

**No contract change required.** G2 gate remains PASS.

---

### D5 — `aiohttp` session lifetime in GatewayMain

**Question**: Where should the `aiohttp.ClientSession` used by PerimeterGuard be created and managed?

**Decision**: Create a single `aiohttp.ClientSession` in `GatewayMain.__init__` when `PerimeterGuard` is instantiated, and close it during `run()` teardown alongside other resource cleanup.

**Rationale**: `GatewayMain.run()` already manages task lifecycle via `asyncio.gather` + cancel. Adding session cleanup there (e.g., `async with aiohttp.ClientSession() as session`) follows the existing pattern used by `sentrycs_sim.loop.run()`.

**Implementation note**: The session is created conditionally:
```python
if config.perimeter and config.perimeter.enabled:
    self._perimeter_session = aiohttp.ClientSession()
    self._perimeter_guard = PerimeterGuard(
        sp_lat=config.perimeter.sp_lat,
        sp_lon=config.perimeter.sp_lon,
        uds_url=config.perimeter.uds_url,
        radius_m=config.perimeter.radius_m,
        holding_lat=config.perimeter.holding_lat,
        holding_lon=config.perimeter.holding_lon,
        holding_alt_m=config.perimeter.holding_alt_m,
        session=self._perimeter_session,
    )
```
Session close in `run()` finally block.

---

### D6 — `clearLayers()` race condition (RC2)

**Question**: Is there a risk of a race condition between `refreshSites()` and `refreshTracks()` after the fix?

**Decision**: No cross-timer dependency is introduced. Each function manages its own layer group independently.

**Rationale**: `refreshSites()` manages `siteLayer` and `sensorLayer`. `refreshTracks()` manages `trackLayer`. They run on independent `setInterval` timers (30 s vs 2 s). The fix moves `clearLayers()` inside the success branch of each function's own try block — no shared state, no locking needed. This matches the existing `refreshTracks()` pattern where `trackLayer.clearLayers()` already occurs inside the success branch.

---

### D7 — Cache-Control for `/tracks` and `/sites`

**Question**: Which headers are required to prevent browser and proxy caching?

**Decision**: `Cache-Control: no-store, no-cache` + `Pragma: no-cache` applied as response headers on `/tracks` and `/sites` only.

**Rationale**: 
- `no-store`: prevents writing to cache (strongest directive, required by FR-011-001).
- `no-cache`: requires revalidation even if cached (belt-and-suspenders for HTTP/1.0 proxies).
- `Pragma: no-cache`: HTTP/1.0 backward compatibility (common in embedded TAK client environments).
- `/health` is excluded (FR-011-003) — polling tools may rely on cached health responses.
- No `fetch` API `{cache: 'no-store'}` option is added to the JS (it is sufficient to set headers server-side; client-side fetch options are redundant and add maintenance surface).

---

### D8 — `PerimeterGuardConfig` field `sp_lat` / `sp_lon` source

**Question**: Should `sp_lat`/`sp_lon` come from `perimeter:` config or be auto-derived from `sites.yaml`?

**Decision**: Explicitly set in `perimeter:` section of `demo.yaml` (per spec Assumptions §1).

**Rationale**: The spec explicitly states: "PerimeterGuard SP coordinates are explicitly set in `cot-gateway/config/demo.yaml` under the `perimeter:` section; they need not be auto-derived from `sites.yaml`." This keeps PerimeterGuard independent of the sites file at runtime and avoids coupling config loading order. Values will match in practice (`sp_lat: 24.725806, sp_lon: 121.033750`).

---

## Dependency Matrix

| Dependency | Already Present | Version | Notes |
|------------|----------------|---------|-------|
| `aiohttp` | ✅ cot-gateway | ≥ 3.9 | Used by SentrycsAdapter, web/server.py |
| `pydantic v2` | ✅ cot-gateway | ≥ 2.0 | Used by config.py |
| `structlog` | ✅ cot-gateway | any | Used by all services |
| `PyYAML` | ✅ cot-gateway | any | Used by config loader |
| `pytest-asyncio` | ✅ cot-gateway | any | Used in existing tests |
| `haversine_m` | ✅ cot-gateway | internal | `cot_gateway.correlate.haversine` |
| `entity_keys_for` | ✅ cot-gateway | internal | `cot_gateway.cot.uid` |

**No new packages required.** `pyproject.toml` files need no changes.

---

## Conclusion

All NEEDS CLARIFICATION items resolved. Zero new external dependencies. Implementation can proceed directly to Phase 1 design and task generation.
