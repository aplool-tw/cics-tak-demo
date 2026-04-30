"""UID source-switch detection (T033)."""

from __future__ import annotations

from datetime import datetime, timezone

from cot_gateway.cot.uid import detect_source_switch, entity_keys_for, uid_for
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _echo(track_id="TRK-001"):
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=0,
        lon=0,
        alt_m=0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
    )


def _sentrycs(rf_id="DRN-001"):
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=rf_id,
        rf_track_id=rf_id,
        lat=0,
        lon=0,
        alt_m=0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        detection_status="DETECTED",
    )


def _fused(radar_id="TRK-001", rf_id="DRN-001"):
    return UnifiedTrack(
        source=TrackSource.FUSED,
        track_id=f"FUSED-{rf_id}",
        radar_track_id=radar_id,
        rf_track_id=rf_id,
        correlation_id=f"FUSED-{rf_id}",
        lat=0,
        lon=0,
        alt_m=0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        detection_status="DETECTED",
    )


def test_uid_prefixes():
    assert uid_for(_echo()) == "ECHO-TRK-001"
    assert uid_for(_sentrycs()) == "SENTRYCS-DRN-001"
    assert uid_for(_fused()) == "FUSED-DRN-001"


def test_first_emission_no_old_uid():
    prev = {}
    old, new = detect_source_switch(_echo(), prev)
    assert old == []
    assert new == "ECHO-TRK-001"


def test_echo_to_fused_switch():
    prev = {"radar:TRK-001": "ECHO-TRK-001"}
    old, new = detect_source_switch(_fused(), prev)
    assert old == ["ECHO-TRK-001"]
    assert new == "FUSED-DRN-001"


def test_sentrycs_to_fused_switch():
    prev = {"rf:DRN-001": "SENTRYCS-DRN-001"}
    old, new = detect_source_switch(_fused(), prev)
    assert old == ["SENTRYCS-DRN-001"]
    assert new == "FUSED-DRN-001"


def test_fused_to_echo_switch():
    prev = {"radar:TRK-001": "FUSED-DRN-001"}
    old, new = detect_source_switch(_echo(), prev)
    assert old == ["FUSED-DRN-001"]
    assert new == "ECHO-TRK-001"


def test_fused_to_sentrycs_switch():
    prev = {"rf:DRN-001": "FUSED-DRN-001"}
    old, new = detect_source_switch(_sentrycs(), prev)
    assert old == ["FUSED-DRN-001"]
    assert new == "SENTRYCS-DRN-001"


def test_no_switch_when_uid_unchanged():
    prev = {"radar:TRK-001": "ECHO-TRK-001"}
    old, new = detect_source_switch(_echo(), prev)
    assert old == []
    assert new == "ECHO-TRK-001"


def test_fused_has_two_entity_keys():
    keys = entity_keys_for(_fused())
    assert "radar:TRK-001" in keys
    assert "rf:DRN-001" in keys


def test_dual_uid_both_keys_map_to_different_old_uids():
    """FR-012-019: Both radar and rf keys map to distinct old uids → both returned."""
    prev = {
        "radar:TRK-001": "ECHO-TRK-001",
        "rf:DRN-001": "SENTRYCS-DRN-001",
    }
    old, new = detect_source_switch(_fused(), prev)
    assert set(old) == {"ECHO-TRK-001", "SENTRYCS-DRN-001"}
    assert new == "FUSED-DRN-001"


def test_dedup_two_entity_keys_same_old_uid():
    """FR-012-020: Two entity keys map to the same old uid → list contains it exactly once."""
    prev = {
        "radar:TRK-001": "ECHO-TRK-001",
        "rf:DRN-001": "ECHO-TRK-001",  # same old uid under different key
    }
    old, new = detect_source_switch(_fused(), prev)
    assert old.count("ECHO-TRK-001") == 1
    assert new == "FUSED-DRN-001"
