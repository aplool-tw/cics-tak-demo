"""Main loop — drives trajectory.step + push per tick."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from uds.engine.trajectory import DroneContext, step
from uds.logging import get_logger
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState

_log = get_logger("uds.loop")


class MainLoop:
    """Asyncio drift-corrected loop at ``hz`` Hz.

    Each tick: compute dt, call ``trajectory.step`` for every drone, then
    ``map_client.enqueue(drone)`` for drones with ``flight_state ∉ {IDLE}``
    and ``landed_finalized == False``. When a LANDING → LANDED transition
    happens in the same tick, the final LANDED payload is enqueued and
    ``map_client.finalize_landed(drone_id)`` is called (FR-UDS-006).
    """

    def __init__(
        self,
        *,
        drones: dict[str, DroneState],
        hz: int,
        map_client,
        contexts: Optional[dict[str, DroneContext]] = None,
        on_tick: Optional[Callable] = None,
    ) -> None:
        self.drones = drones
        self.hz = hz
        self.map_client = map_client
        self.contexts = contexts or {did: DroneContext(waypoints=[], landing_point=(0.0, 0.0, 0.0, 3.0)) for did in drones}
        self.on_tick = on_tick
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_tick_ts: Optional[float] = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="uds.MainLoop")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                pass
            self._task = None

    async def _run(self) -> None:
        period = 1.0 / float(self.hz)
        next_tick = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            dt = 0.0 if self._last_tick_ts is None else (now - self._last_tick_ts)
            self._last_tick_ts = now
            try:
                self._tick(dt)
            except Exception as exc:  # never kill the loop
                _log.error("loop.tick_error", error=str(exc), error_class=type(exc).__name__)
            next_tick += period
            sleep_for = next_tick - time.monotonic()
            if sleep_for < 0:
                # Fell behind — resync to now
                next_tick = time.monotonic()
                sleep_for = 0
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=sleep_for)
                break  # stop requested
            except asyncio.TimeoutError:
                continue

    def _tick(self, dt: float) -> None:
        for drone in self.drones.values():
            if drone.flight_state == FlightState.IDLE:
                continue
            if drone.landed_finalized:
                continue
            prev_state = drone.flight_state
            ctx = self.contexts.get(drone.drone_id) or DroneContext(waypoints=[], landing_point=(0.0, 0.0, 0.0, 3.0))
            step(drone, dt=dt, ctx=ctx)
            drone.last_tick_ts = datetime.now(timezone.utc)
            # Enqueue push (also for the same tick that transitioned to LANDED)
            self.map_client.enqueue(drone)
            if self.on_tick is not None:
                try:
                    self.on_tick(drone)
                except Exception:
                    pass
            # Finalize if this tick transitioned LANDING → LANDED
            if prev_state == FlightState.LANDING and drone.flight_state == FlightState.LANDED:
                self.map_client.finalize_landed(drone.drone_id)
                drone.landed_finalized = True
