#!/usr/bin/env python3
"""Validate and record a received start-work handoff in the Manager-owned ledger."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from prepare_outbound_handoff import APPEND_EVENT, append_event
from validate_handoff import extract_label, validate_payload


INBOUND = {
    "developer_completion": {
        "actor": "D1",
        "to": "M",
        "summary": "developer completion received",
        "status_map": {
            "complete": "developer_done",
            "blocked": "blocked",
        },
        "next_action": "Manager should inspect the diff and checks before appending main_integration_check.",
    },
    "developer_fix_completion": {
        "actor": "D1",
        "to": "M",
        "summary": "developer fix completion received",
        "status_map": {
            "complete": "",
            "blocked": "blocked",
        },
        "next_action": "Manager should verify the fix and then run followup_status_command to append main_integration_check.",
        "followup_status": "main_integration_check",
        "followup_summary": "post-fix integration check complete",
    },
    "reviewer_fix": {
        "actor": "R1",
        "to": "D1",
        "summary": "reviewer fix copy received",
        "status_map": {
            "changes required": "review_done",
        },
        "next_action": (
            "Manager should record the blocking decision, then run followup_status_commands "
            "in order after confirming this Manager copy represents a real D1 handoff."
        ),
        "followup_statuses": [
            {
                "actor": "R1",
                "to": "D1",
                "thread_role": "D1",
                "status": "fix_required",
                "summary": "blocking findings require fixes",
            },
            {
                "actor": "R1",
                "to": "D1",
                "thread_role": "D1",
                "status": "developer_fix_running",
                "summary": "blocking fix request sent",
            },
        ],
    },
    "reviewer_accepted": {
        "actor": "R1",
        "to": "M",
        "summary": "review accepted received",
        "status_map": {
            "accepted": "review_done",
        },
        "next_action": "Manager should verify the current repository state and then run followup_status_command to append accepted.",
        "followup_status": "accepted",
        "followup_summary": "review accepted",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    if args.body:
        return args.body
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Pass --body-file, --body, or pipe a handoff payload on stdin.")


def payload_msg_id(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.search(r"\b([A-Za-z][A-Za-z0-9]{0,3}-\d{3})\b", stripped)
        return match.group(1).upper() if match else ""
    return ""


def next_handoff_sent_word(text: str) -> str:
    value = extract_label(text, "Next handoff sent")[1]
    if not value:
        return ""
    return value.split(None, 1)[0].strip(".,;:").lower()


def roster_thread_id(run_dir: Path, role: str) -> str:
    metadata = load_json(run_dir / "run.json")
    team = metadata.get("team", {})
    roster = team.get("roster", {}) if isinstance(team, dict) else {}
    entry = roster.get(role, {}) if isinstance(roster, dict) else {}
    thread_id = str(entry.get("thread_id", "")).strip() if isinstance(entry, dict) else ""
    if not thread_id:
        raise SystemExit(f"Run roster has no thread_id for {role}.")
    return thread_id


def followup_status_items(spec: dict[str, Any]) -> list[dict[str, str]]:
    items = spec.get("followup_statuses", [])
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    status = str(spec.get("followup_status", ""))
    if not status:
        return []
    return [
        {
            "actor": "M",
            "to": "",
            "thread_role": "",
            "status": status,
            "summary": str(spec.get("followup_summary", status)),
        }
    ]


def followup_status_commands(run_dir: Path, spec: dict[str, Any]) -> list[list[str]]:
    commands: list[list[str]] = []
    for item in followup_status_items(spec):
        status = str(item.get("status", ""))
        if not status:
            continue
        actor = str(item.get("actor", "M") or "M")
        to = str(item.get("to", ""))
        thread_role = str(item.get("thread_role", ""))
        thread_id = roster_thread_id(run_dir, thread_role) if thread_role else ""
        command = [
            sys.executable,
            str(APPEND_EVENT),
            "--run-dir",
            str(run_dir),
            "--kind",
            "status",
            "--actor",
            actor,
            "--summary",
            str(item.get("summary", status)),
            "--run-status",
            status,
            "--print-json",
        ]
        if to:
            command.extend(["--to", to])
        if thread_id:
            command.extend(["--thread-id", thread_id])
        commands.append(command)
    return commands


def record(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")
    spec = INBOUND[args.kind]
    body = read_body(args)
    validation = validate_payload(args.kind, body)
    if not validation["ok"]:
        return {
            "ok": False,
            "kind": args.kind,
            "run_dir": str(run_dir),
            "validation": validation,
            "problems": validation["problems"],
            "next_actions": ["Repair the inbound handoff payload before recording it."],
        }

    payload_from = extract_label(body, "From")[1]
    payload_to = extract_label(body, "To")[1]
    status_value = extract_label(body, "Status")[1]
    if payload_from != spec["actor"] or payload_to != spec["to"]:
        return {
            "ok": False,
            "kind": args.kind,
            "run_dir": str(run_dir),
            "validation": validation,
            "problems": [f"Payload route {payload_from}->{payload_to} does not match inbound route {spec['actor']}->{spec['to']}."],
            "next_actions": ["Repair the payload route before recording this handoff."],
        }

    status_map = spec["status_map"]
    run_status = status_map.get(status_value, "") if isinstance(status_map, dict) else ""
    if status_value and status_value not in status_map:
        return {
            "ok": False,
            "kind": args.kind,
            "run_dir": str(run_dir),
            "validation": validation,
            "problems": [f"Unexpected Status for {args.kind}: {status_value}"],
            "next_actions": ["Repair the payload status before recording this handoff."],
        }

    sent_word = next_handoff_sent_word(body)
    thread_id = args.thread_id.strip() or roster_thread_id(run_dir, spec["to"])
    if args.kind == "reviewer_fix" and sent_word == "no":
        thread_id = ""
    event_args = [
        "--run-dir",
        str(run_dir),
        "--kind",
        "message",
        "--actor",
        spec["actor"],
        "--to",
        spec["to"],
        "--thread-id",
        thread_id,
        "--summary",
        args.summary or spec["summary"],
        "--print-json",
    ]
    if args.body_file:
        event_args.extend(["--body-file", str(Path(args.body_file).expanduser())])
    else:
        event_args.extend(["--body", body])
    if run_status:
        event_args.extend(["--run-status", run_status])
    msg_id = args.msg_id.strip() or payload_msg_id(body)
    if msg_id:
        event_args.extend(["--msg-id", msg_id])

    event = append_event(event_args)
    followups = followup_status_commands(run_dir, spec)
    next_actions = [spec["next_action"]]
    if args.kind == "reviewer_fix" and sent_word == "no":
        followups = []
        next_actions = [
            "Reviewer fix copy says Next handoff sent: no; send or relay the exact fix payload to D1 before recording fix_required or developer_fix_running.",
        ]
    if not followups and run_status == "blocked":
        next_actions = ["Report the blocker and stop the loop until the blocking condition changes."]
    return {
        "ok": True,
        "kind": args.kind,
        "run_dir": str(run_dir),
        "validation": validation,
        "event": event,
        "recorded_run_status": run_status,
        "followup_status_command": followups[0] if len(followups) == 1 else [],
        "followup_status_commands": followups,
        "next_actions": next_actions,
    }


def print_text(summary: dict[str, Any]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Kind: {summary.get('kind', '')}")
    event = summary.get("event", {})
    if isinstance(event, dict) and event.get("id"):
        print(f"Recorded: {event.get('id')} {event.get('summary')}")
    problems = summary.get("problems", [])
    if isinstance(problems, list) and problems:
        print("Problems:")
        for problem in problems:
            print(f"- {problem}")
    next_actions = summary.get("next_actions", [])
    if isinstance(next_actions, list) and next_actions:
        print("Next Actions:")
        for action in next_actions:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Path to a start-work run directory.")
    parser.add_argument("--kind", required=True, choices=sorted(INBOUND), help="Inbound handoff type.")
    parser.add_argument("--body", default="", help="Payload text to validate and record.")
    parser.add_argument("--body-file", default="", help="Path to the exact payload file.")
    parser.add_argument("--thread-id", default="", help="Override recipient thread id.")
    parser.add_argument("--summary", default="", help="Override the recorded event summary.")
    parser.add_argument("--msg-id", default="", help="Override the local event/message id.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    summary = record(args)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
