"""PerimeterGuard: fires UDS takeover when a track crosses the SP defense radius."""

from __future__ import annotations

from typing import Awaitable, Callable

import aiohttp

from cot_gateway.correlate.haversine import haversine_m
from cot_gateway.logging import get_logger
from cot_gateway.models.track import TrackSource, UnifiedTrack

_TAKEOVER_SOURCES = {TrackSource.SENTRYCS, TrackSource.FUSED}
_TAKEOVER_STATUSES = {"DETECTED", "MITIGATING"}


class PerimeterGuard:
    """Fires a UDS takeover command when a qualifying track breaches the defense radius.

    Idempotency latch (G6): once a track_id is successfully issued (HTTP 200 or 409),
    it is added to _triggered and will never fire again until service restart.

    Transport errors do NOT set the latch — the guard retries on the next tick.
    """

    def __init__(
        self,
        *,
        sp_lat: float,
        sp_lon: float,
        uds_url: str,
        radius_m: float,
        holding_lat: float,
        holding_lon: float,
        holding_alt_m: float,
        descent_speed_ms: float,
        uds_timeout_s: float = 3.0,
    ) -> None:
        self._sp_lat = sp_lat
        self._sp_lon = sp_lon
        self._uds_url = uds_url.rstrip("/")
        self._radius_m = radius_m
        self._holding_lat = holding_lat
        self._holding_lon = holding_lon
        self._holding_alt_m = holding_alt_m
        self._descent_speed_ms = descent_speed_ms
        self._timeout = aiohttp.ClientTimeout(total=uds_timeout_s)
        self._triggered: set[str] = set()
        self._log = get_logger("cot_gateway.perimeter")

    async def check(
        self,
        track: UnifiedTrack,
        *,
        uid: str,
        mark_takeover: Callable[[str], Awaitable[None]],
    ) -> None:
        """Check if track qualifies for a perimeter takeover and issue if so."""
        if track.source not in _TAKEOVER_SOURCES:
            return
        if track.detection_status not in _TAKEOVER_STATUSES:
            return
        if track.track_id in self._triggered:
            return
        dist_m = haversine_m(self._sp_lat, self._sp_lon, track.lat, track.lon)
        if dist_m >= self._radius_m:
            return
        self._log.info(
            "perimeter_breach",
            track_id=track.track_id,
            uid=uid,
            source=track.source.value,
            dist_m=round(dist_m, 1),
            radius_m=self._radius_m,
        )
        await self._issue_takeover(track, uid=uid, mark_takeover=mark_takeover)

    async def _issue_takeover(
        self,
        track: UnifiedTrack,
        *,
        uid: str,
        mark_takeover: Callable[[str], Awaitable[None]],
    ) -> None:
        """POST takeover command to UDS.

        On HTTP 200 or 409: set idempotency latch + call mark_takeover.
        On transport error: log warning, do NOT set latch (retry next tick).
        """
        # Use rf_track_id (the raw UDS drone_id) rather than the prefixed
        # track_id ("FUSED-TRK-E01", "SENTRYCS-TRK-E01") that UDS never registered.
        payload = {
            "drone_id": track.rf_track_id,
            "target_lat": self._holding_lat,
            "target_lon": self._holding_lon,
            "target_alt_m": self._holding_alt_m,
            "descent_speed_ms": self._descent_speed_ms,
        }
        url = f"{self._uds_url}/command/takeover"
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status in (200, 409):
                        self._triggered.add(track.track_id)
                        self._log.info(
                            "takeover_issued",
                            track_id=track.track_id,
                            uid=uid,
                            http_status=resp.status,
                        )
                        await mark_takeover(uid)
                    else:
                        body = await resp.text()
                        self._log.warning(
                            "takeover_rejected",
                            track_id=track.track_id,
                            http_status=resp.status,
                            body=body[:200],
                        )
        except Exception as exc:
            self._log.warning(
                "takeover_transport_failed",
                track_id=track.track_id,
                error=repr(exc),
            )
