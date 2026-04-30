"""In-memory store for the most recent CoT event per UID, with stale eviction."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from tak_client_sim.models import CotEvent

# Keep entries this many seconds after their stale timestamp before evicting
_STALE_GRACE_S: int = 60


class CotStore:
    """Thread-safe asyncio store: latest CotEvent per UID, auto-evicts on read."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._events: dict[str, CotEvent] = {}

    async def upsert(self, event: CotEvent) -> None:
        async with self._lock:
            self._events[event.uid] = event

    async def get_all(self) -> list[CotEvent]:
        """Return all non-expired events, evicting those > _STALE_GRACE_S past stale."""
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [uid for uid, evt in self._events.items() if (now - evt.stale).total_seconds() > _STALE_GRACE_S]
            for uid in expired:
                del self._events[uid]
            return list(self._events.values())
