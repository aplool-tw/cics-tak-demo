"""Integration test helpers: a synchronous "driver" that runs a LoopRunner
tick-by-tick while controlling scenario elapsed time."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import aiohttp

from sentrycs_sim.config import SentrycsConfig
from sentrycs_sim.loop import LoopRunner
from sentrycs_sim.mapsim import MapSimClient
from sentrycs_sim.models import DroneRegistry
from sentrycs_sim.state import StateMachine
from sentrycs_sim.uds import UdsClient


class ScenarioDriver:
    """Holds runner + mocks scenario_elapsed_s with an injectable clock."""

    def __init__(
        self,
        cfg: SentrycsConfig,
        *,
        session: aiohttp.ClientSession,
        start: datetime | None = None,
    ) -> None:
        self.registry = DroneRegistry()
        self.sm = StateMachine()
        self.mapsim = MapSimClient(session, cfg.map_sim_url, timeout_s=cfg.map_sim_timeout_s)
        self.uds = UdsClient(session, cfg.uds_url, timeout_s=cfg.uds_timeout_s)
        self._elapsed = 0.0
        self._now = start or datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)

        def _clock() -> datetime:
            return self._now

        self.runner = LoopRunner(
            cfg,
            registry=self.registry,
            state_machine=self.sm,
            mapsim=self.mapsim,
            uds=self.uds,
            clock=_clock,
        )
        # inject elapsed
        self.runner.scenario_elapsed_s = lambda: self._elapsed  # type: ignore[assignment]

    def advance(self, seconds: float) -> None:
        self._elapsed += seconds
        self._now = self._now + timedelta(seconds=seconds)

    async def tick(self, advance_s: float = 0.0) -> None:
        if advance_s:
            self.advance(advance_s)
        await self.runner.run_one_tick()
        # allow scheduled takeover tasks to complete
        tasks = [t for t in self.runner._takeover_tasks.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@asynccontextmanager
async def driver(cfg: SentrycsConfig) -> AsyncIterator[ScenarioDriver]:
    async with aiohttp.ClientSession() as session:
        drv = ScenarioDriver(cfg, session=session)
        try:
            yield drv
        finally:
            await drv.runner._cancel_takeovers()
