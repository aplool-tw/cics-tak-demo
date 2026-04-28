"""EchodyneAdapter: TCP client that parses newline-JSON from EchoShield Sim into UnifiedTracks."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from cot_gateway.logging import get_logger
from cot_gateway.models.track import TrackSource, UnifiedTrack

REQUIRED_FIELDS = (
    "track_id",
    "lat",
    "lon",
    "altitude_m",
    "velocity_ms",
    "azimuth_deg",
    "elevation_deg",
    "timestamp",
    "track_status",
    "classification",
)


def _parse_iso8601(s: str) -> datetime:
    # Accept "Z" or "+HH:MM"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _validate_and_build(msg: dict) -> UnifiedTrack | None:
    """Return UnifiedTrack or None (with caller logging). Raises nothing."""
    for f in REQUIRED_FIELDS:
        if f not in msg:
            raise KeyError(f"missing required field: {f}")
    lat = float(msg["lat"])
    lon = float(msg["lon"])
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lat/lon out of range: {lat},{lon}")
    status = msg["track_status"]
    if status not in ("Active", "Lost"):
        raise ValueError(f"invalid track_status: {status!r}")
    track_id = str(msg["track_id"])
    if not track_id:
        raise ValueError("empty track_id")
    now = datetime.now(timezone.utc)
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=lat,
        lon=lon,
        alt_m=float(msg["altitude_m"]),
        velocity_ms=float(msg["velocity_ms"]),
        azimuth_deg=float(msg["azimuth_deg"]),
        elevation_deg=float(msg["elevation_deg"]),
        timestamp=_parse_iso8601(msg["timestamp"]),
        received_at=now,
        last_updated=now,
        track_status=status,
        classification=str(msg["classification"]),
    )


class EchodyneAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        track_queue: asyncio.Queue,
        *,
        reconnect_interval_s: float = 5.0,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.track_queue = track_queue
        self.reconnect_interval_s = reconnect_interval_s
        self._stop = stop_event or asyncio.Event()
        self._log = get_logger("cot_gateway.echoshield")

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
            except (OSError, ConnectionError) as exc:
                self._log.warning(
                    "echoshield_disconnected",
                    error=str(exc),
                    retry_in_s=self.reconnect_interval_s,
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.reconnect_interval_s)
                except asyncio.TimeoutError:
                    pass
                continue

            self._log.info("echoshield_connected", host=self.host, port=self.port)
            try:
                await self._read_loop(reader)
            except (ConnectionResetError, asyncio.IncompleteReadError, OSError) as exc:
                self._log.warning("echoshield_disconnected", error=str(exc))
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

            if self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.reconnect_interval_s)
            except asyncio.TimeoutError:
                pass

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while not self._stop.is_set():
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            if not line:
                raise ConnectionResetError("EOF from echoshield")
            await self._handle_line(line)

    async def _handle_line(self, line: bytes) -> None:
        try:
            text = line.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            self._log.error("invalid_json", error=str(exc))
            return
        if not text:
            return
        try:
            msg = json.loads(text)
        except json.JSONDecodeError as exc:
            self._log.error("invalid_json", error=str(exc), line=text[:200])
            return
        if not isinstance(msg, dict):
            self._log.error("invalid_json", error="top-level not object")
            return
        try:
            track = _validate_and_build(msg)
        except KeyError as exc:
            self._log.error("invalid_wire_fields", error=str(exc), msg=msg)
            return
        except ValueError as exc:
            err = str(exc)
            if "track_status" in err:
                self._log.warning("invalid_wire_enum", error=err, msg=msg)
            elif "range" in err or "lat/lon" in err:
                self._log.warning("invalid_wire_range", error=err, msg=msg)
            else:
                self._log.warning("invalid_wire_fields", error=err, msg=msg)
            return
        if track is None:
            return
        self._log.debug("track_parsed", track_id=track.track_id)
        await self.track_queue.put(track)
