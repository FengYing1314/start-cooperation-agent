#!/usr/bin/env python3
"""Plan a safe Codex App thread-mode live drill without touching live threads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from inspect_project import inspect_project
from inspect_team import inspect_team, resolve_repo


SCRIPT_DIR = Path(__file__).resolve().parent


def command(script_name: str, *args: str) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / script_name), *args]


def count_pending(latest_runs: object) -> tuple[int, int]:
    if not isinstance(latest_runs, list):
        return 0, 0
    pending_outbound = 0
    reviewer_fix_needs_send = 0
    for run in latest_runs:
        if not isinstance(run, dict):
            continue
        if run.get("pending_outbound"):
            pending_outbound += 1
        reviewer_fix = run.get("reviewer_fix_send_state")
        if isinstance(reviewer_fix, dict) and reviewer_fix.get("next_handoff_sent") == "no":
            reviewer_fix_needs_send += 1
    return pending_outbound, reviewer_fix_needs_send


def target_presence(team: dict[str, Any]) -> dict[str, dict[str, bool]]:
    roster = team.get("roster", {})
    result: dict[str, dict[str, bool]] = {}
    for local_id in ("M", "D1", "R1"):
        entry = roster.get(local_id, {}) if isinstance(roster, dict) else {}
        if not isinstance(entry, dict):
            entry = {}
        result[local_id] = {
            "thread_id_present": bool(str(entry.get("thread_id", "")).strip()),
            "callback_present": bool(str(entry.get("callback", "")).strip()),
        }
    return result


def non_destructive_preflight(repo: Path) -> list[dict[str, object]]:
    return [
        {
            "step": "discover_thread_tools",
            "tool": "tool_search",
            "query": "Codex app thread create read send message title archive list projects",
            "when": "Only if Codex App thread tools are not already visible.",
            "allowed_without_live_approval": True,
        },
        {
            "step": "match_project",
            "tool": "list_projects",
            "purpose": "Select the Codex App project whose path exactly matches the repo.",
            "allowed_without_live_approval": True,
        },
        {
            "step": "exact_thread_lookup",
            "tool": "list_threads",
            "purpose": "Only exact lookup of existing role threads or exact user-provided thread ids.",
            "allowed_without_live_approval": True,
        },
        {
            "step": "inspect_project",
            "command": command("inspect_project.py", "--repo", str(repo), "--print-json"),
            "purpose": "Read structured team readiness, latest runs, and pending outbound sends.",
            "allowed_without_live_approval": True,
        },
        {
            "step": "inspect_team",
            "command": command("inspect_team.py", "--repo", str(repo), "--print-json"),
            "purpose": "Verify roster targets, acknowledgements, and role-to-role route shape.",
            "allowed_without_live_approval": True,
        },
    ]


def blocked_without_approval() -> list[dict[str, str]]:
    return [
        {
            "tool": "create_thread",
            "reason": "Creates user-owned role threads; require explicit user approval to initialize or replace live D1/R1 threads.",
        },
        {
            "tool": "send_message_to_thread",
            "reason": "Delivers a real thread message; require a prepared payload or standing instruction that should actually be sent.",
        },
        {
            "tool": "read_thread",
            "reason": "Not normal transport; use only for recovery, exact audit, or user-requested status investigation.",
        },
    ]


def live_drill_when_approved(repo: Path) -> list[dict[str, object]]:
    return [
        {
            "step": "confirm_project_target",
            "tool": "list_projects",
            "success_condition": "One project path exactly matches the repo.",
        },
        {
            "step": "create_or_confirm_role_threads",
            "tools": ["create_thread", "set_thread_title", "list_threads"],
            "guardrail": "Use one long-lived D1 Developer and one long-lived R1 Reviewer per project; do not create per-task role threads.",
        },
        {
            "step": "record_roster",
            "command": command(
                "init_team.py",
                "--repo",
                str(repo),
                "--manager-thread-id",
                "<manager-thread-id>",
                "--developer-thread-id",
                "<developer-thread-id>",
                "--reviewer-thread-id",
                "<reviewer-thread-id>",
                "--print-json",
            ),
        },
        {
            "step": "send_standing_instructions",
            "tool": "send_message_to_thread",
            "prompt_rule": "Read team/standing-developer.md and team/standing-reviewer.md as UTF-8; pass exact file contents as prompt.",
        },
        {
            "step": "record_acknowledgements",
            "commands": [
                command("ack_team.py", "--repo", str(repo), "--role", "D1", "--print-json"),
                command("ack_team.py", "--repo", str(repo), "--role", "R1", "--print-json"),
                command("inspect_team.py", "--repo", str(repo), "--print-json"),
            ],
        },
        {
            "step": "start_tiny_run",
            "command": command(
                "init_run.py",
                "--repo",
                str(repo),
                "--slug",
                "live-drill",
                "--request",
                "<tiny reversible drill task>",
                "--print-json",
            ),
        },
        {
            "step": "manager_to_developer",
            "commands": [
                command(
                    "prepare_outbound_handoff.py",
                    "--run-dir",
                    "<run-dir>",
                    "--kind",
                    "work_order",
                    "--body-file",
                    "<work-order-payload.md>",
                    "--print-json",
                ),
                "send_message_to_thread(threadId=<send_to_thread_id>, prompt=<exact payload_file contents>)",
                "run finalize_sent_command with --send-evidence when a useful receipt exists",
            ],
        },
        {
            "step": "developer_to_manager",
            "expected_message": "D1 sends developer_completion directly to M; Manager records it with record_inbound_handoff.py --kind developer_completion.",
        },
        {
            "step": "manager_to_reviewer",
            "expected_message": "Manager checks the integrated diff, prepares review_request, sends exact payload to R1, then finalizes the send.",
        },
        {
            "step": "reviewer_outcome",
            "expected_message": "R1 sends reviewer_accepted to M, or sends reviewer_fix directly to D1 with a separate Manager copy.",
        },
    ]


def recommended_next_actions(
    *,
    team: dict[str, Any],
    pending_outbound_count: int,
    reviewer_fix_needs_send_count: int,
) -> list[str]:
    if pending_outbound_count or reviewer_fix_needs_send_count:
        return [
            "Resolve existing pending sends before starting a live drill.",
            "For pending_outbound, read payload_file and send exact contents, then finalize sent or failed.",
            "For reviewer_fix_send_state.next_handoff_sent=no, send the exact payload to D1 before advancing fix statuses.",
        ]
    if not team.get("ok"):
        return [
            "Run the non-destructive preflight first.",
            "Ask the user for explicit approval before creating role threads or sending standing instructions.",
            "After approval, initialize the roster and require D1/R1 acknowledgements before any task run.",
        ]
    if team.get("manual_relay_ready") and not team.get("codex_thread_ready"):
        return [
            "Record a real Manager thread id before a direct Codex App thread drill.",
            "Use callback/manual relay only if the user chooses fallback instead of direct role-to-role messaging.",
        ]
    if team.get("codex_thread_ready"):
        return [
            "Ask the user for explicit live-drill approval, then run the tiny route exercise.",
            "The drill should prove M->D1, D1->M, M->R1, and R1->M or R1->D1 plus Manager copy without Manager polling.",
        ]
    return ["Inspect team readiness again before attempting a live drill."]


def build_plan(repo: Path, limit: int) -> dict[str, object]:
    project = inspect_project(repo, limit)
    team = inspect_team(repo)
    pending_outbound_count, reviewer_fix_needs_send_count = count_pending(project.get("latest_runs"))
    ready_for_live_drill = bool(
        team.get("codex_thread_ready")
        and not pending_outbound_count
        and not reviewer_fix_needs_send_count
        and not project.get("problems")
    )
    return {
        "ok": True,
        "repo": str(repo),
        "ready_for_live_drill": ready_for_live_drill,
        "requires_explicit_live_drill_approval": True,
        "can_run_non_destructive_preflight_now": True,
        "current_state": {
            "team_ok": bool(team.get("ok")),
            "codex_thread_ready": bool(team.get("codex_thread_ready")),
            "manual_relay_ready": bool(team.get("manual_relay_ready")),
            "roster_complete": bool(team.get("roster_complete")),
            "acknowledgements_complete": bool(team.get("acknowledgements_complete")),
            "target_presence": target_presence(team),
            "project_problem_count": len(project.get("problems", [])) if isinstance(project.get("problems"), list) else 0,
            "pending_outbound_count": pending_outbound_count,
            "reviewer_fix_needs_send_count": reviewer_fix_needs_send_count,
        },
        "non_destructive_preflight": non_destructive_preflight(repo),
        "blocked_without_approval": blocked_without_approval(),
        "live_drill_when_approved": live_drill_when_approved(repo),
        "recommended_next_actions": recommended_next_actions(
            team=team,
            pending_outbound_count=pending_outbound_count,
            reviewer_fix_needs_send_count=reviewer_fix_needs_send_count,
        ),
    }


def print_text(plan: dict[str, object]) -> None:
    state = plan.get("current_state", {})
    print(f"OK: {str(plan.get('ok', False)).lower()}")
    print(f"Repo: {plan.get('repo', '')}")
    print(f"Ready For Live Drill: {str(plan.get('ready_for_live_drill', False)).lower()}")
    print(f"Requires Explicit Live Drill Approval: {str(plan.get('requires_explicit_live_drill_approval', True)).lower()}")
    if isinstance(state, dict):
        print(f"Codex Thread Ready: {str(state.get('codex_thread_ready', False)).lower()}")
        print(f"Pending Outbound Sends: {state.get('pending_outbound_count', 0)}")
        print(f"Reviewer Fix Sends Needed: {state.get('reviewer_fix_needs_send_count', 0)}")
    actions = plan.get("recommended_next_actions", [])
    if isinstance(actions, list) and actions:
        print("Recommended Next Actions:")
        for action in actions:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--limit", type=int, default=5, help="Recent run count to inspect for pending sends.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable plan.")
    args = parser.parse_args()

    if args.limit < 0:
        raise SystemExit("--limit must be 0 or greater.")
    repo, _ = resolve_repo(args.repo)
    plan = build_plan(repo, args.limit)
    if args.print_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print_text(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
