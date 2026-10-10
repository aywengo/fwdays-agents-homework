"""MCP server: hourly Polish energy prices (RCE/PSE) from the godzinowe.pl API.

The API is free for private use and rate-limited, so every successful
response is cached on disk per date. A cached day is returned when the API
answers 429 or is unreachable.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .common import atomic_write_json, run, state_dir

log = logging.getLogger("home_mcp.prices")

API_URL = os.getenv("PRICES_API_URL", "https://godzinowe.pl/api.php")
# Fallback: the original PSE RCE data that godzinowe.pl aggregates.
PSE_API_URL = os.getenv("PSE_API_URL", "https://api.raporty.pse.pl/api/rce-pln")
TZ = ZoneInfo(os.getenv("HOME_TZ", "Europe/Warsaw"))
USER_AGENT = "fwdays-agents-homework/0.1 (private home energy assistant)"
# Tomorrow's prices usually appear after 13:00-14:00; re-check at most this often.
UNAVAILABLE_RETRY_SECONDS = 30 * 60

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
server = FastMCP("rce-prices")


class PricesError(RuntimeError):
    pass


def _today() -> dt.date:
    return dt.datetime.now(TZ).date()


def _cache_path(day: dt.date):
    return state_dir() / "prices" / f"{day.isoformat()}.json"


def _read_cache(day: dt.date) -> dict | None:
    path = _cache_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _action_for(day: dt.date) -> dict[str, str]:
    today = _today()
    if day == today:
        return {"action": "today_classified"}
    if day == today + dt.timedelta(days=1):
        return {"action": "tomorrow_classified"}
    return {"action": "date", "date": day.isoformat()}


def summarize(records: list[dict]) -> dict[str, Any]:
    """Deterministic summary so the model does not have to do arithmetic."""
    if not records:
        return {}
    prices = [(r["hour"], float(r["price_per_kwh"])) for r in records if r.get("price_per_kwh") is not None]
    if not prices:
        return {}
    ordered = sorted(prices, key=lambda item: item[1])
    values = [p for _, p in prices]
    avg = sum(values) / len(values)

    def cheapest_window(length: int) -> dict | None:
        if len(prices) < length:
            return None
        best = min(range(len(prices) - length + 1),
                   key=lambda i: sum(p for _, p in prices[i:i + length]))
        window = prices[best:best + length]
        return {"start_hour": window[0][0], "end_hour": window[-1][0],
                "avg_pln_kwh": round(sum(p for _, p in window) / length, 4)}

    return {
        "unit": "PLN/kWh net (RCE)",
        "hours": len(prices),
        "min": {"hour": ordered[0][0], "pln_kwh": round(ordered[0][1], 4)},
        "max": {"hour": ordered[-1][0], "pln_kwh": round(ordered[-1][1], 4)},
        "avg_pln_kwh": round(avg, 4),
        "cheapest_hours": [{"hour": h, "pln_kwh": round(p, 4)} for h, p in ordered[:4]],
        "most_expensive_hours": [{"hour": h, "pln_kwh": round(p, 4)} for h, p in ordered[-4:][::-1]],
        "negative_or_zero_hours": [h for h, p in prices if round(p, 2) <= 0],
        "cheapest_3h_window": cheapest_window(3),
        "classification_counts": _count(r.get("classification") for r in records),
    }


def _count(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        if item:
            out[item] = out.get(item, 0) + 1
    return out


def normalize(payload: dict, day: dt.date) -> dict[str, Any]:
    if not payload.get("success", False):
        raise PricesError(f"API returned an unsuccessful response: {str(payload)[:300]}")
    data = payload.get("data")
    if isinstance(data, list):  # ?action=date returns a bare record list on some versions
        data = {"date": day.isoformat(), "available": bool(data), "records": data}
    data = data or {}
    records = [
        {
            "hour": r.get("hour"),
            "price_pln_mwh": r.get("price"),
            "price_per_kwh": r.get("price_per_kwh"),
            "classification": r.get("classification"),
        }
        for r in data.get("records") or []
    ]
    available = bool(data.get("available", bool(records))) and bool(records)
    return {
        "date": data.get("date", day.isoformat()),
        "available": available,
        "source": "godzinowe.pl (PSE RCE, 15-min values averaged to hours)",
        "records": records,
        "summary": summarize(records) if available else {},
    }


# Thresholds of the godzinowe.pl classification (PLN/kWh), reused for PSE data.
_CLASSES = ((0.15, "BARDZO NISKA"), (0.35, "NISKA"), (0.55, "ŚREDNIA"),
            (0.75, "WYSOKA"), (1.5, "BARDZO WYSOKA"))


def classify(price_per_kwh: float) -> str:
    if price_per_kwh < 0:
        return "UJEMNA"
    if round(price_per_kwh, 2) == 0:
        return "ZERO"
    for limit, label in _CLASSES:
        if price_per_kwh < limit:
            return label
    return "EKSTREMALNA"


def normalize_pse(payload: dict, day: dt.date) -> dict[str, Any]:
    """PSE RCE 15-minute values (PLN/MWh) -> hourly records like godzinowe.pl."""
    quarters: dict[int, list[float]] = {}
    for row in payload.get("value") or []:
        period, price = str(row.get("period") or ""), row.get("rce_pln")
        if price is None or len(period) < 2 or not period[:2].isdigit():
            continue
        quarters.setdefault(int(period[:2]), []).append(float(price))
    records = []
    for hour in sorted(quarters):
        avg_mwh = sum(quarters[hour]) / len(quarters[hour])
        per_kwh = avg_mwh / 1000
        records.append({"hour": f"{hour:02d}-{hour + 1:02d}", "price_pln_mwh": round(avg_mwh, 2),
                        "price_per_kwh": round(per_kwh, 5), "classification": classify(per_kwh)})
    available = len(records) >= 23  # 23/24/25 hours depending on DST
    return {
        "date": day.isoformat(),
        "available": available,
        "source": "PSE RCE (api.raporty.pse.pl), 15-min values averaged to hours",
        "records": records if available else [],
        "summary": summarize(records) if available else {},
    }


async def _from_godzinowe(day: dt.date, client: httpx.AsyncClient) -> dict[str, Any]:
    resp = await client.get(API_URL, params=_action_for(day))
    if resp.status_code == 429:
        raise PricesError("godzinowe.pl rate limit (HTTP 429)")
    resp.raise_for_status()
    return normalize(resp.json(), day)


async def _from_pse(day: dt.date, client: httpx.AsyncClient) -> dict[str, Any]:
    resp = await client.get(PSE_API_URL, params={
        "$filter": f"business_date eq '{day.isoformat()}'", "$first": 200})
    resp.raise_for_status()
    return normalize_pse(resp.json(), day)


async def fetch_day(day: dt.date, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """godzinowe.pl first; PSE (the original source) when it fails or has no data."""
    cached = _read_cache(day)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if cached and cached.get("available"):
        return {**cached, "cache": "hit"}
    if cached and not cached.get("available") and now - cached.get("fetched_at", 0) < UNAVAILABLE_RETRY_SECONDS:
        return {**cached, "cache": "hit"}

    owns = client is None
    client = client or httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT})
    errors: list[str] = []
    result: dict[str, Any] | None = None
    try:
        for name, source in (("godzinowe.pl", _from_godzinowe), ("PSE", _from_pse)):
            try:
                candidate = await source(day, client)
            except (httpx.HTTPError, ValueError, PricesError) as exc:
                errors.append(f"{name}: {exc}")
                log.warning("prices source %s failed for %s: %s", name, day, exc)
                continue
            if candidate.get("available"):
                result = candidate
                break
            result = result or candidate  # remember "not published yet"
    finally:
        if owns:
            await client.aclose()

    if result is None:
        if cached:
            return {**cached, "cache": "stale", "warning": "; ".join(errors)}
        raise PricesError(f"No price source available for {day}: {'; '.join(errors)}")
    if errors:
        result["warnings"] = errors
    result["fetched_at"] = now
    atomic_write_json(_cache_path(day), result)
    return {**result, "cache": "miss"}


def _parse_day(day: str) -> dt.date:
    value = (day or "today").strip().lower()
    if value in {"today", "сьогодні", "dzisiaj"}:
        return _today()
    if value in {"tomorrow", "завтра", "jutro"}:
        return _today() + dt.timedelta(days=1)
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise PricesError("day must be 'today', 'tomorrow' or YYYY-MM-DD") from exc


@server.tool(annotations=READ_ONLY)
async def get_prices(day: str = "today", include_hours: bool = True) -> dict:
    """Hourly RCE electricity prices for Poland (PLN/kWh, net) with a computed summary.

    Args:
        day: "today", "tomorrow" or an ISO date (YYYY-MM-DD). Tomorrow's prices are
             usually published after 13:00-14:00 Europe/Warsaw; before that
             `available` is false.
        include_hours: include all 24 hourly records (set false for a compact answer).

    Returns: date, available, summary (min/max/avg, cheapest and most expensive hours,
    negative-price hours, cheapest 3-hour window, classification counts) and records.
    """
    result = await fetch_day(_parse_day(day))
    if not include_hours:
        result = {k: v for k, v in result.items() if k != "records"}
    return result


@server.tool(annotations=READ_ONLY)
async def get_current_price() -> dict:
    """Price for the current hour (Europe/Warsaw) and how it compares to today's average."""
    today = await fetch_day(_today())
    if not today.get("available"):
        return {"available": False, "date": today.get("date")}
    hour = dt.datetime.now(TZ).hour
    label = f"{hour:02d}-{hour + 1:02d}"  # API uses "23-24" for the last hour
    record = next((r for r in today["records"] if r["hour"] == label), None)
    avg = today["summary"].get("avg_pln_kwh")
    out = {"date": today["date"], "hour": label, "record": record, "day_avg_pln_kwh": avg}
    if record and avg:
        out["vs_avg_percent"] = round((record["price_per_kwh"] - avg) / avg * 100, 1)
    return out


def _start_hour(label: str) -> int:
    return int(str(label).split("-", 1)[0])


def _clock(hour: int) -> str:
    return "23:59" if hour >= 24 else f"{hour:02d}:00"


def plan_charge_window(
    records: list[dict],
    energy_kwh: float,
    max_charge_kw: float,
    earliest_hour: int = 0,
    latest_end_hour: int = 17,
    peak_end_hour: int = 23,
    efficiency: float = 0.9,
    min_spread_pln_kwh: float = 0.2,
) -> dict[str, Any]:
    """Cheapest contiguous grid-charge window vs. the most expensive later window.

    Pure function (no I/O) so the decision is deterministic and testable.
    Grid energy bought = energy_kwh / efficiency; it replaces energy that would
    otherwise be imported during the evening peak window of the same length.
    """
    if energy_kwh <= 0:
        return {"recommended": False, "reason": "no grid charge needed"}
    if max_charge_kw <= 0:
        raise PricesError("max_charge_kw must be positive")
    hours = max(1, math.ceil(energy_kwh / max_charge_kw))
    prices = {_start_hour(r["hour"]): float(r["price_per_kwh"])
              for r in records if r.get("price_per_kwh") is not None}

    def windows(start: int, end: int) -> list[tuple[int, float]]:
        out = []
        for h in range(start, end - hours + 1):
            span = [prices.get(x) for x in range(h, h + hours)]
            if all(p is not None for p in span):
                out.append((h, sum(span) / hours))
        return out

    charge = windows(max(0, earliest_hour), min(24, latest_end_hour))
    if not charge:
        return {"recommended": False, "hours_needed": hours,
                "reason": f"no {hours}h window between {_clock(earliest_hour)} and {_clock(latest_end_hour)}"}
    c_start, c_avg = min(charge, key=lambda w: w[1])
    peak = windows(latest_end_hour, min(24, peak_end_hour + 1))
    p_start, p_avg = max(peak, key=lambda w: w[1]) if peak else (None, None)

    effective = c_avg / efficiency
    spread = None if p_avg is None else p_avg - effective
    bought = energy_kwh / efficiency
    result = {
        "hours_needed": hours,
        "energy_to_battery_kwh": round(energy_kwh, 2),
        "grid_energy_kwh": round(bought, 2),
        "charge_start": _clock(c_start),
        "charge_end": _clock(c_start + hours),
        "charge_avg_pln_kwh": round(c_avg, 4),
        "charge_cost_pln": round(bought * c_avg, 2),
        "peak_start": _clock(p_start) if p_start is not None else None,
        "peak_end": _clock(p_start + hours) if p_start is not None else None,
        "peak_avg_pln_kwh": round(p_avg, 4) if p_avg is not None else None,
        "spread_pln_kwh": round(spread, 4) if spread is not None else None,
        "estimated_saving_pln": round(energy_kwh * spread, 2) if spread is not None else None,
        "min_spread_pln_kwh": min_spread_pln_kwh,
        "efficiency": efficiency,
    }
    if c_avg <= 0:
        result.update(recommended=True, reason="zero or negative prices: charging is paid for or free")
    elif spread is None:
        result.update(recommended=False, reason="no later peak window to compare against")
    elif spread >= min_spread_pln_kwh:
        result.update(recommended=True, reason="peak minus charge price (after losses) exceeds the threshold")
    else:
        result.update(recommended=False, reason="price spread too small to cover battery losses and wear")
    return result


@server.tool(annotations=READ_ONLY)
async def plan_grid_charge(
    energy_kwh: float,
    max_charge_kw: float,
    day: str = "today",
    latest_end_hour: int = 17,
    min_spread_pln_kwh: float = 0.2,
    efficiency: float = 0.9,
) -> dict:
    """Find the cheapest window to charge the battery from the grid and say if it pays off.

    Args:
        energy_kwh: energy to put into the battery from the grid (from the dispatcher's estimate).
        max_charge_kw: maximum grid charging power of the battery/inverter.
        day: "today" or "tomorrow". For today, only hours from the current hour onward are used.
        latest_end_hour: the window must end by this hour (default 17, before the evening peak).
        min_spread_pln_kwh: required margin between the evening peak price and the
            charge price after losses (default 0.20 zl/kWh) to recommend charging.
        efficiency: round-trip efficiency of the battery (default 0.9).

    Returns charge_start/charge_end as HH:MM (ready for the inverter), prices, cost,
    estimated saving, the evening peak window used for comparison, and
    `recommended` with a reason.
    """
    target = _parse_day(day)
    data = await fetch_day(target)
    if not data.get("available"):
        return {"recommended": False, "date": data.get("date"), "reason": "prices not published yet"}
    # Today: start no earlier than the next full hour (the current one has begun).
    earliest = dt.datetime.now(TZ).hour + 1 if target == _today() else 0
    plan = plan_charge_window(data["records"], energy_kwh, max_charge_kw, earliest_hour=earliest,
                              latest_end_hour=latest_end_hour, efficiency=efficiency,
                              min_spread_pln_kwh=min_spread_pln_kwh)
    return {"date": data["date"], **plan}


def main() -> None:
    run(server)


if __name__ == "__main__":
    main()
