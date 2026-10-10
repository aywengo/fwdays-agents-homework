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


def pse_payload(day: str, hours: int = 24) -> dict:
    """PSE-shaped response: 4 quarters per hour, price = 100*hour + quarter PLN/MWh."""
    rows = []
    for h in range(hours):
        for q in range(4):
            start = f"{h:02d}:{q * 15:02d}"
            rows.append({"period": f"{start} - next", "rce_pln": 100.0 * h + q, "business_date": day})
    return {"value": rows}


def test_pse_quarters_averaged_to_hours():
    result = ps.normalize_pse(pse_payload("2026-10-10"), dt.date(2026, 10, 10))
    assert result["available"] and len(result["records"]) == 24
    h1 = result["records"][1]
    assert h1["hour"] == "01-02" and h1["price_pln_mwh"] == 101.5 and h1["price_per_kwh"] == 0.1015
    assert h1["classification"] == "BARDZO NISKA"
    assert result["records"][0]["classification"] == "ZERO"  # 1.5 PLN/MWh -> 0.0015 PLN/kWh
    assert result["summary"]["min"]["hour"] == "00-01"


def test_pse_incomplete_day_is_unavailable():
    assert ps.normalize_pse(pse_payload("2026-10-11", hours=5), dt.date(2026, 10, 11))["available"] is False


@pytest.mark.parametrize("price,label", [(-0.01, "UJEMNA"), (0.004, "ZERO"), (0.2, "NISKA"),
                                         (0.6, "WYSOKA"), (1.0, "BARDZO WYSOKA"), (2.0, "EKSTREMALNA")])
def test_classify_matches_godzinowe_thresholds(price, label):
    assert ps.classify(price) == label


@respx.mock
async def test_falls_back_to_pse_when_godzinowe_has_no_data(monkeypatch):
    day = dt.date(2026, 10, 10)
    monkeypatch.setattr(ps, "_today", lambda: day)
    respx.get(ps.API_URL).mock(return_value=httpx.Response(
        200, json={"success": False, "error": "No data available for 2026-10-10"}))
    pse = respx.get(ps.PSE_API_URL).mock(return_value=httpx.Response(200, json=pse_payload("2026-10-10")))
    result = await ps.fetch_day(day)
    assert result["available"] and result["source"].startswith("PSE")
    assert pse.calls[0].request.url.params["$filter"] == "business_date eq '2026-10-10'"
    assert result["warnings"][0].startswith("godzinowe.pl:")


@respx.mock
async def test_rate_limit_falls_back_to_pse(monkeypatch):
    day = dt.date(2026, 10, 4)
    monkeypatch.setattr(ps, "_today", lambda: day)
    respx.get(ps.API_URL).mock(return_value=httpx.Response(429, text="Too Many Requests"))
    respx.get(ps.PSE_API_URL).mock(return_value=httpx.Response(200, json=pse_payload("2026-10-04")))
    result = await ps.fetch_day(day)
    assert result["available"] and "rate limit" in result["warnings"][0]


@respx.mock
async def test_both_sources_failing_is_clear_error(monkeypatch):
    day = dt.date(2026, 10, 4)
    monkeypatch.setattr(ps, "_today", lambda: day)
    respx.get(ps.API_URL).mock(return_value=httpx.Response(429, text="Too Many Requests"))
    respx.get(ps.PSE_API_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ps.PricesError, match="No price source available"):
        await ps.fetch_day(day)


@respx.mock
async def test_not_published_from_both_stays_unavailable(monkeypatch):
    day = dt.date(2026, 10, 4)
    monkeypatch.setattr(ps, "_today", lambda: day)
    tomorrow = day + dt.timedelta(days=1)
    respx.get(ps.API_URL).mock(return_value=httpx.Response(200, json=load("godzinowe_tomorrow_unavailable.json")))
    respx.get(ps.PSE_API_URL).mock(return_value=httpx.Response(200, json={"value": []}))
    result = await ps.fetch_day(tomorrow)
    assert result["available"] is False and "warnings" not in result


def test_parse_day_accepts_ukrainian(monkeypatch):
    monkeypatch.setattr(ps, "_today", lambda: dt.date(2026, 10, 4))
    assert ps._parse_day("завтра") == dt.date(2026, 10, 5)
    with pytest.raises(ps.PricesError):
        ps._parse_day("someday")
