#!/usr/bin/env python3
"""Fail if tracked files contain values from .env or obvious credentials.

Run before every commit/push:  python3 scripts/check_secrets.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"[MN][A-Za-z\d]{23,25}\.[\w-]{6}\.[\w-]{27,}"),  # Discord bot token shape
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
]


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p]


def env_values() -> set[str]:
    path = ROOT / ".env"
    if not path.exists():
        return set()
    values = set()
    sensitive = re.compile(r"TOKEN|SECRET|PASSWORD|API_KEY|CLIENT_ID|DEVICE_SN|_ID$|ALLOW_FROM|REPORT_TO|_LAT$|_LON$")
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = (part.strip() for part in line.split("=", 1))
            value = value.strip('"').strip("'")
            if sensitive.search(key) and len(value) >= 6:
                values.add(value)
    return values


def main() -> int:
    secrets = env_values()
    problems = []
    for path in tracked_files():
        if not path.is_file() or path.name == ".env":
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        problems += [f"{rel}: contains a value from .env" for v in secrets if v in text]
        problems += [f"{rel}: matches credential pattern {p.pattern[:20]}…" for p in PATTERNS if p.search(text)]
    for problem in sorted(set(problems)):
        print("✗", problem)
    if problems:
        return 1
    print("✓ no secrets found in tracked or untracked-unignored files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
