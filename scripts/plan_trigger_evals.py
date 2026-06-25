#!/usr/bin/env python3
"""Generate a dry-run execution plan for start-work trigger eval prompts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_PROMPTS = SKILL_ROOT / "references" / "trigger-eval-prompts.md"


def parse_table(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells[:4] == ["ID", "Should trigger", "Focus", "Prompt"]:
            continue
        if len(cells) == 4:
            rows.append({"id": cells[0], "should_trigger": cells[1], "focus": cells[2], "prompt": cells[3]})
    return rows


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-") or "eval"


def command_for(codex_bin: str, prompt: str) -> list[str]:
    return [codex_bin, "exec", "--json", prompt]


def shell_quote(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def build_plan(args: argparse.Namespace) -> list[dict[str, object]]:
    prompts_path = Path(args.prompts).expanduser().resolve()
    artifact_dir = Path(args.artifact_dir).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = (SKILL_ROOT / artifact_dir).resolve()

    plan = []
    for row in parse_table(prompts_path):
        artifact = artifact_dir / f"{safe_name(row['id'])}-{safe_name(row['focus'])}.jsonl"
        command = command_for(args.codex_bin, row["prompt"])
        plan.append(
            {
                "id": row["id"],
                "should_trigger": row["should_trigger"] == "true",
                "focus": row["focus"],
                "prompt": row["prompt"],
                "artifact": str(artifact),
                "command": command,
                "shell": f"{shell_quote(command)} > {shlex.quote(str(artifact))}",
            }
        )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS), help="Markdown trigger eval prompt table.")
    parser.add_argument(
        "--artifact-dir",
        default=".agent-work/start-work/evals/trigger",
        help="Directory where jsonl traces should be written by the displayed commands.",
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument("--print-json", action="store_true", help="Print the plan as JSON.")
    args = parser.parse_args()

    plan = build_plan(args)
    if args.print_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        for item in plan:
            expected = "trigger" if item["should_trigger"] else "stay idle"
            print(f"{item['id']} [{expected}] {item['focus']}")
            print(item["shell"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
