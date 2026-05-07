"""CoT 2.0 XML generator: UnifiedTrack → XML string (contracts/cot-xml.md)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from cot_gateway.cot.stale import compute_stale
from cot_gateway.cot.uid import uid_for
from cot_gateway.models.track import TrackSource, UnifiedTrack


def _iso_ms(dt: datetime) -> str:
    """ISO 8601 UTC with milliseconds and Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _cot_type(source: TrackSource) -> str:
    """FUSED → hostile red; others → unknown gray. Lifecycle-fixed (FR-GW-015)."""
    if source == TrackSource.FUSED:
        return "a-h-A-M-F-Q-r"
    return "a-u-A-M-F-Q-r"


def _build_remarks(track: UnifiedTrack) -> str:
    parts = [f"Source: {track.source.value}"]
    if track.drone_model is not None:
        parts.append(f"Model: {track.drone_model}")
    if track.detection_status is not None:
        parts.append(f"Status: {track.detection_status}")
    elif track.classification and track.source == TrackSource.ECHOSHIELD:
        # ECHOSHIELD-only: include classification (US1 slice calls for "remarks only contains
        # classification" — but per contracts/cot-xml.md §6 the format uses "Source:" prefix +
        # Speed/Alt always present. We keep Status line suppressed when None.)
        pass
    parts.append(f"Speed: {track.velocity_ms:.1f}m/s")
    parts.append(f"Alt: {track.alt_m:.0f}m")
    return " | ".join(parts)


def generate_cot(
    track: UnifiedTrack,
    now: Optional[datetime] = None,
    *,
    force_stale_eq_time: bool = False,
    override_uid: Optional[str] = None,
    xml_declaration: bool = False,
) -> str:
    """Render a single CoT event XML string (no trailing newline).

    Parameters
    ----------
    force_stale_eq_time : when True, produce stale == time (source-switch or TTL Lost final CoT).
    override_uid : when set, use this uid (for source-switch "final CoT" on the old uid).
    xml_declaration : when True, prepend ``<?xml version='1.0' encoding='UTF-8' standalone='yes'?>``
        for real TAK server compatibility (ATAK/WinTAK).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    t = _iso_ms(now)

    if force_stale_eq_time:
        stale_dt = now
    else:
        stale_dt = compute_stale(track, now)
    stale = _iso_ms(stale_dt)

    uid = override_uid if override_uid is not None else uid_for(track)
    ctype = _cot_type(track.source) if override_uid is None else _type_from_uid(override_uid)

    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": uid,
            "type": ctype,
            "time": t,
            "start": t,
            "stale": stale,
            "how": "m-g",
        },
    )
    ET.SubElement(
        event,
        "point",
        {
            "lat": f"{track.lat:.6f}",
            "lon": f"{track.lon:.6f}",
            "hae": f"{track.alt_m:.1f}",
            "ce": "10.0",
            "le": "5.0",
        },
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "uid", {"Droid": uid})
    ET.SubElement(detail, "contact", {"callsign": uid})
    remarks = ET.SubElement(detail, "remarks")
    remarks.text = _build_remarks(track)
    ET.SubElement(
        detail,
        "track",
        {"speed": f"{track.velocity_ms:.1f}", "course": f"{track.azimuth_deg:.1f}"},
    )

    xml_str = ET.tostring(event, encoding="unicode")
    if xml_declaration:
        return "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" + xml_str
    return xml_str


def _type_from_uid(uid: str) -> str:
    if uid.startswith("FUSED-"):
        return "a-h-A-M-F-Q-r"
    return "a-u-A-M-F-Q-r"
