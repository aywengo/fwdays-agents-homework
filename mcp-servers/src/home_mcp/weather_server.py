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


# WMO weather interpretation codes (Open-Meteo `weather_code`) -> (English, Ukrainian).
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("clear sky", "ясно"),
    1: ("mainly clear", "переважно ясно"),
    2: ("partly cloudy", "мінлива хмарність"),
    3: ("overcast", "похмуро"),
    45: ("fog", "туман"),
    48: ("rime fog", "туман з інеєм"),
    51: ("light drizzle", "слабка мряка"),
    53: ("drizzle", "мряка"),
    55: ("dense drizzle", "сильна мряка"),
    56: ("freezing drizzle", "крижана мряка"),
    57: ("dense freezing drizzle", "сильна крижана мряка"),
    61: ("light rain", "слабкий дощ"),
    63: ("rain", "дощ"),
    65: ("heavy rain", "сильний дощ"),
    66: ("freezing rain", "крижаний дощ"),
    67: ("heavy freezing rain", "сильний крижаний дощ"),
    71: ("light snow", "слабкий сніг"),
    73: ("snow", "сніг"),
    75: ("heavy snow", "сильний снігопад"),
    77: ("snow grains", "снігова крупа"),
    80: ("light rain showers", "короткочасний дощ"),
    81: ("rain showers", "зливи"),
    82: ("violent rain showers", "сильні зливи"),
    85: ("snow showers", "короткочасний сніг"),
    86: ("heavy snow showers", "сильні снігопади"),
    95: ("thunderstorm", "гроза"),
    96: ("thunderstorm with hail", "гроза з градом"),
    99: ("thunderstorm with heavy hail", "гроза з сильним градом"),
}
# WHO UV index categories: (upper bound exclusive, English, Ukrainian).
UV_LEVELS = ((3, "low", "низький"), (6, "moderate", "помірний"), (8, "high", "високий"),
             (11, "very high", "дуже високий"), (float("inf"), "extreme", "екстремальний"))
PERFORMANCE_RATIO = 0.8
# An hour counts as "productive" when PV gives at least this share of the installed kWp
# (or, without PV_KWP, when irradiance reaches 100 W/m2).
PRODUCTIVE_SHARE = 0.1
RAIN_PROBABILITY_PCT = 50
RAIN_MM = 0.2


def condition(code: Any) -> dict:
    if code is None:
        return {"weather_code": None, "condition": None, "condition_uk": None}
    en, uk = WMO_CODES.get(int(code), (f"code {int(code)}", f"код {int(code)}"))
    return {"weather_code": int(code), "condition": en, "condition_uk": uk}


def uv_level(value: Any) -> dict:
    if value is None:
        return {"uv_level": None, "uv_level_uk": None}
    for limit, en, uk in UV_LEVELS:
        if value < limit:
            return {"uv_level": en, "uv_level_uk": uk}
    return {"uv_level": None, "uv_level_uk": None}  # unreachable


def _parse_local(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ)


def _windows(slots: list[dt.datetime]) -> list[str]:
    """Merge one-hour slots (by start time) into 'HH:MM-HH:MM' ranges."""
    out: list[list[dt.datetime]] = []
    for start in sorted(slots):
        if out and out[-1][1] == start:
            out[-1][1] = start + dt.timedelta(hours=1)
        else:
            out.append([start, start + dt.timedelta(hours=1)])
    return [f"{a:%H:%M}-{'24:00' if b.date() > a.date() else format(b, '%H:%M')}" for a, b in out]


def _slots(hourly: dict) -> list[dict]:
    """Hourly rows as one-hour slots keyed by their START time.

    Open-Meteo reports radiation and precipitation for the hour *preceding* each
    timestamp, so the row at 12:00 describes the 11:00-12:00 slot.
    """
    times = hourly.get("time") or []
    rows = []
    for j, ts in enumerate(times):
        def at(key: str, j: int = j):
            values = hourly.get(key) or []
            return values[j] if j < len(values) else None

        end = _parse_local(ts)
        rows.append({
            "start": end - dt.timedelta(hours=1),
            "end": end,
            "weather_code": at("weather_code"),
            "cloud_cover_pct": at("cloud_cover"),
            "radiation_w_m2": at("shortwave_radiation"),
            "uv_index": at("uv_index"),
            "precip_probability_pct": at("precipitation_probability"),
            "precipitation_mm": at("precipitation"),
            "temp_c": at("temperature_2m"),
        })
    return rows


def _is_wet(slot: dict) -> bool:
    return ((slot["precip_probability_pct"] or 0) >= RAIN_PROBABILITY_PCT
            or (slot["precipitation_mm"] or 0) >= RAIN_MM)


def _pv_kw(slot: dict, pv_kwp: float | None) -> float | None:
    if not pv_kwp or slot["radiation_w_m2"] is None:
        return None
    return round(slot["radiation_w_m2"] / 1000 * pv_kwp * PERFORMANCE_RATIO, 2)


def shape_forecast(body: dict, days: int, pv_kwp: float | None,
                   now: dt.datetime | None = None) -> dict:
    now = (now or dt.datetime.now(TZ)).astimezone(TZ)
    daily = body.get("daily") or {}
    slots = _slots(body.get("hourly") or {})
    out_days = []
    for i, date in enumerate((daily.get("time") or [])[:days]):
        def pick(key: str):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None

        sunrise, sunset = _parse_local(pick("sunrise")), _parse_local(pick("sunset"))
        radiation_mj = pick("shortwave_radiation_sum")
        daylight_s = pick("daylight_duration")
        if daylight_s is None and sunrise and sunset:
            daylight_s = (sunset - sunrise).total_seconds()
        uv_max = pick("uv_index_max")
        day = {
            "date": date,
            **condition(pick("weather_code")),
            "temp_min_c": pick("temperature_2m_min"),
            "temp_max_c": pick("temperature_2m_max"),
            "precipitation_mm": pick("precipitation_sum"),
            "precipitation_hours": pick("precipitation_hours"),
            "precipitation_probability_max_pct": pick("precipitation_probability_max"),
            "wind_max_kmh": pick("wind_speed_10m_max"),
            "gust_max_kmh": pick("wind_gusts_10m_max"),
            "sunrise": f"{sunrise:%H:%M}" if sunrise else None,
            "sunset": f"{sunset:%H:%M}" if sunset else None,
            "daylight_h": round(daylight_s / 3600, 1) if daylight_s is not None else None,
            "sunshine_hours": round(pick("sunshine_duration") / 3600, 1) if pick("sunshine_duration") is not None else None,
            "solar_radiation_kwh_m2": round(radiation_mj / 3.6, 2) if radiation_mj is not None else None,
            "uv_index_max": uv_max,
            **uv_level(uv_max),
        }
        if pv_kwp and day["solar_radiation_kwh_m2"] is not None:
            # Rough yield estimate: irradiation x kWp x performance ratio.
            day["pv_estimate_kwh"] = round(day["solar_radiation_kwh_m2"] * pv_kwp * PERFORMANCE_RATIO, 1)

        day_slots = [s for s in slots if s["start"].date().isoformat() == date]
        if sunrise and sunset:
            light = [s for s in day_slots if s["end"] > sunrise and s["start"] < sunset]
        else:
            light = [s for s in day_slots if (s["radiation_w_m2"] or 0) > 0]
        clouds = [s["cloud_cover_pct"] for s in light if s["cloud_cover_pct"] is not None]
        day["cloud_cover_daylight_avg_pct"] = round(sum(clouds) / len(clouds)) if clouds else None
        day["rain_windows"] = _windows([s["start"] for s in day_slots if _is_wet(s)])
        day["uv_windows_3plus"] = _windows([s["start"] for s in light if (s["uv_index"] or 0) >= 3])

        if pv_kwp:
            productive = [s for s in light if (_pv_kw(s, pv_kwp) or 0) >= PRODUCTIVE_SHARE * pv_kwp]
        else:
            productive = [s for s in light if (s["radiation_w_m2"] or 0) >= 100]
        if productive:
            day["pv_window"] = f"{productive[0]['start']:%H:%M}-{productive[-1]['end']:%H:%M}"
            peak = max(productive, key=lambda s: s["radiation_w_m2"] or 0)
            day["pv_peak_hour"] = f"{peak['start']:%H:%M}"
        else:
            day["pv_window"] = None
            day["pv_peak_hour"] = None

        day["daylight_hours"] = [{
            "time": f"{s['start']:%H:%M}",
            "condition_uk": condition(s["weather_code"])["condition_uk"],
            "cloud_cover_pct": s["cloud_cover_pct"],
            "radiation_w_m2": s["radiation_w_m2"],
            "uv_index": s["uv_index"],
            "precip_probability_pct": s["precip_probability_pct"],
            "precipitation_mm": s["precipitation_mm"],
            "temp_c": s["temp_c"],
            **({"pv_kw": _pv_kw(s, pv_kwp)} if pv_kwp else {}),
        } for s in light]

        if date == now.date().isoformat():
            current = next((s for s in day_slots if s["start"] <= now < s["end"]), None)
            is_day = bool(sunrise and sunset and sunrise <= now < sunset)
            day["now"] = {
                "time": f"{now:%H:%M}",
                "is_daylight": is_day,
                "minutes_to_sunset": int((sunset - now).total_seconds() // 60) if is_day else None,
                "minutes_to_sunrise": int((sunrise - now).total_seconds() // 60) if sunrise and now < sunrise else None,
                **({k: current[k] for k in ("cloud_cover_pct", "uv_index", "temp_c", "precipitation_mm")} if current else {}),
                **(condition(current["weather_code"]) if current else {}),
            }
            if pv_kwp:
                remaining = 0.0
                for s in light:
                    if s["end"] <= now:
                        continue
                    share = min(1.0, (s["end"] - max(now, s["start"])).total_seconds() / 3600)
                    remaining += (_pv_kw(s, pv_kwp) or 0) * share
                day["pv_remaining_kwh"] = round(remaining, 1)
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

    Returns per day (times are local HH:MM):
    - condition / condition_uk (WMO weather code), temperature range;
    - precipitation (mm, hours, max probability) and `rain_windows` (hours with
      >=50% probability or >=0.2 mm); wind and gusts;
    - daylight: sunrise, sunset, daylight_h; sunshine_hours, solar irradiation (kWh/m2);
    - UV: uv_index_max, uv_level / uv_level_uk (WHO scale), uv_windows_3plus;
    - cloud_cover_daylight_avg_pct; pv_window (productive hours) and pv_peak_hour;
    - daylight_hours: one-hour slots between sunrise and sunset (time = slot start)
      with condition, cloud cover, irradiance, UV, rain, temperature, pv_kw;
    - pv_estimate_kwh for the whole day when PV_KWP is configured;
    - today only: `now` (current condition, is_daylight, minutes to sunset or
      sunrise) and pv_remaining_kwh (PV still expected from now until sunset).
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
                "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                "precipitation_hours", "precipitation_probability_max", "wind_speed_10m_max",
                "wind_gusts_10m_max", "sunrise", "sunset", "daylight_duration",
                "sunshine_duration", "shortwave_radiation_sum", "uv_index_max",
            ]),
            "hourly": ",".join([
                "temperature_2m", "weather_code", "cloud_cover", "shortwave_radiation",
                "precipitation_probability", "precipitation", "uv_index",
            ]),
        })
        if resp.status_code >= 400:
            raise WeatherError(f"Open-Meteo request failed (HTTP {resp.status_code})")
        pv = os.getenv("PV_KWP")
        return shape_forecast(resp.json(), days, float(pv) if pv else None)


def main() -> None:
    run(server)


if __name__ == "__main__":
    main()
