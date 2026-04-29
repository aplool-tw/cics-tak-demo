from __future__ import annotations

import asyncio

import pytest

from tak_client_sim.parser import parse_cot_xml


@pytest.mark.parametrize(
    "fixture_name,expected_uid,expected_source,expected_color,expected_delta",
    [
        ("cot_echo_active", "ECHO-TRK-001", "ECHO", "GREY", 11),
        ("cot_echo_lost", "ECHO-TRK-001", "ECHO", "GREY", 0),
        ("cot_sentrycs_detected", "SENTRYCS-DRN-001", "SENTRYCS", "GREY", 11),
        ("cot_sentrycs_mitigating", "SENTRYCS-DRN-001", "SENTRYCS", "GREY", 11),
        ("cot_sentrycs_neutralized", "SENTRYCS-DRN-001", "SENTRYCS", "GREY", 30),
        ("cot_fused_detected", "FUSED-DRN-001", "FUSED", "RED", 11),
        ("cot_fused_mitigating", "FUSED-DRN-001", "FUSED", "RED", 11),
        ("cot_fused_neutralized", "FUSED-DRN-001", "FUSED", "RED", 30),
    ],
)
def test_compliance_matrix(
    request: pytest.FixtureRequest,
    fixture_name: str,
    expected_uid: str,
    expected_source: str,
    expected_color: str,
    expected_delta: int,
) -> None:
    raw = request.getfixturevalue(fixture_name)
    event = parse_cot_xml(raw)
    assert event is not None, f"parse_cot_xml returned None for {fixture_name}"
    assert event.uid == expected_uid
    assert event.source == expected_source
    assert event.color == expected_color
    assert event.delta_s == expected_delta


async def test_stub_server_3_cot(cot_echo_active: str, cot_fused_detected: str, cot_sentrycs_detected: str) -> None:
    """Stub TCP server delivers 3 CoT lines; client parses all 3 correctly."""
    cots = [cot_echo_active, cot_fused_detected, cot_sentrycs_detected]
    received: list[str] = []

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        for c in cots:
            writer.write((c + "\n").encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    async with server:
        reader, writer = await asyncio.open_connection(addr[0], addr[1])
        try:
            while True:
                try:
                    line = await reader.readuntil(b"\n")
                    received.append(line.decode().strip())
                except asyncio.IncompleteReadError:
                    break
        finally:
            writer.close()

    assert len(received) == 3
    events = [parse_cot_xml(r) for r in received]
    assert all(e is not None for e in events)
    uids = {e.uid for e in events if e}  # type: ignore[union-attr]
    assert "ECHO-TRK-001" in uids
    assert "FUSED-DRN-001" in uids
    assert "SENTRYCS-DRN-001" in uids
