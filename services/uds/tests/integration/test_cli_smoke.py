"""CLI smoke tests (T065, T066)."""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time

import pytest
import aiohttp


async def _wait_ready(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    async with aiohttp.ClientSession() as s:
        while time.monotonic() < deadline:
            try:
                async with s.post(
                    f"http://127.0.0.1:{port}/command/takeover",
                    json={"drone_id": "TRK-001", "target_lat": 25.025, "target_lon": 121.5654, "target_alt_m": 0},
                    timeout=aiohttp.ClientTimeout(total=1.0),
                ) as r:
                    # any response means server is up
                    await r.text()
                    return True
            except Exception:
                await asyncio.sleep(0.2)
    return False


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


async def _spawn(scenario_path: str, api_port: int, map_sim_url: str, *, debug: bool = False):
    env = os.environ.copy()
    # Ensure installed-uds is importable; if not, fall back to src/ dir.
    env["PYTHONPATH"] = os.path.join(_repo_root(), "src") + os.pathsep + env.get("PYTHONPATH", "")
    args = [
        sys.executable, "-m", "uds",
        "--scenario", scenario_path,
        "--api-port", str(api_port),
        "--map-sim-url", map_sim_url,
        "--hz", "10",
    ]
    if debug:
        args.append("--debug")
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    return proc


async def test_cli_smoke(scenario_tmpfile, simple_scenario_yaml, fake_map_server, free_port):
    path = scenario_tmpfile(simple_scenario_yaml)
    proc = await _spawn(str(path), free_port, fake_map_server.url, debug=False)
    try:
        assert await _wait_ready(free_port, timeout=10.0), "server never became ready"
        async with aiohttp.ClientSession() as s:
            # Poke the takeover endpoint to exercise happy-path
            async with s.post(
                f"http://127.0.0.1:{free_port}/command/takeover",
                json={
                    "drone_id": "TRK-001",
                    "target_lat": 25.025,
                    "target_lon": 121.5654,
                    "target_alt_m": 0.0,
                    "descent_speed_ms": 3.0,
                },
            ) as r:
                assert r.status == 200
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    stderr = (await proc.stderr.read()).decode()
    # scenario.loaded must have been logged
    assert "scenario.loaded" in stderr, stderr[-2000:]


async def test_debug_mode_registers_endpoints(scenario_tmpfile, simple_scenario_yaml, fake_map_server, free_port):
    path = scenario_tmpfile(simple_scenario_yaml)
    proc = await _spawn(str(path), free_port, fake_map_server.url, debug=True)
    try:
        assert await _wait_ready(free_port, timeout=10.0)
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{free_port}/drones") as r:
                assert r.status == 200
                body = await r.json()
                assert "drones" in body
                assert isinstance(body["drones"], list)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


async def test_debug_off_returns_404(scenario_tmpfile, simple_scenario_yaml, fake_map_server, free_port):
    path = scenario_tmpfile(simple_scenario_yaml)
    proc = await _spawn(str(path), free_port, fake_map_server.url, debug=False)
    try:
        assert await _wait_ready(free_port, timeout=10.0)
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://127.0.0.1:{free_port}/drones") as r:
                assert r.status == 404
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
