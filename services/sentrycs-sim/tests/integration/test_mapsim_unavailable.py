"""T034 [US1]: Map Sim unavailable → registry preserved, API keeps serving."""

from __future__ import annotations

from contextlib import asynccontextmanager

from aiohttp.test_utils import TestClient, TestServer

from tests.integration.helpers import driver
from sentrycs_sim.api import build_app
from sentrycs_sim.models import DetectionStatus


def _obj(uid: str, status: str = "FLYING_NORMAL"):
    return {
        "drone_id": uid,
        "lat": 25.04,
        "lon": 121.57,
        "alt_m": 100.0,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": status,
        "is_lost": False,
    }


@asynccontextmanager
async def _api(registry, reachable_fn):
    app = build_app(registry=registry, start_monotonic=0.0, get_map_sim_reachable=reachable_fn)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


async def test_mapsim_down_preserves_state(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 5.0,
                    "neutralized_at_s": 30.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )

    map_sim_stub.set_objects([_obj("TRK-001")])

    async with driver(cfg) as d:
        # t=0..6: detect + takeover → MITIGATING
        await d.tick()
        for _ in range(6):
            await d.tick(advance_s=1.0)
        assert d.registry.get_track("TRK-001").status is DetectionStatus.MITIGATING
        # API still served during outage
        async with _api(d.registry, lambda: d.runner.map_sim_reachable) as client:
            h = await (await client.get("/health")).json()
            assert h["status"] == "ok"
            body = await (await client.get("/detections")).json()
            assert body[0]["uid"] == "TRK-001"

            # Map Sim goes down (503); injected fake-sleep avoids wall-clock waits.
            map_sim_stub.status = 503
            d.runner._sleep = _fast_sleep  # type: ignore[assignment]
            await d.tick(advance_s=1.0)
            # map_sim_reachable must now be False
            h = await (await client.get("/health")).json()
            assert h["map_sim_reachable"] is False
            # But we still return 200 and the registry contents
            body = await (await client.get("/detections")).json()
            assert body[0]["detection_status"] == "MITIGATING"


async def _fast_sleep(_s: float) -> None:  # noqa: N802
    return None
