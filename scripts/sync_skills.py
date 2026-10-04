#!/usr/bin/env python3
"""Vendor external agent skills at pinned commits and verify them.

    python3 scripts/sync_skills.py sync            # fetch every source at its pinned ref -> skills/vendor/
    python3 scripts/sync_skills.py verify          # vendored files match skills/skills.lock.json; local skills valid
    python3 scripts/sync_skills.py update <name>   # move <name> to the repo's latest commit, then sync
    python3 scripts/sync_skills.py list            # skills available to render_config.py

Skills are prompt instructions that run with the agent's tools, so third-party
skills are pinned to a full commit SHA, vendored into git (reviewable in PRs) and
hash-locked. Never point an agent at a moving branch.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SOURCES = SKILLS / "sources.json"
LOCK = SKILLS / "skills.lock.json"
VENDOR = SKILLS / "vendor"
LOCAL = SKILLS / "local"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^name:\s*['\"]?([a-z0-9][a-z0-9_-]*)['\"]?\s*$", re.M)


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def skill_name(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SystemExit(f"{skill_dir}: SKILL.md has no YAML frontmatter")
    front = text.split("---", 2)[1]
    match = NAME_RE.search(front)
    if not match or "description:" not in front:
        raise SystemExit(f"{skill_dir}: frontmatter needs `name` and `description`")
    return match.group(1)


def file_hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def load_sources() -> list[dict]:
    return json.loads(SOURCES.read_text())["skills"]


def fetch(source: dict) -> None:
    name, ref = source["name"], source["ref"]
    if not SHA_RE.match(ref):
        raise SystemExit(f"{name}: ref must be a full 40-char commit SHA, got {ref!r}")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git("init", "-q", cwd=repo)
        git("remote", "add", "origin", source["repo"], cwd=repo)
        git("fetch", "-q", "--depth", "1", "origin", ref, cwd=repo)
        git("checkout", "-q", "FETCH_HEAD", cwd=repo)
        src = repo / source["path"]
        if not (src / "SKILL.md").exists():
            raise SystemExit(f"{name}: no SKILL.md at {source['path']} in {ref[:12]}")
        if skill_name(src) != name:
            raise SystemExit(f"{name}: SKILL.md name is {skill_name(src)!r}")
        dst = VENDOR / name
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git*"))
        for license_file in sorted(repo.glob("LICENSE*")):
            if not (dst / license_file.name).exists():
                shutil.copyfile(license_file, dst / license_file.name)
        (dst / "SOURCE.md").write_text(
            f"# Source\n\n- Repository: {source['repo']}\n- Commit: `{ref}`\n- Path: `{source['path']}`\n"
            f"- License: {source.get('license', 'see LICENSE')}\n\n"
            "Vendored by `scripts/sync_skills.py`. Do not edit here; override with a local skill instead.\n"
        )
    print(f"synced {name} @ {ref[:12]}")


def write_lock(sources: list[dict]) -> None:
    lock = {"skills": [
        {"name": s["name"], "repo": s["repo"], "ref": s["ref"], "path": s["path"],
         "license": s.get("license"), "files": file_hashes(VENDOR / s["name"])}
        for s in sources
    ]}
    LOCK.write_text(json.dumps(lock, indent=2) + "\n")


def available() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for base in (VENDOR, LOCAL):
        for skill_md in sorted(base.glob("*/SKILL.md")):
            name = skill_name(skill_md.parent)
            if name != skill_md.parent.name:
                raise SystemExit(f"{skill_md.parent}: directory must match skill name {name!r}")
            if name in found:
                raise SystemExit(f"duplicate skill name {name!r} in {found[name]} and {skill_md.parent}")
            found[name] = skill_md.parent
    return found


def verify() -> int:
    problems = []
    lock = {entry["name"]: entry for entry in json.loads(LOCK.read_text())["skills"]} if LOCK.exists() else {}
    for source in load_sources():
        entry = lock.get(source["name"])
        if not entry or entry["ref"] != source["ref"]:
            problems.append(f"{source['name']}: lock out of date (run sync)")
            continue
        actual = file_hashes(VENDOR / source["name"]) if (VENDOR / source["name"]).exists() else {}
        if actual != entry["files"]:
            changed = sorted(set(actual.items()) ^ set(entry["files"].items()))
            problems.append(f"{source['name']}: vendored files differ from lock: {[c[0] for c in changed][:5]}")
    try:
        names = available()
    except SystemExit as exc:
        problems.append(str(exc))
        names = {}
    for problem in problems:
        print("✗", problem)
    if problems:
        return 1
    print(f"✓ {len(names)} skills valid: {', '.join(sorted(names))}")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "verify"
    if cmd == "sync":
        sources = load_sources()
        VENDOR.mkdir(parents=True, exist_ok=True)
        for source in sources:
            fetch(source)
        write_lock(sources)
        return verify()
    if cmd == "update" and len(argv) == 3:
        data = json.loads(SOURCES.read_text())
        source = next((s for s in data["skills"] if s["name"] == argv[2]), None)
        if not source:
            raise SystemExit(f"unknown skill {argv[2]!r}")
        head = git("ls-remote", source["repo"], "HEAD").split()[0]
        print(f"{source['name']}: {source['ref'][:12]} -> {head[:12]} (review the diff before committing)")
        source["ref"] = head
        SOURCES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return main([argv[0], "sync"])
    if cmd == "verify":
        return verify()
    if cmd == "list":
        for name, path in sorted(available().items()):
            print(f"{name:24} {path.relative_to(ROOT)}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
