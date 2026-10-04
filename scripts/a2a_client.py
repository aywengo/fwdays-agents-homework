#!/usr/bin/env python3
"""Minimal A2A 1.0 JSON-RPC client for the Gateway's A2A channel.

    python3 scripts/a2a_client.py card
    python3 scripts/a2a_client.py send "Який зараз заряд батареї і яка ціна енергії?"
    python3 scripts/a2a_client.py send --no-wait "Підготуй ранковий звіт"   # then: get <task-id>
    python3 scripts/a2a_client.py get <task-id>

Authenticates as the `homework-client` peer with A2A_CLIENT_TOKEN from .env.
The task is routed to the dispatcher, which may delegate to weather-cast and trader.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("A2A_BASE_URL", "http://127.0.0.1:18789")


def token() -> str:
    if os.getenv("A2A_CLIENT_TOKEN"):
        return os.environ["A2A_CLIENT_TOKEN"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("A2A_CLIENT_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("A2A_CLIENT_TOKEN is not set")


def rpc(method: str, params: dict, timeout: int = 200) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}).encode()
    req = urllib.request.Request(f"{BASE}/a2a/v1", data=body, headers={
        "Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def show(result: dict) -> None:
    if "error" in result:
        print("error:", json.dumps(result["error"], ensure_ascii=False))
        return
    task = result["result"].get("task", result["result"])
    print(f"task {task.get('id')} [{task.get('status', {}).get('state')}] context={task.get('contextId')}")
    for artifact in task.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            if "text" in part:
                print(part["text"])


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"card", "send", "get"}:
        print(__doc__)
        return 2
    if argv[1] == "card":
        with urllib.request.urlopen(f"{BASE}/.well-known/agent-card.json", timeout=10) as resp:
            card = json.load(resp)
        print(json.dumps({k: card.get(k) for k in ("name", "description", "version")}, ensure_ascii=False))
        for skill in card.get("skills", []):
            print(f"- skill {skill.get('id')}: {skill.get('name')}")
        return 0
    if argv[1] == "get":
        show(rpc("GetTask", {"id": argv[2]}))
        return 0
    wait = "--no-wait" not in argv
    text = " ".join(a for a in argv[2:] if a != "--no-wait")
    params = {"message": {"messageId": str(uuid.uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}}
    if not wait:
        params["configuration"] = {"returnImmediately": True}
    show(rpc("SendMessage", params))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
