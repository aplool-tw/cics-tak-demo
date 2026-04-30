"""GatewayMain: orchestrates 5 coroutines + 2 queues + state (seen_uids, prev_uid_by_entity_key)."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Optional

from cot_gateway.config import GatewayConfig
from cot_gateway.correlate.correlator import TrackCorrelator
from cot_gateway.cot.generator import generate_cot
from cot_gateway.cot.uid import detect_source_switch, entity_keys_for, uid_for
from cot_gateway.echoshield.adapter import EchodyneAdapter
from cot_gateway.logging import get_logger
from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.sentrycs.adapter import SentrycsAdapter
from cot_gateway.tak.transmitter import TakTransmitter
from cot_gateway.web.track_store import TrackStore


class GatewayMain:
    """Main coordinator; build and run all coroutines."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        ssl_context=None,
        tak_host_override: Optional[str] = None,
        tak_port_override: Optional[int] = None,
        echoshield_host_override: Optional[str] = None,
        echoshield_port_override: Optional[int] = None,
        sentrycs_base_url_override: Optional[str] = None,
        track_store: Optional[TrackStore] = None,
    ) -> None:
        self.config = config
        self._log = get_logger("cot_gateway.loop")
        self._stop = asyncio.Event()
        self._track_store = track_store

        self.track_queue: asyncio.Queue[UnifiedTrack] = asyncio.Queue(maxsize=1000)
        self.cot_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=config.tak_server.queue_maxsize)

        self.correlator = TrackCorrelator(
            distance_threshold_m=config.correlator.distance_threshold_m,
            time_window_s=config.correlator.time_window_s,
            ttl_s=config.correlator.ttl_s,
        )

        self.seen_uids: set[str] = set()
        self.prev_uid_by_entity_key: dict[str, str] = {}

        self.echoshield = EchodyneAdapter(
            host=echoshield_host_override or config.echoshield.host,
            port=echoshield_port_override or config.echoshield.port,
            track_queue=self.track_queue,
            reconnect_interval_s=config.echoshield.reconnect_interval_s,
            stop_event=self._stop,
        )
        self.sentrycs: SentrycsAdapter | None = None
        if config.sentrycs.enabled:
            self.sentrycs = SentrycsAdapter(
                host=config.sentrycs.host,
                port=config.sentrycs.port,
                track_queue=self.track_queue,
                poll_interval_s=config.sentrycs.poll_interval_s,
                timeout_s=config.sentrycs.timeout_s,
                stop_event=self._stop,
                base_url=sentrycs_base_url_override,
            )

        self.transmitter = TakTransmitter(
            host=tak_host_override or config.tak_server.host,
            port=tak_port_override or config.tak_server.port,
            cot_queue=self.cot_queue,
            ssl_context=ssl_context,
            max_retries=config.tak_server.max_retries,
            backoff_initial_s=config.tak_server.backoff_initial_s,
            backoff_cap_s=config.tak_server.backoff_cap_s,
            stop_event=self._stop,
        )

        self._perimeter_guard = None
        if config.perimeter is not None and config.perimeter.enabled:
            from cot_gateway.perimeter.guard import PerimeterGuard

            cfg = config.perimeter
            self._perimeter_guard = PerimeterGuard(
                sp_lat=config.web.sp_lat,
                sp_lon=config.web.sp_lon,
                uds_url=cfg.uds_url,
                radius_m=cfg.radius_m,
                holding_lat=cfg.holding_lat,
                holding_lon=cfg.holding_lon,
                holding_alt_m=cfg.holding_alt_m,
                descent_speed_ms=cfg.descent_speed_ms,
                uds_timeout_s=cfg.uds_timeout_s,
            )

    # ------------------------------------------------------------------
    # Coroutines
    # ------------------------------------------------------------------

    async def process_loop(self) -> None:
        """Consume track_queue → correlate → detect source switch → emit CoT(s)."""
        while not self._stop.is_set():
            try:
                track = await asyncio.wait_for(self.track_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            final_track = self.correlator.correlate(track)
            now = datetime.now(timezone.utc)
            await self._emit_for_track(final_track, now)

    async def _emit_for_track(self, track: UnifiedTrack, now: datetime) -> None:
        old_uids, new_uid = detect_source_switch(track, self.prev_uid_by_entity_key)
        for old_uid in old_uids:
            # Emit stale=time final CoT for each superseded uid
            final_xml = generate_cot(track, now=now, force_stale_eq_time=True, override_uid=old_uid)
            self.transmitter.enqueue(final_xml)
            self.seen_uids.discard(old_uid)
            if self._track_store is not None:
                await self._track_store.remove(old_uid)
            self._log.info(
                "source_switch",
                old_uid=old_uid,
                new_uid=new_uid,
                track_id=track.track_id,
                entity_keys=entity_keys_for(track),
            )

        # Emit current CoT for new uid
        xml = generate_cot(track, now=now)
        self.transmitter.enqueue(xml)
        if self._track_store is not None:
            await self._track_store.upsert(new_uid, track)

        if self._perimeter_guard is not None and self._track_store is not None:
            await self._perimeter_guard.check(
                track,
                uid=new_uid,
                mark_takeover=self._track_store.mark_takeover,
            )

        if new_uid not in self.seen_uids:
            self.seen_uids.add(new_uid)
            self._log.info(
                "track_first_seen",
                uid=new_uid,
                source=track.source.value,
                track_id=track.track_id,
            )

        # Update entity key map
        for key in entity_keys_for(track):
            self.prev_uid_by_entity_key[key] = new_uid

        if track.source == TrackSource.FUSED:
            self._log.info("correlation_hit", uid=new_uid)

    async def ttl_loop(self, interval_s: float = 1.0) -> None:
        """1 Hz tick; mark Lost → emit final CoT on old uid."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval_s)
                return
            except asyncio.TimeoutError:
                pass
            now = datetime.now(timezone.utc)
            lost = self.correlator.update_ttl(now)
            for lost_track in lost:
                uid = uid_for(lost_track)
                xml = generate_cot(lost_track, now=now, force_stale_eq_time=True)
                self.transmitter.enqueue(xml)
                self.seen_uids.discard(uid)
                if self._track_store is not None:
                    await self._track_store.remove(uid)
                for key in entity_keys_for(lost_track):
                    self.prev_uid_by_entity_key.pop(key, None)
                self._log.info("ttl_expired", uid=uid, track_id=lost_track.track_id)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def run(self) -> int:
        """Run all coroutines; return exit code (0 normal, != 0 on fatal)."""
        coroutines = [
            self.echoshield.run(),
            self.process_loop(),
            self.ttl_loop(),
            self.transmitter.run(),
        ]
        if self.sentrycs is not None:
            coroutines.append(self.sentrycs.run())

        # Start optional web server
        web_task: asyncio.Task | None = None
        if self.config.web.enabled and self._track_store is not None:
            from cot_gateway.web.server import run_web_server
            from cot_gateway.web.sites import load_sites

            sites_cfg = load_sites(self.config.web.sites_file)
            sp_lat = self.config.web.sp_lat
            sp_lon = self.config.web.sp_lon
            for s in sites_cfg.sites:
                if s.type == "strategic_point":
                    sp_lat, sp_lon = s.lat, s.lon
                    break
            web_task = asyncio.create_task(
                run_web_server(
                    host=self.config.web.host,
                    port=self.config.web.port,
                    sites_config=sites_cfg,
                    track_store=self._track_store,
                    echoshield_info_url=self.config.web.echoshield_info_url,
                    sentrycs_sensor_url=self.config.web.sentrycs_sensor_url,
                    sp_lat=sp_lat,
                    sp_lon=sp_lon,
                    stop=self._stop,
                )
            )

        tasks = [asyncio.create_task(c) for c in coroutines]
        exit_code = 0
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

        for t in done:
            if t.cancelled():
                continue
            exc = t.exception()
            if exc is not None:
                # Fatal only for TAK max retries
                if isinstance(exc, ConnectionError) and "max retries" in str(exc).lower():
                    exit_code = 1
                    self._log.error("gateway_fatal", error=str(exc))
                else:
                    self._log.warning("coroutine_exited_unexpectedly", error=repr(exc))

        self._stop.set()
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if web_task is not None:
            with contextlib.suppress(Exception):
                await web_task
        return exit_code

    def request_stop(self) -> None:
        self._stop.set()
