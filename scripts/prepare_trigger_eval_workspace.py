#!/usr/bin/env python3
"""Prepare an isolated repository fixture for start-work trigger evals."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from plan_trigger_evals import DEFAULT_PROMPTS, build_plan


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


AGENTS_MD = """# Fixture AGENTS.md

- Keep changes inside this temporary fixture.
- Do not contact external services unless the eval prompt explicitly asks.
- Do not commit, push, or create remotes.
"""

README_MD = """# Trigger Eval Fixture

This repository is a disposable fixture for start-work trigger evals.
"""

PARSER_PY = """def parse(value):
    return value.strip()
"""


def next_commands(plan_path: Path) -> dict[str, list[str]]:
    runner = SCRIPT_DIR / "run_trigger_eval_plan.py"
    scorer = SCRIPT_DIR / "score_trigger_evals.py"
    base_run = [sys.executable, str(runner), "--plan", str(plan_path), "--print-json"]
    base_score = [sys.executable, str(scorer), "--plan", str(plan_path), "--print-json"]
    return {
        "dry_run": [*base_run, "--dry-run"],
        "run": base_run,
        "score": base_score,
        "focused_run": [*base_run, "--id", "<eval-id>"],
        "focused_score": [*base_score, "--id", "<eval-id>"],
    }


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def write_fixture(repo: Path, *, init_git: bool) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    (repo / "README.md").write_text(README_MD, encoding="utf-8")
    src = repo / "src"
    src.mkdir(exist_ok=True)
    (src / "parser.py").write_text(PARSER_PY, encoding="utf-8")
    if init_git:
        run_git(repo, "init")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Directory where the fixture should be created.")
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS), help="Markdown trigger eval prompt table.")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument("--no-git", action="store_true", help="Do not initialize the fixture as a git repository.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable result.")
    args = parser.parse_args()

    root = Path(args.output_dir).expanduser().resolve()
    repo = root / "repo"
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_fixture(repo, init_git=not args.no_git)

    plan = build_plan(
        SimpleNamespace(
            prompts=args.prompts,
            artifact_dir=str(artifact_dir),
            cwd=str(repo),
            codex_bin=args.codex_bin,
        )
    )
    plan_path = root / "trigger-eval-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "fixture_dir": str(root),
        "repo": str(repo),
        "artifact_dir": str(artifact_dir),
        "plan": str(plan_path),
        "next_commands": next_commands(plan_path),
        "prompt_count": len(plan),
    }
    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Fixture: {root}")
        print(f"Repo: {repo}")
        print(f"Plan: {plan_path}")
        print(f"Dry run: {subprocess.list2cmdline(result['next_commands']['dry_run'])}")
        print(f"Score: {subprocess.list2cmdline(result['next_commands']['score'])}")
        print(f"Prompts: {len(plan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
