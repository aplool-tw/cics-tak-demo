from __future__ import annotations

import pytest


def _make_cot(
    uid: str,
    cot_type: str,
    time_str: str,
    stale_str: str,
    lat: float = 25.059800,
    lon: float = 121.565400,
    hae: float = 101.0,
    speed: float = 12.5,
    course: float = 45.0,
    remarks: str = "",
) -> str:
    return (
        f'<event version="2.0" uid="{uid}" type="{cot_type}" '
        f'time="{time_str}" start="{time_str}" stale="{stale_str}" how="m-g">'
        f'<point lat="{lat}" lon="{lon}" hae="{hae}" ce="10.0" le="5.0"/>'
        f"<detail>"
        f'<contact callsign="{uid}"/>'
        f"<remarks>{remarks}</remarks>"
        f'<track speed="{speed}" course="{course}"/>'
        f"</detail>"
        f"</event>"
    )


# Base timestamps: time + delta = stale
_T_BASE = "2026-04-29T11:00:00.000Z"
_T_11S = "2026-04-29T11:00:11.000Z"  # +11s
_T_30S = "2026-04-29T11:00:30.000Z"  # +30s
_T_0S = _T_BASE  # +0s (Lost)


@pytest.fixture
def cot_echo_active() -> str:
    return _make_cot(
        uid="ECHO-TRK-001",
        cot_type="a-u-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_11S,
        remarks="Source: ECHOSHIELD | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_echo_lost() -> str:
    return _make_cot(
        uid="ECHO-TRK-001",
        cot_type="a-u-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_0S,
        remarks="Source: ECHOSHIELD | Speed: 0.0m/s | Alt: 101m",
    )


@pytest.fixture
def cot_sentrycs_detected() -> str:
    return _make_cot(
        uid="SENTRYCS-DRN-001",
        cot_type="a-u-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_11S,
        remarks="Source: SENTRYCS | Model: DJI Mavic 3 | Status: DETECTED | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_sentrycs_mitigating() -> str:
    return _make_cot(
        uid="SENTRYCS-DRN-001",
        cot_type="a-u-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_11S,
        remarks="Source: SENTRYCS | Model: DJI Mavic 3 | Status: MITIGATING | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_sentrycs_neutralized() -> str:
    return _make_cot(
        uid="SENTRYCS-DRN-001",
        cot_type="a-u-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_30S,
        remarks="Source: SENTRYCS | Model: DJI Mavic 3 | Status: NEUTRALIZED | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_fused_detected() -> str:
    return _make_cot(
        uid="FUSED-DRN-001",
        cot_type="a-h-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_11S,
        remarks="Source: FUSED | Model: DJI Mavic 3 | Status: DETECTED | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_fused_mitigating() -> str:
    return _make_cot(
        uid="FUSED-DRN-001",
        cot_type="a-h-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_11S,
        remarks="Source: FUSED | Model: DJI Mavic 3 | Status: MITIGATING | Speed: 12.5m/s | Alt: 101m",
    )


@pytest.fixture
def cot_fused_neutralized() -> str:
    return _make_cot(
        uid="FUSED-DRN-001",
        cot_type="a-h-A-M-F-Q-r",
        time_str=_T_BASE,
        stale_str=_T_30S,
        remarks="Source: FUSED | Model: DJI Mavic 3 | Status: NEUTRALIZED | Speed: 12.5m/s | Alt: 101m",
    )
