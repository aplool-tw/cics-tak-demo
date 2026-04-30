"""aiohttp UDS takeover client (contracts/takeover-caller.md)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from ..logging import get_logger
from ..models import (
    DroneTrack,
    TakeoverResult,
    classify_http_status,
)


class UdsClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        timeout_s: float = 3.0,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=float(timeout_s))
        self._log = get_logger("sentrycs_sim.uds")

    async def call_takeover(
        self,
        track: DroneTrack,
        *,
        target_lat: float | None = None,
        target_lon: float | None = None,
        target_alt_m: float = 0.0,
    ) -> TakeoverResult:
        """POST /command/takeover with exact 4-field body; return TakeoverResult.

        Pre-send latch: if ``track.takeover_sent`` already True, skip.
        Emits ``takeover_request`` + ``takeover_response`` structlog events.

        Args:
            track: the drone track being taken over.
            target_lat: desired takeover target latitude; falls back to
                ``track.lat`` when *None* (backward-compatible default).
            target_lon: desired takeover target longitude; falls back to
                ``track.lon`` when *None*.
            target_alt_m: desired takeover target altitude in metres (default 0.0).
        """
        # pre-send latch (FR-SC-010 / takeover-caller.md §5.1)
        if track.takeover_sent:
            return track.takeover_result or TakeoverResult.ACCEPTED

        body: dict[str, Any] = {
            "drone_id": track.uid,
            "target_lat": target_lat if target_lat is not None else float(track.lat),
            "target_lon": target_lon if target_lon is not None else float(track.lon),
            "target_alt_m": target_alt_m,
        }
        self._log.info(
            "takeover_request",
            uid=track.uid,
            drone_id=track.uid,
            target_lat=body["target_lat"],
            target_lon=body["target_lon"],
            target_alt_m=body["target_alt_m"],
        )

        t0 = time.monotonic()
        http_status: int | None = None
        error: str | None = None
        try:
            async with self._session.post(
                f"{self._base}/command/takeover",
                json=body,
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            ) as resp:
                http_status = resp.status
                # body MAY fail to parse — we log a warn but ignore.
                try:
                    await resp.read()
                except Exception:
                    self._log.warning(
                        "takeover_response_body_unreadable", uid=track.uid
                    )
                result = classify_http_status(resp.status)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            result = TakeoverResult.FAILED_TRANSPORT
            error = f"timeout:{exc}"
        except aiohttp.ClientConnectionError as exc:
            result = TakeoverResult.FAILED_TRANSPORT
            error = f"connection:{exc}"
        except aiohttp.ClientError as exc:
            result = TakeoverResult.FAILED_TRANSPORT
            error = f"client_error:{exc}"

        latency_ms = round((time.monotonic() - t0) * 1000.0, 3)
        kw: dict[str, Any] = {
            "uid": track.uid,
            "http_status": http_status,
            "result": result.value,
            "latency_ms": latency_ms,
        }
        if error is not None:
            kw["error"] = error
        self._log.info("takeover_response", **kw)
        return result
