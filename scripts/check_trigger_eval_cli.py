#!/usr/bin/env python3
"""Check whether the Codex CLI can launch before running trigger evals."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

AUTO_CODEX_NAMES = {"", "auto", "codex", "codex.exe"}


def tail(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def next_actions(ok: bool, codex_bin: str) -> list[str]:
    if ok:
        return [
            f"Run prepare_trigger_eval_workspace.py with --codex-bin {codex_bin!r}.",
            "Run the returned dry_run command before real evals.",
            "Run eval and score sequentially; do not score before artifacts are written.",
        ]
    return [
        f"Fix the Codex CLI launch path or pass --codex-bin for a working executable instead of {codex_bin!r}.",
        "Do not run real trigger evals until this check returns ok=true.",
        "If the app-bundled WindowsApps codex.exe is not launchable from this shell, use a CLI installed on PATH or an absolute executable path.",
    ]


def add_candidate(candidates: list[str], value: str | None) -> None:
    candidate = (value or "").strip()
    if candidate and candidate not in candidates:
        candidates.append(candidate)


def windows_codex_paths() -> list[str]:
    paths: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        paths.append(str(Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"))
    paths.append(str(Path.home() / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"))
    return paths


def codex_candidates(requested: str) -> list[str]:
    requested = requested.strip()
    if requested not in AUTO_CODEX_NAMES:
        return [requested]

    candidates: list[str] = []
    add_candidate(candidates, os.environ.get("CODEX_BIN"))
    add_candidate(candidates, "codex" if requested in {"", "auto"} else requested)
    add_candidate(candidates, "codex.exe")
    for path in windows_codex_paths():
        add_candidate(candidates, path)
    return candidates


def resolve_candidate(candidate: str) -> str:
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    path = Path(candidate).expanduser()
    if path.is_file():
        return str(path)
    return ""


def check_cli(args: argparse.Namespace) -> dict[str, object]:
    requested_codex_bin = args.codex_bin.strip() or "auto"
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    candidates = codex_candidates(requested_codex_bin)
    attempted: list[dict[str, object]] = []
    base = {
        "requested_codex_bin": requested_codex_bin,
        "cwd": str(cwd),
        "timeout_seconds": args.timeout_seconds,
        "candidate_paths": candidates,
    }

    last_error = "Executable not found on PATH or filesystem."
    for candidate in candidates:
        resolved_path = resolve_candidate(candidate)
        command_bin = resolved_path or candidate
        command = [command_bin, "--version"]
        attempt: dict[str, object] = {
            "candidate": candidate,
            "resolved_path": resolved_path,
            "command": command,
        }
        if not resolved_path:
            attempt.update({"ok": False, "returncode": None, "error": "Executable not found on PATH or filesystem."})
            attempted.append(attempt)
            continue
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
            attempt.update(
                {
                    "ok": False,
                    "returncode": None,
                    "timeout": True,
                    "stdout_tail": tail(str(exc.stdout or "")),
                    "stderr_tail": tail(str(exc.stderr or "")),
                }
            )
            attempted.append(attempt)
            last_error = "Timed out while launching Codex CLI."
            continue
        except OSError as exc:
            attempt.update({"ok": False, "returncode": None, "error": str(exc)})
            attempted.append(attempt)
            last_error = str(exc)
            continue

        attempt.update(
            {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout_tail": tail(proc.stdout),
                "stderr_tail": tail(proc.stderr),
            }
        )
        attempted.append(attempt)
        if proc.returncode == 0:
            return {
                **base,
                "ok": True,
                "codex_bin": command_bin,
                "resolved_path": resolved_path,
                "command": command,
                "returncode": proc.returncode,
                "stdout_tail": tail(proc.stdout),
                "stderr_tail": tail(proc.stderr),
                "attempted": attempted,
                "next_actions": next_actions(True, command_bin),
            }
        last_error = f"Candidate exited with code {proc.returncode}: {command_bin}"

    return {
        **base,
        "ok": False,
        "codex_bin": "",
        "resolved_path": "",
        "command": [],
        "returncode": None,
        "error": last_error,
        "attempted": attempted,
        "next_actions": next_actions(False, requested_codex_bin),
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
