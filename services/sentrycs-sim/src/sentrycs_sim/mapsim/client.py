"""aiohttp Map Sim client with exponential-backoff retry (research.md R5)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Optional

import aiohttp


class MapSimUnavailableReason(str, Enum):
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    DECODE_ERROR = "decode_error"
    OTHER = "other"


class MapSimUnavailable(Exception):
    def __init__(self, reason: MapSimUnavailableReason, detail: str = "") -> None:
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class MapSimObject:
    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    status: str
    is_lost: bool

    @classmethod
    def from_raw(cls, raw: dict) -> "MapSimObject":
        return cls(
            drone_id=str(raw["drone_id"]),
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            alt_m=float(raw["alt_m"]),
            speed_ms=float(raw.get("speed_ms", 0.0)),
            heading_deg=float(raw.get("heading_deg", 0.0)) % 360.0,
            status=str(raw.get("status", "")),
            is_lost=bool(raw.get("is_lost", False)),
        )


BACKOFF_SCHEDULE_S: tuple[float, ...] = (1.0, 2.0, 4.0, 10.0)


class MapSimClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        timeout_s: float = 1.0,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=float(timeout_s))

    async def fetch_objects(
        self, lat: float, lon: float, radius_m: float = 8000.0
    ) -> list[MapSimObject]:
        """Single request; raises :class:`MapSimUnavailable` on any failure."""
        params = {"lat": lat, "lon": lon, "radius_m": radius_m}
        try:
            async with self._session.get(
                f"{self._base}/objects", params=params, timeout=self._timeout
            ) as resp:
                if resp.status >= 500:
                    raise MapSimUnavailable(
                        MapSimUnavailableReason.HTTP_ERROR, f"status={resp.status}"
                    )
                if resp.status >= 400:
                    raise MapSimUnavailable(
                        MapSimUnavailableReason.HTTP_ERROR, f"status={resp.status}"
                    )
                try:
                    payload = await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise MapSimUnavailable(MapSimUnavailableReason.DECODE_ERROR, str(exc)) from exc
        except MapSimUnavailable:
            raise
        except aiohttp.ClientConnectionError as exc:
            raise MapSimUnavailable(MapSimUnavailableReason.CONNECTION_REFUSED, str(exc)) from exc
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise MapSimUnavailable(MapSimUnavailableReason.TIMEOUT, str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise MapSimUnavailable(MapSimUnavailableReason.OTHER, repr(exc)) from exc

        raw_objs = payload.get("objects", []) if isinstance(payload, dict) else []
        out: list[MapSimObject] = []
        for item in raw_objs:
            if not isinstance(item, dict):
                continue
            obj = MapSimObject.from_raw(item)
            if obj.is_lost:
                # FR-SC-007: filter lost at client layer.
                continue
            out.append(obj)
        return out

    async def fetch_objects_with_retry(
        self,
        lat: float,
        lon: float,
        radius_m: float = 8000.0,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_failure: Optional[Callable[[MapSimUnavailable, float], None]] = None,
        max_attempts: int = len(BACKOFF_SCHEDULE_S) + 1,
    ) -> list[MapSimObject]:
        """Retry with exponential backoff 1/2/4/10s; raises on final failure."""
        last_exc: MapSimUnavailable | None = None
        for attempt in range(max_attempts):
            try:
                return await self.fetch_objects(lat, lon, radius_m)
            except MapSimUnavailable as exc:
                last_exc = exc
                if attempt >= len(BACKOFF_SCHEDULE_S):
                    break
                delay = BACKOFF_SCHEDULE_S[attempt]
                if on_failure is not None:
                    on_failure(exc, delay)
                await sleep(delay)
        assert last_exc is not None
        raise last_exc
