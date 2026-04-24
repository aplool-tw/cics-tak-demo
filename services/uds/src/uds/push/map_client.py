"""Map Simulator HTTP push client (contracts §3)."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from uds.logging import get_logger
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState

_log = get_logger("uds.push")

_PUSH_TIMEOUT_S = 0.5
_QUEUE_MAX = 2


def build_payload(drone: DroneState) -> dict:
    """Serialize DroneState → POST /objects/update JSON body (contracts §3.2)."""
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "drone_id": drone.drone_id,
        "lat": drone.lat,
        "lon": drone.lon,
        "alt_m": drone.alt_m,
        "speed_ms": drone.velocity_ms,
        "heading_deg": drone.heading_deg,
        "status": drone.flight_state.value,
        "timestamp": ts,
    }


class MapClient:
    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        base_url: str,
        drones: dict[str, DroneState],
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.drones = drones
        self.queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._finalized: set[str] = set()
        self._stopped = False
        self.stats: dict[str, int] = defaultdict(int)

    @property
    def url(self) -> str:
        return f"{self.base_url}/objects/update"

    async def start(self) -> None:
        for drone_id in self.drones.keys():
            q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
            self.queues[drone_id] = q
            self._workers[drone_id] = asyncio.create_task(
                self._worker(drone_id, q), name=f"uds.push[{drone_id}]"
            )

    async def close(self) -> None:
        self._stopped = True
        for t in self._workers.values():
            t.cancel()
        for t in self._workers.values():
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._workers.clear()

    # --- public enqueue API ---

    def enqueue(self, drone: DroneState) -> None:
        """Enqueue latest state for push. Silently no-op after finalize_landed."""
        drone_id = drone.drone_id
        if drone_id in self._finalized:
            return
        if drone.flight_state == FlightState.IDLE:
            return
        q = self.queues.get(drone_id)
        if q is None:
            return
        payload = build_payload(drone)
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop oldest, push newest (contracts §3.3)
            try:
                dropped = q.get_nowait()
                self.stats["push.backpressure"] += 1
                _log.warning(
                    "push.backpressure",
                    drone_id=drone_id,
                    dropped_timestamp=dropped.get("timestamp"),
                )
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def finalize_landed(self, drone_id: str) -> None:
        """Mark a drone as LANDED-finalized. Further enqueues are no-ops."""
        self._finalized.add(drone_id)

    # --- worker loop ---

    async def _worker(self, drone_id: str, q: asyncio.Queue) -> None:
        while True:
            try:
                payload = await q.get()
            except asyncio.CancelledError:
                return
            try:
                await self._post(drone_id, payload)
            except Exception as exc:  # hard guarantee: never propagate
                _log.error(
                    "push.unhandled",
                    drone_id=drone_id,
                    error_class=type(exc).__name__,
                    error=str(exc),
                )

    async def _post(self, drone_id: str, payload: dict) -> None:
        try:
            async with asyncio.timeout(_PUSH_TIMEOUT_S):
                async with self.session.post(self.url, json=payload) as resp:
                    if 200 <= resp.status < 300:
                        self.stats["push.ok"] += 1
                        _log.debug("push.ok", drone_id=drone_id, http_status=resp.status)
                    elif 400 <= resp.status < 500:
                        self.stats["push.client_error"] += 1
                        _log.warning(
                            "push.client_error", drone_id=drone_id, http_status=resp.status
                        )
                    elif 500 <= resp.status < 600:
                        self.stats["push.server_error"] += 1
                        _log.warning(
                            "push.server_error", drone_id=drone_id, http_status=resp.status
                        )
                    else:
                        _log.warning(
                            "push.unexpected_status",
                            drone_id=drone_id,
                            http_status=resp.status,
                        )
        except asyncio.TimeoutError:
            self.stats["push.timeout"] += 1
            _log.warning("push.timeout", drone_id=drone_id, error_class="TimeoutError")
        except aiohttp.ClientConnectorError as exc:
            self.stats["push.conn_error"] += 1
            _log.warning(
                "push.conn_error",
                drone_id=drone_id,
                error_class=type(exc).__name__,
                error=str(exc),
            )
        except aiohttp.ClientResponseError as exc:
            self.stats["push.client_error"] += 1
            _log.warning(
                "push.client_error",
                drone_id=drone_id,
                http_status=getattr(exc, "status", 0),
                error_class=type(exc).__name__,
            )
        except aiohttp.ClientError as exc:
            self.stats["push.conn_error"] += 1
            _log.warning(
                "push.conn_error",
                drone_id=drone_id,
                error_class=type(exc).__name__,
                error=str(exc),
            )
