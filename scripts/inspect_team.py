#!/usr/bin/env python3
"""Inspect a start-work team roster and report structured readiness."""

from __future__ import annotations

import argparse
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


def resolve_repo(path: str) -> tuple[Path, bool]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise SystemExit(f"Repository path does not exist: {candidate}")

    code, out, _ = run_git(candidate, "rev-parse", "--show-toplevel")
    if code == 0 and out:
        return Path(out).expanduser().resolve(), True
    return candidate, False


def load_json_object(path: Path, problems: list[str]) -> dict[str, object]:
    if not path.exists():
        problems.append(f"Missing team registry: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"Invalid JSON in {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        problems.append(f"Expected JSON object in {path}")
        return {}
    return data


def roster_entry(roster: object, local_id: str, problems: list[str]) -> dict[str, object]:
    if not isinstance(roster, dict):
        problems.append("team.json roster must be an object")
        return {}
    entry = roster.get(local_id)
    if not isinstance(entry, dict):
        problems.append(f"Missing roster entry: {local_id}")
        return {}
    return entry


def compact_roster_entry(entry: dict[str, object]) -> dict[str, object]:
    return {
        "role": entry.get("role", ""),
        "thread_id": entry.get("thread_id", ""),
        "callback": entry.get("callback", ""),
        "status": entry.get("status", ""),
    }


def acknowledgement_entry(acknowledgements: object, local_id: str) -> dict[str, object]:
    if not isinstance(acknowledgements, dict):
        return {}
    entry = acknowledgements.get(local_id)
    return entry if isinstance(entry, dict) else {}


def acknowledgement_ready(
    acknowledgements: object,
    local_id: str,
    expected_thread: str,
    problems: list[str],
) -> bool:
    entry = acknowledgement_entry(acknowledgements, local_id)
    if entry.get("status") != "acknowledged":
        problems.append(f"{local_id} acknowledgement pending")
        return False
    ack_thread = str(entry.get("thread_id", "")).strip()
    if expected_thread and ack_thread != expected_thread:
        problems.append(f"{local_id} acknowledgement thread mismatch: expected {expected_thread}, got {ack_thread}")
        return False
    return True


def route_entries(handoff_route: object, problems: list[str]) -> list[dict[str, object]]:
    if not isinstance(handoff_route, list):
        problems.append("team.json handoff_route must be a list")
        return []
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(handoff_route, start=1):
        if not isinstance(entry, dict):
            problems.append(f"handoff_route entry {index} must be an object")
            continue
        entries.append(entry)
    return entries


def has_route(
    entries: list[dict[str, object]],
    source: str,
    target: str,
    trigger: str,
    manager_copy: str,
) -> bool:
    return any(
        str(entry.get("from", "")).strip() == source
        and str(entry.get("to", "")).strip() == target
        and str(entry.get("trigger", "")).strip() == trigger
        and str(entry.get("manager_copy", "")).strip() == manager_copy
        for entry in entries
    )


def validate_handoff_route(
    entries: list[dict[str, object]],
    *,
    manager_target: str,
    problems: list[str],
) -> bool:
    required = [
        ("M", "D1", "work order ready", "n/a"),
        ("D1", manager_target, "implementation ready", "n/a"),
        ("M", "R1", "review-ready package", "n/a"),
        ("R1", "D1", "blocking findings", "yes"),
        ("R1", manager_target, "accepted or blocked", "n/a"),
    ]
    missing = [
        f"{source}->{target} trigger={trigger} manager_copy={manager_copy}"
        for source, target, trigger, manager_copy in required
        if not has_route(entries, source, target, trigger, manager_copy)
    ]
    for item in missing:
        problems.append(f"Missing handoff route: {item}")
    return not missing


def inspect_team(repo: Path) -> dict[str, object]:
    problems: list[str] = []
    warnings: list[str] = []
    team_dir = repo / ".agent-work" / "start-work" / "team"
    team_path = team_dir / "team.json"
    team = load_json_object(team_path, problems)

    team_repo = str(team.get("repo", "")).strip()
    if team_repo and team_repo != str(repo):
        problems.append(f"Team repo mismatch: team.json={team_repo}, current={repo}")

    roster = team.get("roster", {})
    manager = roster_entry(roster, "M", problems)
    developer = roster_entry(roster, "D1", problems)
    reviewer = roster_entry(roster, "R1", problems)
    acknowledgements = team.get("acknowledgements", {})
    if acknowledgements and not isinstance(acknowledgements, dict):
        problems.append("team.json acknowledgements must be an object")

    manager_thread = str(manager.get("thread_id", "")).strip()
    manager_callback = str(manager.get("callback", "")).strip()
    developer_thread = str(developer.get("thread_id", "")).strip()
    reviewer_thread = str(reviewer.get("thread_id", "")).strip()

    if not (manager_thread or manager_callback):
        problems.append("M.thread_id or M.callback is required")
    if not developer_thread:
        problems.append("D1.thread_id is required")
    if not reviewer_thread:
        problems.append("R1.thread_id is required")

    developer_ack = acknowledgement_ready(acknowledgements, "D1", developer_thread, problems)
    reviewer_ack = acknowledgement_ready(acknowledgements, "R1", reviewer_thread, problems)
    acknowledgements_ready = developer_ack and reviewer_ack
    roster_ready = bool((manager_thread or manager_callback) and developer_thread and reviewer_thread)

    direct_ready = bool(manager_thread and developer_thread and reviewer_thread and acknowledgements_ready)
    manual_relay_ready = bool(
        not manager_thread and manager_callback and developer_thread and reviewer_thread and acknowledgements_ready
    )
    if manual_relay_ready:
        warnings.append("Manager has a callback but no thread_id; direct codex-thread runs will fail.")

    expected_manager_direct = bool(manager_thread)
    stored_manager_direct = team.get("manager_direct_handoff")
    if stored_manager_direct is not None and bool(stored_manager_direct) != expected_manager_direct:
        problems.append(
            "manager_direct_handoff mismatch: "
            f"team.json={stored_manager_direct}, expected={expected_manager_direct}"
        )

    stored_roster_complete = team.get("roster_complete")
    if stored_roster_complete is not None and bool(stored_roster_complete) != roster_ready:
        problems.append(f"roster_complete mismatch: team.json={stored_roster_complete}, expected={roster_ready}")

    stored_ack_complete = team.get("acknowledgements_complete")
    if stored_ack_complete is not None and bool(stored_ack_complete) != acknowledgements_ready:
        problems.append(
            f"acknowledgements_complete mismatch: team.json={stored_ack_complete}, "
            f"expected={acknowledgements_ready}"
        )

    manager_target = "M" if expected_manager_direct else "M via recorded callback (manual relay)"
    handoff_route = route_entries(team.get("handoff_route", []), problems)
    route_ready = validate_handoff_route(handoff_route, manager_target=manager_target, problems=problems)
    codex_thread_ready = direct_ready and route_ready
    callback_ready = manual_relay_ready and route_ready

    return {
        "ok": not problems and (codex_thread_ready or callback_ready),
        "repo": str(repo),
        "team_dir": str(team_dir),
        "team_json": str(team_path),
        "team_id": team.get("team_id", ""),
        "roster_complete": roster_ready,
        "acknowledgements_complete": acknowledgements_ready,
        "codex_thread_ready": codex_thread_ready,
        "manual_relay_ready": callback_ready,
        "manager_direct_handoff": expected_manager_direct,
        "handoff_route_valid": route_ready,
        "manager_target": manager_target,
        "roster": {
            "M": compact_roster_entry(manager),
            "D1": compact_roster_entry(developer),
            "R1": compact_roster_entry(reviewer),
        },
        "acknowledgements": {
            "D1": acknowledgement_entry(acknowledgements, "D1"),
            "R1": acknowledgement_entry(acknowledgements, "R1"),
        },
        "handoff_route_count": len(handoff_route),
        "warnings": warnings,
        "problems": problems,
    }


def print_text(summary: dict[str, object]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Team ID: {summary.get('team_id', '')}")
    print(f"Codex Thread Ready: {str(summary.get('codex_thread_ready', False)).lower()}")
    print(f"Manual Relay Ready: {str(summary.get('manual_relay_ready', False)).lower()}")
    print(f"Roster Complete: {str(summary.get('roster_complete', False)).lower()}")
    print(f"Acknowledgements Complete: {str(summary.get('acknowledgements_complete', False)).lower()}")
    warnings = summary.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    problems = summary.get("problems", [])
    if isinstance(problems, list) and problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    repo, _ = resolve_repo(args.repo)
    summary = inspect_team(repo)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
