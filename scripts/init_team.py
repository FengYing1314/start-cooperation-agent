#!/usr/bin/env python3
"""Initialize or update a project-local long-lived start-work team roster."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

from start_work_contract import required_route_specs

IGNORE_RULE = "/.agent-work/"
SCRIPT_DIR = Path(__file__).resolve().parent


def run_git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def resolve_repo(path: str) -> tuple[Path, bool]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise SystemExit(f"Repository path does not exist: {candidate}")

    code, out, _ = run_git(candidate, "rev-parse", "--show-toplevel")
    if code == 0 and out:
        return Path(out).expanduser().resolve(), True
    return candidate, False


def slugify(value: str, fallback: str = "team") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:64].strip("-") or fallback


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def ensure_local_exclude(repo: Path, is_git_repo: bool) -> str | None:
    if not is_git_repo:
        return None

    code, out, err = run_git(repo, "rev-parse", "--git-path", "info/exclude")
    if code != 0 or not out:
        raise SystemExit(f"Unable to locate git info/exclude: {err}")

    exclude_path = Path(out)
    if not exclude_path.is_absolute():
        exclude_path = (repo / exclude_path).resolve()

    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    text = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    lines = [line.strip() for line in text.splitlines()]
    if IGNORE_RULE not in lines:
        prefix = "" if text.endswith("\n") or not text else "\n"
        with exclude_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{prefix}{IGNORE_RULE}\n")

    return str(exclude_path)


def merge_project_docs(existing: list[object], updates: list[str]) -> list[str]:
    docs: list[str] = []
    for item in existing:
        if isinstance(item, str) and item.strip() and item.strip() not in docs:
            docs.append(item.strip())
    for item in updates:
        if item.strip() and item.strip() not in docs:
            docs.append(item.strip())
    return docs


def roster_complete(team: dict[str, object]) -> bool:
    roster = team.get("roster")
    if not isinstance(roster, dict):
        return False
    developer = roster.get("D1")
    reviewer = roster.get("R1")
    manager = roster.get("M")
    if not all(isinstance(item, dict) for item in (developer, reviewer, manager)):
        return False
    if not developer.get("thread_id") or not reviewer.get("thread_id"):
        return False
    return bool(manager.get("thread_id") or manager.get("callback"))


def ack_complete(team: dict[str, object]) -> bool:
    acknowledgements = team.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        return False
    for local_id in ("D1", "R1"):
        entry = acknowledgements.get(local_id)
        if not isinstance(entry, dict) or entry.get("status") != "acknowledged":
            return False
    return True


def build_route(manager_direct: bool) -> list[dict[str, str]]:
    developer_to_manager_note = (
        "Developer sends completion directly to Manager for integration check."
        if manager_direct
        else "Developer prepares completion for Manager through callback/manual relay."
    )
    reviewer_fix_note = (
        "Reviewer sends fix request directly to Developer and sends Manager a separate copy."
        if manager_direct
        else "Reviewer sends fix request directly to Developer and prepares Manager copy through callback/manual relay."
    )
    reviewer_to_manager_note = (
        "Reviewer sends accepted or blocked status directly to Manager."
        if manager_direct
        else "Reviewer prepares accepted or blocked status for Manager through callback/manual relay."
    )
    notes = {
        ("M", "work order ready"): "Manager sends the work order directly to Developer.",
        ("D1", "implementation ready"): developer_to_manager_note,
        ("M", "review-ready package"): "Manager sends the review package directly to Reviewer.",
        ("R1", "blocking findings"): reviewer_fix_note,
        ("R1", "accepted or blocked"): reviewer_to_manager_note,
    }
    return [
        {
            "from": source,
            "to": target,
            "trigger": trigger,
            "manager_copy": manager_copy,
            "notes": notes[(source, trigger)],
        }
        for source, target, trigger, manager_copy in required_route_specs(manager_direct)
    ]


def team_markdown(team: dict[str, object]) -> str:
    roster = team["roster"]
    acknowledgements = team.get("acknowledgements", {})
    docs = team.get("project_docs", [])
    route = team.get("handoff_route", [])

    def role_row(local_id: str) -> str:
        data = roster.get(local_id, {})
        return (
            f"| {local_id} | {data.get('role', '')} | {data.get('thread_id', '')} | "
            f"{data.get('callback', '')} | {data.get('status', '')} |"
        )

    def ack_row(local_id: str) -> str:
        data = acknowledgements.get(local_id, {}) if isinstance(acknowledgements, dict) else {}
        return (
            f"| {local_id} | {data.get('status', 'pending')} | "
            f"{data.get('thread_id', '')} | {data.get('acknowledged_at', '')} | "
            f"{data.get('notes', '')} |"
        )

    route_rows = "\n".join(
        f"| {item.get('from', '')} | {item.get('to', '')} | {item.get('trigger', '')} | "
        f"{item.get('manager_copy', '')} | {item.get('notes', '')} |"
        for item in route
        if isinstance(item, dict)
    )
    doc_lines = "\n".join(f"- {doc}" for doc in docs) or "- Nearest AGENTS.md and project instructions"

    return f"""# Start Work Team

Team ID: {team["team_id"]}
Project Path: {team["repo"]}
Created At: {team["created_at"]}
Updated At: {team["updated_at"]}
Manager Direct Handoff: {team["manager_direct_handoff"]}
Roster Complete: {team["roster_complete"]}
Acknowledgements Complete: {team["acknowledgements_complete"]}

## Roster

| Local ID | Role | Thread ID | Callback | Status |
| --- | --- | --- | --- | --- |
{role_row("M")}
{role_row("D1")}
{role_row("R1")}

## Project Reading

{doc_lines}

## Handoff Route

| From | To | Trigger | Manager Copy | Notes |
| --- | --- | --- | --- | --- |
{route_rows}

## Acknowledgements

| Local ID | Ack Status | Thread ID | Acknowledged At | Notes |
| --- | --- | --- | --- | --- |
{ack_row("D1")}
{ack_row("R1")}
"""


def standing_instruction(team: dict[str, object], target: str) -> str:
    roster = team["roster"]
    docs = team.get("project_docs", [])
    route = team.get("handoff_route", [])
    target_role = roster[target]["role"]
    doc_lines = "\n".join(f"- {doc}" for doc in docs) or "- Nearest AGENTS.md and project instructions"
    roster_lines = "\n".join(
        f"- {local_id}: {data.get('role')} thread_id={data.get('thread_id') or '<none>'} "
        f"callback={data.get('callback') or '<none>'}"
        for local_id, data in roster.items()
        if isinstance(data, dict)
    )
    route_lines = "\n".join(
        f"- {item.get('from')} -> {item.get('to')}: {item.get('trigger')} "
        f"(manager copy: {item.get('manager_copy')})"
        for item in route
        if isinstance(item, dict)
    )
    manager_direct = bool(team.get("manager_direct_handoff"))

    if target == "D1" and manager_direct:
        role_rules = """- Implement only assigned work orders.
- Stay inside assigned ownership.
- Send completion handoffs directly to Manager after implementation or fixes are ready.
- If Reviewer sends blocking findings, fix only those findings unless Manager expands scope."""
    elif target == "D1":
        role_rules = """- Implement only assigned work orders.
- Stay inside assigned ownership.
- Prepare completion handoffs for Manager through the recorded callback or manual relay.
- If Reviewer sends blocking findings, fix only those findings unless Manager expands scope."""
    elif manager_direct:
        role_rules = """- Review integrated repository state only after Manager sends or authorizes a review-ready package.
- Stay read-only unless Manager explicitly changes your role.
- Send blocking fix handoffs directly to Developer and send Manager a separate status copy.
- Send accepted or blocked status directly to Manager."""
    else:
        role_rules = """- Review integrated repository state only after Manager sends or authorizes a review-ready package.
- Stay read-only unless Manager explicitly changes your role.
- Send blocking fix handoffs directly to Developer and prepare the Manager copy through callback or manual relay.
- Prepare accepted or blocked status for Manager through the recorded callback or manual relay."""

    if manager_direct:
        transport_rules = """- Send handoffs directly to the roster target thread with the available thread messaging tool.
- If thread messaging tools are not visible, call tool_search for Codex app thread send message tools.
- Do not wait for Manager to read your thread as the normal communication path.
- If direct thread messaging is unavailable, end with the exact handoff payload and target."""
    else:
        transport_rules = """- Manager has no thread_id in this roster; this team cannot run direct codex-thread tasks until Manager supplies one.
- For handoffs to Manager, use the recorded callback only if it is an actual user-approved messaging route.
- If the callback is not directly callable, end with the exact handoff payload and target for manual relay.
- Do not wait for Manager to read your thread as the normal communication path."""

    return f"""You are {target} ({target_role}) in start-work team {team["team_id"]}.

Project path:
{team["repo"]}

Shared roster:
{roster_lines}

Project reading:
{doc_lines}

Default handoff route:
{route_lines}

Role rules:
{role_rules}

Handoff payload contract:
- Every handoff you send or return must include local message id, run id, team id, From, To, status, summary, checks, `Evidence references:`, and requested next action.
- Keep the handoff message short; put bulky logs, diffs, traces, screenshots, or reports in run artifacts and cite their paths, commands, or event ids under `Evidence references:`.
- If a direct message is sent, set `Next handoff sent:` to `yes` and name the target thread.
- If a direct message is not sent, set `Next handoff sent:` to `no` and include the exact unsent payload and target.

Global rules:
- Read project instructions before changing or reviewing files.
- Do not revert unrelated changes.
- Do not stage, commit, push, or rewrite history unless the user explicitly asks.
- Do not edit Manager-owned ledger files.
{transport_rules}
- If any thread id changes, wait for a roster update before sending handoffs.
- Reply with: ACK roster saved for {target}, team {team["team_id"]}.
"""


def roster_update(team: dict[str, object], changes: list[str]) -> str:
    roster = team["roster"]
    roster_lines = "\n".join(
        f"- {local_id}: {data.get('role')} thread_id={data.get('thread_id') or '<none>'} "
        f"callback={data.get('callback') or '<none>'}"
        for local_id, data in roster.items()
        if isinstance(data, dict)
    )
    change_lines = "\n".join(f"- {change}" for change in changes) or "- Team metadata refreshed."
    return f"""Start-work roster update for team {team["team_id"]}.

Changes:
{change_lines}

Current roster:
{roster_lines}

Use this roster for all future handoffs. Acknowledge after updating your local context.
"""


def next_commands(repo: Path) -> dict[str, list[str]]:
    return {
        "inspect_team": [
            sys.executable,
            str(SCRIPT_DIR / "inspect_team.py"),
            "--repo",
            str(repo),
            "--print-json",
        ],
        "ack_developer": [
            sys.executable,
            str(SCRIPT_DIR / "ack_team.py"),
            "--repo",
            str(repo),
            "--role",
            "D1",
            "--print-json",
        ],
        "ack_reviewer": [
            sys.executable,
            str(SCRIPT_DIR / "ack_team.py"),
            "--repo",
            str(repo),
            "--role",
            "R1",
            "--print-json",
        ],
        "init_run": [
            sys.executable,
            str(SCRIPT_DIR / "init_run.py"),
            "--repo",
            str(repo),
            "--slug",
            "<work-slug>",
            "--request",
            "<user request>",
            "--print-json",
        ],
    }


def next_actions(team: dict[str, object], update_written: bool) -> list[str]:
    if not team.get("roster_complete"):
        return [
            "Complete M, D1, and R1 roster targets before creating a run.",
            "Run inspect_team after updating the roster.",
        ]
    if not team.get("acknowledgements_complete"):
        actions = [
            "Read standing-developer.md and standing-reviewer.md, then send each file's exact contents as send_message_to_thread.prompt to the roster target thread.",
            "After each role replies with the roster acknowledgement, run ack_developer and ack_reviewer.",
            "Run inspect_team before starting a task run.",
        ]
        if update_written:
            actions.insert(0, "Send roster-update.md to active role threads before recording fresh acknowledgements.")
        return actions
    return [
        "Run inspect_team to confirm codex_thread_ready or manual_relay_ready.",
        "Start the next task with init_run.",
    ]


def update_team(existing: dict[str, object] | None, args: argparse.Namespace, repo: Path, now: str) -> tuple[dict[str, object], list[str]]:
    existing_team_id = ""
    if existing and isinstance(existing.get("team_id"), str):
        existing_team_id = str(existing["team_id"]).strip()
    team_id = slugify(args.team_id or existing_team_id or repo.name or "team", fallback="team")
    team = existing or {
        "schema_version": 1,
        "team_id": team_id,
        "repo": str(repo),
        "created_at": now,
        "roster": {},
        "project_docs": [],
    }
    changes: list[str] = []

    if team.get("team_id") != team_id:
        changes.append(f"team_id: {team.get('team_id')} -> {team_id}")
        team["team_id"] = team_id
    if team.get("repo") != str(repo):
        changes.append(f"repo: {team.get('repo')} -> {repo}")
        team["repo"] = str(repo)

    roster = team.setdefault("roster", {})
    if not isinstance(roster, dict):
        raise SystemExit("team.json roster must be an object")
    acknowledgements = team.setdefault("acknowledgements", {})
    if not isinstance(acknowledgements, dict):
        raise SystemExit("team.json acknowledgements must be an object")
    defaults = {
        "M": {"role": "Manager", "thread_id": "", "callback": "", "status": "active"},
        "D1": {"role": "Developer", "thread_id": "", "callback": "", "status": "active"},
        "R1": {"role": "Reviewer", "thread_id": "", "callback": "", "status": "active"},
    }
    for local_id, default in defaults.items():
        current = roster.setdefault(local_id, default.copy())
        if not isinstance(current, dict):
            raise SystemExit(f"team.json roster.{local_id} must be an object")
        for key, value in default.items():
            current.setdefault(key, value)
    for local_id in ("D1", "R1"):
        current_ack = acknowledgements.setdefault(
            local_id,
            {"status": "pending", "thread_id": "", "acknowledged_at": "", "notes": ""},
        )
        if not isinstance(current_ack, dict):
            raise SystemExit(f"team.json acknowledgements.{local_id} must be an object")
        current_ack.setdefault("status", "pending")
        current_ack.setdefault("thread_id", "")
        current_ack.setdefault("acknowledged_at", "")
        current_ack.setdefault("notes", "")

    updates = {
        ("M", "thread_id"): args.manager_thread_id,
        ("M", "callback"): args.manager_callback,
        ("D1", "thread_id"): args.developer_thread_id,
        ("R1", "thread_id"): args.reviewer_thread_id,
    }
    for (local_id, key), value in updates.items():
        if value is None:
            continue
        old = str(roster[local_id].get(key, ""))
        new = value.strip()
        if old != new:
            changes.append(f"{local_id}.{key}: {old or '<empty>'} -> {new or '<empty>'}")
            roster[local_id][key] = new

    docs = merge_project_docs(team.get("project_docs", []), args.project_doc or [])
    if docs != team.get("project_docs", []):
        changes.append("project_docs updated")
        team["project_docs"] = docs

    if changes:
        for local_id in ("D1", "R1"):
            acknowledgements[local_id] = {
                "status": "pending",
                "thread_id": str(roster[local_id].get("thread_id", "")),
                "acknowledged_at": "",
                "notes": "Pending acknowledgement after roster update.",
            }

    manager = roster["M"]
    team["manager_direct_handoff"] = bool(manager.get("thread_id"))
    team["handoff_route"] = build_route(bool(team["manager_direct_handoff"]))
    team["roster_complete"] = roster_complete(team)
    team["acknowledgements_complete"] = ack_complete(team)
    team["updated_at"] = now
    return team, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--team-id", default="", help="Stable team id. Defaults to the existing team id, then the repo name.")
    parser.add_argument("--manager-thread-id", default=None, help="Current Manager thread id, when available.")
    parser.add_argument("--manager-callback", default=None, help="Fallback target for Manager handoffs when thread id is unavailable.")
    parser.add_argument("--developer-thread-id", default=None, help="Long-lived Developer thread id.")
    parser.add_argument("--reviewer-thread-id", default=None, help="Long-lived Reviewer thread id.")
    parser.add_argument("--project-doc", action="append", default=[], help="Project instruction document to include in standing instructions. Repeatable.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable result.")
    args = parser.parse_args()

    repo, is_git_repo = resolve_repo(args.repo)
    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    ensure_local_exclude(repo, is_git_repo)

    team_dir = repo / ".agent-work" / "start-work" / "team"
    team_dir.mkdir(parents=True, exist_ok=True)
    team_path = team_dir / "team.json"
    existing = load_json(team_path)
    created = existing is None
    team, changes = update_team(existing, args, repo, now)

    team_path.write_text(json.dumps(team, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (team_dir / "team.md").write_text(team_markdown(team), encoding="utf-8")
    (team_dir / "standing-developer.md").write_text(standing_instruction(team, "D1"), encoding="utf-8")
    (team_dir / "standing-reviewer.md").write_text(standing_instruction(team, "R1"), encoding="utf-8")
    update_written = False
    if changes and not created:
        (team_dir / "roster-update.md").write_text(roster_update(team, changes), encoding="utf-8")
        update_written = True

    result = {
        "created": created,
        "updated": bool(changes),
        "team_id": team["team_id"],
        "repo": str(repo),
        "team_dir": str(team_dir),
        "team_json": str(team_path),
        "roster_complete": team["roster_complete"],
        "acknowledgements_complete": team["acknowledgements_complete"],
        "manager_direct_handoff": team["manager_direct_handoff"],
        "changes": changes,
        "standing_developer": str(team_dir / "standing-developer.md"),
        "standing_reviewer": str(team_dir / "standing-reviewer.md"),
        "roster_update": str(team_dir / "roster-update.md") if update_written else "",
        "next_commands": next_commands(repo),
        "next_actions": next_actions(team, update_written),
    }

    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        action = "created" if created else "updated"
        print(f"Start-work team {action}: {team_dir}")
        print(f"Roster complete: {team['roster_complete']}")
        print(f"Acknowledgements complete: {team['acknowledgements_complete']}")
        print(f"Manager direct handoff: {team['manager_direct_handoff']}")
        print(f"Developer standing instruction: {team_dir / 'standing-developer.md'}")
        print(f"Reviewer standing instruction: {team_dir / 'standing-reviewer.md'}")
        if update_written:
            print(f"Roster update: {team_dir / 'roster-update.md'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
