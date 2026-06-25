#!/usr/bin/env python3
"""Inspect start-work project state across team readiness and recent runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from inspect_run import inspect_run
from inspect_team import inspect_team, resolve_repo


def run_directories(repo: Path) -> list[Path]:
    runs_root = repo / ".agent-work" / "start-work" / "runs"
    if not runs_root.exists():
        return []
    return sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)


def compact_run(summary: dict[str, object]) -> dict[str, object]:
    return {
        "ok": summary.get("ok", False),
        "run_id": summary.get("run_id", ""),
        "mode": summary.get("mode", ""),
        "current_status": summary.get("current_status", ""),
        "next_allowed_statuses": summary.get("next_allowed_statuses", []),
        "event_count": summary.get("event_count", 0),
        "last_event": summary.get("last_event"),
        "pending_outbound": summary.get("pending_outbound"),
        "reviewer_fix_send_state": summary.get("reviewer_fix_send_state"),
        "run_dir": summary.get("run_dir", ""),
        "problems": summary.get("problems", []),
        "next_actions": summary.get("next_actions", []),
    }


def next_actions(team: dict[str, object], latest_runs: list[dict[str, object]]) -> list[str]:
    team_actions = team.get("next_actions", [])
    if not team.get("ok"):
        actions = [
            "Run the non-destructive Codex App preflight in references/codex-thread-mode.md before creating threads or sending messages.",
        ]
        if isinstance(team_actions, list) and team_actions:
            actions.extend(str(item) for item in team_actions)
            return actions
        actions.append("Fix team readiness before starting or resuming codex-thread runs.")
        return actions

    if latest_runs:
        latest = latest_runs[0]
        status = str(latest.get("current_status", ""))
        if status not in {"final_delivery", "blocked"}:
            run_actions = latest.get("next_actions", [])
            actions = [f"Resume latest run {latest.get('run_id', '')} at status {status}."]
            if isinstance(run_actions, list):
                actions.extend(str(item) for item in run_actions)
            return actions

    if team.get("codex_thread_ready"):
        return ["Start a new direct codex-thread run with init_run.py."]
    if team.get("manual_relay_ready"):
        return ["Use callback/manual relay mode, or record M.thread_id before starting a direct codex-thread run."]
    return ["Inspect team readiness before starting the next task."]


def inspect_project(repo: Path, limit: int) -> dict[str, object]:
    team = inspect_team(repo)
    all_runs = run_directories(repo)
    selected_runs = [compact_run(inspect_run(run_dir)) for run_dir in all_runs[:limit]]
    run_problems = [
        {"run_id": run.get("run_id", ""), "problems": run.get("problems", [])}
        for run in selected_runs
        if run.get("problems")
    ]
    problems = []
    if team.get("problems"):
        problems.append({"scope": "team", "problems": team["problems"]})
    problems.extend({"scope": "run", **item} for item in run_problems)

    return {
        "ok": bool(team.get("ok")) and not run_problems,
        "repo": str(repo),
        "team": {
            "ok": team.get("ok", False),
            "team_id": team.get("team_id", ""),
            "codex_thread_ready": team.get("codex_thread_ready", False),
            "manual_relay_ready": team.get("manual_relay_ready", False),
            "roster_complete": team.get("roster_complete", False),
            "acknowledgements_complete": team.get("acknowledgements_complete", False),
            "warnings": team.get("warnings", []),
            "problems": team.get("problems", []),
            "next_actions": team.get("next_actions", []),
        },
        "runs_root": str(repo / ".agent-work" / "start-work" / "runs"),
        "run_count": len(all_runs),
        "latest_runs": selected_runs,
        "problems": problems,
        "next_actions": next_actions(team, selected_runs),
    }


def print_text(summary: dict[str, object]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    team = summary.get("team", {})
    if isinstance(team, dict):
        print(f"Team: {team.get('team_id', '')}")
        print(f"Codex Thread Ready: {str(team.get('codex_thread_ready', False)).lower()}")
        print(f"Manual Relay Ready: {str(team.get('manual_relay_ready', False)).lower()}")
    print(f"Runs: {summary.get('run_count', 0)}")
    latest_runs = summary.get("latest_runs", [])
    if isinstance(latest_runs, list) and latest_runs:
        print("Latest Runs:")
        for run in latest_runs:
            if isinstance(run, dict):
                print(f"- {run.get('run_id', '')}: {run.get('current_status', '')} ({run.get('mode', '')})")
    problems = summary.get("problems", [])
    if isinstance(problems, list) and problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")
    next_action_items = summary.get("next_actions", [])
    if isinstance(next_action_items, list) and next_action_items:
        print("Next Actions:")
        for action in next_action_items:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of recent runs to inspect.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    if args.limit < 0:
        raise SystemExit("--limit must be 0 or greater.")
    repo, _ = resolve_repo(args.repo)
    summary = inspect_project(repo, args.limit)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
