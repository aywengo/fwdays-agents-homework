"""Run the upstream SolaX Cloud MCP server (mouldiwarp/solax-cloud-mcp) with our transport.

Upstream only ships stdio MCP plus a separate REST API. This wrapper reuses
its FastMCP instance unchanged and serves it over streamable HTTP with the same
bearer-token guard as the other home MCP servers, so it can live in its own
container on the private Compose network.

Control boundary: when SOLAX_ALLOW_CONTROL is not "true", the write tool
`set_battery_self_use_mode` is removed from the server before it starts. The
OpenClaw config applies the same filter, so the boundary holds on both sides.
"""

from __future__ import annotations

import logging
import os

from .common import run

log = logging.getLogger("home_mcp.solax")
CONTROL_TOOL = "set_battery_self_use_mode"


def control_allowed() -> bool:
    return os.getenv("SOLAX_ALLOW_CONTROL", "false").strip().lower() in {"1", "true", "yes"}


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
    return server


def main() -> None:
    run(load_server())


if __name__ == "__main__":
    main()
