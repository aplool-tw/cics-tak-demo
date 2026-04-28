"""Contract: TAK uplink — delimiter / exp backoff / queue drop (T016 + T043)."""

from __future__ import annotations

import asyncio

import pytest

from cot_gateway.tak.transmitter import TakTransmitter


@pytest.mark.asyncio
async def test_newline_delimited_writes(tak_stub):
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    stop = asyncio.Event()
    tx = TakTransmitter(host="127.0.0.1", port=tak_stub.port, cot_queue=q, stop_event=stop)
    task = asyncio.create_task(tx.run())
    try:
        await asyncio.wait_for(tx.connected_event.wait(), timeout=2.0)
        tx.enqueue('<event uid="A"/>')
        tx.enqueue('<event uid="B"/>')
        tx.enqueue('<event uid="C"/>')
        # allow consume
        for _ in range(40):
            if len(tak_stub.lines) >= 3:
                break
            await asyncio.sleep(0.05)
        assert tak_stub.lines == ['<event uid="A"/>', '<event uid="B"/>', '<event uid="C"/>']
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_queue_full_drops_newest():
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=3)
    tx = TakTransmitter(host="127.0.0.1", port=1, cot_queue=q)
    for i in range(5):
        tx.enqueue(f'<event uid="U{i}"/>')
    # queue has 3; last 2 were dropped
    assert q.qsize() == 3
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    assert items == ['<event uid="U0"/>', '<event uid="U1"/>', '<event uid="U2"/>']


@pytest.mark.asyncio
async def test_exp_backoff_raises_after_max_retries(monkeypatch):
    """Unreachable port → exp backoff series 1/2/4/8/16 → raise ConnectionError after 5."""

    sleep_calls: list[float] = []

    async def fake_wait_for(awaitable, timeout):
        sleep_calls.append(timeout)
        # Consume the coroutine to avoid warning
        try:
            awaitable.close()
        except Exception:
            pass
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    q: asyncio.Queue[str] = asyncio.Queue()
    tx = TakTransmitter(
        host="127.0.0.1",
        port=1,  # unreachable
        cot_queue=q,
        max_retries=5,
        backoff_initial_s=1.0,
        backoff_cap_s=60.0,
    )
    with pytest.raises(ConnectionError):
        await tx._connect_with_retry()

    # attempts 1..5 used delays 1,2,4,8,16
    assert sleep_calls[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]


@pytest.mark.asyncio
async def test_reconnect_after_disconnect(tak_stub):
    """Mid-transmission disconnect → transmitter should retry and deliver later CoT."""
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    stop = asyncio.Event()
    tx = TakTransmitter(
        host="127.0.0.1",
        port=tak_stub.port,
        cot_queue=q,
        stop_event=stop,
        backoff_initial_s=0.1,
        backoff_cap_s=0.1,
        max_retries=10,
    )
    task = asyncio.create_task(tx.run())
    try:
        await asyncio.wait_for(tx.connected_event.wait(), timeout=2.0)
        tx.enqueue('<event uid="pre"/>')
        for _ in range(20):
            if tak_stub.lines:
                break
            await asyncio.sleep(0.05)
        assert '<event uid="pre"/>' in tak_stub.lines

        # Close from stub side
        for w in tak_stub._writers:
            w.close()
        await asyncio.sleep(0.3)
        # Send a burst to trigger BrokenPipeError → reconnect
        for i in range(5):
            tx.enqueue(f'<event uid="post{i}"/>')
            await asyncio.sleep(0.05)
        for _ in range(60):
            if any("post" in line for line in tak_stub.lines[1:]):
                break
            await asyncio.sleep(0.1)
        # At least one post-reconnect event must arrive
        assert any("post" in line for line in tak_stub.lines[1:])
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_source_switch_two_messages_in_order(tak_stub):
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    stop = asyncio.Event()
    tx = TakTransmitter(host="127.0.0.1", port=tak_stub.port, cot_queue=q, stop_event=stop)
    task = asyncio.create_task(tx.run())
    try:
        await asyncio.wait_for(tx.connected_event.wait(), timeout=2.0)
        tx.enqueue('<event uid="ECHO-TRK-001" stale=time/>')
        tx.enqueue('<event uid="FUSED-DRN-001" new/>')
        for _ in range(40):
            if len(tak_stub.lines) >= 2:
                break
            await asyncio.sleep(0.05)
        assert tak_stub.lines[0].startswith('<event uid="ECHO-TRK-001"')
        assert tak_stub.lines[1].startswith('<event uid="FUSED-DRN-001"')
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
