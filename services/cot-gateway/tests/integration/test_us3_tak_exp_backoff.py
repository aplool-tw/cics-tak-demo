"""US3: TAK exponential backoff & fatal exit after max_retries (T049)."""

from __future__ import annotations

import asyncio

import pytest

from cot_gateway.tak.transmitter import TakTransmitter


@pytest.mark.asyncio
async def test_exp_backoff_delay_sequence(monkeypatch):
    sleep_calls: list[float] = []

    async def fake_wait_for(awaitable, timeout):
        sleep_calls.append(timeout)
        try:
            awaitable.close()
        except Exception:
            pass
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    q: asyncio.Queue[str] = asyncio.Queue()
    tx = TakTransmitter(
        host="127.0.0.1",
        port=1,
        cot_queue=q,
        max_retries=5,
        backoff_initial_s=1.0,
        backoff_cap_s=60.0,
    )
    with pytest.raises(ConnectionError):
        await tx._connect_with_retry()
    assert sleep_calls[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]


@pytest.mark.asyncio
async def test_max_retries_cap(monkeypatch):
    """Verify cap applies when initial*2^(attempt-1) exceeds cap."""
    sleep_calls: list[float] = []

    async def fake_wait_for(awaitable, timeout):
        sleep_calls.append(timeout)
        try:
            awaitable.close()
        except Exception:
            pass
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    q: asyncio.Queue[str] = asyncio.Queue()
    tx = TakTransmitter(
        host="127.0.0.1",
        port=1,
        cot_queue=q,
        max_retries=10,
        backoff_initial_s=1.0,
        backoff_cap_s=16.0,
    )
    with pytest.raises(ConnectionError):
        await tx._connect_with_retry()
    # delays: 1,2,4,8,16,16,16,16,16,16
    assert sleep_calls[:10] == [1.0, 2.0, 4.0, 8.0, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0]
