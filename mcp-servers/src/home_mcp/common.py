"""Shared runtime helpers for the home MCP servers.

Every server can run over stdio (native OpenClaw, Claude Code) or over
streamable HTTP (Docker Compose). HTTP mode is meant for a private Docker
network only and requires a bearer token (MCP_AUTH_TOKEN) on every request.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

log = logging.getLogger("home_mcp")


class BearerAuthMiddleware:
    """Minimal ASGI middleware: reject HTTP requests without the shared token."""

    def __init__(self, app: Any, token: str, open_paths: tuple[str, ...] = ("/healthz",)):
        self.app = app
        self.expected = f"Bearer {token}".encode()
        self.open_paths = open_paths

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") in self.open_paths:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        supplied = headers.get(b"authorization", b"")
        if not hmac.compare_digest(supplied, self.expected):
            body = json.dumps({"error": "unauthorized"}).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _health_app(app: Any) -> Any:
    async def wrapper(scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/healthz":
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"status":"ok"}'})
            return
        await app(scope, receive, send)
    return wrapper


def build_http_app(server: FastMCP, token: str | None) -> Any:
    """Streamable-HTTP ASGI app with health check and optional bearer auth."""
    # The Docker service name (e.g. "weather-mcp:8000") is the Host header, so the
    # loopback-only DNS-rebinding allowlist must be replaced. Auth is the token.
    server.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    app = server.streamable_http_app()
    if token:
        app = BearerAuthMiddleware(app, token)
    return _health_app(app)


def run(server: FastMCP) -> None:
    """Run the server with the transport chosen by MCP_TRANSPORT (stdio | http)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        server.run()
        return
    if transport not in {"http", "streamable-http"}:
        raise SystemExit(f"Unsupported MCP_TRANSPORT={transport!r}; use stdio or http")
    token = os.getenv("MCP_AUTH_TOKEN")
    if not token and os.getenv("MCP_ALLOW_NO_AUTH") != "1":
        raise SystemExit("MCP_AUTH_TOKEN is required in HTTP mode (or set MCP_ALLOW_NO_AUTH=1 for local tests)")
    import uvicorn

    uvicorn.run(
        build_http_app(server, token),
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        lifespan="on",
    )


def state_dir() -> Path:
    """Writable directory for caches and rotated tokens (never inside the repo)."""
    path = Path(os.getenv("HOME_MCP_STATE_DIR", Path.home() / ".local/state/home-mcp")).expanduser()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def atomic_write_json(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
