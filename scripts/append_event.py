#!/usr/bin/env python3
"""Append a start-work event and optional message/artifact payload."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

RUN_STATUSES = {
    "init",
    "manager_work_order",
    "developer_running",
    "developer_done",
    "main_integration_check",
    "reviewer_running",
    "review_done",
    "fix_required",
    "developer_fix_running",
    "main_fixing",
    "accepted",
    "blocked",
    "final_delivery",
}


def slugify(value: str, fallback: str = "event") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:48].strip("-") or fallback


def prefix_for(actor: str) -> str:
    raw = actor.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,3}", raw):
        return raw.upper()
    lowered = raw.lower()
    if "review" in lowered:
        return "R1"
    if "develop" in lowered or "worker" in lowered or "exec" in lowered:
        return "D1"
    if "manager" in lowered or "coordinator" in lowered or lowered == "main":
        return "M"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", raw).upper()
    return (cleaned[:4] or "E")


def load_events(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def next_id(events: list[dict[str, object]], prefix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{3}})$")
    seen = []
    for event in events:
        match = pattern.match(str(event.get("id", "")))
        if match:
            seen.append(int(match.group(1)))
    return f"{prefix}-{(max(seen) + 1) if seen else 1:03d}"


def event_id_exists(events: list[dict[str, object]], local_id: str) -> bool:
    return any(str(event.get("id", "")) == local_id for event in events)


def table_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    return args.body or ""


def payload_directory(run_dir: Path, kind: str, requested: str) -> Path | None:
    if requested == "none":
        return None
    if requested == "messages":
        return run_dir / "messages"
    if requested == "artifacts":
        return run_dir / "artifacts"
    if kind == "message":
        return run_dir / "messages"
    if kind in {"artifact", "review", "validation"}:
        return run_dir / "artifacts"
    return None


def ensure_event_log(coordination: Path) -> str:
    text = coordination.read_text(encoding="utf-8") if coordination.exists() else ""
    if "## Event Log" not in text:
        if text and not text.endswith("\n"):
            text += "\n"
        text += """
## Event Log

| Time | ID | Kind | Actor | To | Thread | Status | Summary | File |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    if not text.endswith("\n"):
        text += "\n"
    return text


def set_run_status(text: str, status: str) -> str:
    if not status:
        return text
    if re.search(r"^Status:.*$", text, flags=re.MULTILINE):
        return re.sub(r"^Status:.*$", f"Status: {status}", text, count=1, flags=re.MULTILINE)
    return text.rstrip() + f"\n\nStatus: {status}\n"


def validate_run_status(status: str) -> None:
    if status and status not in RUN_STATUSES:
        allowed = ", ".join(sorted(RUN_STATUSES))
        raise SystemExit(f"Unknown run status '{status}'. Allowed: {allowed}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Path to a start-work run directory.")
    parser.add_argument(
        "--kind",
        default="note",
        choices=["note", "message", "decision", "status", "validation", "risk", "blocker", "review", "artifact"],
    )
    parser.add_argument("--actor", required=True, help="Manager, Developer, Reviewer, D1, R1, etc.")
    parser.add_argument("--summary", required=True, help="Short event summary.")
    parser.add_argument("--to", default="", help="Recipient role or thread.")
    parser.add_argument("--thread-id", default="", help="Codex thread id or subagent id.")
    parser.add_argument("--status", default="recorded", help="Event status.")
    parser.add_argument(
        "--run-status",
        default="",
        help="Optional run status to write to coordination.md.",
    )
    parser.add_argument("--msg-id", default="", help="Explicit local message/event id.")
    parser.add_argument("--body", default="", help="Optional payload text.")
    parser.add_argument("--body-file", default="", help="Optional payload file to copy into the run.")
    parser.add_argument(
        "--write-file",
        choices=["auto", "messages", "artifacts", "none"],
        default="auto",
        help="Where to store payload text.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable event.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    coordination = run_dir / "coordination.md"
    if not coordination.exists():
        raise SystemExit(f"coordination.md not found in run directory: {run_dir}")

    events_path = run_dir / "events.jsonl"
    events = load_events(events_path)
    local_id = args.msg_id.strip() or next_id(events, prefix_for(args.actor))
    if event_id_exists(events, local_id):
        raise SystemExit(f"Event id already exists in this run: {local_id}")
    validate_run_status(args.run_status)
    timestamp = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()

    body = read_body(args)
    file_path = ""
    target_dir = payload_directory(run_dir, args.kind, args.write_file)
    if body and target_dir:
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{local_id}-{slugify(args.summary)}.md"
        payload_path = target_dir / filename
        if payload_path.exists():
            raise SystemExit(f"Payload file already exists: {payload_path}")
        payload_path.write_text(body.rstrip() + "\n", encoding="utf-8")
        file_path = str(payload_path.relative_to(run_dir))

    event = {
        "time": timestamp,
        "id": local_id,
        "kind": args.kind,
        "actor": args.actor,
        "to": args.to,
        "thread_id": args.thread_id,
        "status": args.status,
        "summary": args.summary,
        "file": file_path,
    }

    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    row = (
        f"| {table_cell(timestamp)} | {table_cell(local_id)} | {table_cell(args.kind)} | "
        f"{table_cell(args.actor)} | {table_cell(args.to)} | {table_cell(args.thread_id)} | "
        f"{table_cell(args.status)} | {table_cell(args.summary)} | {table_cell(file_path)} |\n"
    )
    coordination_text = set_run_status(ensure_event_log(coordination), args.run_status)
    coordination.write_text(coordination_text + row, encoding="utf-8")

    if args.print_json:
        print(json.dumps(event, ensure_ascii=False, indent=2))
    else:
        print(f"Recorded {local_id}: {args.summary}")
        if file_path:
            print(f"Payload: {file_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
