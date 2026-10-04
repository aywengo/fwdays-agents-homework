"""MCP server: hourly Polish energy prices (RCE/PSE) from the godzinowe.pl API.

The API is free for private use and rate-limited, so every successful
response is cached on disk per date. A cached day is returned when the API
answers 429 or is unreachable.
"""

from __future__ import annotations

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

log = logging.getLogger("home_mcp.prices")

API_URL = os.getenv("PRICES_API_URL", "https://godzinowe.pl/api.php")
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


async def fetch_day(day: dt.date, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    cached = _read_cache(day)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if cached and cached.get("available"):
        return {**cached, "cache": "hit"}
    if cached and not cached.get("available") and now - cached.get("fetched_at", 0) < UNAVAILABLE_RETRY_SECONDS:
        return {**cached, "cache": "hit"}

    owns = client is None
    client = client or httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT})
    try:
        resp = await client.get(API_URL, params=_action_for(day))
        if resp.status_code == 429:
            if cached:
                return {**cached, "cache": "stale", "warning": "rate limited by API; returned cached data"}
            raise PricesError("godzinowe.pl rate limit (HTTP 429); try again in a few minutes")
        resp.raise_for_status()
        result = normalize(resp.json(), day)
    except (httpx.HTTPError, ValueError) as exc:
        if cached:
            return {**cached, "cache": "stale", "warning": f"API error: {exc}"}
        raise PricesError(f"Could not fetch prices for {day}: {exc}") from exc
    finally:
        if owns:
            await client.aclose()

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


def main() -> None:
    run(server)


if __name__ == "__main__":
    main()
