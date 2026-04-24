"""Contract tests for POST /command/takeover (US2 Acceptance 1–8).

The app runs in-process via aiohttp TestClient. MapClient is replaced with a
no-op stub so that /command/takeover is testable without booting the main loop.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from uds.api.server import create_app
from uds.config import Settings
from uds.models.flight_state import FlightState
from uds.scenario.loader import build_initial_drones, load_scenario


class StubMapClient:
    """Records any enqueue/finalize so tests can assert zero side effects."""

    def __init__(self) -> None:
        self.enqueued: list = []
        self.finalized: list = []

    def enqueue(self, drone) -> None:
        self.enqueued.append(drone.drone_id)

    def finalize_landed(self, drone_id: str) -> None:
        self.finalized.append(drone_id)


@pytest.fixture
async def app_env(scenario_tmpfile, simple_scenario_yaml):
    """Return (client, drones, stub_map) for contract tests. debug=False."""
    path = scenario_tmpfile(simple_scenario_yaml)
    scenario = load_scenario(str(path))
    settings = Settings.from_args_and_scenario(
        scenario_path=str(path),
        cli_api_port=None,
        cli_hz=None,
        map_sim_url="http://127.0.0.1:9",
        verbose=False,
        debug=False,
        scenario=scenario,
    )
    drones = build_initial_drones(scenario)
    # Pre-seed the drone to FLYING_NORMAL unless a specific test overrides.
    drones["TRK-001"].flight_state = FlightState.FLYING_NORMAL
    stub = StubMapClient()
    app = create_app(settings=settings, drones=drones, map_client=stub)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    try:
        yield client, drones, stub
    finally:
        await server.close()


async def _post_takeover(client: TestClient, body) -> tuple[int, dict]:
    resp = await client.post(
        "/command/takeover",
        data=body if isinstance(body, (str, bytes)) else json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    txt = await resp.text()
    try:
        j = json.loads(txt)
    except Exception:
        j = {"_raw": txt}
    return resp.status, j


# ---------- T011 ----------
async def test_accept_flying_normal(app_env):
    client, drones, stub = app_env
    status, body = await _post_takeover(
        client,
        {
            "drone_id": "TRK-001",
            "target_lat": 25.0250,
            "target_lon": 121.5654,
            "target_alt_m": 0.0,
            "descent_speed_ms": 3.0,
        },
    )
    assert status == 200, body
    assert body["status"] == "accepted"
    assert body["drone_id"] == "TRK-001"
    assert body["previous_state"] == "FLYING_NORMAL"
    assert body["new_state"] == "MITIGATING_TAKEOVER"
    assert isinstance(body["estimated_landing_s"], (int, float))
    assert body["estimated_landing_s"] >= 0
    assert drones["TRK-001"].flight_state == FlightState.MITIGATING_TAKEOVER


# ---------- T012 ----------
async def test_unknown_drone_id_400(app_env):
    client, drones, stub = app_env
    prior = drones["TRK-001"].flight_state
    status, body = await _post_takeover(
        client,
        {"drone_id": "TRK-999", "target_lat": 0, "target_lon": 0, "target_alt_m": 0},
    )
    assert status == 400
    assert body == {"status": "error", "reason": "drone_id not found"}
    assert drones["TRK-001"].flight_state == prior
    assert stub.enqueued == []


# ---------- T013 ----------
async def test_landed_drone_400(app_env):
    client, drones, stub = app_env
    drones["TRK-001"].flight_state = FlightState.LANDED
    status, body = await _post_takeover(
        client,
        {"drone_id": "TRK-001", "target_lat": 0, "target_lon": 0, "target_alt_m": 0},
    )
    assert status == 400
    assert body["reason"] == "already landed"
    assert drones["TRK-001"].flight_state == FlightState.LANDED


# ---------- T014 ----------
async def test_idle_drone_409(app_env):
    client, drones, stub = app_env
    drones["TRK-001"].flight_state = FlightState.IDLE
    status, body = await _post_takeover(
        client,
        {"drone_id": "TRK-001", "target_lat": 0, "target_lon": 0, "target_alt_m": 0},
    )
    assert status == 409
    assert body == {"status": "error", "reason": "drone not airborne"}


# ---------- T015 ----------
@pytest.mark.parametrize(
    "body,expect_reason",
    [
        (
            {"drone_id": "TRK-001", "target_lat": 999, "target_lon": 0, "target_alt_m": 0},
            "invalid coordinates",
        ),
        (
            {"drone_id": "TRK-001", "target_lat": 0, "target_lon": -181, "target_alt_m": 0},
            "invalid coordinates",
        ),
        (
            {"drone_id": "TRK-001", "target_lon": 0, "target_alt_m": 0},
            "missing field: target_lat",
        ),
    ],
)
async def test_invalid_coordinates_400(app_env, body, expect_reason):
    client, drones, stub = app_env
    status, resp = await _post_takeover(client, body)
    assert status == 400
    assert resp["reason"] == expect_reason


# ---------- T016 ----------
@pytest.mark.parametrize(
    "body",
    [
        {"drone_id": "TRK-001", "target_lat": 0, "target_lon": 0, "target_alt_m": -1},
        {"drone_id": "TRK-001", "target_lat": 0, "target_lon": 0},
    ],
)
async def test_invalid_altitude_400(app_env, body):
    client, drones, stub = app_env
    status, resp = await _post_takeover(client, body)
    assert status == 400
    assert resp["reason"] == "invalid altitude"


# ---------- T017 ----------
async def test_consecutive_takeover_overwrites(app_env):
    client, drones, stub = app_env
    # 1st takeover
    status, body1 = await _post_takeover(
        client,
        {
            "drone_id": "TRK-001",
            "target_lat": 25.0,
            "target_lon": 121.5,
            "target_alt_m": 5.0,
            "descent_speed_ms": 3.0,
        },
    )
    assert status == 200
    assert drones["TRK-001"].flight_state == FlightState.MITIGATING_TAKEOVER
    # 2nd takeover (overwrite) - different target
    status2, body2 = await _post_takeover(
        client,
        {
            "drone_id": "TRK-001",
            "target_lat": 24.9,
            "target_lon": 121.4,
            "target_alt_m": 0.0,
            "descent_speed_ms": 5.0,
        },
    )
    assert status2 == 200
    assert body2["status"] == "accepted"
    # No overwrite flag leaks in response
    forbidden_keys = {"overwrite_flag", "overwrite_count", "overwritten", "is_overwrite"}
    assert forbidden_keys.isdisjoint(set(body2.keys()))
    # takeover_cmd holds *new* values
    tc = drones["TRK-001"].takeover_cmd
    assert tc is not None
    assert tc.target_lat == pytest.approx(24.9)
    assert tc.target_lon == pytest.approx(121.4)
    assert tc.target_alt_m == pytest.approx(0.0)
    assert tc.descent_speed_ms == pytest.approx(5.0)


# ---------- T018 ----------
async def test_debug_endpoints_404_without_flag(app_env):
    client, drones, stub = app_env
    resp1 = await client.get("/status/TRK-001")
    resp2 = await client.get("/drones")
    assert resp1.status == 404
    assert resp2.status == 404


# ---------- T019 ----------
async def test_invalid_json_body(app_env):
    client, drones, stub = app_env
    status, body = await _post_takeover(client, "{not-json")
    assert status == 400
    assert body["reason"] == "invalid json"


# ---------- T020 ----------
async def test_unknown_field_rejected(app_env):
    client, drones, stub = app_env
    status, body = await _post_takeover(
        client,
        {
            "drone_id": "TRK-001",
            "target_lat": 0,
            "target_lon": 0,
            "target_alt_m": 0,
            "bogus": 1,
        },
    )
    assert status == 400
    assert body["reason"] == "unknown field: bogus"


# ---------- T021 ----------
@pytest.mark.parametrize("speed", [0, -1])
async def test_descent_speed_zero_or_negative(app_env, speed):
    client, drones, stub = app_env
    status, body = await _post_takeover(
        client,
        {
            "drone_id": "TRK-001",
            "target_lat": 25,
            "target_lon": 121,
            "target_alt_m": 0,
            "descent_speed_ms": speed,
        },
    )
    assert status == 400
    assert body["reason"] == "invalid descent speed"


# ---------- T022 ----------
async def test_rejected_requests_have_no_side_effects(app_env):
    """All 400/409 cases must not enqueue pushes or mutate state."""
    client, drones, stub = app_env
    start_state = drones["TRK-001"].flight_state
    # Fire a bunch of invalid requests
    bad_bodies = [
        {"drone_id": "TRK-999", "target_lat": 0, "target_lon": 0, "target_alt_m": 0},
        {"drone_id": "TRK-001", "target_lat": 999, "target_lon": 0, "target_alt_m": 0},
        {"drone_id": "TRK-001", "target_lat": 0, "target_lon": 0, "target_alt_m": -1},
        {"drone_id": "TRK-001", "target_lon": 0, "target_alt_m": 0},  # missing lat
    ]
    for b in bad_bodies:
        status, _ = await _post_takeover(client, b)
        assert status in (400, 409)
    assert drones["TRK-001"].flight_state == start_state
    assert stub.enqueued == []
    assert stub.finalized == []
