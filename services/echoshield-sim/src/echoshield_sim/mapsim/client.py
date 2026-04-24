"""aiohttp Map Sim client — GET /objects."""

from __future__ import annotations

from enum import Enum

import aiohttp

from ..models.lifecycle import MapSimObject


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

    async def fetch(self, lat: float, lon: float, radius_m: float) -> list[MapSimObject]:
        params = {"lat": lat, "lon": lon, "radius_m": radius_m}
        try:
            async with self._session.get(
                f"{self._base}/objects", params=params, timeout=self._timeout
            ) as resp:
                if resp.status >= 400:
                    raise MapSimUnavailable(
                        MapSimUnavailableReason.HTTP_ERROR,
                        f"status={resp.status}",
                    )
                try:
                    payload = await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise MapSimUnavailable(MapSimUnavailableReason.DECODE_ERROR, str(exc)) from exc
        except MapSimUnavailable:
            raise
        except aiohttp.ClientConnectionError as exc:
            raise MapSimUnavailable(MapSimUnavailableReason.CONNECTION_REFUSED, str(exc)) from exc
        except TimeoutError as exc:
            raise MapSimUnavailable(MapSimUnavailableReason.TIMEOUT, str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise MapSimUnavailable(MapSimUnavailableReason.OTHER, repr(exc)) from exc

        raw = payload.get("objects", []) if isinstance(payload, dict) else []
        result: list[MapSimObject] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            obj = MapSimObject.model_validate(item)
            if obj.is_lost:
                # FR-ES-012: ignore Map Sim is_lost entries.
                continue
            result.append(obj)
        return result
