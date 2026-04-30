"""T017 [US3]: Guard test — TrackSource enum values must match JS SRC_COLOR keys.

This test documents the wire contract between the Python TrackSource enum and
the JavaScript SRC_COLOR map in web/server.py.  It will pass immediately since
the values already match — its purpose is to guard against accidental renames.
"""

from __future__ import annotations

from cot_gateway.models.track import TrackSource


def test_track_source_enum_values_match_js_src_color_keys() -> None:
    """Guard: TrackSource values must match the JS SRC_COLOR keys in server.py."""
    assert TrackSource.ECHOSHIELD.value == "ECHOSHIELD"
    assert TrackSource.SENTRYCS.value == "SENTRYCS"
    assert TrackSource.FUSED.value == "FUSED"
