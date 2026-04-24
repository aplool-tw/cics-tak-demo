"""Stable error reason strings + helper (contracts §5)."""
from __future__ import annotations

from aiohttp import web

REASON_INVALID_JSON = "invalid json"
REASON_RADIUS_NON_POSITIVE = "radius_m must be > 0"
REASON_INVALID_COORDS = "invalid coordinates"


def reason_missing_field(name: str) -> str:
    return f"missing required field: {name}"


def reason_invalid_type(name: str) -> str:
    return f"invalid type: {name}"


def reason_missing_param(name: str) -> str:
    return f"missing required parameter: {name}"


def error_response(reason: str, status: int = 400) -> web.Response:
    return web.json_response({"status": "error", "reason": reason}, status=status)
