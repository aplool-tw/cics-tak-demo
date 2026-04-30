"""Unit tests for tak_client_sim.web_server."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from aiohttp.test_utils import TestClient, TestServer

from tak_client_sim.cot_store import CotStore
from tak_client_sim.models import CotEvent
from tak_client_sim.web_server import _build_app, _build_map_html, _event_to_dict, _fmt_dt

# ── helpers ───────────────────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _make_event(
    uid: str = "ECHO-TRK-E01",
    source: str = "ECHO",
    color: str = "GREY",
    lat: float = 24.725806,
    lon: float = 121.033750,
    hae: float = 100.0,
    speed: float = 35.0,
    course: float = 180.0,
    remarks: str = "Active",
    stale_offset_s: float = 30.0,
) -> CotEvent:
    """Create a fresh CotEvent with stale time relative to now."""
    now = _now_utc()
    return CotEvent(
        uid=uid,
        cot_type="a-u-A-M-F-Q-r",
        source=source,  # type: ignore[arg-type]
        color=color,  # type: ignore[arg-type]
        time=now,
        stale=now + timedelta(seconds=stale_offset_s),
        delta_s=int(stale_offset_s),
        lat=lat,
        lon=lon,
        hae=hae,
        speed=speed,
        course=course,
        remarks=remarks,
        raw_xml="<event/>",
    )


def _make_client() -> tuple[CotStore, TestClient]:
    """Create a test client backed by a fresh CotStore."""
    store = CotStore()
    html = _build_map_html(24.725806, 121.033750, 24.725806, 121.071889)
    app = _build_app(html, store)
    return store, TestClient(TestServer(app))  # type: ignore[arg-type]


# ── _build_map_html ────────────────────────────────────────────────────────


def test_build_map_html_injects_sp_lat() -> None:
    html = _build_map_html(24.725806, 121.033750, 24.725806, 121.071889)
    assert "24.725806" in html


def test_build_map_html_injects_sp_lon() -> None:
    html = _build_map_html(24.725806, 121.033750, 24.725806, 121.071889)
    # Python strips trailing zeros: str(121.033750) → '121.03375'
    assert "121.03375" in html


def test_build_map_html_injects_hp_lon() -> None:
    html = _build_map_html(24.725806, 121.033750, 24.725806, 121.071889)
    assert "121.071889" in html


def test_build_map_html_no_placeholders() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)
    assert "__SP_LAT__" not in html
    assert "__SP_LON__" not in html
    assert "__HP_LAT__" not in html
    assert "__HP_LON__" not in html


def test_build_map_html_contains_sp_hp_markers() -> None:
    html = _build_map_html(24.725806, 121.033750, 24.725806, 121.071889)
    assert "SP" in html
    assert "HP" in html
    assert "1 km" in html
    assert "2 km" in html
    assert "3 km" in html


# ── _fmt_dt ───────────────────────────────────────────────────────────────


def test_fmt_dt_iso_format() -> None:
    dt = datetime(2026, 4, 28, 1, 42, 41, 123000, tzinfo=timezone.utc)
    assert _fmt_dt(dt) == "2026-04-28T01:42:41.123Z"


def test_fmt_dt_zero_millis() -> None:
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert _fmt_dt(dt) == "2026-01-01T00:00:00.000Z"


# ── _event_to_dict ────────────────────────────────────────────────────────


def test_event_to_dict_fields() -> None:
    now = _now_utc()
    stale = now + timedelta(seconds=11)
    query_time = now + timedelta(seconds=5)
    evt = CotEvent(
        uid="ECHO-TRK-E01",
        cot_type="a-u-A-M-F-Q-r",
        source="ECHO",
        color="GREY",  # type: ignore[arg-type]
        time=now,
        stale=stale,
        delta_s=11,
        lat=24.725806,
        lon=121.033750,
        hae=100.0,
        speed=35.0,
        course=180.0,
        remarks="Active",
        raw_xml="<e/>",
    )
    d = _event_to_dict(evt, query_time)
    assert d["uid"] == "ECHO-TRK-E01"
    assert d["source"] == "ECHO"
    assert d["color"] == "GREY"
    assert d["lat"] == 24.725806
    assert d["lon"] == 121.033750
    assert d["is_stale"] is False
    assert d["stale_in_s"] == 6  # stale=now+11, query=now+5 → 6s remaining


def test_event_to_dict_stale_flag() -> None:
    now = _now_utc()
    stale_at = now - timedelta(seconds=5)
    evt = CotEvent(
        uid="OLD",
        cot_type="a-u-A-M-F-Q-r",
        source="ECHO",
        color="GREY",  # type: ignore[arg-type]
        time=now - timedelta(seconds=20),
        stale=stale_at,
        delta_s=5,
        lat=24.7,
        lon=121.0,
        hae=100.0,
        speed=0.0,
        course=0.0,
        remarks="",
        raw_xml="<e/>",
    )
    d = _event_to_dict(evt, now)
    assert d["is_stale"] is True
    assert d["stale_in_s"] < 0


# ── HTTP endpoints ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_map_endpoint_returns_html() -> None:
    _, client = _make_client()
    async with client:
        resp = await client.get("/map")
        assert resp.status == 200
        assert resp.content_type == "text/html"
        text = await resp.text()
        assert "TAK CLIENT SIM" in text
        assert "SP" in text


@pytest.mark.asyncio
async def test_events_endpoint_empty() -> None:
    _, client = _make_client()
    async with client:
        resp = await client.get("/events")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 0
        assert data["events"] == []


@pytest.mark.asyncio
async def test_events_endpoint_no_cache_header() -> None:
    _, client = _make_client()
    async with client:
        resp = await client.get("/events")
        assert "no-store" in resp.headers.get("Cache-Control", "")


@pytest.mark.asyncio
async def test_events_endpoint_with_event() -> None:
    store, client = _make_client()
    evt = _make_event()
    await store.upsert(evt)
    async with client:
        resp = await client.get("/events")
        data = await resp.json()
        assert data["count"] == 1
        assert data["events"][0]["uid"] == "ECHO-TRK-E01"
        assert data["events"][0]["source"] == "ECHO"
        assert data["events"][0]["lat"] == pytest.approx(24.725806)


@pytest.mark.asyncio
async def test_events_endpoint_multiple_sources() -> None:
    store, client = _make_client()
    await store.upsert(_make_event(uid="ECHO-TRK-E01", source="ECHO"))
    await store.upsert(_make_event(uid="SENTRYCS-TRK-E01", source="SENTRYCS", color="RED"))
    await store.upsert(_make_event(uid="FUSED-TRK-E01", source="FUSED", color="RED"))
    async with client:
        resp = await client.get("/events")
        data = await resp.json()
        assert data["count"] == 3
        sources = {e["uid"]: e["source"] for e in data["events"]}
        assert sources["ECHO-TRK-E01"] == "ECHO"
        assert sources["SENTRYCS-TRK-E01"] == "SENTRYCS"
        assert sources["FUSED-TRK-E01"] == "FUSED"


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    _, client = _make_client()
    async with client:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["tracked"] == 0


@pytest.mark.asyncio
async def test_health_endpoint_no_cache_header() -> None:
    _, client = _make_client()
    async with client:
        resp = await client.get("/health")
        assert "no-store" in resp.headers.get("Cache-Control", "")


@pytest.mark.asyncio
async def test_health_tracked_count() -> None:
    store, client = _make_client()
    await store.upsert(_make_event(uid="A"))
    await store.upsert(_make_event(uid="B"))
    async with client:
        resp = await client.get("/health")
        data = await resp.json()
        assert data["tracked"] == 2


@pytest.mark.asyncio
async def test_events_endpoint_stale_eviction() -> None:
    store, client = _make_client()
    # already_expired has stale 10 minutes in the past, well beyond _STALE_GRACE_S=60
    already_expired_stale = _now_utc() - timedelta(minutes=10)
    stale_evt = CotEvent(
        uid="OLD-TRK",
        cot_type="a-u-A-M-F-Q-r",
        source="ECHO",
        color="GREY",  # type: ignore[arg-type]
        time=already_expired_stale - timedelta(seconds=11),
        stale=already_expired_stale,
        delta_s=11,
        lat=24.7,
        lon=121.0,
        hae=100.0,
        speed=0.0,
        course=0.0,
        remarks="",
        raw_xml="<e/>",
    )
    fresh_evt = _make_event(uid="FRESH-TRK")
    await store.upsert(stale_evt)
    await store.upsert(fresh_evt)
    async with client:
        resp = await client.get("/events")
        data = await resp.json()
        uids = {e["uid"] for e in data["events"]}
        assert "OLD-TRK" not in uids
        assert "FRESH-TRK" in uids
