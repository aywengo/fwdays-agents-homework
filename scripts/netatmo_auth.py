#!/usr/bin/env python3
"""One-time Netatmo OAuth (authorization code) to obtain a refresh token.

1. Create an app at https://dev.netatmo.com/apps and add the redirect URI
   http://localhost:8765/callback
2. Put NETATMO_CLIENT_ID and NETATMO_CLIENT_SECRET in .env
3. python3 scripts/netatmo_auth.py   -> opens the browser, writes NETATMO_REFRESH_TOKEN to .env

Only the read_station scope is requested. The weather MCP server rotates the
token afterwards and keeps the current one in its private state volume.
"""
from __future__ import annotations

import http.server
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REDIRECT = "http://localhost:8765/callback"


def read_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def set_env(key: str, value: str) -> None:
    path = ROOT / ".env"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def main() -> int:
    env = read_env()
    cid, secret = env.get("NETATMO_CLIENT_ID"), env.get("NETATMO_CLIENT_SECRET")
    if not cid or not secret:
        print("Set NETATMO_CLIENT_ID and NETATMO_CLIENT_SECRET in .env first", file=sys.stderr)
        return 1
    state = secrets.token_urlsafe(16)
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] == state and "code" in query:
                result["code"] = query["code"][0]
                body = "Netatmo authorized. You can close this tab."
            else:
                body = "Authorization failed or state mismatch."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    url = "https://api.netatmo.com/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "scope": "read_station", "state": state})
    print("Opening browser for Netatmo consent:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", 8765), Handler) as srv:
        while "code" not in result:
            srv.handle_request()

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "client_id": cid, "client_secret": secret,
        "code": result["code"], "redirect_uri": REDIRECT, "scope": "read_station"}).encode()
    with urllib.request.urlopen("https://api.netatmo.com/oauth2/token", data=data, timeout=20) as resp:
        tokens = json.load(resp)
    set_env("NETATMO_REFRESH_TOKEN", tokens["refresh_token"])
    print("Saved NETATMO_REFRESH_TOKEN to .env (value not shown). Restart weather-mcp:\n"
          "  docker compose up -d weather-mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
