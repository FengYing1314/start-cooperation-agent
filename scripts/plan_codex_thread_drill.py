#!/usr/bin/env python3
"""Plan a safe Codex App thread-mode live drill without touching live threads."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from inspect_project import inspect_project
from inspect_team import inspect_team, resolve_repo


SCRIPT_DIR = Path(__file__).resolve().parent


def command(script_name: str, *args: str) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / script_name), *args]


def normalize_path_text(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def path_match_keys(value: str) -> set[str]:
    normalized = normalize_path_text(value)
    keys = {normalized} if normalized else set()

    parts = normalized.split("/")
    if len(parts) > 4 and parts[0] == "" and parts[1] == "" and parts[2] in {"wsl.localhost", "wsl$"}:
        keys.add("/" + "/".join(parts[4:]))

    drive_match = re.match(r"^([a-z]):/(.+)$", normalized)
    if drive_match:
        keys.add(f"/mnt/{drive_match.group(1)}/{drive_match.group(2)}")

    mount_match = re.match(r"^/mnt/([a-z])/(.+)$", normalized)
    if mount_match:
        keys.add(f"{mount_match.group(1)}:/{mount_match.group(2)}")

    return keys


def parse_codex_project_entries(entries: list[str]) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    for raw in entries:
        text = raw.strip()
        if not text:
            continue
        project_id = ""
        path = text
        if "=" in text:
            project_id, path = text.split("=", 1)
        projects.append({"project_id": project_id.strip(), "path": path.strip()})
    return projects


def codex_project_match(repo: Path, codex_projects: list[dict[str, str]]) -> dict[str, object]:
    repo_text = str(repo)
    repo_keys = path_match_keys(repo_text)
    matches = [
        project
        for project in codex_projects
        if repo_keys.intersection(path_match_keys(project.get("path", "")))
        or repo_keys.intersection(path_match_keys(project.get("project_id", "")))
    ]
    return {
        "required_for_live_drill": True,
        "checked": bool(codex_projects),
        "matched": bool(matches),
        "repo": repo_text,
        "candidate_count": len(codex_projects),
        "matches": matches,
    }


def approval_gate(live_approval_evidence: str) -> dict[str, object]:
    evidence = live_approval_evidence.strip()
    return {
        "required_for_live_drill": True,
        "approved": bool(evidence),
        "source": "--live-approval-evidence",
        "evidence": evidence,
        "live_actions_remain_blocked": not bool(evidence),
    }


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
            "followup": "Rerun this script with --codex-project <projectId=path> entries from list_projects for deterministic matching.",
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


def live_drill_success_criteria() -> list[dict[str, str]]:
    return [
        {
            "id": "project_target_proven",
            "requirement": "codex_project_match.checked=true and matched=true for the repo before creating or sending role-thread messages.",
        },
        {
            "id": "explicit_approval",
            "requirement": "The user explicitly approved live thread creation or live drill execution in the current task context.",
        },
        {
            "id": "roster_acknowledged",
            "requirement": "M, D1, and R1 thread targets are recorded; standing instructions were sent; D1 and R1 acknowledgements are recorded.",
        },
        {
            "id": "manager_to_developer_sent",
            "requirement": "Manager prepared a work_order, sent the exact payload to D1, and finalized the send with evidence when available.",
        },
        {
            "id": "developer_to_manager_received",
            "requirement": "D1 sent developer_completion directly to M, and Manager recorded the exact payload with record_inbound_handoff.py.",
        },
        {
            "id": "manager_to_reviewer_sent",
            "requirement": "Manager completed the integration checkpoint, sent the exact review_request payload to R1, and finalized the send.",
        },
        {
            "id": "reviewer_route_proven",
            "requirement": "R1 sent reviewer_accepted to M, or sent reviewer_fix directly to D1 with a separate Manager copy and recorded send state.",
        },
        {
            "id": "no_manager_polling_transport",
            "requirement": "read_thread was not used as normal transport; any read_thread use is explicitly marked as recovery, audit, or user-requested status.",
        },
    ]


def completion_evidence_contract(repo: Path) -> list[dict[str, object]]:
    return [
        {
            "evidence": "codex_project_match",
            "source": "plan_codex_thread_drill.py output after passing list_projects candidates with --codex-project.",
            "must_show": ["checked=true", "matched=true", f"repo={repo}"],
        },
        {
            "evidence": "approval_gate",
            "source": "plan_codex_thread_drill.py output after passing current-turn approval summary with --live-approval-evidence.",
            "must_show": ["approved=true", "explicit current-context approval evidence"],
        },
        {
            "evidence": "team_readiness",
            "source": "inspect_team.py --repo <repo-root> --print-json",
            "must_show": ["codex_thread_ready=true", "acknowledgements_complete=true", "handoff_route_valid=true"],
        },
        {
            "evidence": "manager_send_events",
            "source": "prepare_outbound_handoff.py and finalize_outbound_handoff.py outputs plus run artifacts.",
            "must_show": ["work_order finalized sent", "review_request finalized sent", "send evidence artifact when receipt exists"],
        },
        {
            "evidence": "inbound_handoffs",
            "source": "record_inbound_handoff.py outputs and run events.jsonl.",
            "must_show": ["developer_completion recorded", "reviewer_accepted recorded or reviewer_fix send-state recorded"],
        },
        {
            "evidence": "transport_audit",
            "source": "final Manager summary and run artifacts.",
            "must_show": ["role-to-role send_message_to_thread path", "no Manager polling as normal transport"],
        },
    ]


def recommended_next_actions(
    *,
    team: dict[str, Any],
    project_match: dict[str, object],
    approval: dict[str, object],
    pending_outbound_count: int,
    reviewer_fix_needs_send_count: int,
) -> list[str]:
    if project_match.get("checked") and not project_match.get("matched"):
        return [
            "Open or add a Codex App project whose path exactly matches this repo before a live thread drill.",
            "Do not create role threads against a different project target.",
            "After the matching project appears in list_projects, rerun plan_codex_thread_drill.py with --codex-project <projectId=path>.",
        ]
    if pending_outbound_count or reviewer_fix_needs_send_count:
        return [
            "Resolve existing pending sends before starting a live drill.",
            "For pending_outbound, read payload_file and send exact contents, then finalize sent or failed.",
            "For reviewer_fix_send_state.next_handoff_sent=no, send the exact payload to D1 before advancing fix statuses.",
        ]
    if not team.get("ok"):
        return [
            "Run the non-destructive preflight first.",
            "Include list_projects and rerun this script with --codex-project <projectId=path> before any live drill.",
            "Ask the user for explicit approval before creating role threads or sending standing instructions.",
            "After approval, initialize the roster and require D1/R1 acknowledgements before any task run.",
        ]
    if team.get("manual_relay_ready") and not team.get("codex_thread_ready"):
        return [
            "Record a real Manager thread id before a direct Codex App thread drill.",
            "Use callback/manual relay only if the user chooses fallback instead of direct role-to-role messaging.",
        ]
    if team.get("codex_thread_ready"):
        if project_match.get("checked") and project_match.get("matched") and not approval.get("approved"):
            return [
                "Record explicit current-context live-drill approval before creating role threads or sending live role-thread messages.",
                "Rerun this script with --live-approval-evidence <approval summary or message id> after the user approves the live drill.",
                "Only follow live_drill_when_approved after live_drill_authorized=true.",
            ]
        if project_match.get("checked") and project_match.get("matched") and approval.get("approved"):
            return [
                "Live drill gates are satisfied; follow live_drill_when_approved in order.",
                "Create or confirm long-lived D1/R1 threads only under the matched Codex App project target.",
                "Record Manager send finalization and inbound Developer/Reviewer handoff evidence before claiming success.",
            ]
        return [
            "Confirm the exact Codex App project target with list_projects and rerun this script with --codex-project <projectId=path>.",
            "Ask the user for explicit live-drill approval only after codex_project_match.matched=true.",
            "The drill should prove M->D1, D1->M, M->R1, and R1->M or R1->D1 plus Manager copy without Manager polling.",
        ]
    return ["Inspect team readiness again before attempting a live drill."]


def build_plan(repo: Path, limit: int, codex_projects: list[dict[str, str]], live_approval_evidence: str) -> dict[str, object]:
    project = inspect_project(repo, limit)
    team = inspect_team(repo)
    project_match = codex_project_match(repo, codex_projects)
    approval = approval_gate(live_approval_evidence)
    pending_outbound_count, reviewer_fix_needs_send_count = count_pending(project.get("latest_runs"))
    ledger_ready_for_live_drill = bool(
        team.get("codex_thread_ready")
        and not pending_outbound_count
        and not reviewer_fix_needs_send_count
        and not project.get("problems")
    )
    ready_for_live_drill = bool(
        ledger_ready_for_live_drill
        and project_match["checked"]
        and project_match["matched"]
    )
    live_drill_authorized = bool(ready_for_live_drill and approval["approved"])
    return {
        "ok": True,
        "repo": str(repo),
        "ledger_ready_for_live_drill": ledger_ready_for_live_drill,
        "ready_for_live_drill": ready_for_live_drill,
        "live_drill_authorized": live_drill_authorized,
        "requires_explicit_live_drill_approval": True,
        "approval_gate": approval,
        "can_run_non_destructive_preflight_now": True,
        "codex_project_match": project_match,
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
        "live_drill_success_criteria": live_drill_success_criteria(),
        "completion_evidence_contract": completion_evidence_contract(repo),
        "recommended_next_actions": recommended_next_actions(
            team=team,
            project_match=project_match,
            approval=approval,
            pending_outbound_count=pending_outbound_count,
            reviewer_fix_needs_send_count=reviewer_fix_needs_send_count,
        ),
    }


def print_text(plan: dict[str, object]) -> None:
    state = plan.get("current_state", {})
    project_match = plan.get("codex_project_match", {})
    print(f"OK: {str(plan.get('ok', False)).lower()}")
    print(f"Repo: {plan.get('repo', '')}")
    print(f"Ledger Ready For Live Drill: {str(plan.get('ledger_ready_for_live_drill', False)).lower()}")
    print(f"Ready For Live Drill: {str(plan.get('ready_for_live_drill', False)).lower()}")
    print(f"Live Drill Authorized: {str(plan.get('live_drill_authorized', False)).lower()}")
    print(f"Requires Explicit Live Drill Approval: {str(plan.get('requires_explicit_live_drill_approval', True)).lower()}")
    approval = plan.get("approval_gate", {})
    if isinstance(approval, dict):
        print(f"Approval Gate Approved: {str(approval.get('approved', False)).lower()}")
    if isinstance(project_match, dict):
        checked = str(project_match.get("checked", False)).lower()
        matched = str(project_match.get("matched", False)).lower()
        print(f"Codex Project Match Checked: {checked}")
        print(f"Codex Project Matched: {matched}")
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
    parser.add_argument(
        "--codex-project",
        action="append",
        default=[],
        help="Codex App project entry from list_projects as <projectId=path>. Repeat for each candidate.",
    )
    parser.add_argument(
        "--live-approval-evidence",
        default="",
        help="Current-context user approval evidence for live thread creation or message sends. This only records the gate; it does not create or send anything.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable plan.")
    args = parser.parse_args()

    if args.limit < 0:
        raise SystemExit("--limit must be 0 or greater.")
    repo, _ = resolve_repo(args.repo)
    plan = build_plan(repo, args.limit, parse_codex_project_entries(args.codex_project), args.live_approval_evidence)
    if args.print_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print_text(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
