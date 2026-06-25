#!/usr/bin/env python3
"""Validate a start-work handoff payload before sending it to another role."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HandoffSpec:
    required_labels: tuple[str, ...]
    expected_values: dict[str, tuple[str, ...]]
    suggested_next_action: str


SPECS = {
    "work_order": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Manager Thread",
            "Developer Thread",
            "Reviewer Thread",
            "Project Path",
            "User goal",
            "Ownership",
            "Acceptance criteria",
            "Required checks",
            "Developer response format",
        ),
        expected_values={"From": ("M",), "To": ("D1",)},
        suggested_next_action="Send the validated work order to D1, then record developer_running only after send succeeds.",
    ),
    "developer_completion": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Status",
            "Summary",
            "Changed files",
            "Checks",
            "Evidence references",
            "Requested next action",
            "Next handoff sent",
        ),
        expected_values={"From": ("D1",), "To": ("M",), "Status": ("complete", "blocked")},
        suggested_next_action="Record developer_done or blocked after receiving this handoff.",
    ),
    "review_request": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Developer Thread",
            "Reviewer Thread",
            "Project Path",
            "User goal",
            "Acceptance criteria",
            "Review scope",
            "Manager checkpoint",
            "Changed files",
            "Developer summary",
            "Evidence references",
            "Reviewer report format",
        ),
        expected_values={"From": ("M",), "To": ("R1",)},
        suggested_next_action="Send the validated review request to R1, then record reviewer_running only after send succeeds.",
    ),
    "reviewer_fix": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Manager copy",
            "Status",
            "Blocking findings",
            "Allowed fix scope",
            "Do not change",
            "Evidence references",
            "Requested next action",
            "Next handoff sent",
        ),
        expected_values={"From": ("R1",), "To": ("D1",), "Manager copy": ("M",), "Status": ("changes required",)},
        suggested_next_action="Send the fix handoff to D1 and a separate Manager copy before recording developer_fix_running.",
    ),
    "developer_fix_completion": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Status",
            "Fixed findings",
            "Changed files",
            "Checks run",
            "Evidence references",
            "Remaining risk",
            "Requested next action",
            "Next handoff sent",
        ),
        expected_values={"From": ("D1",), "To": ("M",), "Status": ("complete", "blocked")},
        suggested_next_action="Record main_integration_check after Manager verifies the fix completion.",
    ),
    "reviewer_accepted": HandoffSpec(
        required_labels=(
            "Run ID",
            "Team ID",
            "From",
            "To",
            "Status",
            "Accepted scope",
            "Checks reviewed",
            "Evidence references",
            "Residual risk",
            "Requested next action",
            "Next handoff sent",
        ),
        expected_values={"From": ("R1",), "To": ("M",), "Status": ("accepted",)},
        suggested_next_action="Record accepted, then prepare final_delivery after Manager verifies final state.",
    ),
}

ALL_LABELS = sorted({label for spec in SPECS.values() for label in spec.required_labels}, key=len, reverse=True)
LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9 /-]{0,64}:\s*")
PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
FREEFORM_LABELS = {"Developer response format", "Reviewer report format"}


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    if args.body:
        return args.body
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Pass --body-file, --body, or pipe a handoff payload on stdin.")


def is_next_label(line: str, current_label: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("```") or stripped.startswith("#"):
        return True
    if current_label in FREEFORM_LABELS:
        return False
    for label in ALL_LABELS:
        if label != current_label and stripped.startswith(f"{label}:"):
            return True
    return bool(LABEL_RE.match(stripped))


def extract_label(text: str, label: str) -> tuple[bool, str]:
    lines = text.splitlines()
    prefix = f"{label}:"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        chunks = [stripped[len(prefix):].strip()]
        for next_line in lines[index + 1:]:
            if is_next_label(next_line, label):
                break
            chunks.append(next_line.strip())
        value = "\n".join(chunk for chunk in chunks if chunk).strip()
        return True, value
    return False, ""


def validate_payload(kind: str, text: str) -> dict[str, object]:
    spec = SPECS[kind]
    fields: dict[str, str] = {}
    problems: list[str] = []

    for label in spec.required_labels:
        present, value = extract_label(text, label)
        if not present:
            problems.append(f"Missing required label: {label}")
            continue
        fields[label] = value
        if not value:
            problems.append(f"Required label is empty: {label}")
        elif PLACEHOLDER_RE.search(value):
            problems.append(f"Unresolved placeholder in {label}: {value}")

    for label, allowed in spec.expected_values.items():
        value = fields.get(label, "")
        if value and value not in allowed:
            problems.append(f"Unexpected {label}: got {value!r}, expected one of: {', '.join(allowed)}")

    sent_value = fields.get("Next handoff sent", "")
    if sent_value:
        sent_word = sent_value.split(None, 1)[0].strip(".,;:").lower()
        if sent_word not in {"yes", "no"}:
            problems.append("Next handoff sent must start with yes or no.")

    next_actions = (
        [spec.suggested_next_action]
        if not problems
        else ["Repair the listed handoff payload problems before sending or advancing run status."]
    )
    return {
        "ok": not problems,
        "kind": kind,
        "field_count": len(fields),
        "problems": problems,
        "next_actions": next_actions,
    }


def print_text(summary: dict[str, object]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Kind: {summary['kind']}")
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
    parser.add_argument("--kind", required=True, choices=sorted(SPECS), help="Handoff payload type.")
    parser.add_argument("--body", default="", help="Payload text to validate.")
    parser.add_argument("--body-file", default="", help="Path to a payload file to validate.")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    summary = validate_payload(args.kind, read_body(args))
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
