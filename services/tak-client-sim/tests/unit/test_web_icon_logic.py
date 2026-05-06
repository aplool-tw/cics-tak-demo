from __future__ import annotations

from tak_client_sim.web_server import _build_map_html


def test_unknown_icon_svg_template() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert '<circle r="10" fill="#90a4ae" stroke="#546e7a" stroke-width="2"/>' in html
    assert '<line x1="-5" y1="-5" x2="5" y2="5" stroke="#546e7a" stroke-width="1.5" stroke-linecap="round"/>' in html
    assert '<line x1="5" y1="-5" x2="-5" y2="5" stroke="#546e7a" stroke-width="1.5" stroke-linecap="round"/>' in html


def test_hostile_icon_svg_template() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert '<rect x="-8" y="-8" width="16" height="16" fill="#ef5350" stroke="#b71c1c" stroke-width="2" transform="rotate(45)"/>' in html


def test_stale_icon_template_uses_dimmed_opacity() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert 'opacity:0.45' in html
    assert "const fill = isStale ? '#546e7a' : '#ef5350';" in html


def test_course_arrow_template_is_conditional_on_speed() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert 'const arrow = (speed > 0.3)' in html
    assert '<polygon points="0,-7 -3,-1 3,-1" fill="white" opacity="0.85"/>' in html


def test_unknown_fallback_checks_hostile_prefix() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert "cotType.startsWith('a-h')" in html


def test_legend_uses_mil_std_labels() -> None:
    html = _build_map_html(1.0, 2.0, 3.0, 4.0)

    assert '未知目標 Unknown (a-u-*)' in html
    assert '敵對目標 Hostile (a-h-*)' in html
    assert '過期 Stale' in html
    assert '灰色目標 (GREY)' not in html
