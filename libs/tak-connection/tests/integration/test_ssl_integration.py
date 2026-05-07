"""Integration tests — require real TAK server certs. Skip unless INTEGRATION_CERTS=1."""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    not os.getenv("INTEGRATION_CERTS"),
    reason="real certs not available — set INTEGRATION_CERTS=1",
)
def test_real_cert_roundtrip():
    """Placeholder for real-cert round-trip test."""
    pass
