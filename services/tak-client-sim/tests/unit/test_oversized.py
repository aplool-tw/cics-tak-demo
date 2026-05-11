from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from tak_client_sim.config import ClientConfig
from tak_client_sim.models import ConnectionStats, CotEvent
from tak_client_sim.runner import receive_loop


def _make_event(uid: str = "ECHO-TRK-001") -> CotEvent:
    t = datetime(2026, 4, 29, 11, 0, 0, 0, tzinfo=timezone.utc)
    s = datetime(2026, 4, 29, 11, 0, 11, 0, tzinfo=timezone.utc)
    return CotEvent(
        uid=uid,
        cot_type="a-u-A-M-F-Q-r",
        source="ECHO",
        color="GREY",
        time=t,
        stale=s,
        delta_s=11,
        lat=25.06,
        lon=121.56,
        hae=100.0,
        speed=5.0,
        course=45.0,
        remarks="test",
        raw_xml="<event/>",
    )


async def test_cot_oversized_handling() -> None:
    """Event >65536 bytes increments total_oversized and logs cot_oversized; loop continues."""
    config = ClientConfig(host="127.0.0.1", port=18089, use_ssl_verify=False)
    stats = ConnectionStats()
    stop = asyncio.Event()

    # Valid CoT XML delivered after the oversized one
    valid_xml = (
        '<event version="2.0" uid="ECHO-TRK-001" type="a-u-A-M-F-Q-r" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        '<detail><remarks>ok</remarks><track speed="5.0" course="0.0"/></detail>'
        "</event>"
    )

    # Oversized event: pad <remarks> to push total bytes beyond 65536
    oversized_xml = (
        '<event version="2.0" uid="HUGE" type="a-u-A-M-F-Q-r" '
        'time="2026-04-29T11:00:00.000Z" start="2026-04-29T11:00:00.000Z" '
        'stale="2026-04-29T11:00:11.000Z" how="m-g">'
        '<point lat="25.06" lon="121.56" hae="100.0" ce="10.0" le="5.0"/>'
        "<detail><remarks>" + "x" * 70000 + "</remarks></detail>"
        "</event>"
    )

    call_count = 0

    async def _mock_read(n: int) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Return oversized + valid concatenated in one chunk; set stop so loop exits after
            stop.set()
            return (oversized_xml + valid_xml).encode()
        raise asyncio.IncompleteReadError(b"", None)

    mock_reader = MagicMock(spec=asyncio.StreamReader)
    mock_reader.read = _mock_read

    with patch("tak_client_sim.runner._log") as mock_log:
        mock_log.warning = MagicMock()
        mock_log.info = MagicMock()
        try:
            await receive_loop(mock_reader, config, stats, stop)
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            pass

    assert stats.total_oversized == 1
    # Verify cot_oversized warning was logged with bytes_seen
    warning_calls = [str(c) for c in mock_log.warning.call_args_list]
    assert any("cot_oversized" in c for c in warning_calls)
    # The valid CoT after the oversized one should have been received
    assert stats.total_received == 1
