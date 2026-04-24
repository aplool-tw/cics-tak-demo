"""GET /objects handler (User Story 2) — manual query-param parsing."""
from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from ..logging import get_logger
from ..models.drone_object import serialize
from .errors import (
    REASON_INVALID_COORDS,
    REASON_RADIUS_NON_POSITIVE,
    error_response,
    reason_invalid_type,
    reason_missing_param,
)

log = get_logger("map_sim.query")


def _parse_bool(raw: str) -> bool | None:
    s = raw.strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None


async def query(request: web.Request) -> web.Response:
    q = request.rel_url.query

    # required params
    for name in ("lat", "lon", "radius_m"):
        if name not in q:
            reason = reason_missing_param(name)
            log.warning("query.rejected", reason=reason)
            return error_response(reason)

    try:
        lat = float(q["lat"])
    except (TypeError, ValueError):
        reason = reason_invalid_type("lat")
        log.warning("query.rejected", reason=reason)
        return error_response(reason)
    try:
        lon = float(q["lon"])
    except (TypeError, ValueError):
        reason = reason_invalid_type("lon")
        log.warning("query.rejected", reason=reason)
        return error_response(reason)
    try:
        radius_m = float(q["radius_m"])
    except (TypeError, ValueError):
        reason = reason_invalid_type("radius_m")
        log.warning("query.rejected", reason=reason)
        return error_response(reason)

    # include_lost optional
    include_lost = False
    if "include_lost" in q:
        parsed = _parse_bool(q["include_lost"])
        if parsed is None:
            reason = reason_invalid_type("include_lost")
            log.warning("query.rejected", reason=reason)
            return error_response(reason)
        include_lost = parsed

    if radius_m <= 0:
        log.warning("query.rejected", reason=REASON_RADIUS_NON_POSITIVE)
        return error_response(REASON_RADIUS_NON_POSITIVE)

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        log.warning("query.rejected", reason=REASON_INVALID_COORDS)
        return error_response(REASON_INVALID_COORDS)

    registry = request.app["registry"]
    pairs = await registry.query_radius(lat, lon, radius_m, include_lost)
    now = datetime.now(timezone.utc)
    ttl_warn_s = registry.ttl_warn_s

    objects = [
        serialize(obj, ttl_warn_s, now, center_lat=lat, center_lon=lon) for obj, _ in pairs
    ]

    resp = {
        "query": {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m,
            "include_lost": include_lost,
            "timestamp": now.isoformat().replace("+00:00", "Z"),
        },
        "count": len(objects),
        "objects": objects,
    }
    log.debug("query.ok", count=len(objects), radius_m=radius_m, include_lost=include_lost)
    return web.json_response(resp, status=200)
