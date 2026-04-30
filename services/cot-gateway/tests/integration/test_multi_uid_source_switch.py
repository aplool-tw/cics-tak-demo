"""FR-012-021: Integration test — multi-uid source switch stale CoT emission."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cot_gateway.config import GatewayConfig, SentrycsConfig
from cot_gateway.loop import GatewayMain
from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.web.track_store import TrackStore

NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _fused(radar_id: str = "TRK-001", rf_id: str = "DRN-001") -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.FUSED,
        track_id=f"FUSED-{rf_id}",
        radar_track_id=radar_id,
        rf_track_id=rf_id,
        correlation_id=f"FUSED-{rf_id}",
        lat=25.0598,
        lon=121.5654,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
    )


@pytest.mark.asyncio
async def test_dual_old_uids_both_stale_emitted_and_removed():
    """FR-012-021: When a FUSED track supersedes both ECHO and SENTRYCS uids,
    two stale CoTs appear before the live FUSED CoT, both old uids are removed
    from TrackStore, and both are absent from seen_uids.
    """
    cfg = GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
    )

    track_store = TrackStore()

    # Pre-populate track store with the two single-source tracks
    echo_track = UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=25.0,
        lon=121.0,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
    )
    sntr_track = UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=25.0,
        lon=121.0,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        detection_status="DETECTED",
    )
    await track_store.upsert("ECHO-TRK-001", echo_track)
    await track_store.upsert("SENTRYCS-DRN-001", sntr_track)

    # Build GatewayMain with mocked transmitter
    gw = GatewayMain(cfg, track_store=track_store)

    enqueued: list[str] = []
    gw.transmitter.enqueue = lambda xml: enqueued.append(xml)

    # Pre-fill seen_uids and prev_uid_by_entity_key as if both single-source tracks
    # had already been seen
    gw.seen_uids.add("ECHO-TRK-001")
    gw.seen_uids.add("SENTRYCS-DRN-001")
    gw.prev_uid_by_entity_key["radar:TRK-001"] = "ECHO-TRK-001"
    gw.prev_uid_by_entity_key["rf:DRN-001"] = "SENTRYCS-DRN-001"

    fused = _fused()
    await gw._emit_for_track(fused, NOW)

    # (a) Two stale CoTs appear before the live FUSED CoT — total 3
    assert len(enqueued) == 3, f"Expected 3 CoTs (2 stale + 1 live), got {len(enqueued)}"

    stale_xmls = enqueued[:2]
    live_xml = enqueued[2]

    # Both old uids must appear in the stale CoTs
    stale_uids_found: set[str] = set()
    for xml in stale_xmls:
        if "ECHO-TRK-001" in xml:
            stale_uids_found.add("ECHO-TRK-001")
        if "SENTRYCS-DRN-001" in xml:
            stale_uids_found.add("SENTRYCS-DRN-001")
    assert stale_uids_found == {
        "ECHO-TRK-001",
        "SENTRYCS-DRN-001",
    }, f"Expected both old uids in stale CoTs, got: {stale_uids_found}"

    # Live FUSED CoT must contain FUSED-DRN-001
    assert "FUSED-DRN-001" in live_xml, "Expected FUSED-DRN-001 uid in live CoT"

    # (b) Both old uids removed from TrackStore
    remaining = await track_store.get_all()
    remaining_uids = {r["uid"] for r in remaining}
    assert (
        "ECHO-TRK-001" not in remaining_uids
    ), "ECHO-TRK-001 should have been removed from TrackStore"
    assert "SENTRYCS-DRN-001" not in remaining_uids, "SENTRYCS-DRN-001 should have been removed"

    # (c) Both old uids absent from seen_uids
    assert "ECHO-TRK-001" not in gw.seen_uids
    assert "SENTRYCS-DRN-001" not in gw.seen_uids
