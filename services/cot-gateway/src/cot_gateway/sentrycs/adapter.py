"""SentrycsAdapter: aiohttp 1 Hz poller of GET /detections → UnifiedTrack enqueue."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from cot_gateway.logging import get_logger
from cot_gateway.models.track import TrackSource, UnifiedTrack


def _parse_iso8601(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _detection_to_track(d: dict[str, Any]) -> UnifiedTrack:
    now = datetime.now(timezone.utc)
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=d["uid"],
        rf_track_id=d["uid"],
        lat=float(d["lat"]),
        lon=float(d["lon"]),
        alt_m=float(d["alt_m"]),
        velocity_ms=0.0,
        azimuth_deg=0.0,
        elevation_deg=0.0,
        timestamp=_parse_iso8601(d["timestamp"]),
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
        detection_status=d["detection_status"],
        drone_model=d.get("model"),
        operator_lat=d.get("operator_lat"),
        operator_lon=d.get("operator_lon"),
    )


class SentrycsAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        track_queue: asyncio.Queue,
        *,
        poll_interval_s: float = 1.0,
        timeout_s: float = 2.0,
        stop_event: asyncio.Event | None = None,
        base_url: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.track_queue = track_queue
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s
        self._stop = stop_event or asyncio.Event()
        self._log = get_logger("cot_gateway.sentrycs")
        self._base_url = base_url or f"http://{host}:{port}"

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self._stop.is_set():
                tick_start = time.monotonic()
                try:
                    detections = await self._fetch(session)
                    if detections:
                        self._log.info("sentrycs_poll", count=len(detections))
                        for d in detections:
                            try:
                                track = _detection_to_track(d)
                            except (KeyError, ValueError) as exc:
                                self._log.warning(
                                    "sentrycs_poll_failed",
                                    error=f"bad detection: {exc}",
                                )
                                continue
                            try:
                                self.track_queue.put_nowait(track)
                            except asyncio.QueueFull:
                                self._log.warning(
                                    "queue_full_drop",
                                    uid=track.track_id,
                                    source="sentrycs",
                                )
                    else:
                        self._log.debug("sentrycs_empty")
                except Exception as exc:
                    self._log.warning("sentrycs_poll_failed", error=str(exc))
                elapsed = time.monotonic() - tick_start
                remaining = max(0.0, self.poll_interval_s - elapsed)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    async def _fetch(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        url = f"{self._base_url}/detections"
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = await resp.json()
        if not isinstance(data, list):
            raise RuntimeError(f"response not a list: {type(data).__name__}")
        return data
