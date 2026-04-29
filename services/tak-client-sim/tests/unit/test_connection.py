from __future__ import annotations

import asyncio
import ssl
from unittest.mock import MagicMock, patch

import pytest

from tak_client_sim.config import ClientConfig
from tak_client_sim.connection import build_ssl_context, connect_with_retry
from tak_client_sim.models import ConnectionStats


def test_build_ssl_context_poc_mode() -> None:
    cfg = ClientConfig(use_ssl_verify=False)
    ctx = build_ssl_context(cfg)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_build_ssl_context_verify_mode() -> None:
    cfg = ClientConfig(use_ssl_verify=True)
    ctx = build_ssl_context(cfg)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


async def test_backoff_sequence() -> None:
    """7 consecutive failures yield sleep delays [1,2,4,8,16,32,60]."""
    config = ClientConfig(host="127.0.0.1", port=9999, use_ssl_verify=False, max_retries=0)
    stats = ConnectionStats()
    stop = asyncio.Event()

    call_count = 0
    sleep_calls: list[float] = []

    async def _mock_open(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 7:
            raise ConnectionRefusedError("refused")
        # On 8th call succeed
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        return reader, writer

    async def _mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with (
        patch("tak_client_sim.connection.asyncio.open_connection", _mock_open),
        patch("tak_client_sim.connection.asyncio.sleep", _mock_sleep),
        patch("builtins.print"),
    ):
        await connect_with_retry(config, stats, stop)

    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]


async def test_max_retries_exceeded_exits_1() -> None:
    """With max_retries=3, 3 consecutive failures → SystemExit(1)."""
    config = ClientConfig(host="127.0.0.1", port=9999, use_ssl_verify=False, max_retries=3)
    stats = ConnectionStats()
    stop = asyncio.Event()

    async def _always_fail(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    async def _mock_sleep(_: float) -> None:
        pass

    with (
        patch("tak_client_sim.connection.asyncio.open_connection", _always_fail),
        patch("tak_client_sim.connection.asyncio.sleep", _mock_sleep),
        patch("builtins.print"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await connect_with_retry(config, stats, stop)
    assert exc_info.value.code == 1


async def test_reconnect_count_increments() -> None:
    """2 failures before success → stats.reconnect_count == 2."""
    config = ClientConfig(host="127.0.0.1", port=9999, use_ssl_verify=False, max_retries=0)
    stats = ConnectionStats()
    stop = asyncio.Event()
    call_count = 0

    async def _mock_open(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionRefusedError("refused")
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        return reader, writer

    async def _mock_sleep(_: float) -> None:
        pass

    with (
        patch("tak_client_sim.connection.asyncio.open_connection", _mock_open),
        patch("tak_client_sim.connection.asyncio.sleep", _mock_sleep),
        patch("builtins.print"),
    ):
        await connect_with_retry(config, stats, stop)

    assert stats.reconnect_count == 2


async def test_attempt_resets_on_success() -> None:
    """After successful connect, first delay on next failure series starts at 1s."""
    config = ClientConfig(host="127.0.0.1", port=9999, use_ssl_verify=False, max_retries=0)
    stats = ConnectionStats()
    stop = asyncio.Event()
    call_count = 0
    sleep_calls: list[float] = []

    async def _mock_open(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call succeeds immediately
            reader = MagicMock(spec=asyncio.StreamReader)
            writer = MagicMock(spec=asyncio.StreamWriter)
            return reader, writer
        # Subsequent calls fail once then succeed
        if call_count == 2:
            raise ConnectionRefusedError("refused")
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        return reader, writer

    async def _mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with (
        patch("tak_client_sim.connection.asyncio.open_connection", _mock_open),
        patch("tak_client_sim.connection.asyncio.sleep", _mock_sleep),
        patch("builtins.print"),
    ):
        # First connect: success
        await connect_with_retry(config, stats, stop)
        # Second connect: 1 failure then success
        await connect_with_retry(config, stats, stop)

    assert sleep_calls == [1.0]
