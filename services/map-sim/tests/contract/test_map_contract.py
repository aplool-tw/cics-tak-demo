"""Contract tests for GET /map — browser Leaflet.js map viewer."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_map_returns_200(client):
    resp = await client.get("/map")
    assert resp.status == 200


@pytest.mark.asyncio
async def test_map_content_type_is_html(client):
    resp = await client.get("/map")
    assert "text/html" in resp.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_map_contains_leaflet(client):
    resp = await client.get("/map")
    text = await resp.text()
    assert "leaflet" in text.lower()


@pytest.mark.asyncio
async def test_map_polls_objects_all(client):
    resp = await client.get("/map")
    text = await resp.text()
    assert "/objects/all" in text


@pytest.mark.asyncio
async def test_map_contains_refresh_interval(client):
    resp = await client.get("/map")
    text = await resp.text()
    assert "setInterval" in text
    assert "REFRESH_MS" in text
