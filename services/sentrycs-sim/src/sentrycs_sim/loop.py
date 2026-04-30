"""Main 2 Hz tick loop: Map Sim query → registry sync → per-drone state + takeover."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import aiohttp

from .config import SentrycsConfig
from .geo import destination_point
from .logging import get_logger, get_throttled_logger
from .mapsim import MapSimClient, MapSimObject, MapSimUnavailable
from .models import (
    DetectionStatus,
    DroneRegistry,
    DroneTrack,
    OperatorEstimate,
    TakeoverResult,
)
from .state import StateMachine
from .uds import UdsClient


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class LoopRunner:
    """Owns the main 2 Hz scenario loop and per-drone takeover tasks."""

    def __init__(
        self,
        config: SentrycsConfig,
        *,
        registry: DroneRegistry,
        state_machine: StateMachine,
        mapsim: MapSimClient,
        uds: UdsClient,
        clock: Callable[[], datetime] = _now_utc,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self.registry = registry
        self.sm = state_machine
        self.mapsim = mapsim
        self.uds = uds
        self._clock = clock
        self._sleep = sleep
        self._log = get_logger("sentrycs_sim.loop")
        self._throttled = get_throttled_logger(self._log, min_interval_s=1.0)
        self._stop = asyncio.Event()
        self._scenario_start: float | None = None  # monotonic time
        self._map_sim_reachable: bool = True
        self._takeover_tasks: dict[str, asyncio.Task[None]] = {}

    # -- public API --------------------------------------------------------

    @property
    def map_sim_reachable(self) -> bool:
        return self._map_sim_reachable

    def stop(self) -> None:
        self._stop.set()

    def scenario_elapsed_s(self) -> float:
        if self._scenario_start is None:
            return 0.0
        return time.monotonic() - self._scenario_start

    async def run_forever(self) -> None:
        self._scenario_start = time.monotonic()
        period = float(self.config.poll_interval_s)
        while not self._stop.is_set():
            await self.run_one_tick()
            # sleep until next period, but wake if stop
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=period)
                break
            except asyncio.TimeoutError:
                pass
        # cancel any in-flight takeover tasks on exit
        await self._cancel_takeovers()

    # -- internals ---------------------------------------------------------

    async def run_one_tick(self) -> None:
        now_utc = self._clock()
        elapsed = self.scenario_elapsed_s()

        # 1. fetch Map Sim objects (single attempt per tick; retry is handled
        #    by blocking backoff when Map Sim is down).
        try:
            objects = await self._fetch_with_backoff()
        except MapSimUnavailable:
            # total failure after all backoffs; leave registry untouched.
            self._map_sim_reachable = False
            return

        self._map_sim_reachable = True

        # 2. sync registry from observations.
        seen_ids = {obj.drone_id for obj in objects}
        by_uid: dict[str, MapSimObject] = {obj.drone_id: obj for obj in objects}

        # Update / create tracks for seen objects.
        for obj in objects:
            scenario = self.config.drone_by_uid(obj.drone_id)
            track = self.registry.get_track(obj.drone_id)
            if track is None:
                # only create when scenario time reached detected_at_s
                if scenario is not None and elapsed < float(scenario.detected_at_s):
                    continue
                track = self._create_track(obj, scenario, now_utc)
                self.registry.add(track)
            else:
                self._update_track_from_obj(track, obj, now_utc)

        # 3. state transitions on existing tracks.
        to_remove: list[str] = []
        for track in list(self.registry):
            self._advance_track(
                track=track,
                elapsed_s=elapsed,
                latest=by_uid.get(track.uid),
                seen=track.uid in seen_ids,
                now_utc=now_utc,
            )
            # NEUTRALIZED → IDLE (= remove) after neutralized_hold_s
            if track.status is DetectionStatus.NEUTRALIZED:
                age = (now_utc - track.status_changed_at).total_seconds()
                if age >= float(self.config.neutralized_hold_s):
                    to_remove.append(track.uid)
        for uid in to_remove:
            self.sm.transition(
                self.registry.get_track(uid),  # type: ignore[arg-type]
                DetectionStatus.IDLE,
                reason="neutralized_hold_expired",
                now=now_utc,
            )
            self.registry.remove(uid)

        # 4. time-based DETECTED → MITIGATING transition (takeover issued by CoT Gateway)
        for track in list(self.registry):
            if track.status is not DetectionStatus.DETECTED:
                continue
            if track.takeover_sent:
                continue
            scenario = self.config.drone_by_uid(track.uid)
            if scenario is None:
                continue
            if elapsed < float(scenario.mitigating_at_s):
                continue
            self.sm.transition(track, DetectionStatus.MITIGATING, reason="time_based", now=now_utc)
            track.takeover_sent = True

    # -- track lifecycle ---------------------------------------------------

    def _create_track(
        self,
        obj: MapSimObject,
        scenario,
        now_utc: datetime,
    ) -> DroneTrack:
        if scenario is None:
            # unregistered — use "Unknown" + default operator 300m @ 0deg
            op_lat, op_lon = destination_point(obj.lat, obj.lon, 0.0, 300.0)
            operator = OperatorEstimate(
                operator_lat=op_lat,
                operator_lon=op_lon,
                operator_distance_m=300.0,
                operator_bearing_deg=0.0,
            )
            self._log.warning("unregistered_uid", uid=obj.drone_id)
            model = "Unknown"
        else:
            op_lat, op_lon = destination_point(
                obj.lat,
                obj.lon,
                float(scenario.operator_bearing_deg),
                float(scenario.operator_distance_m),
            )
            operator = OperatorEstimate(
                operator_lat=op_lat,
                operator_lon=op_lon,
                operator_distance_m=float(scenario.operator_distance_m),
                operator_bearing_deg=float(scenario.operator_bearing_deg),
            )
            model = scenario.model

        track = DroneTrack(
            uid=obj.drone_id,
            model=model,
            status=DetectionStatus.IDLE,
            status_changed_at=now_utc,
            lat=obj.lat,
            lon=obj.lon,
            alt_m=obj.alt_m,
            velocity_ms=obj.speed_ms,
            azimuth_deg=obj.heading_deg,
            timestamp=now_utc,
            last_seen_at=now_utc,
            operator=operator,
        )
        # emit operator_locked event
        self._log.info(
            "operator_locked",
            uid=track.uid,
            operator_lat=operator.operator_lat,
            operator_lon=operator.operator_lon,
            bearing_deg=operator.operator_bearing_deg,
            distance_m=operator.operator_distance_m,
        )
        # IDLE → DETECTED transition (scheduled)
        self.sm.transition(track, DetectionStatus.DETECTED, reason="scheduled", now=now_utc)
        return track

    def _update_track_from_obj(
        self, track: DroneTrack, obj: MapSimObject, now_utc: datetime
    ) -> None:
        track.lat = obj.lat
        track.lon = obj.lon
        track.alt_m = obj.alt_m
        track.velocity_ms = obj.speed_ms
        track.azimuth_deg = obj.heading_deg
        track.timestamp = now_utc
        track.last_seen_at = now_utc

    def _advance_track(
        self,
        *,
        track: DroneTrack,
        elapsed_s: float,
        latest: Optional[MapSimObject],
        seen: bool,
        now_utc: datetime,
    ) -> None:
        if track.status is DetectionStatus.DETECTED:
            if not seen:
                # disappear during DETECTED → rollback to IDLE (remove).
                self.sm.transition(
                    track,
                    DetectionStatus.IDLE,
                    reason="disappear_detected",
                    now=now_utc,
                )
                self.registry.remove(track.uid)
            return
        if track.status is DetectionStatus.MITIGATING:
            # LANDED or disappear-grace → NEUTRALIZED
            if latest is not None and latest.status == "LANDED":
                self.sm.transition(track, DetectionStatus.NEUTRALIZED, reason="landed", now=now_utc)
            elif not seen:
                gap = (now_utc - track.last_seen_at).total_seconds()
                if gap >= float(self.config.mitigating_disappear_grace_s):
                    self.sm.transition(
                        track,
                        DetectionStatus.NEUTRALIZED,
                        reason="mitigating_disappear_grace",
                        now=now_utc,
                    )
            return
        # NEUTRALIZED handled in outer loop (neutralized_hold_s).

    # -- takeover tasks ----------------------------------------------------

    def _ensure_takeover_task(self, track: DroneTrack, now_utc: datetime) -> None:
        uid = track.uid
        existing = self._takeover_tasks.get(uid)
        if existing is not None and not existing.done():
            return  # already in-flight for this drone

        # Capture target coords now (before the async closure runs)
        scenario = self.config.drone_by_uid(uid)
        target_lat: float | None = scenario.takeover_target_lat if scenario is not None else None
        target_lon: float | None = scenario.takeover_target_lon if scenario is not None else None
        target_alt_m: float = scenario.takeover_target_alt_m if scenario is not None else 0.0

        async def _do_takeover() -> None:
            result = await self.uds.call_takeover(
                track,
                target_lat=target_lat,
                target_lon=target_lon,
                target_alt_m=target_alt_m,
            )
            # apply result on the main loop via state machine
            self.sm.apply_takeover_result(track, result, now=self._clock())
            if result is TakeoverResult.FAILED_TRANSPORT:
                self._throttled.warning(
                    "takeover_transport_failed", key=f"takeover_failed:{uid}", uid=uid
                )

        task = asyncio.create_task(_do_takeover(), name=f"takeover:{uid}")
        self._takeover_tasks[uid] = task

    async def _cancel_takeovers(self) -> None:
        if not self._takeover_tasks:
            return
        for t in self._takeover_tasks.values():
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._takeover_tasks.values(), return_exceptions=True)
        self._takeover_tasks.clear()

    # -- Map Sim backoff ---------------------------------------------------

    async def _fetch_with_backoff(self) -> list[MapSimObject]:
        def _on_fail(exc: MapSimUnavailable, retry_in_s: float) -> None:
            self._map_sim_reachable = False
            self._throttled.warning(
                "mapsim_unavailable",
                key=f"mapsim_unavailable:{exc.reason.value}",
                error=exc.reason.value,
                retry_in_s=retry_in_s,
            )

        t0 = time.monotonic()
        objs = await self.mapsim.fetch_objects_with_retry(
            self.config.sensor_lat,
            self.config.sensor_lon,
            self.config.detection_radius_m,
            sleep=self._sleep,
            on_failure=_on_fail,
        )
        latency_ms = round((time.monotonic() - t0) * 1000.0, 3)
        self._log.debug("mapsim_query", count=len(objs), latency_ms=latency_ms)
        return objs


async def run(config: SentrycsConfig) -> None:
    """High-level entry: wire up stubs, start API, run loop until cancelled."""
    log = get_logger("sentrycs_sim")
    registry = DroneRegistry()
    sm = StateMachine()
    start_mono = time.monotonic()

    async with aiohttp.ClientSession() as session:
        mapsim = MapSimClient(session, config.map_sim_url, timeout_s=config.map_sim_timeout_s)
        uds = UdsClient(session, config.uds_url, timeout_s=config.uds_timeout_s)
        runner = LoopRunner(
            config,
            registry=registry,
            state_machine=sm,
            mapsim=mapsim,
            uds=uds,
        )

        from .api import build_app
        from aiohttp import web

        app = build_app(
            registry=registry,
            start_monotonic=start_mono,
            get_map_sim_reachable=lambda: runner.map_sim_reachable,
            sensor_lat=config.sensor_lat,
            sensor_lon=config.sensor_lon,
            sensor_alt_m=config.sensor_alt_m,
            detection_radius_m=config.detection_radius_m,
        )
        aio_runner = web.AppRunner(app)
        await aio_runner.setup()
        site = web.TCPSite(aio_runner, config.api_host, config.api_port)
        await site.start()
        log.info(
            "startup",
            api_host=config.api_host,
            api_port=config.api_port,
            drones=len(config.drones),
        )

        loop_task = asyncio.create_task(runner.run_forever())
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        finally:
            runner.stop()
            t0 = time.monotonic()
            if not loop_task.done():
                loop_task.cancel()
                try:
                    await asyncio.wait_for(loop_task, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            await site.stop()
            await aio_runner.cleanup()
            duration_ms = round((time.monotonic() - t0) * 1000.0, 3)
            log.info("shutdown", signal="sigint", duration_ms=duration_ms)
