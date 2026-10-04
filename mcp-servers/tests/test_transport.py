import os

import httpx
import pytest

from home_mcp.common import build_http_app
from home_mcp.prices_server import server as prices
from home_mcp.weather_server import server as weather


@pytest.mark.parametrize("server", [prices, weather])
async def test_auth_and_health(server):
    app = build_http_app(server, "s3cret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://weather-mcp:8000") as c:
        assert (await c.get("/healthz")).status_code == 200
        r = await c.post("/mcp", json={})
        assert r.status_code == 401


async def test_tool_catalog():
    assert sorted(t.name for t in await prices.list_tools()) == ["get_current_price", "get_prices", "plan_grid_charge"]
    assert sorted(t.name for t in await weather.list_tools()) == ["get_forecast", "get_station_readings"]


def test_solax_control_filter(monkeypatch):
    import asyncio
    import importlib

    monkeypatch.setenv("SOLAX_CLIENT_ID", "x")
    monkeypatch.setenv("SOLAX_CLIENT_SECRET", "y")
    import solax_cloud_mcp.server as upstream
    from home_mcp import solax_http

    monkeypatch.setenv("SOLAX_ALLOW_CONTROL", "true")
    importlib.reload(upstream)
    names = {t.name for t in asyncio.run(solax_http.load_server().list_tools())}
    assert "set_battery_self_use_mode" in names
    monkeypatch.setenv("SOLAX_ALLOW_CONTROL", "false")
    importlib.reload(upstream)
    names = {t.name for t in asyncio.run(solax_http.load_server().list_tools())}
    assert names == {"get_realtime_data", "estimate_grid_charge_need", "build_tou_settings"}


async def test_read_only_annotations():
    for server in (prices, weather):
        for tool in await server.list_tools():
            assert tool.annotations and tool.annotations.readOnlyHint is True
