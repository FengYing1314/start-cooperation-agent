#!/usr/bin/env python3
"""Validate and record an outbound start-work handoff before thread sending."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from validate_handoff import extract_label, validate_payload


SCRIPT_DIR = Path(__file__).resolve().parent
APPEND_EVENT = SCRIPT_DIR / "append_event.py"

OUTBOUND = {
    "work_order": {
        "actor": "M",
        "to": "D1",
        "record_status": "manager_work_order",
        "summary": "work order ready",
        "post_send_status": "developer_running",
        "post_send_summary": "work order sent",
        "next_action": "Send the recorded work order to D1 with send_message_to_thread, then run post_send_status_command only after the send succeeds.",
    },
    "review_request": {
        "actor": "M",
        "to": "R1",
        "record_status": "",
        "summary": "review request ready",
        "post_send_status": "reviewer_running",
        "post_send_summary": "review request sent",
        "next_action": "Send the recorded review request to R1 with send_message_to_thread, then run post_send_status_command only after the send succeeds.",
    },
    "reviewer_fix": {
        "actor": "R1",
        "to": "D1",
        "record_status": "fix_required",
        "summary": "blocking fix request ready",
        "post_send_status": "developer_fix_running",
        "post_send_summary": "blocking fix request sent",
        "next_action": "Send the recorded fix request to D1 and a separate Manager copy, then run post_send_status_command only after the D1 send succeeds.",
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


def roster_thread_id(run_dir: Path, role: str) -> str:
    metadata = load_json(run_dir / "run.json")
    team = metadata.get("team", {})
    roster = team.get("roster", {}) if isinstance(team, dict) else {}
    entry = roster.get(role, {}) if isinstance(roster, dict) else {}
    thread_id = str(entry.get("thread_id", "")).strip() if isinstance(entry, dict) else ""
    if not thread_id:
        raise SystemExit(f"Run roster has no thread_id for {role}.")
    return thread_id


def append_event(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(APPEND_EVENT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "append_event.py failed")
    data = json.loads(proc.stdout)
    if not isinstance(data, dict):
        raise SystemExit("append_event.py returned non-object JSON")
    return data


def post_send_status_command(run_dir: Path, spec: dict[str, str], thread_id: str) -> list[str]:
    return [
        sys.executable,
        str(APPEND_EVENT),
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        spec["actor"],
        "--to",
        spec["to"],
        "--thread-id",
        thread_id,
        "--summary",
        spec["post_send_summary"],
        "--run-status",
        spec["post_send_status"],
        "--print-json",
    ]


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")
    spec = OUTBOUND[args.kind]
    body = read_body(args)
    validation = validate_payload(args.kind, body)
    if not validation["ok"]:
        return {
            "ok": False,
            "kind": args.kind,
            "run_dir": str(run_dir),
            "validation": validation,
            "problems": validation["problems"],
            "next_actions": ["Repair the payload before recording or sending this handoff."],
        }

    payload_from = extract_label(body, "From")[1]
    payload_to = extract_label(body, "To")[1]
    if payload_from != spec["actor"] or payload_to != spec["to"]:
        return {
            "ok": False,
            "kind": args.kind,
            "run_dir": str(run_dir),
            "validation": validation,
            "problems": [f"Payload route {payload_from}->{payload_to} does not match outbound route {spec['actor']}->{spec['to']}."],
            "next_actions": ["Repair the payload route before recording or sending this handoff."],
        }

    thread_id = roster_thread_id(run_dir, spec["to"])
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
    if spec["record_status"]:
        event_args.extend(["--run-status", spec["record_status"]])
    msg_id = args.msg_id.strip() or payload_msg_id(body)
    if msg_id:
        event_args.extend(["--msg-id", msg_id])

    event = append_event(event_args)
    payload_file = str(run_dir / str(event.get("file", ""))) if event.get("file") else ""
    return {
        "ok": True,
        "kind": args.kind,
        "run_dir": str(run_dir),
        "validation": validation,
        "event": event,
        "send_to": spec["to"],
        "send_to_thread_id": thread_id,
        "payload_file": payload_file,
        "post_send_status": spec["post_send_status"],
        "post_send_status_command": post_send_status_command(run_dir, spec, thread_id),
        "next_actions": [
            spec["next_action"],
            "If send_message_to_thread fails, record a blocker event and do not run post_send_status_command.",
        ],
    }


def print_text(summary: dict[str, Any]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Kind: {summary.get('kind', '')}")
    if summary.get("send_to_thread_id"):
        print(f"Send To: {summary['send_to']} {summary['send_to_thread_id']}")
    if summary.get("payload_file"):
        print(f"Payload: {summary['payload_file']}")
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
    parser.add_argument("--kind", required=True, choices=sorted(OUTBOUND), help="Outbound handoff type.")
    parser.add_argument("--body", default="", help="Payload text to validate and record.")
    parser.add_argument("--body-file", default="", help="Path to the exact payload file.")
    parser.add_argument("--summary", default="", help="Override the recorded event summary.")
    parser.add_argument("--msg-id", default="", help="Override the local event/message id.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    summary = prepare(args)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
