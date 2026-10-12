#!/usr/bin/env python3
"""Decide which team stacks a change affects.

Rules:
  * A change under teams/<team>/ affects only that team.
  * A change under modules/ (or to shared CI/lint config) affects EVERY team,
    because all teams consume the shared modules.
  * Docs-only changes affect nothing.

Usage (CI):
    git diff --name-only origin/main...HEAD | python scripts/changed_stacks.py
Prints a JSON list, e.g. ["team-a", "team-c"], for a GitHub Actions matrix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SHARED_PREFIXES = ("modules/", ".tflint.hcl", "backend.hcl", ".github/workflows/")


def all_teams(root: Path) -> list[str]:
    teams_dir = root / "teams"
    return sorted(p.name for p in teams_dir.iterdir() if p.is_dir())


def affected_teams(changed_files: list[str], teams: list[str]) -> list[str]:
    affected: set[str] = set()
    for raw in changed_files:
        path = raw.strip()
        if not path:
            continue
        if path.startswith(SHARED_PREFIXES):
            return sorted(teams)
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == "teams" and parts[1] in teams:
            affected.add(parts[1])
    return sorted(affected)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    print(json.dumps(affected_teams(sys.stdin.read().splitlines(), all_teams(root))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
