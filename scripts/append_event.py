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

DIRECT_SEND_STATUSES = {
    "developer_running",
    "reviewer_running",
    "developer_fix_running",
}

ALLOWED_STATUS_TRANSITIONS = {
    "init": {"manager_work_order", "blocked"},
    "manager_work_order": {"developer_running", "blocked"},
    "developer_running": {"developer_done", "blocked"},
    "developer_done": {"main_integration_check", "blocked"},
    "main_integration_check": {"reviewer_running", "blocked"},
    "reviewer_running": {"review_done", "blocked"},
    "review_done": {"accepted", "fix_required", "blocked"},
    "fix_required": {"developer_fix_running", "main_fixing", "blocked"},
    "developer_fix_running": {"main_integration_check", "blocked"},
    "main_fixing": {"main_integration_check", "blocked"},
    "accepted": {"final_delivery"},
    "blocked": {"final_delivery"},
    "final_delivery": set(),
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


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def current_run_status(text: str) -> str:
    match = re.search(r"^Status:\s*(\S+).*$", text, flags=re.MULTILINE)
    return match.group(1) if match else ""


def validate_run_status(status: str) -> None:
    if status and status not in RUN_STATUSES:
        allowed = ", ".join(sorted(RUN_STATUSES))
        raise SystemExit(f"Unknown run status '{status}'. Allowed: {allowed}")


def validate_status_transport(args: argparse.Namespace, run_dir: Path) -> None:
    if args.run_status not in DIRECT_SEND_STATUSES:
        return
    metadata = load_json(run_dir / "run.json") or {}
    mode = str(metadata.get("mode", ""))
    if mode in {"subagent", "single-agent"} and not args.allow_fallback_direct_status:
        raise SystemExit(
            f"{args.run_status} records a real direct send, but this run is {mode}. "
            "Use a non-running status for fallback payloads, or pass "
            "--allow-fallback-direct-status with --thread-id only after a real message was sent."
        )
    if mode in {"subagent", "single-agent"} and not args.thread_id.strip():
        raise SystemExit("--allow-fallback-direct-status requires --thread-id for fallback direct-send statuses.")


def validate_status_transition(args: argparse.Namespace, coordination: Path) -> None:
    if not args.run_status or args.allow_status_jump:
        return
    text = coordination.read_text(encoding="utf-8")
    current = current_run_status(text)
    if not current or current == args.run_status:
        return
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, set())
    if args.run_status not in allowed:
        allowed_text = ", ".join(sorted(allowed)) or "<none>"
        raise SystemExit(
            f"Invalid run status transition: {current} -> {args.run_status}. "
            f"Allowed next statuses: {allowed_text}. "
            "Use --allow-status-jump only for recovery or audit corrections."
        )


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
    parser.add_argument(
        "--allow-fallback-direct-status",
        action="store_true",
        help="Allow direct-send running statuses in fallback runs only when a real message was sent.",
    )
    parser.add_argument(
        "--allow-status-jump",
        action="store_true",
        help="Bypass state-machine transition checks for recovery or audit corrections.",
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
    validate_status_transport(args, run_dir)
    validate_status_transition(args, coordination)
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
