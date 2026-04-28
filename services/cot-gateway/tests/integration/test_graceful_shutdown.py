"""Graceful shutdown (T051): request_stop → exit ≤3s, exit code 0."""

from __future__ import annotations

import asyncio
import time

import pytest

from cot_gateway.config import GatewayConfig, SentrycsConfig
from cot_gateway.loop import GatewayMain


@pytest.mark.asyncio
async def test_graceful_shutdown(echoshield_stub, tak_stub):
    cfg = GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
    )
    gw = GatewayMain(
        cfg,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=echoshield_stub.port,
        tak_host_override="127.0.0.1",
        tak_port_override=tak_stub.port,
    )
    task = asyncio.create_task(gw.run())
    await echoshield_stub.wait_connected(3.0)
    t0 = time.monotonic()
    gw.request_stop()
    exit_code = await asyncio.wait_for(task, timeout=5.0)
    elapsed = time.monotonic() - t0
    assert elapsed < 3.5
    assert exit_code == 0
