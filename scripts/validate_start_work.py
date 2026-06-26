#!/usr/bin/env python3
"""Run deterministic local validation for the start-work skill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from collections.abc import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def rel(path: Path) -> str:
    return str(path.relative_to(SKILL_ROOT))


def run_step(label: str, command: list[str], *, command_timeout_seconds: float = 0.0) -> dict[str, object]:
    timeout = None if command_timeout_seconds <= 0 else command_timeout_seconds
    print(f"== {label}", flush=True)
    command_str = subprocess.list2cmdline(command)
    print(command_str, flush=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    start = time.perf_counter()
    event: dict[str, object] = {
        "label": label,
        "command": command,
        "command_str": command_str,
        "timeout_seconds": timeout,
    }
    try:
        proc = subprocess.run(
            command,
            cwd=str(SKILL_ROOT),
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        timeout_cmd = list(exc.cmd) if isinstance(exc.cmd, list) else [str(exc.cmd)]
        event["ok"] = False
        event["timeout"] = True
        event["returncode"] = None
        event["elapsed_seconds"] = elapsed
        event["error"] = "timeout"
        print(f"[{label}] Command timed out after {timeout}s: {subprocess.list2cmdline(timeout_cmd)}", flush=True)
        return event
    event["ok"] = proc.returncode == 0
    event["timeout"] = False
    event["returncode"] = proc.returncode
    event["elapsed_seconds"] = time.perf_counter() - start
    return event


def split_test_names(values: Iterable[str]) -> list[str]:
    names: list[str] = []
    for item in values:
        for part in item.split(","):
            name = part.strip()
            if name:
                names.append(name)
    return names


def is_git_worktree() -> bool:
    proc = subprocess.run(
        ["git", "-C", str(SKILL_ROOT), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def print_json_report(
    *,
    enabled: bool,
    args: argparse.Namespace,
    events: list[dict[str, object]],
    ok: bool,
    failed_at: str | None = None,
    message: str | None = None,
) -> None:
    if not enabled:
        return
    report = {
        "ok": ok,
        "command_timeout_seconds": args.command_timeout_seconds,
        "events": events,
    }
    if args.ultra_fast:
        report["mode"] = "ultra-fast"
    elif args.fast:
        report["mode"] = "fast"
    elif args.quick:
        report["mode"] = "quick"
    else:
        report["mode"] = "full"
    if args.tests:
        report["tests"] = split_test_names(args.tests)
    if args.max_test_seconds:
        report["max_test_seconds"] = args.max_test_seconds
    if failed_at:
        report["failed_at"] = failed_at
    if message:
        report["message"] = message
    report["code"] = 0 if ok else 1
    print(json.dumps(report, ensure_ascii=False))


def fail_or_exit(
    events: list[dict[str, object]],
    message: str,
    args: argparse.Namespace,
    failed_at: str,
) -> None:
    print(message)
    print_json_report(
        enabled=args.print_json,
        args=args,
        events=events,
        ok=False,
        failed_at=failed_at,
        message=message,
    )
    raise SystemExit(1)


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
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Emit a compact JSON report after validation completes.",
    )
    args = parser.parse_args()
    events: list[dict[str, object]] = []

    if args.list_tests:
        event = run_step(
            "list tests",
            [sys.executable, rel(SCRIPT_DIR / "test_start_work.py"), "--list-tests"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
        events.append(event)
        if not event["ok"]:
            fail_or_exit(
                events=events,
                message=f"Validation failed in step: {event['label']}",
                args=args,
                failed_at=event["label"],
            )
        print_json_report(enabled=args.print_json, args=args, events=events, ok=True)
        return 0

    has_mode = bool(args.ultra_fast or args.fast or args.quick)
    if args.tests and has_mode:
        fail_or_exit(
            events=events,
            message="--tests cannot be used with --ultra-fast/--fast/--quick.",
            args=args,
            failed_at="arg_validation",
        )

    event = run_step(
        "syntax check scripts",
        [
            sys.executable,
            "-c",
            (
                "import ast, pathlib; "
                "[ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) "
                "for path in sorted(pathlib.Path('scripts').glob('*.py'))]"
            ),
        ],
        command_timeout_seconds=args.command_timeout_seconds,
    )
    events.append(event)
    if not event["ok"]:
        fail_or_exit(
            events=events,
            message=f"Validation failed in step: {event['label']}",
            args=args,
            failed_at=event["label"],
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
    event = run_step("smoke tests", test_command, command_timeout_seconds=args.command_timeout_seconds)
    events.append(event)
    if not event["ok"]:
        fail_or_exit(events, f"Validation failed in step: {event['label']}", args, failed_at=event["label"])

    if args.skip_git_diff_check:
        print("== git diff checks skipped")
    elif is_git_worktree():
        event = run_step(
            "git diff --check",
            ["git", "diff", "--check"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
        events.append(event)
        if not event["ok"]:
            fail_or_exit(
                events,
                f"Validation failed in step: {event['label']}",
                args,
                failed_at=event["label"],
            )

        event = run_step(
            "git diff --cached --check",
            ["git", "diff", "--cached", "--check"],
            command_timeout_seconds=args.command_timeout_seconds,
        )
        events.append(event)
        if not event["ok"]:
            fail_or_exit(
                events,
                f"Validation failed in step: {event['label']}",
                args,
                failed_at=event["label"],
            )
    else:
        print("== git diff checks skipped: not a git worktree")

    print("start-work local validation passed")
    print_json_report(enabled=args.print_json, args=args, events=events, ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
