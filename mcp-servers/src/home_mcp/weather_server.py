"""MCP server: home weather station (Netatmo) plus a solar-relevant forecast (Open-Meteo).

Read-only by design: the Netatmo app only needs the `read_station` scope.

Netatmo rotates refresh tokens. The current pair is stored in
$HOME_MCP_STATE_DIR/netatmo-token.json (outside the repository). The
NETATMO_REFRESH_TOKEN environment variable is only the bootstrap value.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .common import atomic_write_json, run, state_dir

log = logging.getLogger("home_mcp.weather")

NETATMO_TOKEN_URL = "https://api.netatmo.com/oauth2/token"
NETATMO_STATIONS_URL = "https://api.netatmo.com/api/getstationsdata"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TZ_NAME = os.getenv("HOME_TZ", "Europe/Warsaw")
TZ = ZoneInfo(TZ_NAME)

MODULE_KINDS = {
    "NAMain": "indoor",
    "NAModule1": "outdoor",
    "NAModule2": "wind",
    "NAModule3": "rain",
    "NAModule4": "indoor_extra",
}

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
server = FastMCP("netatmo-weather")
_token_lock = asyncio.Lock()


class WeatherError(RuntimeError):
    pass


# --------------------------------------------------------------------------- Netatmo auth
def _token_file():
    return state_dir() / "netatmo-token.json"


def _load_tokens() -> dict:
    path = _token_file()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            log.warning("Ignoring unreadable Netatmo token file")
    refresh = os.getenv("NETATMO_REFRESH_TOKEN")
    if not refresh:
        raise WeatherError("Netatmo is not configured: set NETATMO_REFRESH_TOKEN (see scripts/netatmo_auth.py)")
    return {"refresh_token": refresh, "access_token": None, "expires_at": 0}


def _client_credentials() -> tuple[str, str]:
    cid, secret = os.getenv("NETATMO_CLIENT_ID"), os.getenv("NETATMO_CLIENT_SECRET")
    if not cid or not secret:
        raise WeatherError("Netatmo is not configured: set NETATMO_CLIENT_ID and NETATMO_CLIENT_SECRET")
    return cid, secret


async def _access_token(client: httpx.AsyncClient, force: bool = False) -> str:
    async with _token_lock:
        tokens = _load_tokens()
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if not force and tokens.get("access_token") and tokens.get("expires_at", 0) - 120 > now:
            return tokens["access_token"]
        cid, secret = _client_credentials()
        resp = await client.post(NETATMO_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
            "client_secret": secret,
        })
        if resp.status_code >= 400:
            raise WeatherError(f"Netatmo token refresh failed (HTTP {resp.status_code}); re-run scripts/netatmo_auth.py")
        body = resp.json()
        tokens = {
            "access_token": body["access_token"],
            "refresh_token": body.get("refresh_token", tokens["refresh_token"]),
            "expires_at": now + int(body.get("expires_in", 10800)),
        }
        atomic_write_json(_token_file(), tokens)
        return tokens["access_token"]


async def fetch_stations(client: httpx.AsyncClient) -> dict:
    params = {"get_favorites": "false"}
    if os.getenv("NETATMO_DEVICE_ID"):
        params["device_id"] = os.environ["NETATMO_DEVICE_ID"]
    for attempt in (0, 1):
        token = await _access_token(client, force=attempt == 1)
        resp = await client.get(NETATMO_STATIONS_URL, params=params,
                                headers={"Authorization": f"Bearer {token}"})
        if resp.status_code in (401, 403) and attempt == 0:
            continue
        if resp.status_code >= 400:
            raise WeatherError(f"Netatmo getstationsdata failed (HTTP {resp.status_code})")
        return resp.json()
    raise WeatherError("Netatmo authentication failed twice")


# --------------------------------------------------------------------------- shaping
def _ts(value: Any) -> str | None:
    if not value:
        return None
    return dt.datetime.fromtimestamp(int(value), TZ).isoformat(timespec="minutes")


def _module_reading(kind: str, data: dict) -> dict:
    d = data or {}
    common = {"measured_at": _ts(d.get("time_utc"))}
    if kind in ("indoor", "indoor_extra"):
        return {**common, "temperature_c": d.get("Temperature"), "humidity_pct": d.get("Humidity"),
                "co2_ppm": d.get("CO2"), "noise_db": d.get("Noise"),
                "pressure_hpa": d.get("Pressure"), "pressure_trend": d.get("pressure_trend"),
                "min_temp_c": d.get("min_temp"), "max_temp_c": d.get("max_temp")}
    if kind == "outdoor":
        return {**common, "temperature_c": d.get("Temperature"), "humidity_pct": d.get("Humidity"),
                "temp_trend": d.get("temp_trend"), "min_temp_c": d.get("min_temp"),
                "min_temp_at": _ts(d.get("date_min_temp")), "max_temp_c": d.get("max_temp"),
                "max_temp_at": _ts(d.get("date_max_temp"))}
    if kind == "wind":
        return {**common, "wind_kmh": d.get("WindStrength"), "wind_angle_deg": d.get("WindAngle"),
                "gust_kmh": d.get("GustStrength"), "gust_angle_deg": d.get("GustAngle"),
                "max_wind_today_kmh": d.get("max_wind_str"), "max_wind_at": _ts(d.get("date_max_wind_str"))}
    if kind == "rain":
        return {**common, "rain_now_mm": d.get("Rain"), "rain_last_hour_mm": d.get("sum_rain_1"),
                "rain_today_mm": d.get("sum_rain_24")}
    return {**common, "raw": d}


def shape_stations(body: dict) -> dict:
    devices = (body.get("body") or {}).get("devices") or []
    if not devices:
        raise WeatherError("No Netatmo weather station found for this account")
    stations = []
    for device in devices:
        place = device.get("place") or {}
        modules = [{
            "name": device.get("module_name") or "Indoor",
            "kind": "indoor",
            "reachable": True,
            **_module_reading("indoor", device.get("dashboard_data")),
        }]
        for module in device.get("modules") or []:
            kind = MODULE_KINDS.get(module.get("type"), module.get("type", "unknown"))
            modules.append({
                "name": module.get("module_name") or kind,
                "kind": kind,
                "reachable": module.get("reachable", True),
                "battery_pct": module.get("battery_percent"),
                **(_module_reading(kind, module.get("dashboard_data")) if module.get("reachable", True) else {}),
            })
        stations.append({
            "station_name": device.get("station_name") or device.get("home_name"),
            "city": place.get("city"),
            "altitude_m": place.get("altitude"),
            "modules": modules,
        })
    return {"timezone": TZ_NAME, "stations": stations}


def station_location(body: dict) -> tuple[float, float] | None:
    for device in (body.get("body") or {}).get("devices") or []:
        loc = (device.get("place") or {}).get("location")
        if loc and len(loc) == 2:
            return float(loc[1]), float(loc[0])  # Netatmo stores [lon, lat]
    return None


def shape_forecast(body: dict, days: int, pv_kwp: float | None) -> dict:
    daily = body.get("daily") or {}
    hourly = body.get("hourly") or {}
    out_days = []
    for i, date in enumerate((daily.get("time") or [])[:days]):
        def pick(key: str):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None

        radiation_mj = pick("shortwave_radiation_sum")
        day = {
            "date": date,
            "temp_min_c": pick("temperature_2m_min"),
            "temp_max_c": pick("temperature_2m_max"),
            "precipitation_mm": pick("precipitation_sum"),
            "precipitation_probability_max_pct": pick("precipitation_probability_max"),
            "wind_max_kmh": pick("wind_speed_10m_max"),
            "gust_max_kmh": pick("wind_gusts_10m_max"),
            "sunrise": pick("sunrise"),
            "sunset": pick("sunset"),
            "sunshine_hours": round(pick("sunshine_duration") / 3600, 1) if pick("sunshine_duration") is not None else None,
            "solar_radiation_kwh_m2": round(radiation_mj / 3.6, 2) if radiation_mj is not None else None,
        }
        if pv_kwp and day["solar_radiation_kwh_m2"] is not None:
            # Rough yield estimate: irradiation x kWp x performance ratio 0.8.
            day["pv_estimate_kwh"] = round(day["solar_radiation_kwh_m2"] * pv_kwp * 0.8, 1)
        hours = []
        for j, ts in enumerate(hourly.get("time") or []):
            if not ts.startswith(date):
                continue

            def at(key: str, j: int = j):
                values = hourly.get(key) or []
                return values[j] if j < len(values) else None

            hours.append({
                "time": ts[11:16],
                "cloud_cover_pct": at("cloud_cover"),
                "radiation_w_m2": at("shortwave_radiation"),
                "precip_probability_pct": at("precipitation_probability"),
                "temp_c": at("temperature_2m"),
            })
        day["daylight_hours"] = [h for h in hours if (h["radiation_w_m2"] or 0) > 0]
        out_days.append(day)
    return {"source": "Open-Meteo", "timezone": body.get("timezone", TZ_NAME), "days": out_days}


# --------------------------------------------------------------------------- tools
@server.tool(annotations=READ_ONLY)
async def get_station_readings() -> dict:
    """Current readings from the home Netatmo weather station.

    Covers the indoor base station, the outdoor module (temperature, humidity,
    today's min/max), the anemometer (wind and gusts, km/h) and the rain gauge
    (now, last hour, today in mm), plus module battery levels.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        return shape_stations(await fetch_stations(client))


@server.tool(annotations=READ_ONLY)
async def get_forecast(days: int = 1) -> dict:
    """Weather forecast for the home location with solar-production indicators.

    Args:
        days: 1 (today) to 3. Day 1 is today in the home time zone.

    Returns per day: temperature range, precipitation, wind, sunrise/sunset,
    sunshine hours, solar irradiation (kWh/m2), an hourly daylight breakdown
    (cloud cover, radiation) and, when PV_KWP is configured, a rough PV yield estimate.
    """
    days = max(1, min(int(days), 3))
    async with httpx.AsyncClient(timeout=20) as client:
        lat, lon = os.getenv("HOME_LAT"), os.getenv("HOME_LON")
        if lat and lon:
            location = (float(lat), float(lon))
        else:
            location = station_location(await fetch_stations(client))
            if not location:
                raise WeatherError("Set HOME_LAT/HOME_LON or configure Netatmo so the station location is known")
        resp = await client.get(OPEN_METEO_URL, params={
            "latitude": round(location[0], 3),
            "longitude": round(location[1], 3),
            "timezone": TZ_NAME,
            "forecast_days": days,
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max",
                "sunrise", "sunset", "sunshine_duration", "shortwave_radiation_sum",
            ]),
            "hourly": "temperature_2m,cloud_cover,shortwave_radiation,precipitation_probability",
        })
        if resp.status_code >= 400:
            raise WeatherError(f"Open-Meteo request failed (HTTP {resp.status_code})")
        pv = os.getenv("PV_KWP")
        return shape_forecast(resp.json(), days, float(pv) if pv else None)


def main() -> None:
    run(server)


if __name__ == "__main__":
    main()
