#!/usr/bin/env python3
"""Record a Developer or Reviewer acknowledgement for a start-work team roster."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def run_git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def resolve_repo(path: str) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise SystemExit(f"Repository path does not exist: {candidate}")

    code, out, _ = run_git(candidate, "rev-parse", "--show-toplevel")
    if code == 0 and out:
        return Path(out).expanduser().resolve()
    return candidate


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"Start-work team is not initialized: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def ack_complete(team: dict[str, object]) -> bool:
    acknowledgements = team.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        return False
    for local_id in ("D1", "R1"):
        entry = acknowledgements.get(local_id)
        if not isinstance(entry, dict) or entry.get("status") != "acknowledged":
            return False
    return True


def render_team_markdown(team: dict[str, object]) -> str:
    roster = team.get("roster", {})
    acknowledgements = team.get("acknowledgements", {})
    docs = team.get("project_docs", [])
    route = team.get("handoff_route", [])

    def role_row(local_id: str) -> str:
        entry = roster.get(local_id, {}) if isinstance(roster, dict) else {}
        return (
            f"| {local_id} | {entry.get('role', '')} | {entry.get('thread_id', '')} | "
            f"{entry.get('callback', '')} | {entry.get('status', '')} |"
        )

    def ack_row(local_id: str) -> str:
        entry = acknowledgements.get(local_id, {}) if isinstance(acknowledgements, dict) else {}
        return (
            f"| {local_id} | {entry.get('status', 'pending')} | "
            f"{entry.get('thread_id', '')} | {entry.get('acknowledged_at', '')} | "
            f"{entry.get('notes', '')} |"
        )

    route_rows = "\n".join(
        f"| {item.get('from', '')} | {item.get('to', '')} | {item.get('trigger', '')} | "
        f"{item.get('manager_copy', '')} | {item.get('notes', '')} |"
        for item in route
        if isinstance(item, dict)
    )
    doc_lines = "\n".join(f"- {doc}" for doc in docs if isinstance(doc, str)) or "- Nearest AGENTS.md and project instructions"

    return f"""# Start Work Team

Team ID: {team.get("team_id", "")}
Project Path: {team.get("repo", "")}
Created At: {team.get("created_at", "")}
Updated At: {team.get("updated_at", "")}
Manager Direct Handoff: {team.get("manager_direct_handoff", False)}
Roster Complete: {team.get("roster_complete", False)}
Acknowledgements Complete: {team.get("acknowledgements_complete", False)}

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--role", required=True, choices=["D1", "R1"], help="Role acknowledging the roster.")
    parser.add_argument("--thread-id", default="", help="Acknowledging thread id. Defaults to the roster thread id.")
    parser.add_argument("--notes", default="", help="Optional acknowledgement note.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable result.")
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    team_dir = repo / ".agent-work" / "start-work" / "team"
    team_path = team_dir / "team.json"
    team = load_json(team_path)
    roster = team.get("roster")
    if not isinstance(roster, dict):
        raise SystemExit(f"team.json roster must be an object: {team_path}")

    role_entry = roster.get(args.role)
    if not isinstance(role_entry, dict):
        raise SystemExit(f"team.json roster missing {args.role}: {team_path}")

    expected_thread = str(role_entry.get("thread_id", ""))
    ack_thread = args.thread_id.strip() or expected_thread
    if not ack_thread:
        raise SystemExit(f"No thread id available for {args.role}; update roster before acknowledging.")
    if expected_thread and ack_thread != expected_thread:
        raise SystemExit(
            f"Acknowledgement thread id mismatch for {args.role}: expected {expected_thread}, got {ack_thread}"
        )

    acknowledgements = team.setdefault("acknowledgements", {})
    if not isinstance(acknowledgements, dict):
        raise SystemExit(f"team.json acknowledgements must be an object: {team_path}")

    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    acknowledgements[args.role] = {
        "status": "acknowledged",
        "thread_id": ack_thread,
        "acknowledged_at": now,
        "notes": args.notes.strip(),
    }
    team["acknowledgements_complete"] = ack_complete(team)
    team["updated_at"] = now

    team_path.write_text(json.dumps(team, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (team_dir / "team.md").write_text(render_team_markdown(team), encoding="utf-8")

    result = {
        "team_id": team.get("team_id"),
        "repo": str(repo),
        "role": args.role,
        "thread_id": ack_thread,
        "acknowledged_at": now,
        "acknowledgements_complete": team["acknowledgements_complete"],
        "team_json": str(team_path),
    }

    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Recorded {args.role} acknowledgement for team {team.get('team_id')}")
        print(f"Acknowledgements complete: {team['acknowledgements_complete']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
