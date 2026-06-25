#!/usr/bin/env python3
"""Self-contained smoke tests for start-work scripts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INIT_TEAM = SCRIPT_DIR / "init_team.py"
ACK_TEAM = SCRIPT_DIR / "ack_team.py"
INIT_RUN = SCRIPT_DIR / "init_run.py"
APPEND_EVENT = SCRIPT_DIR / "append_event.py"
INSPECT_TEAM = SCRIPT_DIR / "inspect_team.py"
INSPECT_RUN = SCRIPT_DIR / "inspect_run.py"
INSPECT_PROJECT = SCRIPT_DIR / "inspect_project.py"
START_WORK_CONTRACT = SCRIPT_DIR / "start_work_contract.py"
VALIDATE_START_WORK = SCRIPT_DIR / "validate_start_work.py"
PLAN_TRIGGER_EVALS = SCRIPT_DIR / "plan_trigger_evals.py"
SCORE_TRIGGER_EVALS = SCRIPT_DIR / "score_trigger_evals.py"
PREPARE_TRIGGER_EVAL_WORKSPACE = SCRIPT_DIR / "prepare_trigger_eval_workspace.py"
RUN_TRIGGER_EVAL_PLAN = SCRIPT_DIR / "run_trigger_eval_plan.py"
SKILL_ROOT = SCRIPT_DIR.parent


def import_contract_module():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import start_work_contract
    finally:
        try:
            sys.path.remove(str(SCRIPT_DIR))
        except ValueError:
            pass
    return start_work_contract


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(command)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def make_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    run(["git", "-C", str(repo), "init"])
    return repo


def script(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(path), *args], check=check)


def init_team(repo: Path, *args: str) -> dict[str, object]:
    proc = script(INIT_TEAM, "--repo", str(repo), *args, "--print-json")
    return json.loads(proc.stdout)


def ack(repo: Path, role: str) -> None:
    script(ACK_TEAM, "--repo", str(repo), "--role", role)


def append_status(
    run_dir: Path,
    *,
    actor: str,
    summary: str,
    run_status: str,
    to: str = "",
    thread_id: str = "",
) -> dict[str, object]:
    args = [
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        actor,
        "--summary",
        summary,
        "--run-status",
        run_status,
        "--print-json",
    ]
    if to:
        args.extend(["--to", to])
    if thread_id:
        args.extend(["--thread-id", thread_id])
    proc = script(APPEND_EVENT, *args)
    return json.loads(proc.stdout)


def inspect_run(run_dir: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return script(INSPECT_RUN, "--run-dir", str(run_dir), "--print-json", check=check)


def inspect_team(repo: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return script(INSPECT_TEAM, "--repo", str(repo), "--print-json", check=check)


def inspect_project(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return script(INSPECT_PROJECT, "--repo", str(repo), *args, "--print-json", check=check)


def test_team_id_is_stable(root: Path) -> None:
    repo = make_repo(root, "team-id-stable")
    init_team(
        repo,
        "--team-id",
        "custom-team",
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    result = init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    assert result["team_id"] == "custom-team", result
    assert result["updated"] is False, result


def test_team_inspection_requires_acknowledgements(root: Path) -> None:
    repo = make_repo(root, "team-inspection")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    proc = inspect_team(repo, check=False)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    data = json.loads(proc.stdout)
    assert data["ok"] is False, data
    assert data["roster_complete"] is True, data
    assert data["acknowledgements_complete"] is False, data
    assert data["codex_thread_ready"] is False, data
    assert any("D1 acknowledgement pending" in problem for problem in data["problems"]), data

    ack(repo, "D1")
    ack(repo, "R1")
    ready = json.loads(inspect_team(repo).stdout)
    assert ready["ok"] is True, ready
    assert ready["codex_thread_ready"] is True, ready
    assert ready["manual_relay_ready"] is False, ready
    assert ready["handoff_route_valid"] is True, ready
    assert ready["handoff_route_count"] == 5, ready


def test_team_inspection_rejects_broken_handoff_route(root: Path) -> None:
    repo = make_repo(root, "broken-route")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    team_path = repo / ".agent-work" / "start-work" / "team" / "team.json"
    team = json.loads(team_path.read_text(encoding="utf-8"))
    team["handoff_route"] = [
        entry
        for entry in team["handoff_route"]
        if not (entry.get("from") == "R1" and entry.get("to") == "D1")
    ]
    team_path.write_text(json.dumps(team, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = inspect_team(repo, check=False)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    data = json.loads(proc.stdout)
    assert data["ok"] is False, data
    assert data["codex_thread_ready"] is False, data
    assert data["handoff_route_valid"] is False, data
    assert any("R1->D1" in problem for problem in data["problems"]), data


def test_project_inspection_summarizes_team_and_recent_runs(root: Path) -> None:
    repo = make_repo(root, "project-inspection")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    first = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--run-id",
            "20260101-000001-first",
            "--request",
            "first run",
            "--print-json",
        ).stdout
    )
    second = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--run-id",
            "20260101-000002-second",
            "--request",
            "second run",
            "--print-json",
        ).stdout
    )
    append_status(
        Path(str(second["run_dir"])),
        actor="M",
        to="D1",
        thread_id="dev-thread",
        run_status="manager_work_order",
        summary="second work order recorded",
    )

    summary = json.loads(inspect_project(repo, "--limit", "1").stdout)
    assert summary["ok"] is True, summary
    assert summary["team"]["codex_thread_ready"] is True, summary
    assert summary["run_count"] == 2, summary
    assert len(summary["latest_runs"]) == 1, summary
    latest = summary["latest_runs"][0]
    assert latest["run_id"] == "20260101-000002-second", summary
    assert latest["current_status"] == "manager_work_order", summary
    assert latest["event_count"] == 1, summary
    assert Path(str(first["run_dir"])).exists(), first


def test_callback_only_rejected_for_direct_thread_mode(root: Path) -> None:
    repo = make_repo(root, "callback-only")
    init_team(
        repo,
        "--manager-callback",
        "manager-callback",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    inspected = json.loads(inspect_team(repo).stdout)
    assert inspected["ok"] is True, inspected
    assert inspected["codex_thread_ready"] is False, inspected
    assert inspected["manual_relay_ready"] is True, inspected
    assert inspected["handoff_route_valid"] is True, inspected
    assert inspected["warnings"], inspected

    proc = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--slug",
        "callback-only",
        "--request",
        "test",
        "--print-json",
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "requires M.thread_id" in combined, combined

    standing = repo / ".agent-work" / "start-work" / "team" / "standing-developer.md"
    text = standing.read_text(encoding="utf-8")
    assert "cannot run direct codex-thread tasks" in text, text
    assert "Prepare completion handoffs for Manager" in text, text

    team_doc = (repo / ".agent-work" / "start-work" / "team" / "team.md").read_text(encoding="utf-8")
    assert "Developer prepares completion for Manager through callback/manual relay." in team_doc, team_doc
    assert "Reviewer prepares accepted or blocked status for Manager through callback/manual relay." in team_doc, team_doc
    assert "Developer sends completion directly to Manager" not in team_doc, team_doc


def test_direct_thread_happy_path(root: Path) -> None:
    repo = make_repo(root, "direct-happy")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
        "--project-doc",
        "AGENTS.md",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    run_result = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--slug",
        "direct",
        "--request",
        "test direct flow",
        "--print-json",
    )
    run_data = json.loads(run_result.stdout)
    run_dir = Path(str(run_data["run_dir"]))
    assert run_data["current_status"] == "init", run_data
    assert run_data["event_count"] == 0, run_data
    invalid_result = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--summary",
        "skip to accepted",
        "--run-status",
        "accepted",
        check=False,
    )
    invalid_combined = invalid_result.stdout + invalid_result.stderr
    assert invalid_result.returncode != 0, invalid_combined
    assert "Invalid run status transition" in invalid_combined, invalid_combined

    event_result = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "message",
        "--actor",
        "M",
        "--to",
        "D1",
        "--thread-id",
        "dev-thread",
        "--summary",
        "work order ready",
        "--run-status",
        "manager_work_order",
        "--body",
        "payload",
        "--print-json",
    )
    event = json.loads(event_result.stdout)
    assert event["id"] == "M-001", event
    assert event["file"].replace("\\", "/") == "messages/M-001-work-order-ready.md", event
    sent_result = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--to",
        "D1",
        "--thread-id",
        "dev-thread",
        "--summary",
        "work order sent",
        "--run-status",
        "developer_running",
        "--print-json",
    )
    sent = json.loads(sent_result.stdout)
    assert sent["id"] == "M-002", sent
    coordination = (run_dir / "coordination.md").read_text(encoding="utf-8")
    assert "Status: developer_running" in coordination, coordination
    assert "Manager sends the work order directly to Developer." in coordination, coordination
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["current_status"] == "developer_running", run_metadata
    assert run_metadata["status_event_id"] == "M-002", run_metadata
    assert run_metadata["last_event_id"] == "M-002", run_metadata
    assert run_metadata["event_count"] == 2, run_metadata
    inspected = json.loads(inspect_run(run_dir).stdout)
    assert inspected["ok"] is True, inspected
    assert inspected["current_status"] == "developer_running", inspected
    assert inspected["next_allowed_statuses"] == ["developer_done", "blocked"], inspected
    assert inspected["last_event"]["id"] == "M-002", inspected

    jumped_result = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--summary",
        "audit jump",
        "--run-status",
        "accepted",
        "--allow-status-jump",
        "--print-json",
    )
    jumped = json.loads(jumped_result.stdout)
    assert jumped["summary"] == "audit jump", jumped
    jumped_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert jumped_metadata["current_status"] == "accepted", jumped_metadata
    assert jumped_metadata["status_event_id"] == "M-003", jumped_metadata


def test_full_fix_review_cycle_status_path(root: Path) -> None:
    repo = make_repo(root, "fix-review-cycle")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    run_result = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--slug",
        "fix-loop",
        "--request",
        "exercise a full fix and review loop",
        "--print-json",
    )
    run_data = json.loads(run_result.stdout)
    run_dir = Path(str(run_data["run_dir"]))

    statuses = [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer handoff received"),
        ("M", "", "", "main_integration_check", "integration check complete"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
        ("R1", "M", "manager-thread", "review_done", "review findings received"),
        ("R1", "D1", "dev-thread", "fix_required", "blocking fix requested"),
        ("R1", "D1", "dev-thread", "developer_fix_running", "fix request sent"),
        ("M", "", "", "main_integration_check", "post-fix integration check complete"),
        ("M", "R1", "review-thread", "reviewer_running", "re-review request sent"),
        ("R1", "M", "manager-thread", "review_done", "re-review complete"),
        ("R1", "M", "manager-thread", "accepted", "review accepted"),
        ("M", "", "", "final_delivery", "final user delivery"),
    ]

    events = [
        append_status(
            run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
        for actor, to, thread_id, run_status, summary in statuses
    ]

    assert [event["run_status"] for event in events] == [item[3] for item in statuses], events
    assert events[0]["id"] == "M-001", events[0]
    assert events[-1]["id"] == "M-007", events[-1]

    coordination = (run_dir / "coordination.md").read_text(encoding="utf-8")
    assert "Status: final_delivery" in coordination, coordination
    assert "Event Status | Run Status" in coordination, coordination
    assert "fix_required" in coordination, coordination
    assert "developer_fix_running" in coordination, coordination

    event_lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(event_lines) == len(statuses), event_lines
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["current_status"] == "final_delivery", run_metadata
    assert run_metadata["status_event_id"] == "M-007", run_metadata
    assert run_metadata["last_event_id"] == "M-007", run_metadata
    assert run_metadata["event_count"] == len(statuses), run_metadata
    inspected = json.loads(inspect_run(run_dir).stdout)
    assert inspected["ok"] is True, inspected
    assert inspected["current_status"] == "final_delivery", inspected
    assert inspected["next_allowed_statuses"] == [], inspected
    assert inspected["event_count"] == len(statuses), inspected


def test_run_json_status_mismatch_is_rejected(root: Path) -> None:
    repo = make_repo(root, "status-mismatch")
    init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    ack(repo, "D1")
    ack(repo, "R1")
    run_result = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--slug",
        "mismatch",
        "--request",
        "test status mismatch",
        "--print-json",
    )
    run_data = json.loads(run_result.stdout)
    run_dir = Path(str(run_data["run_dir"]))
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["current_status"] = "developer_running"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--summary",
        "advance with mismatched ledger",
        "--run-status",
        "developer_done",
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "Run status mismatch" in combined, combined
    inspected = inspect_run(run_dir, check=False)
    inspected_combined = inspected.stdout + inspected.stderr
    assert inspected.returncode != 0, inspected_combined
    inspected_data = json.loads(inspected.stdout)
    assert inspected_data["ok"] is False, inspected_data
    assert any("Status mismatch" in problem for problem in inspected_data["problems"]), inspected_data


def test_subagent_fallback_without_team(root: Path) -> None:
    repo = make_repo(root, "subagent-fallback")
    proc = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--mode",
        "subagent",
        "--fallback-reason",
        "thread tools unavailable",
        "--slug",
        "fallback",
        "--request",
        "test fallback",
        "--print-json",
    )
    data = json.loads(proc.stdout)
    assert data["mode"] == "subagent", data
    assert data["fallback_reason"] == "thread tools unavailable", data
    run_dir = Path(str(data["run_dir"]))
    coordination = (run_dir / "coordination.md").read_text(encoding="utf-8")
    assert "Mode: subagent" in coordination, coordination
    assert "Fallback Reason: thread tools unavailable" in coordination, coordination
    assert "fallback-subagent-fallback" in coordination, coordination
    assert "fallback worker/current caller" in coordination, coordination
    assert "do not claim a thread send" in coordination, coordination

    blocked_status = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--to",
        "D1",
        "--summary",
        "pretend direct send",
        "--run-status",
        "developer_running",
        check=False,
    )
    blocked_combined = blocked_status.stdout + blocked_status.stderr
    assert blocked_status.returncode != 0, blocked_combined
    assert "records a real direct send" in blocked_combined, blocked_combined

    script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--to",
        "D1",
        "--summary",
        "fallback work order recorded",
        "--run-status",
        "manager_work_order",
    )
    allowed_status = script(
        APPEND_EVENT,
        "--run-dir",
        str(run_dir),
        "--kind",
        "status",
        "--actor",
        "M",
        "--to",
        "D1",
        "--thread-id",
        "real-thread",
        "--summary",
        "real fallback direct send",
        "--run-status",
        "developer_running",
        "--allow-fallback-direct-status",
        "--print-json",
    )
    allowed = json.loads(allowed_status.stdout)
    assert allowed["thread_id"] == "real-thread", allowed


def test_fallback_mode_requires_reason(root: Path) -> None:
    repo = make_repo(root, "fallback-reason-required")
    proc = script(
        INIT_RUN,
        "--repo",
        str(repo),
        "--mode",
        "single-agent",
        "--slug",
        "fallback",
        "--request",
        "test fallback reason",
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    assert "--fallback-reason is required" in combined, combined


def test_reference_routing_is_progressive(root: Path) -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Reference Routing" in skill, skill
    assert "Load only the reference needed for the next action" in skill, skill
    assert "templates-team.md" in skill, skill
    assert "templates-run.md" in skill, skill
    assert "templates-work-order.md" in skill, skill
    assert "templates-review.md" in skill, skill
    assert "templates-final.md" in skill, skill
    assert "trigger-eval-prompts.md" in skill, skill
    assert "inspect_team.py" in skill, skill
    assert "inspect_run.py" in skill, skill
    assert "inspect_project.py" in skill, skill
    assert "run_trigger_eval_plan.py" in skill, skill
    assert "start_work_contract.py" in skill, skill
    assert "validate_start_work.py" in skill, skill
    assert "quick_validate.py" in skill, skill
    assert not (SKILL_ROOT / "README.md").exists(), "README.md should not be in the skill package"
    assert "callback/manual relay fallback" in skill, skill
    assert "handoff route invariants" in skill, skill
    assert "structured run metadata" in skill, skill
    assert "full fix-review loop progression" in skill, skill

    template_index = (SKILL_ROOT / "references" / "templates.md").read_text(encoding="utf-8")
    assert "This file is an index" in template_index, template_index
    assert "## Standing Developer Instruction" not in template_index, template_index
    assert len(template_index.splitlines()) <= 30, template_index

    run_templates = (SKILL_ROOT / "references" / "templates-run.md").read_text(encoding="utf-8")
    assert "Do not use it as a source payload" in run_templates, run_templates
    assert "do not claim that a thread message was sent" in run_templates, run_templates
    assert "## Manager Work Order" not in run_templates, run_templates
    assert "--allow-fallback-direct-status" in run_templates, run_templates
    assert "--allow-status-jump" in run_templates, run_templates
    assert len(run_templates.splitlines()) <= 40, run_templates

    for name in ("templates-work-order.md", "templates-review.md", "templates-final.md"):
        assert (SKILL_ROOT / "references" / name).exists(), name

    for path in (SKILL_ROOT / "references").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if len(text.splitlines()) > 100:
            first_lines = "\n".join(text.splitlines()[:20])
            assert "## Contents" in first_lines or "## Table Of Contents" in first_lines, path.name

    roles = (SKILL_ROOT / "references" / "roles.md").read_text(encoding="utf-8")
    assert "## Transport Rules" in roles, roles
    assert "through the roster target" in roles, roles
    assert "Do not claim a handoff was sent unless a real message was sent" in roles, roles

    protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(encoding="utf-8")
    assert "scripts/start_work_contract.py" in protocol, protocol
    assert "## Mode-Specific Transport" in protocol, protocol
    assert "Direct codex-thread route" in protocol, protocol
    assert "do not claim that a thread message was sent unless one really was" in protocol, protocol
    assert "--allow-fallback-direct-status" in protocol, protocol
    assert "--allow-status-jump" in protocol, protocol
    assert "inspect_team.py" in protocol, protocol
    assert "inspect_run.py" in protocol, protocol
    assert "inspect_project.py" in protocol, protocol
    assert "handoff route preserves role-to-role messaging" in protocol, protocol
    assert "machine-readable run index" in protocol, protocol
    assert "updates `run.json` with the current status and last event" in protocol, protocol
    assert "records both its event status and run status" in protocol, protocol
    assert "full fix-review loop as an executable invariant" in protocol, protocol

    openai_yaml = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "roster-routed" in openai_yaml, openai_yaml
    assert "callback/manual relay fallback" in openai_yaml, openai_yaml
    assert "direct-message development team" not in openai_yaml, openai_yaml


def parse_markdown_table(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells[:4] == ["ID", "Should trigger", "Focus", "Prompt"]:
            continue
        if len(cells) == 4:
            rows.append({"id": cells[0], "should_trigger": cells[1], "focus": cells[2], "prompt": cells[3]})
    return rows


def test_trigger_eval_prompts_are_balanced(root: Path) -> None:
    prompts_path = SKILL_ROOT / "references" / "trigger-eval-prompts.md"
    text = prompts_path.read_text(encoding="utf-8")
    rows = parse_markdown_table(text)
    assert 6 <= len(rows) <= 12, rows
    assert len(text.splitlines()) <= 40, text

    should_trigger = {row["should_trigger"] for row in rows}
    assert should_trigger == {"true", "false"}, rows
    focuses = {row["focus"] for row in rows}
    assert {"explicit", "implicit", "contextual", "tiny-task", "skill-authoring"} <= focuses, focuses
    assert any("$start-work" in row["prompt"] for row in rows if row["should_trigger"] == "true"), rows
    assert any("No multi-agent workflow needed" in row["prompt"] for row in rows if row["should_trigger"] == "false"), rows
    assert "prepare_trigger_eval_workspace.py --output-dir" in text, text
    assert "run_trigger_eval_plan.py --plan" in text, text
    assert "plan_trigger_evals.py --print-json" in text, text
    assert "score_trigger_evals.py --plan" in text, text
    assert "Expected behavior:" in text, text


def test_trigger_eval_plan_is_stable(root: Path) -> None:
    assert PLAN_TRIGGER_EVALS.exists(), PLAN_TRIGGER_EVALS
    prompt_rows = parse_markdown_table((SKILL_ROOT / "references" / "trigger-eval-prompts.md").read_text(encoding="utf-8"))
    cwd = root / "fixture-repo"
    cwd.mkdir()
    proc = script(PLAN_TRIGGER_EVALS, "--artifact-dir", str(root / "evals"), "--cwd", str(cwd), "--print-json")
    plan = json.loads(proc.stdout)
    assert len(plan) == len(prompt_rows), plan
    assert {item["should_trigger"] for item in plan} == {True, False}, plan
    first = plan[0]
    assert first["id"] == "trig-01", first
    assert first["command"][:3] == ["codex", "exec", "--json"], first
    assert first["cwd"] == str(cwd.resolve()), first
    assert first["artifact"].endswith("trig-01-explicit.jsonl"), first
    assert "$start-work" in first["prompt"], first
    assert ">" in first["shell"], first


def test_prepare_trigger_eval_workspace(root: Path) -> None:
    assert PREPARE_TRIGGER_EVAL_WORKSPACE.exists(), PREPARE_TRIGGER_EVAL_WORKSPACE
    output_dir = root / "fixture"
    result = json.loads(
        script(PREPARE_TRIGGER_EVAL_WORKSPACE, "--output-dir", str(output_dir), "--print-json").stdout
    )
    repo = Path(result["repo"])
    plan_path = Path(result["plan"])
    assert repo.exists(), result
    assert (repo / "AGENTS.md").exists(), result
    assert (repo / "README.md").exists(), result
    assert (repo / "src" / "parser.py").exists(), result
    assert (repo / ".git").exists(), result
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert result["prompt_count"] == len(plan), result
    assert all(Path(item["artifact"]).parent == Path(result["artifact_dir"]) for item in plan), plan
    assert all(item["cwd"] == str(repo) for item in plan), plan


def test_trigger_eval_runner_respects_cwd_and_artifact(root: Path) -> None:
    assert RUN_TRIGGER_EVAL_PLAN.exists(), RUN_TRIGGER_EVAL_PLAN
    repo = root / "runner-repo"
    repo.mkdir()
    artifact = root / "artifacts" / "runner-01.jsonl"
    skipped_artifact = root / "artifacts" / "runner-02.jsonl"
    plan_path = root / "runner-plan.json"
    code = (
        "import json, os; "
        "print(json.dumps({'cwd': os.getcwd(), 'observed_trigger': False}))"
    )
    plan_path.write_text(
        json.dumps(
            [
                {
                    "id": "runner-01",
                    "should_trigger": False,
                    "focus": "runner",
                    "prompt": "fake prompt",
                    "artifact": str(artifact),
                    "cwd": str(repo),
                    "command": [sys.executable, "-c", code],
                },
                {
                    "id": "runner-02",
                    "should_trigger": False,
                    "focus": "runner",
                    "prompt": "skipped prompt",
                    "artifact": str(skipped_artifact),
                    "cwd": str(repo),
                    "command": [sys.executable, "-c", code],
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    dry = json.loads(
        script(RUN_TRIGGER_EVAL_PLAN, "--plan", str(plan_path), "--id", "runner-01", "--dry-run", "--print-json").stdout
    )
    assert dry["ok"] is True, dry
    assert dry["plan_total"] == 2, dry
    assert dry["total"] == 1, dry
    assert dry["selected_ids"] == ["runner-01"], dry
    assert dry["results"][0]["cwd"] == str(repo.resolve()), dry
    assert not artifact.exists(), artifact

    ran = json.loads(script(RUN_TRIGGER_EVAL_PLAN, "--plan", str(plan_path), "--id", "runner-01", "--print-json").stdout)
    assert ran["ok"] is True, ran
    event = json.loads(artifact.read_text(encoding="utf-8"))
    assert event["cwd"] == str(repo.resolve()), event
    assert event["observed_trigger"] is False, event
    assert not skipped_artifact.exists(), skipped_artifact

    timeout_plan = root / "timeout-plan.json"
    timeout_artifact = root / "artifacts" / "timeout.jsonl"
    timeout_plan.write_text(
        json.dumps(
            [
                {
                    "id": "timeout-01",
                    "artifact": str(timeout_artifact),
                    "cwd": str(repo),
                    "command": [sys.executable, "-c", "import time; time.sleep(2)"],
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    timed_out = script(
        RUN_TRIGGER_EVAL_PLAN,
        "--plan",
        str(timeout_plan),
        "--timeout-seconds",
        "0.1",
        "--print-json",
        check=False,
    )
    assert timed_out.returncode != 0, timed_out.stdout
    timed_out_summary = json.loads(timed_out.stdout)
    assert timed_out_summary["ok"] is False, timed_out_summary
    assert timed_out_summary["results"][0]["timeout"] is True, timed_out_summary
    assert timed_out_summary["results"][0]["returncode"] is None, timed_out_summary


def test_trigger_eval_score_reads_jsonl_artifacts(root: Path) -> None:
    assert SCORE_TRIGGER_EVALS.exists(), SCORE_TRIGGER_EVALS
    artifact_dir = root / "evals"
    plan = json.loads(script(PLAN_TRIGGER_EVALS, "--artifact-dir", str(artifact_dir), "--print-json").stdout)
    for item in plan:
        artifact = Path(item["artifact"])
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if item["should_trigger"]:
            artifact.write_text(json.dumps({"start_work_triggered": True}) + "\n", encoding="utf-8")
        else:
            artifact.write_text(json.dumps({"observed_trigger": False}) + "\n", encoding="utf-8")

    scored = json.loads(script(SCORE_TRIGGER_EVALS, "--artifact-dir", str(artifact_dir), "--print-json").stdout)
    assert scored["ok"] is True, scored
    assert scored["passed"] == len(plan), scored
    assert scored["failed"] == 0, scored

    bad_artifact = Path(plan[-1]["artifact"])
    bad_artifact.write_text(json.dumps({"start_work_triggered": True}) + "\n", encoding="utf-8")
    failed = script(SCORE_TRIGGER_EVALS, "--artifact-dir", str(artifact_dir), "--print-json", check=False)
    assert failed.returncode != 0, failed.stdout
    failed_summary = json.loads(failed.stdout)
    assert failed_summary["ok"] is False, failed_summary
    assert failed_summary["failed"] == 1, failed_summary

    focused_artifact_dir = root / "focused-evals"
    focused_plan = json.loads(
        script(PLAN_TRIGGER_EVALS, "--artifact-dir", str(focused_artifact_dir), "--print-json").stdout
    )
    focused_plan_path = root / "focused-plan.json"
    focused_plan_path.write_text(json.dumps(focused_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    focused_item = focused_plan[0]
    focused_artifact = Path(focused_item["artifact"])
    focused_artifact.parent.mkdir(parents=True, exist_ok=True)
    focused_artifact.write_text(json.dumps({"start_work_triggered": True}) + "\n", encoding="utf-8")

    focused = json.loads(
        script(
            SCORE_TRIGGER_EVALS,
            "--plan",
            str(focused_plan_path),
            "--id",
            focused_item["id"],
            "--print-json",
        ).stdout
    )
    assert focused["ok"] is True, focused
    assert focused["plan_total"] == len(focused_plan), focused
    assert focused["total"] == 1, focused
    assert focused["selected_ids"] == [focused_item["id"]], focused
    assert focused["results"][0]["artifact"] == str(focused_artifact), focused

    relative_dir = root / "relative-plan"
    relative_dir.mkdir()
    relative_artifact = relative_dir / "artifacts" / "relative.jsonl"
    relative_artifact.parent.mkdir()
    relative_artifact.write_text(json.dumps({"observed_trigger": False}) + "\n", encoding="utf-8")
    relative_plan_path = relative_dir / "plan.json"
    relative_plan_path.write_text(
        json.dumps(
            [
                {
                    "id": "relative-01",
                    "should_trigger": "false",
                    "focus": "relative",
                    "artifact": "artifacts/relative.jsonl",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    relative = json.loads(
        script(
            SCORE_TRIGGER_EVALS,
            "--plan",
            str(relative_plan_path),
            "--id",
            "relative-01",
            "--print-json",
        ).stdout
    )
    assert relative["ok"] is True, relative
    assert relative["results"][0]["expected_trigger"] is False, relative
    assert relative["results"][0]["artifact"] == str(relative_artifact.resolve()), relative


def test_shared_contract_matches_generated_routes(root: Path) -> None:
    assert START_WORK_CONTRACT.exists(), START_WORK_CONTRACT
    assert VALIDATE_START_WORK.exists(), VALIDATE_START_WORK

    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import init_team as init_team_script
    finally:
        try:
            sys.path.remove(str(SCRIPT_DIR))
        except ValueError:
            pass
    start_work_contract = import_contract_module()

    direct_route = init_team_script.build_route(True)
    direct_specs = [
        (entry["from"], entry["to"], entry["trigger"], entry["manager_copy"])
        for entry in direct_route
    ]
    assert direct_specs == start_work_contract.required_route_specs(True), direct_specs
    assert direct_route[1]["to"] == "M", direct_route

    relay_route = init_team_script.build_route(False)
    relay_specs = [
        (entry["from"], entry["to"], entry["trigger"], entry["manager_copy"])
        for entry in relay_route
    ]
    assert relay_specs == start_work_contract.required_route_specs(False), relay_specs
    assert relay_route[1]["to"] == start_work_contract.MANUAL_RELAY_MANAGER_TARGET, relay_route


def fenced_block_after(text: str, marker: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(marker)}\s*```text\n(.*?)\n```", flags=re.DOTALL)
    match = pattern.search(text)
    assert match, marker
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def status_flow_lines(block: list[str]) -> list[str]:
    return [line.removeprefix("-> ").strip() for line in block]


def test_protocol_status_docs_match_contract(root: Path) -> None:
    contract = import_contract_module()
    protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(encoding="utf-8")

    assert set(contract.ALLOWED_STATUS_TRANSITIONS) == contract.RUN_STATUSES
    transition_targets = set().union(*contract.ALLOWED_STATUS_TRANSITIONS.values())
    assert transition_targets <= contract.RUN_STATUSES, transition_targets - contract.RUN_STATUSES
    assert set(contract.ORDERED_STATUS_TRANSITIONS) == contract.RUN_STATUSES
    for status, ordered_targets in contract.ORDERED_STATUS_TRANSITIONS.items():
        assert len(ordered_targets) == len(set(ordered_targets)), (status, ordered_targets)
        assert set(ordered_targets) == contract.ALLOWED_STATUS_TRANSITIONS[status], (status, ordered_targets)
        assert contract.next_allowed_statuses(status) == ordered_targets, (status, ordered_targets)

    documented_statuses = fenced_block_after(protocol, "Use these run statuses:")
    assert documented_statuses == contract.RUN_STATUS_ORDER, documented_statuses
    assert set(documented_statuses) == contract.RUN_STATUSES, documented_statuses

    normal_flow = status_flow_lines(fenced_block_after(protocol, "Normal flow:"))
    assert normal_flow == contract.NORMAL_STATUS_FLOW, normal_flow
    for source, target in zip(normal_flow, normal_flow[1:]):
        assert target in contract.ALLOWED_STATUS_TRANSITIONS[source], (source, target)
        assert contract.next_allowed_statuses(source)[0] == target, (source, target)

    fix_flow = status_flow_lines(fenced_block_after(protocol, "Fix flow:"))
    expected_fix_flow = [
        item if isinstance(item, str) else " or ".join(item)
        for item in contract.FIX_STATUS_FLOW
    ]
    assert fix_flow == expected_fix_flow, fix_flow
    assert "fix_required" in contract.ALLOWED_STATUS_TRANSITIONS["review_done"]
    assert {"developer_fix_running", "main_fixing"} <= contract.ALLOWED_STATUS_TRANSITIONS["fix_required"]
    assert "main_integration_check" in contract.ALLOWED_STATUS_TRANSITIONS["developer_fix_running"]
    assert "main_integration_check" in contract.ALLOWED_STATUS_TRANSITIONS["main_fixing"]

    for status in sorted(contract.DIRECT_SEND_STATUSES):
        assert status in protocol, status


def main() -> int:
    tests = [
        test_team_id_is_stable,
        test_team_inspection_requires_acknowledgements,
        test_team_inspection_rejects_broken_handoff_route,
        test_project_inspection_summarizes_team_and_recent_runs,
        test_callback_only_rejected_for_direct_thread_mode,
        test_direct_thread_happy_path,
        test_full_fix_review_cycle_status_path,
        test_run_json_status_mismatch_is_rejected,
        test_subagent_fallback_without_team,
        test_fallback_mode_requires_reason,
        test_reference_routing_is_progressive,
        test_trigger_eval_prompts_are_balanced,
        test_trigger_eval_plan_is_stable,
        test_prepare_trigger_eval_workspace,
        test_trigger_eval_runner_respects_cwd_and_artifact,
        test_trigger_eval_score_reads_jsonl_artifacts,
        test_shared_contract_matches_generated_routes,
        test_protocol_status_docs_match_contract,
    ]
    with tempfile.TemporaryDirectory(prefix="start-work-tests-") as temp:
        root = Path(temp)
        for test in tests:
            test(root)
            print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
