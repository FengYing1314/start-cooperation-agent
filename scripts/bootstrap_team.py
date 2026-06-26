#!/usr/bin/env python3
"""Plan and apply automatic start-work D1/R1 thread bootstrap."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from inspect_team import resolve_repo
from plan_codex_thread_drill import approval_gate, codex_project_match, parse_codex_project_entries

SCRIPT_DIR = Path(__file__).resolve().parent


ROLE_SPECS = {
    "D1": {
        "role": "Developer",
        "title_suffix": "D1 Developer",
        "thread_arg": "--developer-thread-id",
        "standing_file": "standing-developer.md",
    },
    "R1": {
        "role": "Reviewer",
        "title_suffix": "R1 Reviewer",
        "thread_arg": "--reviewer-thread-id",
        "standing_file": "standing-reviewer.md",
    },
}


def command(script_name: str, *args: str) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / script_name), *args]


def slugify(value: str, fallback: str = "team") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:64].strip("-") or fallback


def load_team(repo: Path) -> dict[str, Any]:
    team_path = repo / ".agent-work" / "start-work" / "team" / "team.json"
    if not team_path.exists():
        return {}
    data = json.loads(team_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {team_path}")
    return data


def roster_value(team: dict[str, Any], local_id: str, key: str) -> str:
    roster = team.get("roster", {})
    entry = roster.get(local_id, {}) if isinstance(roster, dict) else {}
    if not isinstance(entry, dict):
        return ""
    return str(entry.get(key, "")).strip()


def choose_team_id(args: argparse.Namespace, team: dict[str, Any], repo: Path) -> str:
    existing = str(team.get("team_id", "")).strip()
    return slugify(args.team_id or existing or repo.name, fallback="team")


def chosen_targets(args: argparse.Namespace, team: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "M": {
            "thread_id": (args.manager_thread_id if args.manager_thread_id is not None else roster_value(team, "M", "thread_id")).strip(),
            "callback": (args.manager_callback if args.manager_callback is not None else roster_value(team, "M", "callback")).strip(),
        },
        "D1": {
            "thread_id": (args.developer_thread_id if args.developer_thread_id is not None else roster_value(team, "D1", "thread_id")).strip(),
            "callback": "",
        },
        "R1": {
            "thread_id": (args.reviewer_thread_id if args.reviewer_thread_id is not None else roster_value(team, "R1", "thread_id")).strip(),
            "callback": "",
        },
    }


def bootstrap_prompt(repo: Path, team_id: str, local_id: str, targets: dict[str, dict[str, str]]) -> str:
    spec = ROLE_SPECS[local_id]
    manager_target = targets["M"]["thread_id"] or targets["M"]["callback"] or "<manager-target-pending>"
    return f"""You are being created as {local_id} ({spec["role"]}) for start-work team {team_id}.

Project path:
{repo}

Manager target:
{manager_target}

Bootstrap rules:
- Do not edit, inspect, review, or implement repository files yet.
- Wait for the Manager to send the start-work standing instructions for this team.
- After the standing instructions arrive, save the roster and reply with the exact acknowledgement line requested there.
- Future handoffs must use the roster target directly with thread messaging when available; do not wait for Manager to read this thread as normal transport.

Reply now with: BOOTSTRAP READY for {local_id}, team {team_id}; waiting for standing instructions.
"""


def selected_project(project_match: dict[str, object]) -> dict[str, str]:
    matches = project_match.get("matches", [])
    if not isinstance(matches, list) or not matches:
        return {}
    first = matches[0]
    return first if isinstance(first, dict) else {}


def role_missing(local_id: str, targets: dict[str, dict[str, str]], args: argparse.Namespace) -> bool:
    if local_id == "D1" and args.replace_developer:
        return True
    if local_id == "R1" and args.replace_reviewer:
        return True
    return not bool(targets[local_id]["thread_id"])


def create_thread_requests(
    *,
    repo: Path,
    team_id: str,
    targets: dict[str, dict[str, str]],
    project: dict[str, str],
    missing_roles: list[str],
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    project_id = str(project.get("project_id", "")).strip()
    target = {"type": "project", "projectId": project_id, "environment": {"type": "local"}} if project_id else {}
    for local_id in missing_roles:
        spec = ROLE_SPECS[local_id]
        title = f"SW Team {team_id} {spec['title_suffix']}"
        requests.append(
            {
                "local_id": local_id,
                "role": spec["role"],
                "tool": "create_thread",
                "request": {
                    "target": target,
                    "prompt": bootstrap_prompt(repo, team_id, local_id, targets),
                },
                "set_title_after_create": {
                    "tool": "set_thread_title",
                    "title": title,
                    "threadId": "<returned threadId>",
                },
                "record_returned_thread_id_as": spec["thread_arg"],
            }
        )
    return requests


def apply_roster_command(
    repo: Path,
    team_id: str,
    targets: dict[str, dict[str, str]],
    project_docs: list[str],
) -> list[str]:
    args = ["--repo", str(repo), "--team-id", team_id]
    if targets["M"]["thread_id"]:
        args.extend(["--manager-thread-id", targets["M"]["thread_id"]])
    if targets["M"]["callback"]:
        args.extend(["--manager-callback", targets["M"]["callback"]])
    args.extend(["--developer-thread-id", targets["D1"]["thread_id"] or "<created-D1-thread-id>"])
    args.extend(["--reviewer-thread-id", targets["R1"]["thread_id"] or "<created-R1-thread-id>"])
    for doc in project_docs:
        args.extend(["--project-doc", doc])
    args.append("--print-json")
    return command("init_team.py", *args)


def run_apply_roster(cmd: list[str]) -> dict[str, Any]:
    if any(part.startswith("<") and part.endswith(">") for part in cmd):
        raise SystemExit("Cannot --apply-roster until manager, developer, and reviewer thread targets are concrete.")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"init_team.py failed.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    data = json.loads(proc.stdout)
    if not isinstance(data, dict):
        raise SystemExit("init_team.py did not return a JSON object.")
    return data


def standing_instruction_sends(repo: Path, targets: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    team_dir = repo / ".agent-work" / "start-work" / "team"
    sends = []
    for local_id in ("D1", "R1"):
        spec = ROLE_SPECS[local_id]
        sends.append(
            {
                "local_id": local_id,
                "threadId": targets[local_id]["thread_id"] or f"<created-{local_id}-thread-id>",
                "prompt_file": str(team_dir / spec["standing_file"]),
                "prompt_instruction": "Read prompt_file as UTF-8 and pass its exact contents as send_message_to_thread.prompt; do not send only the path.",
            }
        )
    return sends


def ack_commands(repo: Path) -> list[list[str]]:
    return [
        command("ack_team.py", "--repo", str(repo), "--role", "D1", "--print-json"),
        command("ack_team.py", "--repo", str(repo), "--role", "R1", "--print-json"),
        command("inspect_team.py", "--repo", str(repo), "--print-json"),
    ]


def blocked_reasons(
    *,
    project_match: dict[str, object],
    project: dict[str, str],
    approval: dict[str, object],
    targets: dict[str, dict[str, str]],
    missing_roles: list[str],
) -> list[str]:
    reasons: list[str] = []
    if missing_roles and not project_match.get("checked"):
        reasons.append("Run list_projects and rerun with --codex-project <projectId=path> before creating role threads.")
    elif missing_roles and not project_match.get("matched"):
        reasons.append("No Codex App project target exactly matches this repo; do not create D1/R1 under a different project.")
    elif missing_roles and not str(project.get("project_id", "")).strip():
        reasons.append("Matched Codex App project is missing projectId; rerun with --codex-project <projectId=path> from list_projects.")
    if missing_roles and not approval.get("approved"):
        reasons.append("Live thread creation requires explicit current-context approval evidence.")
    if not (targets["M"]["thread_id"] or targets["M"]["callback"]):
        reasons.append("Manager target is missing; provide --manager-thread-id for direct codex-thread mode or --manager-callback for manual relay.")
    return reasons


def next_actions(
    *,
    missing_roles: list[str],
    can_create: bool,
    can_apply: bool,
    direct_ready: bool,
    blocked: list[str],
) -> list[str]:
    if blocked:
        return blocked
    if can_create:
        return [
            "Call create_thread for each create_thread_requests item using request.target and request.prompt exactly.",
            "After each create_thread succeeds, call set_thread_title with the returned threadId and set_title_after_create.title.",
            "Rerun bootstrap_team.py with the returned D1/R1 thread ids and --apply-roster.",
        ]
    if can_apply:
        actions = [
            "Run apply_roster_command, or rerun bootstrap_team.py with --apply-roster.",
            "Read each standing_instruction_sends.prompt_file and send its exact contents to the listed threadId.",
            "Wait for D1/R1 acknowledgement replies, then run each ack command and inspect_team.",
        ]
        if not direct_ready:
            actions.append("This roster is callback/manual-relay only until M.thread_id is recorded.")
        return actions
    if missing_roles:
        return ["Resolve missing D1/R1 thread ids, then rerun bootstrap_team.py."]
    return [
        "Roster targets are present; send standing instructions if acknowledgements are incomplete.",
        "Run inspect_team before starting a task run.",
    ]


def build_bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    repo, _ = resolve_repo(args.repo)
    team = load_team(repo)
    team_id = choose_team_id(args, team, repo)
    targets = chosen_targets(args, team)
    if args.replace_developer:
        targets["D1"]["thread_id"] = (args.developer_thread_id or "").strip()
    if args.replace_reviewer:
        targets["R1"]["thread_id"] = (args.reviewer_thread_id or "").strip()

    projects = parse_codex_project_entries(args.codex_project)
    project_match = codex_project_match(repo, projects)
    approval = approval_gate(args.live_approval_evidence)
    project = selected_project(project_match)
    missing_roles = [local_id for local_id in ("D1", "R1") if role_missing(local_id, targets, args)]
    blocked = blocked_reasons(
        project_match=project_match,
        project=project,
        approval=approval,
        targets=targets,
        missing_roles=missing_roles,
    )
    can_create = bool(missing_roles and project and approval.get("approved") and not blocked)
    manager_target_present = bool(targets["M"]["thread_id"] or targets["M"]["callback"])
    can_apply = bool(manager_target_present and targets["D1"]["thread_id"] and targets["R1"]["thread_id"])
    direct_ready = bool(targets["M"]["thread_id"] and targets["D1"]["thread_id"] and targets["R1"]["thread_id"])
    apply_cmd = apply_roster_command(repo, team_id, targets, args.project_doc or [])

    applied_roster: dict[str, Any] = {}
    if args.apply_roster:
        if not can_apply:
            raise SystemExit("Cannot --apply-roster until M target, D1.thread_id, and R1.thread_id are present.")
        applied_roster = run_apply_roster(apply_cmd)

    return {
        "ok": True,
        "repo": str(repo),
        "team_id": team_id,
        "existing_team_loaded": bool(team),
        "manager_target": targets["M"],
        "role_targets": {
            "D1": targets["D1"],
            "R1": targets["R1"],
        },
        "manager_thread_id_required_for_direct_codex_thread": not bool(targets["M"]["thread_id"]),
        "direct_codex_thread_ready_after_apply": direct_ready,
        "manual_relay_ready_after_apply": bool(targets["M"]["callback"] and targets["D1"]["thread_id"] and targets["R1"]["thread_id"]),
        "codex_project_match": project_match,
        "approval_gate": approval,
        "missing_role_threads": missing_roles,
        "blocked_reasons": blocked,
        "can_create_role_threads": can_create,
        "can_apply_roster": can_apply,
        "create_thread_requests": create_thread_requests(
            repo=repo,
            team_id=team_id,
            targets=targets,
            project=project,
            missing_roles=missing_roles,
        ),
        "apply_roster_command": apply_cmd,
        "applied_roster": applied_roster,
        "standing_instruction_sends": standing_instruction_sends(repo, targets),
        "ack_commands": ack_commands(repo),
        "closed_loop_next_actions": next_actions(
            missing_roles=missing_roles,
            can_create=can_create,
            can_apply=can_apply,
            direct_ready=direct_ready,
            blocked=blocked,
        ),
    }


def print_text(result: dict[str, Any]) -> None:
    print(f"OK: {str(result.get('ok', False)).lower()}")
    print(f"Team ID: {result.get('team_id', '')}")
    print(f"Can Create Role Threads: {str(result.get('can_create_role_threads', False)).lower()}")
    print(f"Can Apply Roster: {str(result.get('can_apply_roster', False)).lower()}")
    print(f"Direct Ready After Apply: {str(result.get('direct_codex_thread_ready_after_apply', False)).lower()}")
    blocked = result.get("blocked_reasons", [])
    if isinstance(blocked, list) and blocked:
        print("Blocked Reasons:")
        for reason in blocked:
            print(f"- {reason}")
    actions = result.get("closed_loop_next_actions", [])
    if isinstance(actions, list) and actions:
        print("Closed Loop Next Actions:")
        for action in actions:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--team-id", default="", help="Stable team id. Defaults to existing team id, then repo name.")
    parser.add_argument("--manager-thread-id", default=None, help="Exact current Manager thread id for direct codex-thread mode.")
    parser.add_argument("--manager-callback", default=None, help="Fallback Manager callback/manual relay target.")
    parser.add_argument("--developer-thread-id", default=None, help="Existing or newly created D1 thread id.")
    parser.add_argument("--reviewer-thread-id", default=None, help="Existing or newly created R1 thread id.")
    parser.add_argument("--replace-developer", action="store_true", help="Plan a replacement D1 thread even if one exists.")
    parser.add_argument("--replace-reviewer", action="store_true", help="Plan a replacement R1 thread even if one exists.")
    parser.add_argument("--project-doc", action="append", default=[], help="Project instruction document to include in standing instructions. Repeatable.")
    parser.add_argument("--codex-project", action="append", default=[], help="Codex App project entry from list_projects as <projectId=path>. Repeatable.")
    parser.add_argument("--live-approval-evidence", default="", help="Current-context user approval evidence for creating/sending live role threads.")
    parser.add_argument("--apply-roster", action="store_true", help="Run init_team.py when all concrete thread targets are known.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable bootstrap plan.")
    args = parser.parse_args()

    result = build_bootstrap(args)
    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
