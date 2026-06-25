#!/usr/bin/env python3
"""Run deterministic local validation for the start-work skill."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from collections.abc import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def rel(path: Path) -> str:
    return str(path.relative_to(SKILL_ROOT))


def run_step(label: str, command: list[str], *, command_timeout_seconds: float = 0.0) -> None:
    print(f"== {label}", flush=True)
    print(" ".join(command), flush=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    timeout = None if command_timeout_seconds <= 0 else command_timeout_seconds
    try:
        proc = subprocess.run(
            command,
            cwd=str(SKILL_ROOT),
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"Command timed out after {timeout}s: {exc.cmd}", flush=True)
        raise SystemExit(1)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def split_test_names(values: Iterable[str]) -> list[str]:
    names: list[str] = []
    for item in values:
        for part in item.split(","):
            name = part.strip()
            if name:
                names.append(name)
    return names


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
        "--tests",
        action="append",
        default=[],
        help="Pass only these tests to test_start_work by name (comma-separated and repeatable).",
    )
    parser.add_argument(
        "--max-test-seconds",
        type=float,
        default=0.0,
        help="Fail if any selected test runtime exceeds this many seconds (0 to disable).",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=0.0,
        help="Per-command timeout for validation subprocesses in seconds (0 to disable).",
    )
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="Print available test names from test_start_work and exit.",
    )
    parser.add_argument(
        "--skip-git-diff-check",
        action="store_true",
        help="Skip git whitespace/conflict-marker checks.",
    )
    args = parser.parse_args()

    if args.list_tests:
        run_step(
            "list tests",
            [sys.executable, rel(SCRIPT_DIR / "test_start_work.py"), "--list-tests"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
        return 0

    has_mode = bool(args.ultra_fast or args.fast or args.quick)
    if args.tests and has_mode:
        raise SystemExit("--tests cannot be used with --ultra-fast/--fast/--quick.")

    run_step(
        "compile scripts",
        [sys.executable, "-m", "py_compile", *python_scripts()],
        command_timeout_seconds=args.command_timeout_seconds,
    )
    test_command = [sys.executable, rel(SCRIPT_DIR / "test_start_work.py")]
    if args.ultra_fast:
        test_command.append("--ultra-fast")
    elif args.fast:
        test_command.append("--fast")
    elif args.quick:
        test_command.append("--quick")
    if args.tests:
        for name in split_test_names(args.tests):
            test_command.extend(["--only", name])
    if args.max_test_seconds:
        test_command.extend(["--max-test-seconds", str(args.max_test_seconds)])
    if args.profile:
        test_command.append("--profile")
    run_step("smoke tests", test_command, command_timeout_seconds=args.command_timeout_seconds)

    if args.skip_git_diff_check:
        print("== git diff checks skipped")
    elif is_git_worktree():
        run_step(
            "git diff --check",
            ["git", "diff", "--check"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
        run_step(
            "git diff --cached --check",
            ["git", "diff", "--cached", "--check"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
    else:
        print("== git diff checks skipped: not a git worktree")

    print("start-work local validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
