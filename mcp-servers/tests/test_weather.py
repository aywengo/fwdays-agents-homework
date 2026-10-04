import json

import httpx
import pytest
import respx

from conftest import load
from home_mcp import weather_server as ws


def test_shape_stations_modules():
    out = ws.shape_stations(load("netatmo_stations.json"))
    mods = {m["kind"]: m for m in out["stations"][0]["modules"]}
    assert mods["outdoor"]["temperature_c"] == 8.3
    assert mods["wind"]["gust_kmh"] == 27
    assert mods["rain"]["reachable"] is False and "rain_today_mm" not in mods["rain"]
    assert "location" not in json.dumps(out)  # coordinates are not exposed to the model


def test_station_location_is_lat_lon():
    assert ws.station_location(load("netatmo_stations.json")) == (52.4, 16.9)


def test_forecast_pv_estimate():
    out = ws.shape_forecast(load("open_meteo.json"), 1, pv_kwp=10)
    day = out["days"][0]
    assert day["solar_radiation_kwh_m2"] == 2.5
    assert day["pv_estimate_kwh"] == 20.0
    assert day["sunshine_hours"] == 6.0
    assert [h["time"] for h in day["daylight_hours"]] == ["12:00"]


@respx.mock
async def test_refresh_token_rotation_persisted(monkeypatch):
    monkeypatch.setenv("NETATMO_CLIENT_ID", "id")
    monkeypatch.setenv("NETATMO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("NETATMO_REFRESH_TOKEN", "bootstrap")
    token_route = respx.post(ws.NETATMO_TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "a1", "refresh_token": "rotated", "expires_in": 10800}))
    respx.get(ws.NETATMO_STATIONS_URL).mock(return_value=httpx.Response(200, json=load("netatmo_stations.json")))
    async with httpx.AsyncClient() as client:
        await ws.fetch_stations(client)
        await ws.fetch_stations(client)  # cached access token, no second refresh
    assert token_route.call_count == 1
    assert b"bootstrap" in token_route.calls[0].request.content
    saved = json.loads(ws._token_file().read_text())
    assert saved["refresh_token"] == "rotated"
    assert oct(ws._token_file().stat().st_mode & 0o777) == "0o600"


def test_missing_config_message(monkeypatch):
    monkeypatch.delenv("NETATMO_REFRESH_TOKEN", raising=False)
    with pytest.raises(ws.WeatherError, match="netatmo_auth.py"):
        ws._load_tokens()
