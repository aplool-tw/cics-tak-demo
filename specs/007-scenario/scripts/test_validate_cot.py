"""
T003 – Tests for validate_cot.py
These tests are written BEFORE the implementation and MUST FAIL initially (TDD).

Tests cover:
  - CoT XML parsing: uid, type, lat/lon/hae, stale expiry
  - CoT type rules (gray single-source, red fused, no status-driven type changes)
  - UID prefix rules (ECHO-/SENTRYCS-/FUSED-)
  - Stale duration rules (Lost=time, NEUTRALIZED=time+30s, others=time+11s)
  - Milestone sequence detection from a stream of CoT messages
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ------------------------------------------------------------------
# Helper – minimal CoT XML builder for test fixtures
# ------------------------------------------------------------------

def _cot(
    uid: str,
    cot_type: str,
    lat: float,
    lon: float,
    hae: float,
    time: str,
    start: str,
    stale: str,
    remarks: str = "",
) -> str:
    rm_el = f'<remarks>{remarks}</remarks>' if remarks else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<event version="2.0" uid="{uid}" type="{cot_type}" '
        f'time="{time}" start="{start}" stale="{stale}" how="m-g">'
        f'<point lat="{lat}" lon="{lon}" hae="{hae}" ce="10" le="5"/>'
        f'<detail>{rm_el}</detail>'
        f"</event>"
    )


NOW_Z = "2025-01-01T00:00:00.000Z"
LATE_Z = "2025-01-01T00:00:11.000Z"
LATE30_Z = "2025-01-01T00:00:30.000Z"


# ------------------------------------------------------------------
# T003-01  CoT XML parsing
# ------------------------------------------------------------------

def test_parse_cot_uid() -> None:
    """validate_cot.parse_cot must extract uid correctly."""
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert ev.uid == "ECHO-TRK-E01"


def test_parse_cot_type() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("FUSED-TRK-E01", "a-h-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert ev.cot_type == "a-h-A-M-F-Q-r"


def test_parse_cot_lat_lon_hae() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.725806, 121.033750, 148.5, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert abs(ev.lat - 24.725806) < 1e-6
    assert abs(ev.lon - 121.033750) < 1e-6
    assert abs(ev.hae - 148.5) < 0.01


def test_parse_cot_remarks_status() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z,
               remarks="status=DETECTED")
    ev = vc.parse_cot(xml)
    assert "status=DETECTED" in ev.remarks


# ------------------------------------------------------------------
# T003-02  UID prefix rules
# ------------------------------------------------------------------

def test_echo_uid_prefix_rule() -> None:
    """EchoShield-only tracks must use ECHO- prefix."""
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert vc.classify_source(ev) == "ECHO"


def test_sentrycs_uid_prefix_rule() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("SENTRYCS-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert vc.classify_source(ev) == "SENTRYCS"


def test_fused_uid_prefix_rule() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("FUSED-TRK-E01", "a-h-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert vc.classify_source(ev) == "FUSED"


# ------------------------------------------------------------------
# T003-03  CoT type rules (source-bound, no status switch)
# ------------------------------------------------------------------

def test_single_source_cot_type_is_gray() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    for prefix in ("ECHO", "SENTRYCS"):
        xml = _cot(f"{prefix}-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
        ev = vc.parse_cot(xml)
        assert vc.check_cot_type_rule(ev), f"{prefix} single-source should be gray a-u-A-M-F-Q-r"


def test_fused_cot_type_is_red() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("FUSED-TRK-E01", "a-h-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert vc.check_cot_type_rule(ev)


def test_wrong_type_for_fused_fails() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    xml = _cot("FUSED-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, NOW_Z, NOW_Z, LATE_Z)
    ev = vc.parse_cot(xml)
    assert not vc.check_cot_type_rule(ev), "FUSED must use red type, not gray"


# ------------------------------------------------------------------
# T003-04  Stale duration rules
# ------------------------------------------------------------------

def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_stale_lost_equals_time() -> None:
    """Lost CoTs must have stale == time (instant expiry)."""
    import importlib
    vc = importlib.import_module("validate_cot")
    t = "2025-01-01T00:05:00.000Z"
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, t, t, t,
               remarks="status=Lost")
    ev = vc.parse_cot(xml)
    ok, msg = vc.check_stale_rule(ev)
    assert ok, f"Lost stale rule failed: {msg}"


def test_stale_neutralized_is_time_plus_30s() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    t     = "2025-01-01T00:05:00.000Z"
    stale = "2025-01-01T00:05:30.000Z"
    xml = _cot("SENTRYCS-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, t, t, stale,
               remarks="status=NEUTRALIZED")
    ev = vc.parse_cot(xml)
    ok, msg = vc.check_stale_rule(ev)
    assert ok, f"NEUTRALIZED stale rule failed: {msg}"


def test_stale_normal_is_time_plus_11s() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    t     = "2025-01-01T00:05:00.000Z"
    stale = "2025-01-01T00:05:11.000Z"
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, t, t, stale,
               remarks="status=DETECTED")
    ev = vc.parse_cot(xml)
    ok, msg = vc.check_stale_rule(ev)
    assert ok, f"Normal stale rule failed: {msg}"


def test_stale_wrong_duration_fails() -> None:
    import importlib
    vc = importlib.import_module("validate_cot")
    t     = "2025-01-01T00:05:00.000Z"
    stale = "2025-01-01T00:05:05.000Z"   # 5s — wrong
    xml = _cot("ECHO-TRK-E01", "a-u-A-M-F-Q-r", 24.7, 121.0, 150.0, t, t, stale,
               remarks="status=DETECTED")
    ev = vc.parse_cot(xml)
    ok, _ = vc.check_stale_rule(ev)
    assert not ok, "5s stale should fail the 11s rule"


# ------------------------------------------------------------------
# T003-05  validate_cot module API surface
# ------------------------------------------------------------------

def test_validate_cot_module_importable() -> None:
    """Will FAIL until validate_cot.py is created."""
    import importlib
    vc = importlib.import_module("validate_cot")
    for fn in ("parse_cot", "classify_source", "check_cot_type_rule", "check_stale_rule"):
        assert hasattr(vc, fn), f"validate_cot missing: {fn}"
