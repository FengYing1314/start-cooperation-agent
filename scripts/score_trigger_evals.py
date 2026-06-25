#!/usr/bin/env python3
"""Score start-work trigger eval JSONL artifacts against the prompt table."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from plan_trigger_evals import DEFAULT_PROMPTS, build_plan


DEFAULT_PATTERNS = [
    r"\$start-work\b",
    r"\bstart-work\b",
    r"\bStart Work\b",
    r"\.agent-work/start-work",
    r"\bscripts/init_team\.py\b",
    r"\bscripts/inspect_team\.py\b",
    r"\bInitialize Team Once\b",
]


def bool_from_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "trigger", "triggered"}:
            return True
        if lowered in {"false", "no", "idle", "not_triggered", "not triggered"}:
            return False
    return None


def explicit_observed_trigger(value: Any) -> bool | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"observed_trigger", "start_work_triggered", "skill_triggered"}:
                parsed = bool_from_value(item)
                if parsed is not None:
                    return parsed
            found = explicit_observed_trigger(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = explicit_observed_trigger(item)
            if found is not None:
                return found
    return None


def flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


def parse_jsonl(path: Path) -> tuple[list[Any], str]:
    events = []
    raw_lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw_lines.append(line)
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})
    return events, "\n".join(raw_lines)


def infer_trigger(path: Path, patterns: list[str]) -> tuple[bool | None, str, list[str]]:
    if not path.exists():
        return None, "missing", []
    events, raw_text = parse_jsonl(path)
    for event in events:
        explicit = explicit_observed_trigger(event)
        if explicit is not None:
            return explicit, "explicit", []

    searchable = raw_text + "\n" + "\n".join(flatten_text(event) for event in events)
    matches = [pattern for pattern in patterns if re.search(pattern, searchable, flags=re.IGNORECASE)]
    return bool(matches), "heuristic", matches


def score(args: argparse.Namespace) -> dict[str, object]:
    plan = build_plan(
        SimpleNamespace(
            prompts=args.prompts,
            artifact_dir=args.artifact_dir,
            codex_bin=args.codex_bin,
        )
    )
    patterns = args.trigger_pattern or DEFAULT_PATTERNS
    results = []
    for item in plan:
        artifact = Path(str(item["artifact"]))
        observed, method, evidence = infer_trigger(artifact, patterns)
        expected = bool(item["should_trigger"])
        passed = observed == expected
        results.append(
            {
                "id": item["id"],
                "focus": item["focus"],
                "expected_trigger": expected,
                "observed_trigger": observed,
                "method": method,
                "passed": passed,
                "artifact": str(artifact),
                "evidence": evidence,
            }
        )

    return {
        "ok": all(item["passed"] for item in results),
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "results": results,
    }


def print_text(summary: dict[str, object]) -> None:
    print(f"OK: {str(summary['ok']).lower()}")
    print(f"Passed: {summary['passed']}/{summary['total']}")
    for item in summary["results"]:
        if not isinstance(item, dict):
            continue
        status = "PASS" if item["passed"] else "FAIL"
        print(
            f"{status} {item['id']} expected={item['expected_trigger']} "
            f"observed={item['observed_trigger']} method={item['method']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS), help="Markdown trigger eval prompt table.")
    parser.add_argument(
        "--artifact-dir",
        default=".agent-work/start-work/evals/trigger",
        help="Directory containing JSONL traces named by plan_trigger_evals.py.",
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument(
        "--trigger-pattern",
        action="append",
        default=[],
        help="Regex evidence that start-work triggered. Repeatable; defaults to built-in patterns.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable scoring summary.")
    args = parser.parse_args()

    summary = score(args)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
