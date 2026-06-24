#!/usr/bin/env python3
"""Inspect a start-work run ledger and report a structured resume summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from append_event import ALLOWED_STATUS_TRANSITIONS, RUN_STATUSES, current_run_status


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

    return {
        "ok": not problems,
        "run_dir": str(run_dir),
        "run_id": metadata.get("run_id", ""),
        "mode": metadata.get("mode", ""),
        "current_status": current_status,
        "coordination_status": coordination_status,
        "metadata_status": metadata_status,
        "next_allowed_statuses": sorted(ALLOWED_STATUS_TRANSITIONS.get(current_status, set())),
        "event_count": len(events),
        "metadata_event_count": metadata_event_count,
        "last_event": compact_event(last_event),
        "status_event": compact_event(status_event),
        "problems": problems,
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
