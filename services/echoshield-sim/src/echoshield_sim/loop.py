"""EchoShield main loop: Map Sim query → noise → geometry → TCP broadcast."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import aiohttp

from .config import RadarConfig
from .feed.tcp_server import FeedServer
from .geo.bearing import azimuth_deg, elevation_deg
from .geo.noise import NoiseGenerator, make_noise
from .logging import get_logger, get_throttled_logger
from .mapsim.client import MapSimClient, MapSimUnavailable
from .models.lifecycle import MapSimObject, TrackRegistry, TrackState
from .models.track import RadarTrack


def _format_timestamp(now: Optional[datetime] = None) -> str:
    dt = now if now is not None else datetime.now(tz=timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def build_radar_track(
    *,
    track_id: str,
    obj: MapSimObject,
    sensor_lat: float,
    sensor_lon: float,
    sensor_alt_m: float,
    noise: NoiseGenerator,
    status: str,
    timestamp: str,
) -> RadarTrack:
    """Apply noise + geometry and return a RadarTrack."""
    nlat, nlon = noise.perturb_position(obj.lat, obj.lon)
    nalt = noise.perturb_altitude(obj.alt_m)
    nvel = noise.perturb_velocity(obj.speed_ms)
    az = azimuth_deg(sensor_lat, sensor_lon, nlat, nlon)
    el = elevation_deg(sensor_lat, sensor_lon, sensor_alt_m, nlat, nlon, nalt)
    return RadarTrack(
        track_id=track_id,
        latitude=round(nlat, 7),
        longitude=round(nlon, 7),
        altitude_m=round(nalt, 1),
        velocity_ms=round(nvel, 2),
        azimuth_deg=az,
        elevation_deg=el,
        timestamp=timestamp,
        track_status=status,  # type: ignore[arg-type]
        classification="UAV",
    )


class LoopRunner:
    """Tick-driven coordinator for Map Sim query + broadcast."""

    def __init__(
        self,
        config: RadarConfig,
        *,
        feed_server: FeedServer,
        mapsim: MapSimClient,
        registry: TrackRegistry,
        noise: NoiseGenerator,
        monotonic: Callable[[], float] = time.monotonic,
        now_utc: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> None:
        self.config = config
        self.feed = feed_server
        self.mapsim = mapsim
        self.registry = registry
        self.noise = noise
        self._mono = monotonic
        self._now_utc = now_utc
        self._log = get_logger("echoshield_sim.loop")
        self._throttled = get_throttled_logger(self._log, min_interval_s=1.0)
        self._in_flight = False
        self._tick_id = 0
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        period = 1.0 / float(self.config.update_rate_hz)
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        while not self._stop.is_set():
            now = loop.time()
            if next_deadline > now:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=next_deadline - now)
                    break
                except asyncio.TimeoutError:
                    pass
            await self.run_one_tick()
            next_deadline += period
            # catch up if we fell very far behind
            if next_deadline < loop.time() - period:
                next_deadline = loop.time() + period

    async def run_one_tick(self) -> None:
        tick_id = self._tick_id
        self._tick_id += 1
        if self._in_flight:
            self._log.warning("tick_overrun", tick_id=tick_id, reason="inflight")
            return
        self._in_flight = True
        t0 = self._mono()
        try:
            try:
                objects = await self.mapsim.fetch(
                    self.config.sensor_lat,
                    self.config.sensor_lon,
                    self.config.max_range_m,
                )
            except MapSimUnavailable as exc:
                self._throttled.warning(
                    "map_sim_unavailable",
                    key="map_sim_unavailable",
                    reason=exc.reason.value,
                    detail=exc.detail,
                )
                return
            latency_ms = round((self._mono() - t0) * 1000.0, 3)
            self._log.debug(
                "map_sim_query",
                tick_id=tick_id,
                latency_ms=latency_ms,
                count=len(objects),
                status_code=200,
            )
            now_mono = self._mono()
            active, lost = self.registry.update_from_tick(objects, now_mono)
            await self._broadcast(active, lost)
        finally:
            self._in_flight = False

    async def _broadcast(self, active: list[TrackState], lost: list[TrackState]) -> None:
        if not active and not lost:
            return  # quiet mode
        ts = _format_timestamp(self._now_utc())
        lines: list[bytes] = []
        for st in active:
            track = build_radar_track(
                track_id=st.track_id,
                obj=st.last_known,
                sensor_lat=self.config.sensor_lat,
                sensor_lon=self.config.sensor_lon,
                sensor_alt_m=self.config.sensor_alt_m,
                noise=self.noise,
                status="Active",
                timestamp=ts,
            )
            lines.append(track.to_wire_bytes())
            self._log.debug(
                "track_lifecycle",
                drone_id=st.drone_id,
                track_id=st.track_id,
                lifecycle_event="active",
            )
        for st in lost:
            track = build_radar_track(
                track_id=st.track_id,
                obj=st.last_known,
                sensor_lat=self.config.sensor_lat,
                sensor_lon=self.config.sensor_lon,
                sensor_alt_m=self.config.sensor_alt_m,
                noise=self.noise,
                status="Lost",
                timestamp=ts,
            )
            lines.append(track.to_wire_bytes())
            self._log.info(
                "track_lifecycle",
                drone_id=st.drone_id,
                track_id=st.track_id,
                lifecycle_event="lost",
            )
        await self.feed.broadcast(lines)


async def run(config: RadarConfig) -> None:
    """Top-level entry: wires FeedServer + MapSimClient + loop runner + HTTP info server."""
    log = get_logger("echoshield_sim")
    log.info(
        "startup",
        map_sim_url=config.map_sim_url,
        feed=f"{config.feed_host}:{config.feed_port}",
        info=f"{config.info_host}:{config.info_port}",
        seed=config.noise_seed,
    )
    feed = FeedServer(config.feed_host, config.feed_port, logger=log)
    await feed.start()
    registry = TrackRegistry(config.lost_grace_sec)
    noise = make_noise(config)
    stop_event = asyncio.Event()

    # HTTP info server: exposes GET /info so CoT Gateway can discover sensor position
    from aiohttp import web as aio_web

    async def _info_handler(request: aio_web.Request) -> aio_web.Response:
        return aio_web.json_response(
            {
                "type": "echoshield",
                "sensor_lat": config.sensor_lat,
                "sensor_lon": config.sensor_lon,
                "sensor_alt_m": config.sensor_alt_m,
                "max_range_m": config.max_range_m,
                "feed_port": config.feed_port,
            }
        )

    async def _health_handler(request: aio_web.Request) -> aio_web.Response:
        return aio_web.json_response({"status": "ok", "type": "echoshield"})

    info_app = aio_web.Application()
    info_app.router.add_get("/info", _info_handler)
    info_app.router.add_get("/health", _health_handler)
    info_runner = aio_web.AppRunner(info_app)
    await info_runner.setup()
    info_site = aio_web.TCPSite(info_runner, config.info_host, config.info_port)
    await info_site.start()
    log.info("info_server_started", host=config.info_host, port=config.info_port)

    async with aiohttp.ClientSession() as session:
        mapsim = MapSimClient(session, config.map_sim_url, timeout_s=1.0)
        runner = LoopRunner(
            config,
            feed_server=feed,
            mapsim=mapsim,
            registry=registry,
            noise=noise,
        )

        async def _run():
            try:
                await runner.run_forever()
            finally:
                stop_event.set()

        task = asyncio.create_task(_run())
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            runner.stop()
            raise
        finally:
            runner.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            await feed.stop()
            await info_runner.cleanup()
