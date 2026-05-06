"""SP/HP/ring CoT generator and periodic broadcaster (Feature 014)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from cot_gateway.config import BroadcastConfig
from cot_gateway.logging import get_logger

SP_UID = "CICS-014-SP"
HP_UID = "CICS-014-HP"


def _iso_ms(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ring_uid(radius_m: float) -> str:
    return f"CICS-014-SP-RING-{int(radius_m)}"


def generate_sp_cot(cfg: BroadcastConfig, now: Optional[datetime] = None) -> str:
    """Generate a CoT XML string for the Strategic Point (SP) marker."""
    if now is None:
        now = datetime.now(timezone.utc)
    t = _iso_ms(now)
    stale = _iso_ms(now + timedelta(seconds=2 * cfg.interval_s))
    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": SP_UID,
            "type": "a-f-G-U-C",
            "time": t,
            "start": t,
            "stale": stale,
            "how": "h-e",
        },
    )
    ET.SubElement(
        event,
        "point",
        {
            "lat": f"{cfg.sp_lat:.6f}",
            "lon": f"{cfg.sp_lon:.6f}",
            "hae": f"{cfg.sp_alt_m:.1f}",
            "ce": "10.0",
            "le": "5.0",
        },
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", {"callsign": cfg.sp_name})
    remarks = ET.SubElement(detail, "remarks")
    remarks.text = "Site: SP"
    return ET.tostring(event, encoding="unicode")


def generate_hp_cot(cfg: BroadcastConfig, now: Optional[datetime] = None) -> str:
    """Generate a CoT XML string for the Holding Point (HP) marker."""
    if now is None:
        now = datetime.now(timezone.utc)
    t = _iso_ms(now)
    stale = _iso_ms(now + timedelta(seconds=2 * cfg.interval_s))
    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": HP_UID,
            "type": "a-f-G-U-C",
            "time": t,
            "start": t,
            "stale": stale,
            "how": "h-e",
        },
    )
    ET.SubElement(
        event,
        "point",
        {
            "lat": f"{cfg.hp_lat:.6f}",
            "lon": f"{cfg.hp_lon:.6f}",
            "hae": f"{cfg.hp_alt_m:.1f}",
            "ce": "10.0",
            "le": "5.0",
        },
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", {"callsign": cfg.hp_name})
    remarks = ET.SubElement(detail, "remarks")
    remarks.text = "Site: HP"
    return ET.tostring(event, encoding="unicode")


def generate_ring_cot(cfg: BroadcastConfig, radius_m: float, now: Optional[datetime] = None) -> str:
    """Generate a CoT XML string for a defense ring overlay centered on SP."""
    if now is None:
        now = datetime.now(timezone.utc)
    t = _iso_ms(now)
    stale = _iso_ms(now + timedelta(seconds=2 * cfg.interval_s))
    uid = _ring_uid(radius_m)
    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": uid,
            "type": "u-d-c",
            "time": t,
            "start": t,
            "stale": stale,
            "how": "h-e",
        },
    )
    ET.SubElement(
        event,
        "point",
        {
            "lat": f"{cfg.sp_lat:.6f}",
            "lon": f"{cfg.sp_lon:.6f}",
            "hae": f"{cfg.sp_alt_m:.1f}",
            "ce": "10.0",
            "le": "5.0",
        },
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", {"callsign": f"{cfg.sp_name} \u2014 {int(radius_m)}m ring"})
    shape = ET.SubElement(detail, "shape")
    ET.SubElement(
        shape,
        "ellipse",
        {
            "minor": str(radius_m),
            "major": str(radius_m),
            "angle": "0",
        },
    )
    remarks = ET.SubElement(detail, "remarks")
    remarks.text = f"Defense ring: {int(radius_m)}m"
    return ET.tostring(event, encoding="unicode")


class SitesBroadcaster:
    """Periodically enqueues SP, HP, and ring CoT messages into the CoT queue."""

    def __init__(
        self,
        cfg: BroadcastConfig,
        cot_queue: asyncio.Queue,
        stop_event: asyncio.Event,
    ) -> None:
        self._cfg = cfg
        self._queue = cot_queue
        self._stop = stop_event
        self._log = get_logger("cot_gateway.broadcast")

    def _broadcast_once(self, now: datetime) -> None:
        messages = [
            generate_sp_cot(self._cfg, now),
            generate_hp_cot(self._cfg, now),
        ]
        for r in self._cfg.defense_rings_m:
            messages.append(generate_ring_cot(self._cfg, float(r), now))
        for msg in messages:
            try:
                self._queue.put_nowait(msg)
            except asyncio.QueueFull:
                self._log.warning("broadcast_queue_full", uid=SP_UID)
        self._log.info(
            "broadcast_cycle",
            sp_uid=SP_UID,
            hp_uid=HP_UID,
            ring_count=len(self._cfg.defense_rings_m),
            interval_s=self._cfg.interval_s,
        )

    async def run(self) -> None:
        """Emit immediately, then repeat every interval_s until stop_event is set."""
        self._broadcast_once(datetime.now(timezone.utc))
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._cfg.interval_s)
                return
            except asyncio.TimeoutError:
                pass
            self._broadcast_once(datetime.now(timezone.utc))
