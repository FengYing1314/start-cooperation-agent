#!/usr/bin/env python3
"""Record the result of a real outbound handoff send."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from prepare_outbound_handoff import OUTBOUND, append_event


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
    return events


def find_event(events: list[dict[str, Any]], spec: dict[str, str], event_id: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("kind") == "message"
        and event.get("actor") == spec["actor"]
        and event.get("to") == spec["to"]
    ]
    if event_id:
        for index, event in matches:
            if str(event.get("id", "")) == event_id:
                return index, event
        raise SystemExit(f"Prepared outbound event not found: {event_id}")
    if matches:
        return matches[-1]
    raise SystemExit(f"No prepared outbound {spec['actor']}->{spec['to']} message found in events.jsonl.")


def already_finalized(events: list[dict[str, Any]], start_index: int, spec: dict[str, str], thread_id: str) -> bool:
    for event in events[start_index + 1:]:
        if (
            event.get("actor") == spec["actor"]
            and event.get("to") == spec["to"]
            and event.get("thread_id") == thread_id
            and event.get("run_status") == spec["post_send_status"]
        ):
            return True
    return False


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")
    spec = OUTBOUND[args.kind]
    events = load_events(run_dir / "events.jsonl")
    event_index, outbound_event = find_event(events, spec, args.event_id.strip())
    thread_id = str(outbound_event.get("thread_id", "")).strip()
    if not thread_id:
        raise SystemExit(f"Prepared outbound event has no thread_id: {outbound_event.get('id', '')}")

    if already_finalized(events, event_index, spec, thread_id):
        raise SystemExit(f"Outbound event already finalized as {spec['post_send_status']}: {outbound_event.get('id', '')}")

    if args.result == "sent":
        result_event = append_event(
            [
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
                args.summary or spec["post_send_summary"],
                "--run-status",
                spec["post_send_status"],
                "--print-json",
            ]
        )
        next_actions = ["Wait for the next role handoff through the roster target."]
    else:
        error = args.error.strip()
        if not error:
            raise SystemExit("--error is required when --result failed.")
        body = "\n".join(
            [
                f"Outbound event: {outbound_event.get('id', '')}",
                f"Target: {spec['to']} {thread_id}",
                f"Payload file: {outbound_event.get('file', '')}",
                f"Send error: {error}",
            ]
        )
        result_event = append_event(
            [
                "--run-dir",
                str(run_dir),
                "--kind",
                "blocker",
                "--actor",
                spec["actor"],
                "--to",
                spec["to"],
                "--thread-id",
                thread_id,
                "--summary",
                args.summary or f"{spec['summary']} send failed",
                "--body",
                body,
                "--print-json",
            ]
        )
        next_actions = [
            "Do not advance the run status.",
            "Repair the send target, messaging tool, or payload, then prepare or resend the handoff.",
        ]

    return {
        "ok": True,
        "kind": args.kind,
        "run_dir": str(run_dir),
        "send_result": args.result,
        "outbound_event": outbound_event,
        "result_event": result_event,
        "next_actions": next_actions,
    }


def print_text(summary: dict[str, Any]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Kind: {summary.get('kind', '')}")
    print(f"Send Result: {summary.get('send_result', '')}")
    result_event = summary.get("result_event", {})
    if isinstance(result_event, dict):
        print(f"Recorded: {result_event.get('id', '')} {result_event.get('summary', '')}")
    next_actions = summary.get("next_actions", [])
    if isinstance(next_actions, list) and next_actions:
        print("Next Actions:")
        for action in next_actions:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Path to a start-work run directory.")
    parser.add_argument("--kind", required=True, choices=sorted(OUTBOUND), help="Outbound handoff type.")
    parser.add_argument("--event-id", default="", help="Prepared outbound event id. Defaults to the latest matching event.")
    parser.add_argument("--result", required=True, choices=["sent", "failed"], help="Actual send result.")
    parser.add_argument("--error", default="", help="Required failure detail when --result failed.")
    parser.add_argument("--summary", default="", help="Override recorded result summary.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    summary = finalize(args)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    else:
        print_text(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
