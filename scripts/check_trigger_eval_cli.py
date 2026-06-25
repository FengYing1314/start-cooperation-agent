#!/usr/bin/env python3
"""Check whether the Codex CLI can launch before running trigger evals."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def tail(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def next_actions(ok: bool, codex_bin: str) -> list[str]:
    if ok:
        return [
            "Run prepare_trigger_eval_workspace.py with this codex_bin.",
            "Run the returned dry_run command before real evals.",
            "Run eval and score sequentially; do not score before artifacts are written.",
        ]
    return [
        f"Fix the Codex CLI launch path or pass --codex-bin for a working executable instead of {codex_bin!r}.",
        "Do not run real trigger evals until this check returns ok=true.",
        "If the app-bundled WindowsApps codex.exe is not launchable from this shell, use a CLI installed on PATH or an absolute executable path.",
    ]


def check_cli(args: argparse.Namespace) -> dict[str, object]:
    codex_bin = args.codex_bin.strip()
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    resolved = shutil.which(codex_bin)
    command = [codex_bin, "--version"]
    base = {
        "codex_bin": codex_bin,
        "resolved_path": resolved or "",
        "cwd": str(cwd),
        "command": command,
        "timeout_seconds": args.timeout_seconds,
    }
    if resolved is None and not Path(codex_bin).expanduser().is_file():
        result = {
            **base,
            "ok": False,
            "returncode": None,
            "error": "Executable not found on PATH or filesystem.",
            "next_actions": next_actions(False, codex_bin),
        }
        return result

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=None if args.timeout_seconds <= 0 else args.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base,
            "ok": False,
            "returncode": None,
            "timeout": True,
            "stdout_tail": tail(str(exc.stdout or "")),
            "stderr_tail": tail(str(exc.stderr or "")),
            "next_actions": next_actions(False, codex_bin),
        }
    except OSError as exc:
        return {
            **base,
            "ok": False,
            "returncode": None,
            "error": str(exc),
            "next_actions": next_actions(False, codex_bin),
        }

    ok = proc.returncode == 0
    return {
        **base,
        "ok": ok,
        "returncode": proc.returncode,
        "stdout_tail": tail(proc.stdout),
        "stderr_tail": tail(proc.stderr),
        "next_actions": next_actions(ok, codex_bin),
    }


def print_text(result: dict[str, object]) -> None:
    print(f"OK: {str(result['ok']).lower()}")
    print(f"Command: {' '.join(result['command'])}")
    if result.get("resolved_path"):
        print(f"Resolved: {result['resolved_path']}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    if result.get("stderr_tail"):
        print(f"Stderr: {result['stderr_tail']}")
    print("Next actions:")
    for action in result.get("next_actions", []):
        print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument("--cwd", default=".", help="Directory where the CLI should be launched.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="CLI version check timeout. Use 0 to disable. Defaults to 15 seconds.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable result.")
    args = parser.parse_args()

    result = check_cli(args)
    if args.print_json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print_text(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
