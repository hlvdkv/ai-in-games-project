"""Verify generated quest PDDL files with the local STRIPS solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .pddl import load_domain, load_problem, solve
from .play import find_quest_pairs


def verify_series(series_dir: Path) -> bool:
    domain_path = series_dir / "domain.pddl"
    domain = load_domain(domain_path)
    ok = True
    for json_path, pddl_path in find_quest_pairs(series_dir):
        quest = json.loads(json_path.read_text(encoding="utf-8"))
        problem = load_problem(pddl_path)
        plan = solve(domain, problem, max_depth=80)
        if plan is None:
            print(f"FAIL {pddl_path.name}: no plan")
            ok = False
            continue
        signatures = [action.signature() for action in plan]
        expected = quest.get("expected_plan") or []
        if signatures != expected:
            print(f"WARN {pddl_path.name}: plan differs from expected JSON plan")
            ok = False
        else:
            print(f"OK   {pddl_path.name}: {len(signatures)} actions")
    return ok


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify generated PDDL quests.")
    parser.add_argument("--series", default="quests/generated/ash_bell", help="Generated series directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return 0 if verify_series(Path(args.series)) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
