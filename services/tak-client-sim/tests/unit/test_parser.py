from __future__ import annotations

import pytest

from tak_client_sim.parser import _derive_color, _derive_source, parse_cot_xml


def _make_minimal(uid: str = "ECHO-001", cot_type: str = "a-u-X") -> str:
    t = "2026-04-29T11:00:00.000Z"
    s = "2026-04-29T11:00:11.000Z"
    return (
        f'<event version="2.0" uid="{uid}" type="{cot_type}" '
        f'time="{t}" start="{t}" stale="{s}" how="m-g">'
        f'<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        f"<detail>"
        f'<contact callsign="{uid}"/>'
        f"<remarks>test</remarks>"
        f'<track speed="5.0" course="90.0"/>'
        f"</detail>"
        f"</event>"
    )


def test_parse_happy_path() -> None:
    raw = _make_minimal()
    event = parse_cot_xml(raw)
    assert event is not None
    assert event.uid == "ECHO-001"
    assert event.cot_type == "a-u-X"
    assert event.lat == pytest.approx(25.06)
    assert event.lon == pytest.approx(121.56)
    assert event.hae == pytest.approx(100.0)
    assert event.speed == pytest.approx(5.0)
    assert event.course == pytest.approx(90.0)
    assert event.remarks == "test"
    assert event.delta_s == 11


def test_missing_point_defaults_to_zero() -> None:
    raw = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        "<detail><remarks>no point</remarks></detail>"
        "</event>"
    )
    event = parse_cot_xml(raw)
    assert event is not None
    assert event.lat == 0.0
    assert event.lon == 0.0
    assert event.hae == 0.0


def test_missing_track_defaults_to_zero() -> None:
    raw = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "<detail><remarks>no track</remarks></detail>"
        "</event>"
    )
    event = parse_cot_xml(raw)
    assert event is not None
    assert event.speed == 0.0
    assert event.course == 0.0


def test_missing_remarks_empty_string() -> None:
    raw = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        '<detail><track speed="5.0" course="0.0"/></detail>'
        "</event>"
    )
    event = parse_cot_xml(raw)
    assert event is not None
    assert event.remarks == ""


def test_invalid_xml_returns_none() -> None:
    assert parse_cot_xml("<not valid xml") is None
    assert parse_cot_xml("just plain text") is None
    assert parse_cot_xml("") is None


def test_missing_uid_returns_none() -> None:
    raw = (
        '<event version="2.0" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "</event>"
    )
    assert parse_cot_xml(raw) is None


def test_missing_type_returns_none() -> None:
    raw = (
        '<event version="2.0" uid="X-001" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "</event>"
    )
    assert parse_cot_xml(raw) is None


def test_stale_lt_time_delta_s_zero() -> None:
    # stale earlier than time → delta_s should be 0 (not negative)
    raw = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:11.000Z" start="2026-04-29T11:00:11.000Z" '
        'stale="2026-04-29T11:00:00.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "</event>"
    )
    event = parse_cot_xml(raw)
    assert event is not None
    assert event.delta_s == 0


def test_delta_s_rounds_to_int() -> None:
    # 11.4 seconds should round to 11, 11.5 to 12
    raw_11 = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.400Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "</event>"
    )
    event = parse_cot_xml(raw_11)
    assert event is not None
    assert event.delta_s == 11

    raw_12 = (
        '<event version="2.0" uid="X-001" type="a-u-X" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.500Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "</event>"
    )
    event2 = parse_cot_xml(raw_12)
    assert event2 is not None
    assert event2.delta_s == 12


@pytest.mark.parametrize(
    "uid,expected",
    [
        ("ECHO-TRK-001", "ECHO"),
        ("SENTRYCS-DRN-001", "SENTRYCS"),
        ("FUSED-DRN-001", "FUSED"),
        ("OTHER-123", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_derive_source(uid: str, expected: str) -> None:
    assert _derive_source(uid) == expected


@pytest.mark.parametrize(
    "cot_type,expected",
    [
        ("a-u-A-M-F-Q-r", "GREY"),
        ("a-h-A-M-F-Q-r", "RED"),
        ("a-f-A-M-F-Q-r", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_derive_color(cot_type: str, expected: str) -> None:
    assert _derive_color(cot_type) == expected
