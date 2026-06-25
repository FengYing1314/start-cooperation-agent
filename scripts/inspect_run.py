#!/usr/bin/env python3
"""Inspect a start-work run ledger and report a structured resume summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from start_work_contract import RUN_STATUSES, current_run_status, next_allowed_statuses


def load_json_object(path: Path, problems: list[str]) -> dict[str, object]:
    if not path.exists():
        problems.append(f"Missing JSON file: {path.name}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"Invalid JSON in {path.name}: {exc}")
        return {}
    if not isinstance(data, dict):
        problems.append(f"Expected JSON object in {path.name}")
        return {}
    return data


def load_events(path: Path, problems: list[str]) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"Invalid JSONL event at events.jsonl:{index}: {exc}")
            continue
        if not isinstance(event, dict):
            problems.append(f"Expected JSON object at events.jsonl:{index}")
            continue
        events.append(event)
    return events


def compact_event(event: dict[str, object] | None) -> dict[str, object] | None:
    if event is None:
        return None
    return {
        "id": event.get("id", ""),
        "time": event.get("time", ""),
        "actor": event.get("actor", ""),
        "to": event.get("to", ""),
        "run_status": event.get("run_status", ""),
        "summary": event.get("summary", ""),
        "file": event.get("file", ""),
    }


def latest_status_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if str(event.get("run_status", "")).strip():
            return event
    return None


def next_actions(current_status: str, allowed: list[str], problems: list[str]) -> list[str]:
    if problems:
        return [
            "Repair the listed ledger problems before appending more events.",
            "Use append_event.py --allow-status-jump only for explicit recovery or audit correction.",
        ]
    if current_status == "init":
        return [
            "Write the Manager work order from references/templates-work-order.md.",
            "Record the outbound work order with append_event.py --kind message --run-status manager_work_order.",
        ]
    if current_status == "manager_work_order":
        return [
            "Send the recorded work order to D1 with send_message_to_thread.",
            "Only after the send succeeds, append developer_running.",
        ]
    if current_status == "developer_running":
        return [
            "Wait for the Developer completion handoff through the roster target.",
            "When the handoff arrives, record developer_done; use read_thread only for recovery or user-requested audit.",
        ]
    if current_status == "developer_done":
        return [
            "Manager inspects the diff and runs or records checks.",
            "Append main_integration_check after the integration checkpoint is complete.",
        ]
    if current_status == "main_integration_check":
        return [
            "Prepare the review-ready package from references/templates-review.md.",
            "Send it to R1, then append reviewer_running only after the send succeeds.",
        ]
    if current_status == "reviewer_running":
        return [
            "Wait for Reviewer accepted, blocked, or fix-required handoff through the roster target.",
            "Record review_done when the review handoff is received.",
        ]
    if current_status == "review_done":
        return [
            "If accepted, append accepted; if blocking findings remain, append fix_required.",
            "Do not final-deliver until Manager has verified the current repository state.",
        ]
    if current_status == "fix_required":
        return [
            "Route blocking fixes to D1 or Manager according to ownership.",
            "Append developer_fix_running after sending a real Developer fix request, or main_fixing when Manager owns the fix.",
        ]
    if current_status == "developer_fix_running":
        return [
            "Wait for the Developer fix-complete handoff.",
            "Record main_integration_check after Manager verifies the fix handoff and current diff.",
        ]
    if current_status == "main_fixing":
        return [
            "Complete the Manager-owned fix.",
            "Append main_integration_check before returning to Reviewer.",
        ]
    if current_status == "accepted":
        return [
            "Prepare the final user-facing summary from references/templates-final.md.",
            "Append final_delivery after Manager verifies checks, risks, and Reviewer acceptance.",
        ]
    if current_status == "blocked":
        return [
            "Report the blocker, repeated condition, checks attempted, and required user or external action.",
            "Do not continue the loop until the blocking condition changes.",
        ]
    if current_status == "final_delivery":
        return ["No run status remains; use inspect_project.py for a project-level audit if needed."]
    if allowed:
        return [f"Advance with append_event.py to one of: {', '.join(allowed)}."]
    return ["Inspect the ledger and protocol before appending another event."]


def inspect_run(run_dir: Path) -> dict[str, object]:
    problems: list[str] = []
    if not run_dir.exists():
        problems.append(f"Run directory does not exist: {run_dir}")
    if not run_dir.is_dir():
        problems.append(f"Run path is not a directory: {run_dir}")

    metadata = load_json_object(run_dir / "run.json", problems)
    coordination = run_dir / "coordination.md"
    coordination_status = ""
    if coordination.exists():
        coordination_status = current_run_status(coordination.read_text(encoding="utf-8"))
    else:
        problems.append("Missing coordination.md")

    events = load_events(run_dir / "events.jsonl", problems)
    status_event = latest_status_event(events)
    metadata_status = str(metadata.get("current_status", "")).strip()
    current_status = metadata_status or coordination_status

    if metadata_status and coordination_status and metadata_status != coordination_status:
        problems.append(
            f"Status mismatch: run.json current_status={metadata_status}, "
            f"coordination.md Status={coordination_status}"
        )
    if current_status and current_status not in RUN_STATUSES:
        problems.append(f"Unknown current_status: {current_status}")
    if not current_status:
        problems.append("Missing current run status")

    metadata_event_count = metadata.get("event_count", 0)
    if not isinstance(metadata_event_count, int):
        problems.append("run.json event_count must be an integer")
    elif metadata_event_count != len(events):
        problems.append(f"Event count mismatch: run.json={metadata_event_count}, events.jsonl={len(events)}")

    last_event = events[-1] if events else None
    last_event_id = str(last_event.get("id", "")) if last_event else ""
    metadata_last_event_id = str(metadata.get("last_event_id", "")).strip()
    if metadata_last_event_id and metadata_last_event_id != last_event_id:
        problems.append(f"Last event mismatch: run.json={metadata_last_event_id}, events.jsonl={last_event_id}")

    metadata_status_event_id = str(metadata.get("status_event_id", "")).strip()
    status_event_id = str(status_event.get("id", "")) if status_event else ""
    status_event_status = str(status_event.get("run_status", "")).strip() if status_event else ""
    if metadata_status_event_id and metadata_status_event_id != status_event_id:
        problems.append(f"Status event mismatch: run.json={metadata_status_event_id}, events.jsonl={status_event_id}")
    if status_event_status and current_status and status_event_status != current_status:
        problems.append(f"Latest status event mismatch: event={status_event_status}, current_status={current_status}")

    allowed = next_allowed_statuses(current_status)
    return {
        "ok": not problems,
        "run_dir": str(run_dir),
        "run_id": metadata.get("run_id", ""),
        "mode": metadata.get("mode", ""),
        "current_status": current_status,
        "coordination_status": coordination_status,
        "metadata_status": metadata_status,
        "next_allowed_statuses": allowed,
        "event_count": len(events),
        "metadata_event_count": metadata_event_count,
        "last_event": compact_event(last_event),
        "status_event": compact_event(status_event),
        "problems": problems,
        "next_actions": next_actions(current_status, allowed, problems),
    }


def print_text(summary: dict[str, object]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Run ID: {summary.get('run_id', '')}")
    print(f"Mode: {summary.get('mode', '')}")
    print(f"Current Status: {summary.get('current_status', '')}")
    next_statuses = summary.get("next_allowed_statuses", [])
    print(f"Next Allowed: {', '.join(next_statuses) if isinstance(next_statuses, list) and next_statuses else '<none>'}")
    print(f"Events: {summary.get('event_count', 0)}")
    last_event = summary.get("last_event")
    if isinstance(last_event, dict) and last_event.get("id"):
        print(f"Last Event: {last_event.get('id')} {last_event.get('summary')}")
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
    parser.add_argument("--run-dir", required=True, help="Path to a start-work run directory.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    summary = inspect_run(Path(args.run_dir).expanduser().resolve())
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
