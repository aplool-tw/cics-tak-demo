from __future__ import annotations

from datetime import datetime, timezone

from tak_client_sim.models import CotEvent


def _fmt_ts(dt: datetime) -> str:
    """Format datetime as ISO 8601 UTC with milliseconds."""
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def is_stale_at_receive(event: CotEvent, now: datetime) -> bool:
    """Return True if the event's stale time is more than 30 seconds in the past."""
    return (now - event.stale).total_seconds() > 30


def format_event(event: CotEvent, now: datetime | None = None) -> str:
    """Format a CotEvent as a single human-readable console line."""
    if now is None:
        now = datetime.now(timezone.utc)

    stale_prefix = "[STALE] " if is_stale_at_receive(event, now) else ""
    ts = _fmt_ts(event.time)
    return (
        f"{stale_prefix}[{ts}] [{event.source}][{event.color}] {event.uid}  "
        f"{event.lat:.6f}/{event.lon:.6f}  {event.hae:.1f}m  "
        f"{event.speed:.1f}m/s  {event.course:03.0f}\u00b0  "
        f"delta_s=+{event.delta_s}  {event.remarks}"
    )


def print_event(event: CotEvent) -> None:
    """Print a formatted CoT event to stdout. The only permitted print() call."""
    print(format_event(event))
