#!/usr/bin/env python3
"""Run a generated start-work trigger eval plan and write JSONL artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def stderr_tail(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def command_parts(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("plan item command must be a non-empty list")
    if not all(isinstance(part, str) and part for part in value):
        raise ValueError("plan item command entries must be non-empty strings")
    return value


def run_item(
    item: dict[str, Any],
    *,
    plan_dir: Path,
    dry_run: bool,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    item_id = str(item.get("id", ""))
    command = command_parts(item.get("command"))
    artifact = resolve_from(plan_dir, str(item.get("artifact", "")))
    cwd_value = str(item.get("cwd", ""))
    cwd = resolve_from(plan_dir, cwd_value) if cwd_value else None

    if cwd is not None and not cwd.is_dir():
        raise ValueError(f"{item_id}: cwd is not a directory: {cwd}")
    if not artifact.name:
        raise ValueError(f"{item_id}: artifact path is required")

    result: dict[str, Any] = {
        "id": item_id,
        "cwd": str(cwd) if cwd else "",
        "artifact": str(artifact),
        "command": command,
        "dry_run": dry_run,
        "timeout_seconds": timeout_seconds,
    }
    if dry_run:
        result["returncode"] = 0
        return result

    artifact.parent.mkdir(parents=True, exist_ok=True)
    with artifact.open("w", encoding="utf-8") as stdout:
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                stdout=stdout,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            result["returncode"] = None
            result["timeout"] = True
            if exc.stderr:
                result["stderr_tail"] = stderr_tail(str(exc.stderr))
            return result
    result["returncode"] = proc.returncode
    if proc.stderr:
        result["stderr_tail"] = stderr_tail(proc.stderr)
    return result


def select_items(raw_plan: list[Any], requested_ids: list[str]) -> list[Any]:
    if not requested_ids:
        return raw_plan
    requested = set(requested_ids)
    selected = [
        item
        for item in raw_plan
        if isinstance(item, dict) and str(item.get("id", "")) in requested
    ]
    found = {str(item.get("id", "")) for item in selected if isinstance(item, dict)}
    missing = sorted(requested - found)
    if missing:
        raise SystemExit(f"Requested eval id not found: {', '.join(missing)}")
    return selected


def run_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = Path(args.plan).expanduser().resolve()
    plan_dir = plan_path.parent
    raw_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(raw_plan, list):
        raise SystemExit("Plan file must contain a JSON array.")
    selected_plan = select_items(raw_plan, args.id)
    timeout_seconds = None if args.timeout_seconds <= 0 else args.timeout_seconds

    results = []
    for item in selected_plan:
        if not isinstance(item, dict):
            results.append({"ok": False, "error": "plan item must be an object"})
            if not args.continue_on_error:
                break
            continue
        try:
            result = run_item(
                item,
                plan_dir=plan_dir,
                dry_run=args.dry_run,
                timeout_seconds=timeout_seconds,
            )
            result["ok"] = result["returncode"] == 0
        except (OSError, ValueError) as exc:
            result = {"id": str(item.get("id", "")), "ok": False, "error": str(exc)}
        results.append(result)
        if not result["ok"] and not args.continue_on_error:
            break

    return {
        "ok": all(item.get("ok") for item in results) and len(results) == len(selected_plan),
        "plan": str(plan_path),
        "dry_run": args.dry_run,
        "timeout_seconds": timeout_seconds,
        "selected_ids": args.id,
        "plan_total": len(raw_plan),
        "total": len(selected_plan),
        "completed": len(results),
        "failed": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }


def print_text(summary: dict[str, Any]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Completed: {summary['completed']}/{summary['total']}")
    for item in summary["results"]:
        status = "PASS" if item.get("ok") else "FAIL"
        suffix = " dry-run" if item.get("dry_run") else f" rc={item.get('returncode', 'n/a')}"
        print(f"{status} {item.get('id', '')}{suffix}")
        if item.get("error"):
            print(f"  error: {item['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="Path to trigger-eval-plan.json.")
    parser.add_argument("--id", action="append", default=[], help="Run only this eval id. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report commands without executing them.")
    parser.add_argument("--continue-on-error", action="store_true", help="Run remaining items after a failure.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Per-item timeout. Use 0 to disable. Defaults to 1800 seconds.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable run summary.")
    args = parser.parse_args()

    summary = run_plan(args)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
