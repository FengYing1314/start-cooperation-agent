#!/usr/bin/env python3
"""Run deterministic local validation for the start-work skill."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def rel(path: Path) -> str:
    return str(path.relative_to(SKILL_ROOT))


def run_step(label: str, command: list[str]) -> None:
    print(f"== {label}", flush=True)
    print(" ".join(command), flush=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(command, cwd=str(SKILL_ROOT), env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def python_scripts() -> list[str]:
    return [rel(path) for path in sorted(SCRIPT_DIR.glob("*.py"))]


def is_git_worktree() -> bool:
    proc = subprocess.run(
        ["git", "-C", str(SKILL_ROOT), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="Run a concise fast subset for quick validation.",
    )
    mode.add_argument(
        "--fast",
        action="store_true",
        help="Run a practical fast subset for iterative development.",
    )
    mode.add_argument(
        "--ultra-fast",
        action="store_true",
        help="Run the smallest validation subset for very fast iteration.",
    )
    parser.add_argument("--profile", action="store_true", help="Run smoke tests with timing output.")
    parser.add_argument(
        "--skip-git-diff-check",
        action="store_true",
        help="Skip git whitespace/conflict-marker checks.",
    )
    args = parser.parse_args()

    run_step("compile scripts", [sys.executable, "-m", "py_compile", *python_scripts()])
    test_command = [sys.executable, rel(SCRIPT_DIR / "test_start_work.py")]
    if args.ultra_fast:
        test_command.append("--ultra-fast")
    elif args.fast:
        test_command.append("--fast")
    elif args.quick:
        test_command.append("--quick")
    if args.profile:
        test_command.append("--profile")
    run_step("smoke tests", test_command)

    if args.skip_git_diff_check:
        print("== git diff checks skipped")
    elif is_git_worktree():
        run_step("git diff --check", ["git", "diff", "--check"])
        run_step("git diff --cached --check", ["git", "diff", "--cached", "--check"])
    else:
        print("== git diff checks skipped: not a git worktree")

    print("start-work local validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
