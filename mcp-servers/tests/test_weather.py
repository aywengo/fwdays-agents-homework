import datetime as dt
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
    # Open-Meteo's 12:00 row covers the preceding hour, i.e. the 11:00-12:00 slot.
    assert [h["time"] for h in day["daylight_hours"]] == ["11:00"]
    assert (day["sunrise"], day["sunset"]) == ("07:01", "18:33")
    assert day["daylight_h"] == 11.5


def _day_body():
    date = "2026-10-10"
    times = [f"{date}T{h:02d}:00" for h in range(24)]
    radiation = {9: 50, 10: 150, 11: 300, 12: 450, 13: 500, 14: 450, 15: 300, 16: 150, 17: 40}
    uv = {12: 3.0, 13: 3.5, 14: 3.0}
    return {
        "timezone": "Europe/Warsaw",
        "daily": {"time": [date], "weather_code": [61], "temperature_2m_max": [15.7],
                  "temperature_2m_min": [10.7], "precipitation_sum": [1.5], "precipitation_hours": [2.0],
                  "precipitation_probability_max": [60], "wind_speed_10m_max": [20.9],
                  "wind_gusts_10m_max": [35.3], "sunrise": [f"{date}T07:10"], "sunset": [f"{date}T18:10"],
                  "daylight_duration": [39600.0], "sunshine_duration": [3960.0],
                  "shortwave_radiation_sum": [5.08], "uv_index_max": [3.5]},
        "hourly": {"time": times,
                   "temperature_2m": [12.0] * 24,
                   "weather_code": [61 if h == 14 else 3 for h in range(24)],
                   "cloud_cover": [80] * 24,
                   "shortwave_radiation": [radiation.get(h, 0) for h in range(24)],
                   "precipitation_probability": [60 if h in (16, 17) else 10 for h in range(24)],
                   "precipitation": [0.0] * 24,
                   "uv_index": [uv.get(h, 0.0) for h in range(24)]},
    }


def test_forecast_daylight_conditions_and_uv():
    now = dt.datetime(2026, 10, 10, 13, 30, tzinfo=ws.TZ)
    day = ws.shape_forecast(_day_body(), 1, pv_kwp=8, now=now)["days"][0]
    assert (day["condition"], day["condition_uk"]) == ("light rain", "слабкий дощ")
    assert (day["uv_level"], day["uv_level_uk"]) == ("moderate", "помірний")
    assert day["uv_windows_3plus"] == ["11:00-14:00"]
    assert day["rain_windows"] == ["15:00-17:00"]
    assert day["daylight_h"] == 11.0
    assert day["cloud_cover_daylight_avg_pct"] == 80
    # productive = PV >= 10% of 8 kWp = 0.8 kW, i.e. >= 125 W/m2
    assert day["pv_window"] == "09:00-16:00" and day["pv_peak_hour"] == "12:00"
    hours = [h["time"] for h in day["daylight_hours"]]
    assert hours[0] == "07:00" and hours[-1] == "18:00"  # sunrise..sunset, not radiation > 0
    assert day["now"]["is_daylight"] is True and day["now"]["minutes_to_sunset"] == 280
    assert day["now"]["condition_uk"] == "слабкий дощ"
    # half of the 13-14 slot + the three remaining afternoon slots
    assert day["pv_remaining_kwh"] == 4.6


def test_forecast_after_sunset_and_tomorrow_has_no_now():
    late = dt.datetime(2026, 10, 10, 20, 0, tzinfo=ws.TZ)
    day = ws.shape_forecast(_day_body(), 1, pv_kwp=8, now=late)["days"][0]
    assert day["now"]["is_daylight"] is False and day["now"]["minutes_to_sunset"] is None
    assert day["pv_remaining_kwh"] == 0
    earlier = dt.datetime(2026, 10, 9, 20, 0, tzinfo=ws.TZ)
    assert "now" not in ws.shape_forecast(_day_body(), 1, pv_kwp=8, now=earlier)["days"][0]


def test_uv_levels_and_unknown_codes():
    assert ws.uv_level(0)["uv_level"] == "low" and ws.uv_level(7.9)["uv_level"] == "high"
    assert ws.uv_level(11)["uv_level_uk"] == "екстремальний"
    assert ws.condition(95)["condition_uk"] == "гроза"
    assert ws.condition(42)["condition"] == "code 42"


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
