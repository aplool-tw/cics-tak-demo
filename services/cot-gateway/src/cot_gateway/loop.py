"""GatewayMain: orchestrates 5 coroutines + 2 queues + state (seen_uids, prev_uid_by_entity_key)."""

from __future__ import annotations

import asyncio
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
    ) -> None:
        self.config = config
        self._log = get_logger("cot_gateway.loop")
        self._stop = asyncio.Event()

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
        old_uid, new_uid = detect_source_switch(track, self.prev_uid_by_entity_key)
        if old_uid is not None and old_uid != new_uid:
            # Emit stale=time final CoT for old uid first
            final_xml = generate_cot(track, now=now, force_stale_eq_time=True, override_uid=old_uid)
            self.transmitter.enqueue(final_xml)
            self.seen_uids.discard(old_uid)
            self._log.info(
                "source_switch", old_uid=old_uid, new_uid=new_uid, track_id=track.track_id
            )

        # Emit current CoT for new uid
        xml = generate_cot(track, now=now)
        self.transmitter.enqueue(xml)

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
        return exit_code

    def request_stop(self) -> None:
        self._stop.set()
