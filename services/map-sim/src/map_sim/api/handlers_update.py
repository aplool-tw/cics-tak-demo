"""POST /objects/update handler (User Story 1)."""
from __future__ import annotations

import json

from aiohttp import web
from pydantic import ValidationError

from ..logging import get_logger
from ..models.request import FIELDS_8, UpdatePayload
from .errors import (
    REASON_INVALID_JSON,
    error_response,
    reason_invalid_type,
    reason_missing_field,
)

log = get_logger("map_sim.update")


def _map_validation_error(exc: ValidationError) -> str:
    """Convert first pydantic ValidationError into stable reason string.

    Rules:
    * missing required (type=="missing") → "missing required field: <loc>"
    * otherwise (type error / empty string / bad timestamp) → "invalid type: <loc>"
    """
    errors = exc.errors()
    first = errors[0] if errors else {"type": "missing", "loc": ("unknown",)}
    # pick field name (first loc segment that's a str, ignoring int indexes)
    loc = first.get("loc") or ()
    name = next((seg for seg in loc if isinstance(seg, str)), "unknown")
    etype = first.get("type", "")
    if etype == "missing":
        return reason_missing_field(name)
    return reason_invalid_type(name)


async def update(request: web.Request) -> web.Response:
    raw_bytes = await request.read()
    try:
        raw = json.loads(raw_bytes) if raw_bytes else None
    except (json.JSONDecodeError, ValueError):
        log.warning("update.rejected", reason=REASON_INVALID_JSON)
        return error_response(REASON_INVALID_JSON)

    if not isinstance(raw, dict):
        log.warning("update.rejected", reason=REASON_INVALID_JSON)
        return error_response(REASON_INVALID_JSON)

    try:
        payload = UpdatePayload.model_validate(raw)
    except ValidationError as exc:
        reason = _map_validation_error(exc)
        log.warning("update.rejected", reason=reason)
        return error_response(reason)

    registry = request.app["registry"]
    data = payload.model_dump(include=set(FIELDS_8))
    registered_at = await registry.update(**data)
    registered_at_iso = registered_at.isoformat().replace("+00:00", "Z")

    log.debug("update.ok", drone_id=payload.drone_id, registered_at=registered_at_iso)
    return web.json_response(
        {
            "status": "updated",
            "drone_id": payload.drone_id,
            "registered_at": registered_at_iso,
        },
        status=200,
    )
