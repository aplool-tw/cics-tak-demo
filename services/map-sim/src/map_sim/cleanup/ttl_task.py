"""Background TTL cleanup loop."""
from __future__ import annotations

import asyncio

from ..registry.object_registry import ObjectRegistry


async def run_cleanup_loop(registry: ObjectRegistry, period_s: float, logger) -> None:
    """Loop forever: sleep ``period_s`` → ``cleanup_expired()``.

    Exits cleanly on ``asyncio.CancelledError``.
    """
    try:
        while True:
            await asyncio.sleep(period_s)
            removed = await registry.cleanup_expired()
            if removed:
                logger.info("ttl.cleanup", removed=removed)
    except asyncio.CancelledError:
        return
