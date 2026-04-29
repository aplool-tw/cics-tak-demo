from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import structlog

from tak_client_sim.models import ColorLabel, CotEvent, SourceLabel

log = structlog.get_logger(__name__)


def _parse_iso8601(s: str) -> datetime | None:
    """Parse ISO 8601 UTC timestamp, handling both 'Z' and '+00:00' suffixes."""
    try:
        normalized = s.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return None


def _derive_source(uid: str) -> SourceLabel:
    if uid.startswith("ECHO-"):
        return "ECHO"
    if uid.startswith("SENTRYCS-"):
        return "SENTRYCS"
    if uid.startswith("FUSED-"):
        return "FUSED"
    return "UNKNOWN"


def _derive_color(cot_type: str) -> ColorLabel:
    if cot_type.startswith("a-u-"):
        return "GREY"
    if cot_type.startswith("a-h-"):
        return "RED"
    return "UNKNOWN"


def parse_cot_xml(raw: str) -> CotEvent | None:
    """Parse a CoT 2.0 XML string into a CotEvent. Returns None on any parse failure."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log.warning("cot_parse_error", raw_preview=raw[:200], error=str(exc))
        return None

    uid = root.get("uid")
    cot_type = root.get("type")
    if not uid or not cot_type:
        log.warning("cot_parse_error", raw_preview=raw[:200], error="missing uid or type")
        return None

    now_utc = datetime.now(timezone.utc)

    time_str = root.get("time", "")
    stale_str = root.get("stale", "")
    time_dt = _parse_iso8601(time_str) or now_utc
    stale_dt = _parse_iso8601(stale_str) or now_utc

    if time_str and not _parse_iso8601(time_str):
        log.warning("cot_parse_error", raw_preview=raw[:200], error="invalid time field")
    if stale_str and not _parse_iso8601(stale_str):
        log.warning("cot_parse_error", raw_preview=raw[:200], error="invalid stale field")

    delta_s = max(0, round((stale_dt - time_dt).total_seconds()))

    point = root.find("point")
    lat = float(point.get("lat", "0.0")) if point is not None else 0.0
    lon = float(point.get("lon", "0.0")) if point is not None else 0.0
    hae = float(point.get("hae", "0.0")) if point is not None else 0.0

    detail = root.find("detail")
    track = detail.find("track") if detail is not None else None
    speed = float(track.get("speed", "0.0")) if track is not None else 0.0
    course = float(track.get("course", "0.0")) if track is not None else 0.0

    remarks_el = detail.find("remarks") if detail is not None else None
    remarks = (remarks_el.text or "") if remarks_el is not None else ""

    return CotEvent(
        uid=uid,
        cot_type=cot_type,
        source=_derive_source(uid),
        color=_derive_color(cot_type),
        time=time_dt,
        stale=stale_dt,
        delta_s=delta_s,
        lat=lat,
        lon=lon,
        hae=hae,
        speed=speed,
        course=course,
        remarks=remarks,
        raw_xml=raw,
    )
