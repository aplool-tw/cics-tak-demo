"""T020: quiet mode — empty broadcasts produce zero bytes, keep connection."""

from __future__ import annotations

import asyncio

import pytest

from echoshield_sim.feed.tcp_server import FeedServer
from echoshield_sim.logging import get_logger


async def test_quiet_mode_loop():
    srv = FeedServer("127.0.0.1", 0, logger=get_logger("q"))
    await srv.start()
    host, port = srv.sockname
    try:
        r, w = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)
        for _ in range(50):  # 5 s at 10 Hz
            await srv.broadcast([])
            await asyncio.sleep(0.01)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(r.read(1), timeout=0.3)
        assert not w.is_closing()
        w.close()
        await w.wait_closed()
    finally:
        await srv.stop()
