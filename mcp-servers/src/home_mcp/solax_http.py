"""Run the upstream SolaX Cloud MCP server (mouldiwarp/solax-cloud-mcp) with our transport.

Upstream only ships stdio MCP plus a separate REST API. This wrapper reuses
its FastMCP instance unchanged and serves it over streamable HTTP with the same
bearer-token guard as the other home MCP servers, so it can live in its own
container on the private Compose network.

It also adds two pure planning tools for the dispatcher (no inverter calls):
- estimate_grid_charge_need: how much energy the battery should take from the
  grid today, from SOC, PV forecast and typical consumption;
- build_tou_settings: the exact arguments for set_battery_self_use_mode for a
  proposed charge window and for the household baseline, so the model never
  relies on the upstream defaults (charge_from_grid_enable=1, min_soc=10).

Control boundary: when SOLAX_ALLOW_CONTROL is not "true", the write tool
`set_battery_self_use_mode` is removed from the server before it starts. The
OpenClaw config applies the same filter, so the boundary holds on both sides.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .common import run

log = logging.getLogger("home_mcp.solax")
CONTROL_TOOL = "set_battery_self_use_mode"
# Share of daily consumption used before ~17:00 (the rest is evening + night).
DAYTIME_SHARE = 0.45
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PlanningError(ValueError):
    pass


def control_allowed() -> bool:
    return os.getenv("SOLAX_ALLOW_CONTROL", "false").strip().lower() in {"1", "true", "yes"}


def _env_float(name: str, default: float | None = None) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise PlanningError(f"{name} must be a number, got {raw!r}") from exc


def battery_settings() -> dict[str, float | None]:
    return {
        "capacity_kwh": _env_float("BATTERY_CAPACITY_KWH"),
        "max_charge_kw": _env_float("BATTERY_MAX_CHARGE_KW"),
        "min_soc": _env_float("BATTERY_MIN_SOC", 15),
        "target_soc": _env_float("BATTERY_TARGET_SOC", 90),
        "daily_consumption_kwh": _env_float("HOME_DAILY_CONSUMPTION_KWH"),
    }


def estimate_need(
    soc_pct: float,
    pv_estimate_kwh: float,
    daily_consumption_kwh: float,
    capacity_kwh: float,
    min_soc: float = 15,
    target_soc: float = 90,
) -> dict[str, Any]:
    """Energy (kWh) to add from the grid so the battery covers evening + night.

    Model (deliberately simple and explainable):
      usable_now      = capacity x (soc - min_soc)
      daytime_use     = daily x DAYTIME_SHARE,  evening_night_use = daily - daytime_use
      projected_17h   = clamp(usable_now + pv - daytime_use, 0, capacity x (target - min_soc))
      grid_kwh        = clamp(evening_night_use - projected_17h, 0, room left after PV, room up to target now)
    """
    if capacity_kwh <= 0:
        raise PlanningError("battery capacity must be positive")
    if not 0 <= soc_pct <= 100:
        raise PlanningError("soc_pct must be 0..100")
    if not min_soc < target_soc <= 100:
        raise PlanningError("need min_soc < target_soc <= 100")
    usable_max = capacity_kwh * (target_soc - min_soc) / 100
    usable_now = max(0.0, capacity_kwh * (soc_pct - min_soc) / 100)
    daytime_use = daily_consumption_kwh * DAYTIME_SHARE
    evening_night_use = daily_consumption_kwh - daytime_use
    projected = min(usable_max, max(0.0, usable_now + max(0.0, pv_estimate_kwh) - daytime_use))
    room_now = max(0.0, capacity_kwh * (target_soc - soc_pct) / 100)
    # Grid energy can only fill what PV leaves free, and never above the target SOC.
    grid_kwh = min(max(0.0, evening_night_use - projected), usable_max - projected, room_now)
    return {
        "grid_charge_kwh": round(grid_kwh, 2),
        "needed": grid_kwh >= 0.5,
        "usable_now_kwh": round(usable_now, 2),
        "projected_usable_at_17h_kwh": round(projected, 2),
        "evening_night_need_kwh": round(evening_night_use, 2),
        "daytime_use_kwh": round(daytime_use, 2),
        "pv_estimate_kwh": round(pv_estimate_kwh, 2),
        "assumptions": {
            "capacity_kwh": capacity_kwh, "min_soc": min_soc, "target_soc": target_soc,
            "daily_consumption_kwh": daily_consumption_kwh, "daytime_share": DAYTIME_SHARE,
        },
    }


def tou_settings(charge_start: str | None, charge_end: str | None, min_soc: int,
                 target_soc: int) -> dict[str, Any]:
    """Exact arguments for set_battery_self_use_mode: proposal and baseline."""
    baseline = {
        "min_soc": min_soc,
        "charge_upper_soc": 100,
        "charge_from_grid_enable": 0,
        "discharge_start_time_period1": "00:00",
        "discharge_end_time_period1": "23:59",
        "enable_time_period2": 0,
    }
    if not charge_start and not charge_end:
        return {"apply_args": None, "baseline_args": baseline}
    for value in (charge_start, charge_end):
        if not value or not _HHMM.match(value):
            raise PlanningError("charge_start and charge_end must both be HH:MM (00:00-23:59)")
    if charge_start >= charge_end:
        raise PlanningError("charge window must start before it ends on the same day")
    apply_args = {
        "min_soc": min_soc,
        "charge_upper_soc": target_soc,
        "charge_from_grid_enable": 1,
        "charge_start_time_period1": charge_start,
        "charge_end_time_period1": charge_end,
        "discharge_start_time_period1": "00:00",
        "discharge_end_time_period1": "23:59",
        "enable_time_period2": 0,
    }
    return {"apply_args": apply_args, "baseline_args": baseline}


def register_planning_tools(server: Any) -> None:
    from mcp.types import ToolAnnotations

    pure = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                           openWorldHint=False)

    @server.tool(annotations=pure)
    async def estimate_grid_charge_need(
        soc_pct: float,
        pv_estimate_kwh: float,
        daily_consumption_kwh: float | None = None,
    ) -> dict:
        """Estimate how much energy (kWh) to charge from the grid today. Pure calculation.

        Args:
            soc_pct: current battery SOC (%) from get_realtime_data.
            pv_estimate_kwh: today's PV estimate from weather-cast.
            daily_consumption_kwh: typical daily house consumption (e.g. average of
                recent days from memory). Falls back to HOME_DAILY_CONSUMPTION_KWH.

        Uses BATTERY_CAPACITY_KWH, BATTERY_MIN_SOC, BATTERY_TARGET_SOC and returns
        grid_charge_kwh, `needed`, max_charge_kw and the intermediate figures.
        """
        cfg = battery_settings()
        if not cfg["capacity_kwh"]:
            raise PlanningError("BATTERY_CAPACITY_KWH is not configured")
        daily = daily_consumption_kwh or cfg["daily_consumption_kwh"]
        if not daily:
            raise PlanningError("pass daily_consumption_kwh or configure HOME_DAILY_CONSUMPTION_KWH")
        result = estimate_need(soc_pct, pv_estimate_kwh, daily, cfg["capacity_kwh"],
                               cfg["min_soc"], cfg["target_soc"])
        result["max_charge_kw"] = cfg["max_charge_kw"]
        return result

    @server.tool(annotations=pure)
    async def build_tou_settings(charge_start: str | None = None, charge_end: str | None = None) -> dict:
        """Exact set_battery_self_use_mode arguments for a charge window and for the baseline.

        Args:
            charge_start, charge_end: HH:MM grid-charge window (from trader's plan), or
                omit both to get only the baseline.

        Returns `apply_args` (grid charging in the window up to BATTERY_TARGET_SOC,
        discharge allowed all day) and `baseline_args` (self-use, no grid charging).
        Pass these dictionaries unchanged to set_battery_self_use_mode; never rely
        on that tool's own defaults.
        """
        cfg = battery_settings()
        return tou_settings(charge_start, charge_end, int(cfg["min_soc"]), int(cfg["target_soc"]))


def load_server():
    # Upstream validates SOLAX_CLIENT_ID / SOLAX_CLIENT_SECRET at import time.
    from solax_cloud_mcp.server import server

    from mcp.types import ToolAnnotations

    tools = server._tool_manager._tools  # FastMCP 1.x registry; upstream does not annotate
    tools["get_realtime_data"].annotations = ToolAnnotations(
        title="SolaX realtime data", readOnlyHint=True, destructiveHint=False,
        idempotentHint=True, openWorldHint=True)
    if CONTROL_TOOL in tools:
        tools[CONTROL_TOOL].annotations = ToolAnnotations(
            title="Change battery work mode", readOnlyHint=False, destructiveHint=True,
            idempotentHint=True, openWorldHint=True)
    if not control_allowed():
        server.remove_tool(CONTROL_TOOL)
        log.info("SolaX control tool disabled (SOLAX_ALLOW_CONTROL is not true)")
    if "estimate_grid_charge_need" not in tools:
        register_planning_tools(server)
    return server


def main() -> None:
    run(load_server())


if __name__ == "__main__":
    main()
