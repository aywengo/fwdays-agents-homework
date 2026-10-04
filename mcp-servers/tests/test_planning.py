import asyncio
import importlib
import json

import pytest

from conftest import load
from home_mcp import prices_server as ps
from home_mcp import solax_http as sx

RECORDS = load("godzinowe_today.json")["data"]["records"]


# ---------------------------------------------------------------- trader: charge window
def test_window_on_real_prices():
    plan = ps.plan_charge_window(RECORDS, energy_kwh=6, max_charge_kw=3, earliest_hour=8)
    assert plan["hours_needed"] == 2
    assert (plan["charge_start"], plan["charge_end"]) == ("12:00", "14:00")  # 0.020 + 0.039
    assert (plan["peak_start"], plan["peak_end"]) == ("19:00", "21:00")      # 1.007 + 0.956
    assert plan["recommended"] is True
    assert plan["spread_pln_kwh"] == pytest.approx(0.9818 - 0.0294 / 0.9, abs=1e-3)
    assert plan["grid_energy_kwh"] == pytest.approx(6.67, abs=0.01)


def test_window_respects_earliest_and_latest():
    plan = ps.plan_charge_window(RECORDS, energy_kwh=3, max_charge_kw=3, earliest_hour=14, latest_end_hour=17)
    assert plan["charge_start"] == "14:00"  # 12-13 and 13-14 are no longer allowed
    late = ps.plan_charge_window(RECORDS, energy_kwh=9, max_charge_kw=3, earliest_hour=15, latest_end_hour=17)
    assert late["recommended"] is False and "no 3h window" in late["reason"]


def test_small_spread_not_recommended():
    flat = [{"hour": f"{h:02d}-{h + 1:02d}", "price_per_kwh": 0.50 + (0.05 if h >= 17 else 0)} for h in range(24)]
    plan = ps.plan_charge_window(flat, energy_kwh=2, max_charge_kw=3)
    assert plan["recommended"] is False and "spread too small" in plan["reason"]


def test_negative_price_always_recommended():
    neg = [{"hour": f"{h:02d}-{h + 1:02d}", "price_per_kwh": -0.05 if h == 13 else 0.40} for h in range(24)]
    plan = ps.plan_charge_window(neg, energy_kwh=2, max_charge_kw=3)
    assert plan["recommended"] is True and plan["charge_start"] == "13:00"


def test_nothing_needed():
    assert ps.plan_charge_window(RECORDS, energy_kwh=0, max_charge_kw=3)["recommended"] is False


# ---------------------------------------------------------------- dispatcher: need + settings
def test_sunny_day_needs_no_grid():
    r = sx.estimate_need(soc_pct=40, pv_estimate_kwh=30, daily_consumption_kwh=14, capacity_kwh=10)
    assert r["grid_charge_kwh"] == 0 and r["needed"] is False


def test_cloudy_day_needs_grid():
    r = sx.estimate_need(soc_pct=25, pv_estimate_kwh=3, daily_consumption_kwh=14, capacity_kwh=10)
    # usable 1.0, daytime use 6.3 -> projected 0; evening/night need 7.7; room to 90% = 6.5
    assert r["grid_charge_kwh"] == 6.5 and r["needed"] is True


def test_need_never_exceeds_room():
    r = sx.estimate_need(soc_pct=85, pv_estimate_kwh=0, daily_consumption_kwh=30, capacity_kwh=10)
    assert r["grid_charge_kwh"] == 0.5


def test_tou_settings_are_explicit():
    s = sx.tou_settings("12:00", "14:00", min_soc=15, target_soc=90)
    a, b = s["apply_args"], s["baseline_args"]
    assert a["charge_from_grid_enable"] == 1 and a["charge_upper_soc"] == 90 and a["min_soc"] == 15
    assert (a["charge_start_time_period1"], a["charge_end_time_period1"]) == ("12:00", "14:00")
    assert b["charge_from_grid_enable"] == 0 and "charge_start_time_period1" not in b
    assert sx.tou_settings(None, None, 15, 90)["apply_args"] is None


@pytest.mark.parametrize("start,end", [("12:00", None), ("25:00", "26:00"), ("14:00", "12:00"), ("12", "14")])
def test_tou_settings_rejects_bad_windows(start, end):
    with pytest.raises(sx.PlanningError):
        sx.tou_settings(start, end, 15, 90)


def test_planning_tools_registered_and_use_env(monkeypatch):
    monkeypatch.setenv("SOLAX_CLIENT_ID", "x")
    monkeypatch.setenv("SOLAX_CLIENT_SECRET", "y")
    monkeypatch.setenv("BATTERY_CAPACITY_KWH", "10")
    monkeypatch.setenv("BATTERY_MAX_CHARGE_KW", "3.5")
    monkeypatch.setenv("BATTERY_MIN_SOC", "20")
    monkeypatch.setenv("HOME_DAILY_CONSUMPTION_KWH", "14")
    import solax_cloud_mcp.server as upstream

    importlib.reload(upstream)
    server = sx.load_server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"estimate_grid_charge_need", "build_tou_settings"} <= names
    need = _call(server, "estimate_grid_charge_need", {"soc_pct": 25, "pv_estimate_kwh": 3})
    assert need["max_charge_kw"] == 3.5 and need["assumptions"]["min_soc"] == 20
    settings = _call(server, "build_tou_settings", {"charge_start": "12:00", "charge_end": "14:00"})
    assert settings["apply_args"]["min_soc"] == 20


def _call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    if isinstance(result, tuple):  # (content, structured) on newer FastMCP
        return result[1].get("result", result[1])
    return json.loads(result[0].text)
