from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tak_client_sim.formatter import format_event, is_stale_at_receive
from tak_client_sim.models import CotEvent


def _make_event(
    uid: str = "ECHO-TRK-001",
    source: str = "ECHO",
    color: str = "GREY",
    time_dt: datetime | None = None,
    stale_dt: datetime | None = None,
    delta_s: int = 11,
    lat: float = 25.06,
    lon: float = 121.5654,
    hae: float = 101.0,
    speed: float = 12.5,
    course: float = 45.0,
    remarks: str = "Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m",
) -> CotEvent:
    t = time_dt or datetime(2026, 4, 29, 11, 0, 0, 123000, tzinfo=timezone.utc)
    s = stale_dt or datetime(2026, 4, 29, 11, 0, 11, 123000, tzinfo=timezone.utc)
    return CotEvent(
        uid=uid,
        cot_type="a-u-A-M-F-Q-r",
        source=source,  # type: ignore[arg-type]
        color=color,  # type: ignore[arg-type]
        time=t,
        stale=s,
        delta_s=delta_s,
        lat=lat,
        lon=lon,
        hae=hae,
        speed=speed,
        course=course,
        remarks=remarks,
        raw_xml="<event/>",
    )


def test_format_event_normal() -> None:
    event = _make_event()
    result = format_event(event, now=datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc))
    assert "[ECHO][GREY]" in result
    assert "ECHO-TRK-001" in result
    assert "25.060000" in result
    assert "121.565400" in result
    assert "delta_s=+11" in result
    assert "Source: ECHOSHIELD" in result
    # Timestamp should include milliseconds (contain a dot before Z)
    assert ".123Z" in result


def test_format_event_stale_prefix() -> None:
    """Event whose stale is 35s in the past should get [STALE] prefix."""
    base = datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc)
    event = _make_event(
        stale_dt=base - timedelta(seconds=35),
    )
    now = base
    result = format_event(event, now=now)
    assert result.startswith("[STALE]")


def test_format_event_no_stale_prefix() -> None:
    """Event whose stale is only 25s in the past should NOT get [STALE] prefix."""
    base = datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc)
    event = _make_event(
        stale_dt=base - timedelta(seconds=25),
    )
    result = format_event(event, now=base)
    assert not result.startswith("[STALE]")


def test_format_delta_s_zero() -> None:
    """Lost event (delta_s=0) should show delta_s=+0."""
    event = _make_event(delta_s=0)
    result = format_event(event, now=datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc))
    assert "delta_s=+0" in result


def test_is_stale_at_receive_true() -> None:
    now = datetime(2026, 4, 29, 11, 0, 40, tzinfo=timezone.utc)
    event = _make_event(stale_dt=datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc))
    assert is_stale_at_receive(event, now) is True


def test_is_stale_at_receive_false() -> None:
    now = datetime(2026, 4, 29, 11, 0, 20, tzinfo=timezone.utc)
    event = _make_event(stale_dt=datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc))
    assert is_stale_at_receive(event, now) is False


def test_format_fused_red() -> None:
    event = _make_event(
        uid="FUSED-DRN-001",
        source="FUSED",
        color="RED",
        delta_s=30,
        remarks="Source: FUSED | Status: NEUTRALIZED | Speed: 3.2m/s | Alt: 95m",
    )
    result = format_event(event, now=datetime(2026, 4, 29, 11, 0, 0, tzinfo=timezone.utc))
    assert "[FUSED][RED]" in result
    assert "delta_s=+30" in result


def test_is_filtered_matching_prefix() -> None:
    from tak_client_sim.runner import _is_filtered

    assert _is_filtered("FUSED-DRN-001", "FUSED") is False


def test_is_filtered_non_matching() -> None:
    from tak_client_sim.runner import _is_filtered

    assert _is_filtered("ECHO-TRK-001", "FUSED") is True


def test_is_filtered_none_prefix() -> None:
    from tak_client_sim.runner import _is_filtered

    assert _is_filtered("ECHO-TRK-001", None) is False


def test_is_filtered_empty_string_treated_as_none() -> None:
    from tak_client_sim.runner import _is_filtered

    assert _is_filtered("ECHO-TRK-001", "") is False
