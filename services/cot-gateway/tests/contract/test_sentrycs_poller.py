"""Contract: Sentrycs poller (T030)."""

from __future__ import annotations

import asyncio

import pytest

from cot_gateway.sentrycs.adapter import SentrycsAdapter

SAMPLE = {
    "uid": "DRN-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "alt_m": 101.0,
    "model": "DJI Mavic 3",
    "detection_status": "DETECTED",
    "is_landed": False,
    "operator_lat": 25.0589,
    "operator_lon": 121.5661,
    "operator_distance_m": 120.0,
    "operator_bearing_deg": 45.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "takeover_sent": False,
    "sensor_id": "SNTRX-01",
}


@pytest.mark.asyncio
async def test_empty_array_no_tracks(sentrycs_stub):
    sentrycs_stub.detections = []
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    adapter = SentrycsAdapter(
        host="127.0.0.1",
        port=sentrycs_stub.port,
        track_queue=q,
        poll_interval_s=0.1,
        stop_event=stop,
        base_url=sentrycs_stub.base_url,
    )
    task = asyncio.create_task(adapter.run())
    try:
        await asyncio.sleep(0.3)
        assert q.qsize() == 0
        assert sentrycs_stub.request_count >= 2
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_two_detections_enqueued(sentrycs_stub):
    sentrycs_stub.detections = [dict(SAMPLE), dict(SAMPLE, uid="DRN-002")]
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    adapter = SentrycsAdapter(
        host="127.0.0.1",
        port=sentrycs_stub.port,
        track_queue=q,
        poll_interval_s=0.1,
        stop_event=stop,
        base_url=sentrycs_stub.base_url,
    )
    task = asyncio.create_task(adapter.run())
    try:
        for _ in range(30):
            if q.qsize() >= 2:
                break
            await asyncio.sleep(0.05)
        tracks = []
        while not q.empty():
            tracks.append(q.get_nowait())
        assert len(tracks) >= 2
        uids = {t.rf_track_id for t in tracks}
        assert "DRN-001" in uids and "DRN-002" in uids
        # Field mapping
        t = tracks[0]
        assert t.detection_status == "DETECTED"
        assert t.drone_model == "DJI Mavic 3"
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_http_503_logged_and_continues(sentrycs_stub):
    sentrycs_stub.fail_rate = 2
    sentrycs_stub.detections = [SAMPLE]
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    adapter = SentrycsAdapter(
        host="127.0.0.1",
        port=sentrycs_stub.port,
        track_queue=q,
        poll_interval_s=0.1,
        stop_event=stop,
        base_url=sentrycs_stub.base_url,
    )
    task = asyncio.create_task(adapter.run())
    try:
        for _ in range(30):
            if q.qsize() >= 1:
                break
            await asyncio.sleep(0.05)
        assert q.qsize() >= 1
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_connection_refused_warns_does_not_raise():
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    adapter = SentrycsAdapter(
        host="127.0.0.1",
        port=1,
        track_queue=q,
        poll_interval_s=0.1,
        stop_event=stop,
        base_url="http://127.0.0.1:1",
    )
    task = asyncio.create_task(adapter.run())
    try:
        await asyncio.sleep(0.3)
        assert not task.done()  # still running, no crash
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
