import datetime as dt

import httpx
import pytest
import respx

from conftest import load
from home_mcp import prices_server as ps


def test_summary_from_real_response():
    result = ps.normalize(load("godzinowe_today.json"), dt.date(2026, 10, 4))
    s = result["summary"]
    assert result["available"] and len(result["records"]) == 24
    assert s["min"] == {"hour": "12-13", "pln_kwh": 0.02}
    assert s["max"]["hour"] == "19-20"
    assert s["cheapest_3h_window"] == {"start_hour": "11-12", "end_hour": "13-14", "avg_pln_kwh": 0.0551}
    assert s["negative_or_zero_hours"] == []  # 0.02001 rounds to 0.02, not zero
    assert s["classification_counts"]["BARDZO NISKA"] == 4


def test_zero_rounding_rule():
    recs = [{"hour": "00-01", "price_per_kwh": 0.004}, {"hour": "01-02", "price_per_kwh": 0.5}]
    assert ps.summarize(recs)["negative_or_zero_hours"] == ["00-01"]


def test_unavailable_tomorrow():
    result = ps.normalize(load("godzinowe_tomorrow_unavailable.json"), dt.date(2026, 10, 5))
    assert result["available"] is False and result["summary"] == {}


@respx.mock
async def test_fetch_caches_and_survives_rate_limit(monkeypatch):
    day = dt.date(2026, 10, 4)
    monkeypatch.setattr(ps, "_today", lambda: day)
    route = respx.get(ps.API_URL).mock(return_value=httpx.Response(200, json=load("godzinowe_today.json")))
    first = await ps.fetch_day(day)
    assert first["cache"] == "miss" and route.call_count == 1
    second = await ps.fetch_day(day)
    assert second["cache"] == "hit" and route.call_count == 1


@respx.mock
async def test_rate_limit_without_cache_is_clear_error(monkeypatch):
    day = dt.date(2026, 10, 4)
    monkeypatch.setattr(ps, "_today", lambda: day)
    respx.get(ps.API_URL).mock(return_value=httpx.Response(429, text="Too Many Requests"))
    with pytest.raises(ps.PricesError, match="rate limit"):
        await ps.fetch_day(day)


def test_parse_day_accepts_ukrainian(monkeypatch):
    monkeypatch.setattr(ps, "_today", lambda: dt.date(2026, 10, 4))
    assert ps._parse_day("завтра") == dt.date(2026, 10, 5)
    with pytest.raises(ps.PricesError):
        ps._parse_day("someday")
