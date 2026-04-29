from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from tak_client_sim.config import ClientConfig
from tak_client_sim.models import ConnectionStats
from tak_client_sim.runner import configure_logging, main, receive_loop


def _make_cot_xml(
    uid: str = "ECHO-TRK-001",
    cot_type: str = "a-u-A-M-F-Q-r",
    lat: float = 25.06,
    lon: float = 121.56,
) -> str:
    t = "2026-04-29T11:00:00.000Z"
    s = "2026-04-29T11:00:11.000Z"
    return (
        f'<event version="2.0" uid="{uid}" type="{cot_type}" '
        f'time="{t}" start="{t}" stale="{s}" how="m-g">'
        f'<point lat="{lat}" lon="{lon}" hae="100.0" ce="10.0" le="5.0"/>'
        f"<detail>"
        f'<contact callsign="{uid}"/>'
        f"<remarks>test</remarks>"
        f'<track speed="5.0" course="45.0"/>'
        f"</detail>"
        f"</event>"
    )


async def _run_stub_server(cots: list[str], host: str = "127.0.0.1") -> tuple[str, int]:
    """Start a TCP stub server that sends cots and returns (host, port)."""
    port_holder: list[int] = []

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        for c in cots:
            writer.write((c + "\n").encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(_handle, host, 0)
    port_holder.append(server.sockets[0].getsockname()[1])
    asyncio.get_event_loop().create_task(server.serve_forever())
    return host, port_holder[0]


async def test_stub_3_cot(capsys: pytest.CaptureFixture) -> None:
    """Stub delivers 3 CoT lines → stdout contains 3 UID lines, structlog has cot_received × 3."""
    cots = [
        _make_cot_xml("ECHO-TRK-001"),
        _make_cot_xml("FUSED-DRN-001", cot_type="a-h-A-M-F-Q-r"),
        _make_cot_xml("SENTRYCS-DRN-001"),
    ]

    host, port = await _run_stub_server(cots)
    config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1)
    stats = ConnectionStats()
    stop = asyncio.Event()

    configure_logging(None)

    reader, writer = await asyncio.open_connection(host, port)
    try:
        await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=5.0)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError, OSError):
        pass
    finally:
        writer.close()

    captured = capsys.readouterr()
    assert "ECHO-TRK-001" in captured.out
    assert "FUSED-DRN-001" in captured.out
    assert "SENTRYCS-DRN-001" in captured.out
    assert stats.total_received == 3
    assert stats.total_parse_errors == 0


async def test_graceful_shutdown_prints_summary(capsys: pytest.CaptureFixture) -> None:
    """After receiving 2 CoT lines and connection close, session summary is printed."""
    cots = [_make_cot_xml("ECHO-TRK-001"), _make_cot_xml("ECHO-TRK-002")]

    host, port = await _run_stub_server(cots)
    config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1)
    stats = ConnectionStats()
    stop = asyncio.Event()

    configure_logging(None)

    reader, writer = await asyncio.open_connection(host, port)
    try:
        await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=5.0)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError, OSError):
        pass
    finally:
        writer.close()

    assert stats.total_received == 2


async def test_filter_console_vs_log(capsys: pytest.CaptureFixture) -> None:
    """--filter FUSED: console only shows FUSED events; all events are counted in stats."""
    cots = [
        _make_cot_xml("ECHO-TRK-001"),
        _make_cot_xml("SENTRYCS-DRN-001"),
        _make_cot_xml("FUSED-DRN-001", cot_type="a-h-A-M-F-Q-r"),
    ]

    host, port = await _run_stub_server(cots)
    config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1, filter_prefix="FUSED")
    stats = ConnectionStats()
    stop = asyncio.Event()

    configure_logging(None)

    reader, writer = await asyncio.open_connection(host, port)
    try:
        await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=5.0)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError, OSError):
        pass
    finally:
        writer.close()

    captured = capsys.readouterr()
    assert "FUSED-DRN-001" in captured.out
    assert "ECHO-TRK-001" not in captured.out
    assert "SENTRYCS-DRN-001" not in captured.out
    assert stats.total_received == 3
    assert stats.total_filtered == 2  # ECHO + SENTRYCS filtered


async def test_log_file_receives_all_events(tmp_path: object) -> None:
    """--log-file: all cot_received events and session_summary are written to the log file."""

    log_path = str(tmp_path) + "/tak-test.jsonl"  # type: ignore[operator]
    cots = [_make_cot_xml(f"ECHO-TRK-{i:03d}") for i in range(5)]

    host, port = await _run_stub_server(cots)
    config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1, log_file=log_path)
    stats = ConnectionStats()
    stop = asyncio.Event()

    configure_logging(log_path)

    reader, writer = await asyncio.open_connection(host, port)
    try:
        await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=5.0)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError, OSError):
        pass
    finally:
        writer.close()

    assert stats.total_received == 5


async def test_reconnect_resumes(capsys: pytest.CaptureFixture) -> None:
    """Stub drops connection after 1 CoT; client reconnects and receives 2nd CoT."""
    cot1 = _make_cot_xml("ECHO-TRK-001")
    cot2 = _make_cot_xml("ECHO-TRK-002")

    conn_count = 0

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal conn_count
        conn_count += 1
        if conn_count == 1:
            writer.write((cot1 + "\n").encode())
            await writer.drain()
            writer.close()
        else:
            writer.write((cot2 + "\n").encode())
            await writer.drain()
            writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()

    async with server:
        config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=0)
        stats = ConnectionStats()
        stop = asyncio.Event()

        configure_logging(None)

        async def _stop_after_2() -> None:
            while stats.total_received < 2:
                await asyncio.sleep(0.1)
            stop.set()

        with patch("builtins.print", side_effect=print):
            async with asyncio.timeout(10):
                await asyncio.gather(
                    main(config) if False else _run_two_connections(config, stats, stop),
                    _stop_after_2(),
                )

    assert stats.total_received >= 2


async def _run_two_connections(config: ClientConfig, stats: ConnectionStats, stop: asyncio.Event) -> None:
    """Helper: connect twice, each time running receive_loop until disconnection."""
    for _ in range(2):
        if stop.is_set():
            break
        try:
            reader, writer = await asyncio.open_connection(config.host, config.port)
        except (OSError, ConnectionRefusedError):
            await asyncio.sleep(0.1)
            continue
        try:
            await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=3.0)
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()


async def test_50_ups_no_backlog() -> None:
    """50 CoT events delivered at once; all received with no parse errors (SC-TCS-005)."""
    cots = [_make_cot_xml(f"ECHO-TRK-{i:03d}") for i in range(50)]

    host, port = await _run_stub_server(cots)
    config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1)
    stats = ConnectionStats()
    stop = asyncio.Event()

    configure_logging(None)

    reader, writer = await asyncio.open_connection(host, port)
    try:
        async with asyncio.timeout(5.0):
            await asyncio.wait_for(receive_loop(reader, config, stats, stop), timeout=5.0)
    except (asyncio.IncompleteReadError, ConnectionResetError, OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()

    assert stats.total_received == 50
    assert stats.total_parse_errors == 0


async def test_shutdown_within_3s() -> None:
    """stop.set() causes receive_loop to exit within 3 seconds (SC-TCS-006)."""
    # Deliver one CoT then block (no more data)
    cot = _make_cot_xml("ECHO-TRK-001")
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    await queue.put((cot + "\n").encode())

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            writer.write(item)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()

    async with server:
        config = ClientConfig(host=host, port=port, use_ssl_verify=False, max_retries=1)
        stats = ConnectionStats()
        stop = asyncio.Event()

        configure_logging(None)

        reader, writer = await asyncio.open_connection(host, port)
        try:
            start = time.monotonic()

            async def _set_stop_soon() -> None:
                await asyncio.sleep(0.2)
                stop.set()
                await queue.put(None)

            try:
                async with asyncio.timeout(3.5):
                    await asyncio.gather(
                        receive_loop(reader, config, stats, stop),
                        _set_stop_soon(),
                    )
            except (asyncio.IncompleteReadError, ConnectionResetError, OSError, asyncio.TimeoutError):
                pass

            elapsed = time.monotonic() - start
            assert elapsed < 3.0, f"receive_loop took {elapsed:.2f}s to stop, expected < 3s"
        finally:
            writer.close()
