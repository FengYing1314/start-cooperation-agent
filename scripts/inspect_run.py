#!/usr/bin/env python3
"""Inspect a start-work run ledger and report a structured resume summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from start_work_contract import RUN_STATUSES, current_run_status, next_allowed_statuses
from validate_handoff import extract_label

SCRIPT_DIR = Path(__file__).resolve().parent
FINALIZE_OUTBOUND_HANDOFF = SCRIPT_DIR / "finalize_outbound_handoff.py"

OUTBOUND_RESUME = {
    "work_order": {
        "actor": "M",
        "to": "D1",
        "current_status": "manager_work_order",
        "record_status": "manager_work_order",
        "post_send_status": "developer_running",
        "send_action": "Send the payload to D1 with send_message_to_thread.",
    },
    "review_request": {
        "actor": "M",
        "to": "R1",
        "current_status": "main_integration_check",
        "record_status": "",
        "post_send_status": "reviewer_running",
        "send_action": "Send the payload to R1 with send_message_to_thread.",
    },
}


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


def next_handoff_sent_word(text: str) -> str:
    value = extract_label(text, "Next handoff sent")[1]
    if not value:
        return ""
    return value.split(None, 1)[0].strip(".,;:").lower()


def latest_reviewer_fix_send_state(run_dir: Path, events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("actor") != "R1" or event.get("to") != "D1":
            continue
        if event.get("run_status") != "review_done":
            continue
        summary = str(event.get("summary", "")).lower()
        if "reviewer fix" not in summary:
            continue
        file_name = str(event.get("file", "")).strip()
        payload_text = ""
        if file_name:
            payload_path = run_dir / file_name
            if payload_path.exists():
                payload_text = payload_path.read_text(encoding="utf-8")
        sent_word = next_handoff_sent_word(payload_text) if payload_text else ""
        return {
            "event_id": event.get("id", ""),
            "file": file_name,
            "next_handoff_sent": sent_word,
        }
    return None


def latest_status_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if str(event.get("run_status", "")).strip():
            return event
    return None


def finalize_command(run_dir: Path, kind: str, event_id: str, result: str) -> list[str]:
    command = [
        sys.executable,
        str(FINALIZE_OUTBOUND_HANDOFF),
        "--run-dir",
        str(run_dir),
        "--kind",
        kind,
        "--event-id",
        event_id,
        "--result",
        result,
        "--print-json",
    ]
    if result == "failed":
        command.extend(["--error", "<send error>"])
    return command


def outbound_finalized(
    events: list[dict[str, object]],
    start_index: int,
    spec: dict[str, str],
    thread_id: str,
) -> bool:
    for event in events[start_index + 1:]:
        same_route = (
            event.get("actor") == spec["actor"]
            and event.get("to") == spec["to"]
            and event.get("thread_id") == thread_id
        )
        if not same_route:
            continue
        if event.get("run_status") == spec["post_send_status"]:
            return True
        if event.get("kind") == "blocker":
            return True
    return False


def find_pending_outbound(
    run_dir: Path,
    current_status: str,
    events: list[dict[str, object]],
) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for kind, spec in OUTBOUND_RESUME.items():
        if current_status != spec["current_status"]:
            continue
        for index, event in enumerate(events):
            if event.get("kind") != "message":
                continue
            if event.get("actor") != spec["actor"] or event.get("to") != spec["to"]:
                continue
            record_status = spec["record_status"]
            if record_status and event.get("run_status") != record_status:
                continue
            if not record_status and str(event.get("run_status", "")).strip():
                continue
            thread_id = str(event.get("thread_id", "")).strip()
            if not thread_id:
                continue
            file_name = str(event.get("file", "")).strip()
            if not file_name:
                continue
            if outbound_finalized(events, index, spec, thread_id):
                continue
            event_id = str(event.get("id", "")).strip()
            candidates.append(
                {
                    "kind": kind,
                    "event_id": event_id,
                    "send_to": spec["to"],
                    "send_to_thread_id": thread_id,
                    "payload_file": str(run_dir / file_name) if file_name else "",
                    "post_send_status": spec["post_send_status"],
                    "send_action": spec["send_action"],
                    "finalize_sent_command": finalize_command(run_dir, kind, event_id, "sent"),
                    "finalize_failed_command": finalize_command(run_dir, kind, event_id, "failed"),
                }
            )
    return candidates[-1] if candidates else None


def next_actions(
    current_status: str,
    allowed: list[str],
    problems: list[str],
    pending_outbound: dict[str, object] | None,
    reviewer_fix_send_state: dict[str, object] | None,
) -> list[str]:
    if problems:
        return [
            "Repair the listed ledger problems before appending more events.",
            "Use append_event.py --allow-status-jump only for explicit recovery or audit correction.",
        ]
    if pending_outbound:
        payload_file = str(pending_outbound.get("payload_file", "")).strip() or "the recorded payload"
        return [
            f"Pending outbound {pending_outbound.get('kind', '')} {pending_outbound.get('event_id', '')}: {pending_outbound.get('send_action', '')}",
            f"Use payload file: {payload_file}",
            "After send_message_to_thread succeeds, run pending_outbound.finalize_sent_command.",
            "If send_message_to_thread fails, run pending_outbound.finalize_failed_command with a concrete --error value.",
        ]
    if current_status == "init":
        return [
            "Write the Manager work order from references/templates-work-order.md.",
            "Record the outbound work order with append_event.py --kind message --run-status manager_work_order.",
        ]
    if current_status == "manager_work_order":
        return [
            "If pending_outbound is missing, prepare the work order with prepare_outbound_handoff.py --kind work_order.",
            "Send the prepared payload_file to D1 with send_message_to_thread, then run finalize_sent_command or finalize_failed_command.",
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
            "Prepare the review-ready package from references/templates-review.md with prepare_outbound_handoff.py --kind review_request.",
            "Send it to R1, then run finalize_sent_command or finalize_failed_command.",
        ]
    if current_status == "reviewer_running":
        return [
            "Wait for Reviewer accepted, blocked, or fix-required handoff through the roster target.",
            "Record review_done when the review handoff is received.",
        ]
    if current_status == "review_done":
        if reviewer_fix_send_state:
            sent_word = str(reviewer_fix_send_state.get("next_handoff_sent", ""))
            if sent_word == "no":
                return [
                    "Latest reviewer_fix copy says Next handoff sent: no.",
                    "Send or relay that exact fix payload to D1 before appending fix_required or developer_fix_running.",
                    "After the real D1 send succeeds, record fix_required and then developer_fix_running.",
                ]
            if sent_word == "yes":
                return [
                    "Latest reviewer_fix copy says the D1 fix handoff was sent.",
                    "Run the returned follow-up commands from record_inbound_handoff.py, or append fix_required then developer_fix_running after verifying the real send.",
                ]
        return [
            "If accepted, append accepted; if blocking findings remain, append fix_required.",
            "Do not final-deliver until Manager has verified the current repository state.",
        ]
    if current_status == "fix_required":
        return [
            "Reviewer-originated D1 fix handoffs should arrive as a Manager copy and be recorded with record_inbound_handoff.py --kind reviewer_fix.",
            "If Manager owns the fix instead, append main_fixing.",
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
    pending_outbound = None if problems else find_pending_outbound(run_dir, current_status, events)
    reviewer_fix_send_state = None if problems else latest_reviewer_fix_send_state(run_dir, events)
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
        "pending_outbound": pending_outbound,
        "reviewer_fix_send_state": reviewer_fix_send_state,
        "problems": problems,
        "next_actions": next_actions(current_status, allowed, problems, pending_outbound, reviewer_fix_send_state),
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
    pending_outbound = summary.get("pending_outbound")
    if isinstance(pending_outbound, dict) and pending_outbound.get("event_id"):
        print(
            f"Pending Outbound: {pending_outbound.get('kind')} "
            f"{pending_outbound.get('event_id')} -> {pending_outbound.get('send_to')}"
        )
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
