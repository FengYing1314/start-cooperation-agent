#!/usr/bin/env python3
"""Self-contained smoke tests for start-work scripts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path, PurePosixPath


SCRIPT_DIR = Path(__file__).resolve().parent
INIT_TEAM = SCRIPT_DIR / "init_team.py"
ACK_TEAM = SCRIPT_DIR / "ack_team.py"
INIT_RUN = SCRIPT_DIR / "init_run.py"
APPEND_EVENT = SCRIPT_DIR / "append_event.py"
PREPARE_OUTBOUND_HANDOFF = SCRIPT_DIR / "prepare_outbound_handoff.py"
FINALIZE_OUTBOUND_HANDOFF = SCRIPT_DIR / "finalize_outbound_handoff.py"
RECORD_INBOUND_HANDOFF = SCRIPT_DIR / "record_inbound_handoff.py"
INSPECT_TEAM = SCRIPT_DIR / "inspect_team.py"
INSPECT_RUN = SCRIPT_DIR / "inspect_run.py"
INSPECT_PROJECT = SCRIPT_DIR / "inspect_project.py"
PLAN_CODEX_THREAD_DRILL = SCRIPT_DIR / "plan_codex_thread_drill.py"
START_WORK_CONTRACT = SCRIPT_DIR / "start_work_contract.py"
VALIDATE_START_WORK = SCRIPT_DIR / "validate_start_work.py"
VALIDATE_HANDOFF = SCRIPT_DIR / "validate_handoff.py"
CHECK_TRIGGER_EVAL_CLI = SCRIPT_DIR / "check_trigger_eval_cli.py"
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


def import_drill_module():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import plan_codex_thread_drill
    finally:
        try:
            sys.path.remove(str(SCRIPT_DIR))
        except ValueError:
            pass
    return plan_codex_thread_drill


def run(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(command)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def split_test_names(values: Iterable[str]) -> list[str]:
    names: list[str] = []
    for item in values:
        for part in item.split(","):
            name = part.strip()
            if name:
                names.append(name)
    return names


def make_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    run(["git", "-C", str(repo), "init"])
    return repo


def script(path: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(path), *args], check=check, env=env)


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


def plan_codex_thread_drill(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return script(PLAN_CODEX_THREAD_DRILL, "--repo", str(repo), *args, "--print-json", check=check)


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
    team_result = init_team(
        repo,
        "--manager-thread-id",
        "manager-thread",
        "--developer-thread-id",
        "dev-thread",
        "--reviewer-thread-id",
        "review-thread",
    )
    team_commands = team_result["next_commands"]
    assert team_commands["inspect_team"][1].endswith("inspect_team.py"), team_commands
    assert team_commands["inspect_team"][team_commands["inspect_team"].index("--repo") + 1] == str(repo), team_commands
    assert team_commands["ack_developer"][-3:] == ["--role", "D1", "--print-json"], team_commands
    assert team_commands["ack_reviewer"][-3:] == ["--role", "R1", "--print-json"], team_commands
    assert team_commands["init_run"][1].endswith("init_run.py"), team_commands
    assert any("standing-developer.md" in item for item in team_result["next_actions"]), team_result
    assert any("send_message_to_thread.prompt" in item for item in team_result["next_actions"]), team_result
    for name in ("standing-developer.md", "standing-reviewer.md"):
        standing_text = (repo / ".agent-work" / "start-work" / "team" / name).read_text(encoding="utf-8")
        assert "Handoff payload contract:" in standing_text, standing_text
        assert "Every handoff you send or return must include local message id" in standing_text, standing_text
        assert "`Evidence references:`" in standing_text, standing_text
        assert "put bulky logs, diffs, traces, screenshots, or reports in run artifacts" in standing_text, standing_text
        assert "Next handoff sent:" in standing_text, standing_text
    proc = inspect_team(repo, check=False)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    data = json.loads(proc.stdout)
    assert data["ok"] is False, data
    assert data["roster_complete"] is True, data
    assert data["acknowledgements_complete"] is False, data
    assert data["codex_thread_ready"] is False, data
    assert any("D1 acknowledgement pending" in problem for problem in data["problems"]), data
    assert any("ack_team.py" in action for action in data["next_actions"]), data

    ack(repo, "D1")
    ack(repo, "R1")
    ready = json.loads(inspect_team(repo).stdout)
    assert ready["ok"] is True, ready
    assert ready["codex_thread_ready"] is True, ready
    assert ready["manual_relay_ready"] is False, ready
    assert ready["handoff_route_valid"] is True, ready
    assert ready["handoff_route_count"] == 5, ready
    assert any("Start direct codex-thread runs" in action for action in ready["next_actions"]), ready
    assert any("exact handoff contents" in action for action in ready["next_actions"]), ready


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


def test_project_inspection_guides_preflight_without_team(root: Path) -> None:
    repo = make_repo(root, "project-preflight")
    proc = inspect_project(repo, check=False)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, combined
    summary = json.loads(proc.stdout)
    assert summary["ok"] is False, summary
    assert any("non-destructive Codex App preflight" in item for item in summary["next_actions"]), summary
    assert any("before creating threads or sending messages" in item for item in summary["next_actions"]), summary
    assert any(problem["scope"] == "team" for problem in summary["problems"]), summary


def test_codex_thread_drill_plan_preserves_live_approval_gate(root: Path) -> None:
    repo = make_repo(root, "thread-drill-plan")
    unready = json.loads(plan_codex_thread_drill(repo).stdout)
    assert unready["ok"] is True, unready
    assert unready["ready_for_live_drill"] is False, unready
    assert unready["live_drill_authorized"] is False, unready
    assert unready["requires_explicit_live_drill_approval"] is True, unready
    assert unready["approval_gate"]["required_for_live_drill"] is True, unready
    assert unready["approval_gate"]["approved"] is False, unready
    assert unready["approval_gate"]["live_actions_remain_blocked"] is True, unready
    assert unready["can_run_non_destructive_preflight_now"] is True, unready
    assert unready["codex_project_match"]["required_for_live_drill"] is True, unready
    assert unready["codex_project_match"]["checked"] is False, unready
    assert any(step.get("tool") == "list_projects" for step in unready["non_destructive_preflight"]), unready
    assert any(step.get("tool") == "list_threads" for step in unready["non_destructive_preflight"]), unready
    assert any("codex-project" in str(step.get("followup", "")) for step in unready["non_destructive_preflight"]), unready
    criteria_ids = {item["id"] for item in unready["live_drill_success_criteria"]}
    assert {
        "project_target_proven",
        "explicit_approval",
        "roster_acknowledged",
        "manager_to_developer_sent",
        "developer_to_manager_received",
        "manager_to_reviewer_sent",
        "reviewer_route_proven",
        "no_manager_polling_transport",
    } <= criteria_ids, unready
    evidence_keys = {item["evidence"] for item in unready["completion_evidence_contract"]}
    assert {
        "codex_project_match",
        "approval_gate",
        "team_readiness",
        "manager_send_events",
        "inbound_handoffs",
        "transport_audit",
    } <= evidence_keys, unready
    evidence_text = json.dumps(unready["completion_evidence_contract"], ensure_ascii=False)
    assert "developer_completion recorded" in evidence_text, evidence_text
    assert "no Manager polling as normal transport" in evidence_text, evidence_text
    blocked_tools = {item.get("tool") for item in unready["blocked_without_approval"]}
    assert {"create_thread", "send_message_to_thread", "read_thread"} <= blocked_tools, unready
    assert any("explicit approval" in item for item in unready["recommended_next_actions"]), unready

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
    ready = json.loads(plan_codex_thread_drill(repo).stdout)
    assert ready["ledger_ready_for_live_drill"] is True, ready
    assert ready["ready_for_live_drill"] is False, ready
    state = ready["current_state"]
    assert state["codex_thread_ready"] is True, ready
    assert state["pending_outbound_count"] == 0, ready
    assert state["reviewer_fix_needs_send_count"] == 0, ready
    assert state["target_presence"]["M"]["thread_id_present"] is True, ready
    assert ready["codex_project_match"]["checked"] is False, ready
    drill_text = json.dumps(ready["live_drill_when_approved"], ensure_ascii=False)
    assert "init_team.py" in drill_text, drill_text
    assert "send_message_to_thread" in drill_text, drill_text
    assert "developer_completion" in drill_text, drill_text
    assert "reviewer_accepted" in drill_text, drill_text
    assert "reviewer_fix directly to D1" in drill_text, drill_text
    assert any("without Manager polling" in item for item in ready["recommended_next_actions"]), ready
    assert any("list_projects" in item for item in ready["recommended_next_actions"]), ready
    assert any("matched=true" in item for item in ready["recommended_next_actions"]), ready

    unmatched = json.loads(plan_codex_thread_drill(repo, "--codex-project", "other-project=C:\\other\\repo").stdout)
    assert unmatched["codex_project_match"]["checked"] is True, unmatched
    assert unmatched["codex_project_match"]["matched"] is False, unmatched
    assert unmatched["ready_for_live_drill"] is False, unmatched
    assert any("exactly matches this repo" in item for item in unmatched["recommended_next_actions"]), unmatched

    matched = json.loads(plan_codex_thread_drill(repo, "--codex-project", f"project-1={repo}").stdout)
    assert matched["codex_project_match"]["checked"] is True, matched
    assert matched["codex_project_match"]["matched"] is True, matched
    assert matched["codex_project_match"]["matches"][0]["project_id"] == "project-1", matched
    assert matched["ledger_ready_for_live_drill"] is True, matched
    assert matched["ready_for_live_drill"] is True, matched
    assert matched["live_drill_authorized"] is False, matched
    assert matched["approval_gate"]["approved"] is False, matched
    assert any("live_drill_authorized=true" in item for item in matched["recommended_next_actions"]), matched

    authorized = json.loads(
        plan_codex_thread_drill(
            repo,
            "--codex-project",
            f"project-1={repo}",
            "--live-approval-evidence",
            "user approved live D1/R1 thread drill in this turn",
        ).stdout
    )
    assert authorized["ready_for_live_drill"] is True, authorized
    assert authorized["live_drill_authorized"] is True, authorized
    assert authorized["approval_gate"]["approved"] is True, authorized
    assert authorized["approval_gate"]["live_actions_remain_blocked"] is False, authorized
    assert "user approved live D1/R1 thread drill" in authorized["approval_gate"]["evidence"], authorized
    assert any("Live drill gates are satisfied" in item for item in authorized["recommended_next_actions"]), authorized

    text_result = script(PLAN_CODEX_THREAD_DRILL, "--repo", str(repo))
    assert "Ledger Ready For Live Drill: true" in text_result.stdout, text_result.stdout
    assert "Ready For Live Drill: false" in text_result.stdout, text_result.stdout
    assert "Live Drill Authorized: false" in text_result.stdout, text_result.stdout
    assert "Requires Explicit Live Drill Approval: true" in text_result.stdout, text_result.stdout
    assert "Approval Gate Approved: false" in text_result.stdout, text_result.stdout
    assert "Codex Project Match Checked: false" in text_result.stdout, text_result.stdout


def test_codex_project_match_accepts_wsl_and_mount_equivalent_paths(root: Path) -> None:
    drill = import_drill_module()
    wsl_repo = PurePosixPath("/home/fengying/projects/weeksir/weeksir-frontend")
    wsl_match = drill.codex_project_match(
        wsl_repo,
        [
            {
                "project_id": "frontend",
                "path": r"\\wsl.localhost\Ubuntu-26.04\home\fengying\projects\weeksir\weeksir-frontend",
            }
        ],
    )
    assert wsl_match["matched"] is True, wsl_match
    assert wsl_match["matches"][0]["project_id"] == "frontend", wsl_match

    wsl_dollar_match = drill.codex_project_match(
        wsl_repo,
        [
            {
                "project_id": "frontend-alt",
                "path": r"\\wsl$\Ubuntu-26.04\home\fengying\projects\weeksir\weeksir-frontend",
            }
        ],
    )
    assert wsl_dollar_match["matched"] is True, wsl_dollar_match

    mounted_windows_match = drill.codex_project_match(
        PurePosixPath("/mnt/c/Users/admin/project"),
        [{"project_id": "windows-project", "path": r"C:\Users\admin\project"}],
    )
    assert mounted_windows_match["matched"] is True, mounted_windows_match

    non_match = drill.codex_project_match(
        wsl_repo,
        [{"project_id": "backend", "path": r"\\wsl.localhost\Ubuntu-26.04\home\fengying\projects\weeksir\backend"}],
    )
    assert non_match["matched"] is False, non_match


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
    assert any("Resume latest run" in item for item in summary["next_actions"]), summary
    assert any("prepare_outbound_handoff.py --kind work_order" in item for item in summary["next_actions"]), summary
    assert any("finalize_sent_command" in item for item in summary["next_actions"]), summary
    assert latest["next_actions"], latest
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
    assert any("do not start direct codex-thread runs" in action for action in inspected["next_actions"]), inspected
    assert any("do not guess a thread id" in action for action in inspected["next_actions"]), inspected

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
    assert any("Manager work order" in item for item in run_data["next_actions"]), run_data
    run_commands = run_data["next_commands"]
    assert run_commands["inspect_run"][1].endswith("inspect_run.py"), run_commands
    assert run_commands["inspect_run"][run_commands["inspect_run"].index("--run-dir") + 1] == str(run_dir), run_commands
    assert run_commands["prepare_work_order"][1].endswith("prepare_outbound_handoff.py"), run_commands
    assert "work_order" in run_commands["prepare_work_order"], run_commands
    assert "record_work_order" not in run_commands, run_commands
    assert "record_developer_running" not in run_commands, run_commands
    assert any("finalize_sent_command" in item for item in run_data["next_actions"]), run_data
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
    assert any("Developer completion handoff" in item for item in inspected["next_actions"]), inspected

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
    accepted = json.loads(inspect_run(run_dir).stdout)
    assert any("final user-facing summary" in item for item in accepted["next_actions"]), accepted


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
    assert "prepare_work_order" in data["next_commands"], data
    assert "record_work_order" not in data["next_commands"], data
    assert "record_developer_running" not in data["next_commands"], data
    assert any("do not record direct-send running status" in item for item in data["next_actions"]), data
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
    assert "plan_codex_thread_drill.py" in skill, skill
    assert "--codex-project" in skill, skill
    assert "ledger_ready_for_live_drill" in skill, skill
    assert "live_drill_authorized" in skill, skill
    assert "--live-approval-evidence" in skill, skill
    assert "WSL UNC and native Linux path forms" in skill, skill
    assert "live_drill_success_criteria" in skill, skill
    assert "completion_evidence_contract" in skill, skill
    assert "prepare_outbound_handoff.py" in skill, skill
    assert "finalize_outbound_handoff.py" in skill, skill
    assert "record_inbound_handoff.py" in skill, skill
    assert "validate_handoff.py" in skill, skill
    assert "reviewer_accepted" in skill, skill
    assert "Outbound kinds: `work_order`, `review_request`" in skill, skill
    assert "Reviewer fix handoffs are Reviewer-originated" in skill, skill
    assert "check_trigger_eval_cli.py" in skill, skill
    assert "run_trigger_eval_plan.py" in skill, skill
    assert "start_work_contract.py" in skill, skill
    assert "validate_start_work.py" in skill, skill
    assert "quick_validate.py" in skill, skill
    assert not (SKILL_ROOT / "README.md").exists(), "README.md should not be in the skill package"
    assert "callback/manual relay fallback" in skill, skill
    assert "handoff route invariants" in skill, skill
    assert "team readiness inspection" in skill, skill
    assert "structured run metadata" in skill, skill
    assert "next_commands" in skill, skill
    assert "next_actions" in skill, skill
    assert "pending_outbound" in skill, skill
    assert "--send-evidence" in skill, skill
    assert "full fix-review loop progression" in skill, skill
    assert "non-destructive Codex App preflight" in skill, skill
    assert "read the returned `unsent_handoff.payload_file`" in skill, skill
    assert "unsent_handoff.after_send_evidence_command" in skill, skill
    assert "run `unsent_handoff.after_send_status_commands` only after the real send succeeds" in skill, skill
    assert "run `unsent_handoff.after_send_failed_command` with a concrete send error" in skill, skill
    assert "reviewer fix send-state project resume" in skill, skill
    assert "Codex App live-drill planning" in skill, skill

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
    work_order_templates = (SKILL_ROOT / "references" / "templates-work-order.md").read_text(encoding="utf-8")
    review_templates = (SKILL_ROOT / "references" / "templates-review.md").read_text(encoding="utf-8")
    assert "yes | no, plus target thread or unsent target" in work_order_templates, work_order_templates
    assert "yes | no, plus target thread or unsent target" in review_templates, review_templates

    codex_thread = (SKILL_ROOT / "references" / "codex-thread-mode.md").read_text(encoding="utf-8")
    assert "send_message_to_thread" in codex_thread, codex_thread
    assert "threadId=<send_to_thread_id>" in codex_thread, codex_thread
    assert "prompt=<exact contents of payload_file>" in codex_thread, codex_thread
    assert "prepare_outbound_handoff.py" in codex_thread, codex_thread
    assert "finalize_outbound_handoff.py" in codex_thread, codex_thread
    assert "--send-evidence" in codex_thread, codex_thread
    assert "pending_outbound" in codex_thread, codex_thread
    assert "## Non-Destructive Preflight" in codex_thread, codex_thread
    assert "## Live Drill Gate" in codex_thread, codex_thread
    assert "plan_codex_thread_drill.py" in codex_thread, codex_thread
    assert "blocked_without_approval" in codex_thread, codex_thread
    assert "codex_project_match" in codex_thread, codex_thread
    assert "--codex-project" in codex_thread, codex_thread
    assert "ledger_ready_for_live_drill" in codex_thread, codex_thread
    assert "approval_gate.approved=true" in codex_thread, codex_thread
    assert "live_drill_authorized=true" in codex_thread, codex_thread
    assert "--live-approval-evidence" in codex_thread, codex_thread
    assert "WSL UNC paths" in codex_thread, codex_thread
    assert "ready_for_live_drill=true" in codex_thread, codex_thread
    assert "live_drill_success_criteria" in codex_thread, codex_thread
    assert "completion_evidence_contract" in codex_thread, codex_thread
    assert "Allowed preflight actions" in codex_thread, codex_thread
    assert "Forbidden in preflight" in codex_thread, codex_thread
    assert "do not call `create_thread`" in codex_thread, codex_thread
    assert "do not call `read_thread`" in codex_thread, codex_thread
    assert "list_projects" in codex_thread, codex_thread
    assert "list_threads" in codex_thread, codex_thread
    assert "Current Codex App thread tool shape" in codex_thread, codex_thread
    assert 'create_thread({prompt, target})' in codex_thread, codex_thread
    assert 'target={type:"project", projectId, environment:{type:"local"}}' in codex_thread, codex_thread
    assert "Omit `model` and `thinking` unless the user explicitly requests overrides" in codex_thread, codex_thread
    assert "send_message_to_thread({threadId, prompt})" in codex_thread, codex_thread
    assert "readiness summary" in codex_thread, codex_thread
    assert "Codex CLI is not a substitute for Codex App thread transport" in codex_thread, codex_thread
    assert "do not use `codex exec`/`resume` as proof" in codex_thread, codex_thread
    assert "If it starts with `no`" in codex_thread, codex_thread
    assert "read `unsent_handoff.payload_file`" in codex_thread, codex_thread
    assert "`unsent_handoff.after_send_evidence_command`" in codex_thread, codex_thread
    assert "`unsent_handoff.after_send_failed_command`" in codex_thread, codex_thread
    assert "Do not mark `fix_required` or `developer_fix_running`" in codex_thread, codex_thread
    assert "record_inbound_handoff.py --kind reviewer_fix" in codex_thread, codex_thread
    assert "transport layer" in codex_thread, codex_thread
    assert "scripts/append_event.py --kind message --actor M" not in codex_thread, codex_thread

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
    assert "prepare_outbound_handoff.py" in protocol, protocol
    assert "finalize_outbound_handoff.py" in protocol, protocol
    assert "record_inbound_handoff.py" in protocol, protocol
    assert "validate_handoff.py" in protocol, protocol
    assert "Manager-originated outbound handoffs" in protocol, protocol
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
    assert "next_commands" in protocol, protocol
    assert "next_actions" in protocol, protocol
    assert "pending_outbound" in protocol, protocol
    assert "--send-evidence" in protocol, protocol
    assert "When it starts with `no`" in protocol, protocol
    assert "use the returned `unsent_handoff`" in protocol, protocol
    assert "after_send_evidence_command" in protocol, protocol
    assert "only then run `after_send_status_commands`" in protocol, protocol
    assert "run `after_send_failed_command` with the concrete error" in protocol, protocol
    assert "Do not record `fix_required` or `developer_fix_running`" in protocol, protocol
    assert "updates `run.json` with the current status and last event" in protocol, protocol
    assert "records both its event status and run status" in protocol, protocol
    assert "full fix-review loop as an executable invariant" in protocol, protocol

    openai_yaml = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "Coordinate Codex App thread teams" in openai_yaml, openai_yaml
    assert "Use $start-work" in openai_yaml, openai_yaml
    assert "Manager/Developer/Reviewer" in openai_yaml, openai_yaml
    assert "roster-routed" in openai_yaml, openai_yaml
    assert "run ledgers" in openai_yaml, openai_yaml
    assert "direct-message development team" not in openai_yaml, openai_yaml
    assert "Coordinate roster-routed dev agents" not in openai_yaml, openai_yaml

    codex_thread = (SKILL_ROOT / "references" / "codex-thread-mode.md").read_text(encoding="utf-8")
    assert "do not infer or guess" in codex_thread, codex_thread
    assert "do not create a direct `codex-thread` run from a callback-only roster" in codex_thread, codex_thread


def test_handoff_payload_validation(root: Path) -> None:
    assert VALIDATE_HANDOFF.exists(), VALIDATE_HANDOFF
    good_payload = root / "good-work-order.md"
    good_payload.write_text(
        """Start-work work order M-001
Run ID: 20260101-000001-test
Team ID: team-001
From: M
To: D1
Manager Thread: manager-thread
Developer Thread: dev-thread
Reviewer Thread: review-thread
Project Path: C:/repo

User goal:
Fix the parser error.

Ownership:
src/parser.py

Acceptance criteria:
Parser handles blank input.

Required checks:
python -m pytest tests/test_parser.py

Developer response format:
Status: complete | blocked
Changed files:
Checks run:
Evidence references:
Next handoff sent:
""",
        encoding="utf-8",
    )
    good = json.loads(
        script(
            VALIDATE_HANDOFF,
            "--kind",
            "work_order",
            "--body-file",
            str(good_payload),
            "--print-json",
        ).stdout
    )
    assert good["ok"] is True, good
    assert any("Send the validated work order" in item for item in good["next_actions"]), good

    good_review = root / "good-review-request.md"
    good_review.write_text(
        """Start-work review request M-002
Run ID: 20260101-000001-test
Team ID: team-001
From: M
To: R1
Developer Thread: dev-thread
Reviewer Thread: review-thread
Project Path: C:/repo

User goal:
Fix the parser error.

Acceptance criteria:
Parser handles blank input.

Review scope:
src/parser.py

Manager checkpoint:
Diff inspected; tests passed.

Changed files:
src/parser.py

Developer summary:
Parser now handles blank input.

Evidence references:
python -m pytest tests/test_parser.py

Reviewer report format:
Conclusion: accepted | changes required | blocked
""",
        encoding="utf-8",
    )
    good_review_summary = json.loads(
        script(
            VALIDATE_HANDOFF,
            "--kind",
            "review_request",
            "--body-file",
            str(good_review),
            "--print-json",
        ).stdout
    )
    assert good_review_summary["ok"] is True, good_review_summary

    bad_payload = root / "bad-work-order.md"
    bad_payload.write_text(
        """Start-work work order M-001
Run ID: <run-id>
Team ID: team-001
From: D1
To: R1
Manager Thread: manager-thread
Developer Thread: dev-thread
Reviewer Thread: review-thread

User goal:
Fix the parser error.

Ownership:
Acceptance criteria:
Parser handles blank input.

Required checks:
python -m pytest tests/test_parser.py

Developer response format:
Status: complete | blocked
""",
        encoding="utf-8",
    )
    bad_proc = script(
        VALIDATE_HANDOFF,
        "--kind",
        "work_order",
        "--body-file",
        str(bad_payload),
        "--print-json",
        check=False,
    )
    assert bad_proc.returncode != 0, bad_proc.stdout
    bad = json.loads(bad_proc.stdout)
    assert bad["ok"] is False, bad
    assert any("Missing required label: Project Path" in problem for problem in bad["problems"]), bad
    assert any("Unresolved placeholder in Run ID" in problem for problem in bad["problems"]), bad
    assert any("Unexpected From" in problem for problem in bad["problems"]), bad
    assert any("Unexpected To" in problem for problem in bad["problems"]), bad
    assert any("Required label is empty: Ownership" in problem for problem in bad["problems"]), bad

    bad_completion = root / "bad-developer-completion.md"
    bad_completion.write_text(
        """Start-work handoff D1-001
Run ID: 20260101-000001-test
Team ID: team-001
From: D1
To: M
Status: complete

Summary:
Done.

Changed files:
src/parser.py

Checks:
python -m pytest tests/test_parser.py

Evidence references:
tests/test_parser.py

Requested next action:
Manager checkpoint.

Next handoff sent:
maybe, Manager thread manager-thread.
""",
        encoding="utf-8",
    )
    bad_completion_proc = script(
        VALIDATE_HANDOFF,
        "--kind",
        "developer_completion",
        "--body-file",
        str(bad_completion),
        "--print-json",
        check=False,
    )
    assert bad_completion_proc.returncode != 0, bad_completion_proc.stdout
    bad_completion_summary = json.loads(bad_completion_proc.stdout)
    assert any(
        "Next handoff sent must start with yes or no" in problem
        for problem in bad_completion_summary["problems"]
    ), bad_completion_summary

    missing_evidence = root / "developer-completion-missing-evidence.md"
    missing_evidence.write_text(
        """Start-work handoff D1-002
Run ID: 20260101-000001-test
Team ID: team-001
From: D1
To: M
Status: complete

Summary:
Done.

Changed files:
src/parser.py

Checks:
python -m pytest tests/test_parser.py

Requested next action:
Manager checkpoint.

Next handoff sent:
yes, Manager thread manager-thread.
""",
        encoding="utf-8",
    )
    missing_evidence_proc = script(
        VALIDATE_HANDOFF,
        "--kind",
        "developer_completion",
        "--body-file",
        str(missing_evidence),
        "--print-json",
        check=False,
    )
    assert missing_evidence_proc.returncode != 0, missing_evidence_proc.stdout
    missing_evidence_summary = json.loads(missing_evidence_proc.stdout)
    assert any(
        "Missing required label: Evidence references" in problem
        for problem in missing_evidence_summary["problems"]
    ), missing_evidence_summary


def test_prepare_outbound_handoff_records_and_routes(root: Path) -> None:
    assert PREPARE_OUTBOUND_HANDOFF.exists(), PREPARE_OUTBOUND_HANDOFF
    assert FINALIZE_OUTBOUND_HANDOFF.exists(), FINALIZE_OUTBOUND_HANDOFF
    unsupported_fix = script(
        PREPARE_OUTBOUND_HANDOFF,
        "--run-dir",
        str(root),
        "--kind",
        "reviewer_fix",
        "--body",
        "payload",
        "--print-json",
        check=False,
    )
    unsupported_combined = unsupported_fix.stdout + unsupported_fix.stderr
    assert unsupported_fix.returncode != 0, unsupported_combined
    assert "invalid choice" in unsupported_combined and "reviewer_fix" in unsupported_combined, unsupported_combined
    repo = make_repo(root, "prepare-outbound")
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
    run_data = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "prepare",
            "--request",
            "test prepare outbound handoff",
            "--print-json",
        ).stdout
    )
    run_dir = Path(str(run_data["run_dir"]))
    payload = root / "work-order.md"
    payload.write_text(
        """Start-work work order M-001
Run ID: 20260101-000001-prepare
Team ID: team-prepare
From: M
To: D1
Manager Thread: manager-thread
Developer Thread: dev-thread
Reviewer Thread: review-thread
Project Path: C:/repo

User goal:
Fix the parser error.

Ownership:
src/parser.py

Acceptance criteria:
Parser handles blank input.

Required checks:
python -m pytest tests/test_parser.py

Developer response format:
Status: complete | blocked
Changed files:
Implementation summary:
Checks run:
Evidence references:
Next handoff sent:
""",
        encoding="utf-8",
    )

    prepared = json.loads(
        script(
            PREPARE_OUTBOUND_HANDOFF,
            "--run-dir",
            str(run_dir),
            "--kind",
            "work_order",
            "--body-file",
            str(payload),
            "--print-json",
        ).stdout
    )
    assert prepared["ok"] is True, prepared
    assert prepared["send_to"] == "D1", prepared
    assert prepared["send_to_thread_id"] == "dev-thread", prepared
    assert prepared["event"]["id"] == "M-001", prepared
    assert prepared["event"]["run_status"] == "manager_work_order", prepared
    assert prepared["event"]["file"].replace("\\", "/") == "messages/M-001-work-order-ready.md", prepared
    assert Path(prepared["payload_file"]).exists(), prepared
    assert prepared["send_message_to_thread"]["threadId"] == "dev-thread", prepared
    assert prepared["send_message_to_thread"]["prompt_file"] == prepared["payload_file"], prepared
    assert "do not send only the file path" in prepared["send_message_to_thread"]["prompt_instruction"], prepared
    assert "developer_running" in prepared["post_send_status_command"], prepared
    assert "finalize_outbound_handoff.py" in prepared["finalize_sent_command"][1], prepared
    assert "sent" in prepared["finalize_sent_command"], prepared
    assert "failed" in prepared["finalize_failed_command"], prepared
    assert any("send_message_to_thread" in item for item in prepared["next_actions"]), prepared
    assert any("Do not pass the payload_file path as the prompt" in item for item in prepared["next_actions"]), prepared
    assert any("--send-evidence" in item for item in prepared["next_actions"]), prepared
    inspected = json.loads(inspect_run(run_dir).stdout)
    assert inspected["current_status"] == "manager_work_order", inspected
    assert inspected["event_count"] == 1, inspected
    pending = inspected["pending_outbound"]
    assert pending["kind"] == "work_order", inspected
    assert pending["event_id"] == "M-001", inspected
    assert pending["send_to"] == "D1", inspected
    assert pending["send_to_thread_id"] == "dev-thread", inspected
    assert pending["payload_file"].replace("\\", "/").endswith("messages/M-001-work-order-ready.md"), inspected
    assert pending["send_message_to_thread"]["threadId"] == "dev-thread", inspected
    assert pending["send_message_to_thread"]["prompt_file"] == pending["payload_file"], inspected
    assert "finalize_outbound_handoff.py" in pending["finalize_sent_command"][1], inspected
    assert "sent" in pending["finalize_sent_command"], inspected
    assert "failed" in pending["finalize_failed_command"], inspected
    assert any("Pending outbound work_order M-001" in item for item in inspected["next_actions"]), inspected
    assert any("Do not send only the payload_file path" in item for item in inspected["next_actions"]), inspected
    assert any("--send-evidence" in item for item in inspected["next_actions"]), inspected

    finalized = json.loads(
        script(
            FINALIZE_OUTBOUND_HANDOFF,
            "--run-dir",
            str(run_dir),
            "--kind",
            "work_order",
            "--event-id",
            "M-001",
            "--result",
            "sent",
            "--send-evidence",
            '{"threadId":"dev-thread","delivery":"accepted"}',
            "--print-json",
        ).stdout
    )
    assert finalized["ok"] is True, finalized
    assert finalized["send_result"] == "sent", finalized
    assert finalized["result_event"]["run_status"] == "developer_running", finalized
    assert finalized["evidence_event"]["kind"] == "artifact", finalized
    sent_evidence = (run_dir / finalized["evidence_event"]["file"]).read_text(encoding="utf-8")
    assert '"delivery":"accepted"' in sent_evidence, finalized
    sent_inspected = json.loads(inspect_run(run_dir).stdout)
    assert sent_inspected["current_status"] == "developer_running", sent_inspected
    assert sent_inspected["event_count"] == 3, sent_inspected
    assert sent_inspected["pending_outbound"] is None, sent_inspected

    duplicate_finalize = script(
        FINALIZE_OUTBOUND_HANDOFF,
        "--run-dir",
        str(run_dir),
        "--kind",
        "work_order",
        "--event-id",
        "M-001",
        "--result",
        "sent",
        "--print-json",
        check=False,
    )
    assert duplicate_finalize.returncode != 0, duplicate_finalize.stdout + duplicate_finalize.stderr
    assert "already finalized" in (duplicate_finalize.stdout + duplicate_finalize.stderr), duplicate_finalize.stdout

    bad_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "prepare-bad",
            "--request",
            "test bad prepare outbound handoff",
            "--print-json",
        ).stdout
    )
    bad_run_dir = Path(str(bad_run["run_dir"]))
    bad_payload = root / "bad-outbound.md"
    bad_payload.write_text(
        """Start-work work order M-001
Run ID: <run-id>
Team ID: team-prepare
From: M
To: D1
Manager Thread: manager-thread
Developer Thread: dev-thread
Reviewer Thread: review-thread
Project Path: C:/repo

User goal:
Fix the parser error.

Ownership:
src/parser.py

Acceptance criteria:
Parser handles blank input.

Required checks:
python -m pytest tests/test_parser.py

Developer response format:
Status: complete | blocked
""",
        encoding="utf-8",
    )
    failed = script(
        PREPARE_OUTBOUND_HANDOFF,
        "--run-dir",
        str(bad_run_dir),
        "--kind",
        "work_order",
        "--body-file",
        str(bad_payload),
        "--print-json",
        check=False,
    )
    assert failed.returncode != 0, failed.stdout
    failed_summary = json.loads(failed.stdout)
    assert failed_summary["ok"] is False, failed_summary
    assert any("Unresolved placeholder" in problem for problem in failed_summary["problems"]), failed_summary
    bad_inspected = json.loads(inspect_run(bad_run_dir).stdout)
    assert bad_inspected["event_count"] == 0, bad_inspected

    failed_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "prepare-send-failed",
            "--request",
            "test failed outbound send finalization",
            "--print-json",
        ).stdout
    )
    failed_run_dir = Path(str(failed_run["run_dir"]))
    prepared_failed = json.loads(
        script(
            PREPARE_OUTBOUND_HANDOFF,
            "--run-dir",
            str(failed_run_dir),
            "--kind",
            "work_order",
            "--body-file",
            str(payload),
            "--print-json",
        ).stdout
    )
    assert prepared_failed["ok"] is True, prepared_failed
    failed_finalized = json.loads(
        script(
            FINALIZE_OUTBOUND_HANDOFF,
            "--run-dir",
            str(failed_run_dir),
            "--kind",
            "work_order",
            "--event-id",
            "M-001",
            "--result",
            "failed",
            "--error",
            "tool unavailable",
            "--summary",
            "custom failure note",
            "--print-json",
        ).stdout
    )
    assert failed_finalized["ok"] is True, failed_finalized
    assert failed_finalized["send_result"] == "failed", failed_finalized
    assert failed_finalized["result_event"]["kind"] == "blocker", failed_finalized
    assert failed_finalized["result_event"]["run_status"] == "", failed_finalized
    failed_outbound_body = (failed_run_dir / failed_finalized["result_event"]["file"]).read_text(encoding="utf-8")
    assert "tool unavailable" in failed_outbound_body, failed_finalized
    failed_inspected = json.loads(inspect_run(failed_run_dir).stdout)
    assert failed_inspected["current_status"] == "manager_work_order", failed_inspected
    assert failed_inspected["event_count"] == 2, failed_inspected
    assert failed_inspected["pending_outbound"] is None, failed_inspected


def test_record_inbound_handoff_records_received_payloads(root: Path) -> None:
    assert RECORD_INBOUND_HANDOFF.exists(), RECORD_INBOUND_HANDOFF
    repo = make_repo(root, "record-inbound")
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
    run_data = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound",
            "--request",
            "test inbound handoff recording",
            "--print-json",
        ).stdout
    )
    run_dir = Path(str(run_data["run_dir"]))
    append_status(
        run_dir,
        actor="M",
        to="D1",
        thread_id="dev-thread",
        run_status="manager_work_order",
        summary="work order recorded",
    )
    append_status(
        run_dir,
        actor="M",
        to="D1",
        thread_id="dev-thread",
        run_status="developer_running",
        summary="work order sent",
    )
    completion = root / "developer-completion.md"
    completion.write_text(
        """Start-work handoff D1-001
Run ID: 20260101-000001-inbound
Team ID: team-inbound
From: D1
To: M
Manager copy: n/a
Status: complete

Summary:
Implementation complete.

Changed files:
src/parser.py

Checks:
python -m pytest tests/test_parser.py

Evidence references:
tests/test_parser.py

Scope changes requested:
none

Blocking issues:
none

Requested next action:
Manager checkpoint and send to Reviewer if ready.

Next handoff sent:
yes, Manager thread manager-thread.
""",
        encoding="utf-8",
    )
    recorded = json.loads(
        script(
            RECORD_INBOUND_HANDOFF,
            "--run-dir",
            str(run_dir),
            "--kind",
            "developer_completion",
            "--body-file",
            str(completion),
            "--print-json",
        ).stdout
    )
    assert recorded["ok"] is True, recorded
    assert recorded["event"]["id"] == "D1-001", recorded
    assert recorded["event"]["actor"] == "D1", recorded
    assert recorded["event"]["to"] == "M", recorded
    assert recorded["event"]["thread_id"] == "manager-thread", recorded
    assert recorded["recorded_run_status"] == "developer_done", recorded
    inspected = json.loads(inspect_run(run_dir).stdout)
    assert inspected["current_status"] == "developer_done", inspected

    fix_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound-fix",
            "--request",
            "test inbound fix completion",
            "--print-json",
        ).stdout
    )
    fix_run_dir = Path(str(fix_run["run_dir"]))
    for actor, to, thread_id, run_status, summary in [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer done"),
        ("M", "", "", "main_integration_check", "manager checkpoint"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
        ("R1", "M", "manager-thread", "review_done", "review done"),
        ("R1", "D1", "dev-thread", "fix_required", "fix required"),
        ("R1", "D1", "dev-thread", "developer_fix_running", "fix request sent"),
    ]:
        append_status(
            fix_run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
    fix_completion = root / "developer-fix-completion.md"
    fix_completion.write_text(
        """Start-work fix completion D1-002
Run ID: 20260101-000002-inbound-fix
Team ID: team-inbound
From: D1
To: M
Status: complete

Fixed findings:
Handled blank input.

Changed files:
src/parser.py

Checks run:
python -m pytest tests/test_parser.py

Evidence references:
tests/test_parser.py

Remaining risk:
none

Requested next action:
Manager checkpoint and send re-review if ready.

Next handoff sent:
yes, Manager thread manager-thread.
""",
        encoding="utf-8",
    )
    fix_recorded = json.loads(
        script(
            RECORD_INBOUND_HANDOFF,
            "--run-dir",
            str(fix_run_dir),
            "--kind",
            "developer_fix_completion",
            "--body-file",
            str(fix_completion),
            "--print-json",
        ).stdout
    )
    assert fix_recorded["ok"] is True, fix_recorded
    assert fix_recorded["recorded_run_status"] == "", fix_recorded
    assert "main_integration_check" in fix_recorded["followup_status_command"], fix_recorded
    fix_inspected = json.loads(inspect_run(fix_run_dir).stdout)
    assert fix_inspected["current_status"] == "developer_fix_running", fix_inspected
    fix_followup = json.loads(run(fix_recorded["followup_status_command"]).stdout)
    assert fix_followup["run_status"] == "main_integration_check", fix_followup
    fix_after_followup = json.loads(inspect_run(fix_run_dir).stdout)
    assert fix_after_followup["current_status"] == "main_integration_check", fix_after_followup

    reviewer_fix_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound-reviewer-fix",
            "--request",
            "test inbound reviewer fix copy",
            "--print-json",
        ).stdout
    )
    reviewer_fix_run_dir = Path(str(reviewer_fix_run["run_dir"]))
    for actor, to, thread_id, run_status, summary in [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer done"),
        ("M", "", "", "main_integration_check", "manager checkpoint"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
    ]:
        append_status(
            reviewer_fix_run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
    reviewer_fix_payload = root / "reviewer-fix-copy.md"
    reviewer_fix_payload.write_text(
        """Start-work fix handoff R1-001
Run ID: 20260101-000003-inbound-reviewer-fix
Team ID: team-inbound
From: R1
To: D1
Manager copy: M
Status: changes required

Blocking findings:
Blank input still fails.

Allowed fix scope:
src/parser.py

Do not change:
Public API.

Evidence references:
python -m pytest tests/test_parser.py

Requested next action:
Fix only the blocking findings, then hand off to Manager for checkpoint.

Next handoff sent:
yes, D1 thread dev-thread.
""",
        encoding="utf-8",
    )
    reviewer_fix_recorded = json.loads(
        script(
            RECORD_INBOUND_HANDOFF,
            "--run-dir",
            str(reviewer_fix_run_dir),
            "--kind",
            "reviewer_fix",
            "--body-file",
            str(reviewer_fix_payload),
            "--print-json",
        ).stdout
    )
    assert reviewer_fix_recorded["ok"] is True, reviewer_fix_recorded
    assert reviewer_fix_recorded["recorded_run_status"] == "review_done", reviewer_fix_recorded
    assert reviewer_fix_recorded["event"]["thread_id"] == "dev-thread", reviewer_fix_recorded
    assert reviewer_fix_recorded["followup_status_command"] == [], reviewer_fix_recorded
    fix_commands = reviewer_fix_recorded["followup_status_commands"]
    assert len(fix_commands) == 2, reviewer_fix_recorded
    assert "fix_required" in fix_commands[0], reviewer_fix_recorded
    assert "developer_fix_running" in fix_commands[1], reviewer_fix_recorded
    reviewer_fix_inspected = json.loads(inspect_run(reviewer_fix_run_dir).stdout)
    assert reviewer_fix_inspected["current_status"] == "review_done", reviewer_fix_inspected
    assert reviewer_fix_inspected["reviewer_fix_send_state"]["next_handoff_sent"] == "yes", reviewer_fix_inspected
    assert any("D1 fix handoff was sent" in item for item in reviewer_fix_inspected["next_actions"]), (
        reviewer_fix_inspected
    )
    required_followup = json.loads(run(fix_commands[0]).stdout)
    assert required_followup["run_status"] == "fix_required", required_followup
    running_followup = json.loads(run(fix_commands[1]).stdout)
    assert running_followup["run_status"] == "developer_fix_running", running_followup
    reviewer_fix_after_followup = json.loads(inspect_run(reviewer_fix_run_dir).stdout)
    assert reviewer_fix_after_followup["current_status"] == "developer_fix_running", reviewer_fix_after_followup

    reviewer_fix_unsent_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound-reviewer-fix-unsent",
            "--request",
            "test inbound reviewer fix copy without D1 send",
            "--print-json",
        ).stdout
    )
    reviewer_fix_unsent_run_dir = Path(str(reviewer_fix_unsent_run["run_dir"]))
    for actor, to, thread_id, run_status, summary in [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer done"),
        ("M", "", "", "main_integration_check", "manager checkpoint"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
    ]:
        append_status(
            reviewer_fix_unsent_run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
    reviewer_fix_unsent_payload = root / "reviewer-fix-copy-unsent.md"
    reviewer_fix_unsent_payload.write_text(
        """Start-work fix handoff R1-001
Run ID: 20260101-000004-inbound-reviewer-fix-unsent
Team ID: team-inbound
From: R1
To: D1
Manager copy: M
Status: changes required

Blocking findings:
Blank input still fails.

Allowed fix scope:
src/parser.py

Do not change:
Public API.

Evidence references:
python -m pytest tests/test_parser.py

Requested next action:
Fix only the blocking findings, then hand off to Manager for checkpoint.

Next handoff sent:
no, D1 thread dev-thread is the unsent target.
""",
        encoding="utf-8",
    )
    reviewer_fix_unsent_recorded = json.loads(
        script(
            RECORD_INBOUND_HANDOFF,
            "--run-dir",
            str(reviewer_fix_unsent_run_dir),
            "--kind",
            "reviewer_fix",
            "--body-file",
            str(reviewer_fix_unsent_payload),
            "--thread-id",
            "dev-thread",
            "--summary",
            "custom blocking copy",
            "--print-json",
        ).stdout
    )
    assert reviewer_fix_unsent_recorded["ok"] is True, reviewer_fix_unsent_recorded
    assert reviewer_fix_unsent_recorded["recorded_run_status"] == "review_done", reviewer_fix_unsent_recorded
    assert reviewer_fix_unsent_recorded["event"]["thread_id"] == "", reviewer_fix_unsent_recorded
    assert reviewer_fix_unsent_recorded["followup_status_commands"] == [], reviewer_fix_unsent_recorded
    assert reviewer_fix_unsent_recorded["unsent_handoff"]["send_to_thread_id"] == "dev-thread", (
        reviewer_fix_unsent_recorded
    )
    assert reviewer_fix_unsent_recorded["unsent_handoff"]["send_message_to_thread"]["threadId"] == "dev-thread", (
        reviewer_fix_unsent_recorded
    )
    assert reviewer_fix_unsent_recorded["unsent_handoff"]["payload_file"].replace("\\", "/").endswith(
        "messages/R1-001-custom-blocking-copy.md"
    ), reviewer_fix_unsent_recorded
    assert len(reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_status_commands"]) == 2, (
        reviewer_fix_unsent_recorded
    )
    assert "fix_required" in reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_status_commands"][0], (
        reviewer_fix_unsent_recorded
    )
    assert "artifact" in reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_evidence_command"], (
        reviewer_fix_unsent_recorded
    )
    assert any(
        "<send evidence>" in item
        for item in reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_evidence_command"]
    ), reviewer_fix_unsent_recorded
    assert "blocker" in reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_failed_command"], (
        reviewer_fix_unsent_recorded
    )
    assert any(
        "<send error>" in item
        for item in reviewer_fix_unsent_recorded["unsent_handoff"]["after_send_failed_command"]
    ), reviewer_fix_unsent_recorded
    assert any("After the real D1 send succeeds" in item for item in reviewer_fix_unsent_recorded["next_actions"]), (
        reviewer_fix_unsent_recorded
    )
    assert any("after_send_evidence_command" in item for item in reviewer_fix_unsent_recorded["next_actions"]), (
        reviewer_fix_unsent_recorded
    )
    assert any("after_send_failed_command" in item for item in reviewer_fix_unsent_recorded["next_actions"]), (
        reviewer_fix_unsent_recorded
    )
    reviewer_fix_unsent_inspected = json.loads(inspect_run(reviewer_fix_unsent_run_dir).stdout)
    assert reviewer_fix_unsent_inspected["current_status"] == "review_done", reviewer_fix_unsent_inspected
    assert reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["next_handoff_sent"] == "no", (
        reviewer_fix_unsent_inspected
    )
    assert reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["event_id"] == "R1-001", (
        reviewer_fix_unsent_inspected
    )
    assert reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["send_to_thread_id"] == "dev-thread", (
        reviewer_fix_unsent_inspected
    )
    assert reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["send_message_to_thread"]["threadId"] == "dev-thread", (
        reviewer_fix_unsent_inspected
    )
    assert len(reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["after_send_status_commands"]) == 2, (
        reviewer_fix_unsent_inspected
    )
    assert "artifact" in reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["after_send_evidence_command"], (
        reviewer_fix_unsent_inspected
    )
    assert "blocker" in reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["after_send_failed_command"], (
        reviewer_fix_unsent_inspected
    )
    assert any("Next handoff sent: no" in item for item in reviewer_fix_unsent_inspected["next_actions"]), (
        reviewer_fix_unsent_inspected
    )
    assert any("send its exact contents to D1" in item for item in reviewer_fix_unsent_inspected["next_actions"]), (
        reviewer_fix_unsent_inspected
    )
    assert any("after_send_evidence_command" in item for item in reviewer_fix_unsent_inspected["next_actions"]), (
        reviewer_fix_unsent_inspected
    )
    assert any("after_send_failed_command" in item for item in reviewer_fix_unsent_inspected["next_actions"]), (
        reviewer_fix_unsent_inspected
    )
    evidence_command = [
        item.replace("<send evidence>", '{"threadId":"dev-thread","delivery":"accepted"}')
        for item in reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["after_send_evidence_command"]
    ]
    evidence_result = json.loads(run(evidence_command).stdout)
    assert evidence_result["kind"] == "artifact", evidence_result
    assert evidence_result["run_status"] == "", evidence_result
    evidence_body = (reviewer_fix_unsent_run_dir / evidence_result["file"]).read_text(encoding="utf-8")
    assert '"delivery":"accepted"' in evidence_body, evidence_result
    after_evidence_inspected = json.loads(inspect_run(reviewer_fix_unsent_run_dir).stdout)
    assert after_evidence_inspected["current_status"] == "review_done", after_evidence_inspected
    failed_command = [
        item.replace("<send error>", "transient app send failure")
        for item in reviewer_fix_unsent_inspected["reviewer_fix_send_state"]["after_send_failed_command"]
    ]
    failed_result = json.loads(run(failed_command).stdout)
    assert failed_result["kind"] == "blocker", failed_result
    assert failed_result["run_status"] == "", failed_result
    failed_body = (reviewer_fix_unsent_run_dir / failed_result["file"]).read_text(encoding="utf-8")
    assert "transient app send failure" in failed_body, failed_result
    after_failed_inspected = json.loads(inspect_run(reviewer_fix_unsent_run_dir).stdout)
    assert after_failed_inspected["current_status"] == "review_done", after_failed_inspected
    project_after_unsent = json.loads(inspect_project(repo, "--limit", "10").stdout)
    project_unsent_runs = [
        item
        for item in project_after_unsent["latest_runs"]
        if item.get("run_id") == reviewer_fix_unsent_run["run_id"]
    ]
    assert len(project_unsent_runs) == 1, project_after_unsent
    assert project_unsent_runs[0]["reviewer_fix_send_state"]["next_handoff_sent"] == "no", project_unsent_runs[0]
    assert project_unsent_runs[0]["reviewer_fix_send_state"]["send_message_to_thread"]["threadId"] == "dev-thread", (
        project_unsent_runs[0]
    )
    assert "artifact" in project_unsent_runs[0]["reviewer_fix_send_state"]["after_send_evidence_command"], (
        project_unsent_runs[0]
    )
    assert "blocker" in project_unsent_runs[0]["reviewer_fix_send_state"]["after_send_failed_command"], (
        project_unsent_runs[0]
    )
    assert any("Next handoff sent: no" in item for item in project_unsent_runs[0]["next_actions"]), (
        project_unsent_runs[0]
    )

    reviewer_fix_bad_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound-reviewer-fix-bad-payload",
            "--request",
            "test inbound reviewer fix copy with invalid evidence",
            "--print-json",
        ).stdout
    )
    reviewer_fix_bad_run_dir = Path(str(reviewer_fix_bad_run["run_dir"]))
    for actor, to, thread_id, run_status, summary in [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer done"),
        ("M", "", "", "main_integration_check", "manager checkpoint"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
    ]:
        append_status(
            reviewer_fix_bad_run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
    bad_payload_event = json.loads(
        script(
            APPEND_EVENT,
            "--run-dir",
            str(reviewer_fix_bad_run_dir),
            "--kind",
            "message",
            "--actor",
            "R1",
            "--to",
            "D1",
            "--thread-id",
            "dev-thread",
            "--summary",
            "broken reviewer fix copy",
            "--run-status",
            "review_done",
            "--body",
            "Broken reviewer fix copy without required labels.",
            "--print-json",
        ).stdout
    )
    bad_inspected = json.loads(inspect_run(reviewer_fix_bad_run_dir).stdout)
    assert bad_inspected["current_status"] == "review_done", bad_inspected
    assert bad_inspected["reviewer_fix_send_state"]["event_id"] == bad_payload_event["id"], bad_inspected
    assert bad_inspected["reviewer_fix_send_state"]["next_handoff_sent"] == "unknown", bad_inspected
    assert bad_inspected["reviewer_fix_send_state"]["problems"], bad_inspected
    assert any("cannot prove" in item for item in bad_inspected["next_actions"]), bad_inspected
    assert any("before appending fix_required" in item for item in bad_inspected["next_actions"]), bad_inspected
    assert not any(item.startswith("If accepted") for item in bad_inspected["next_actions"]), bad_inspected
    project_after_bad = json.loads(inspect_project(repo, "--limit", "10").stdout)
    project_bad_runs = [
        item
        for item in project_after_bad["latest_runs"]
        if item.get("run_id") == reviewer_fix_bad_run["run_id"]
    ]
    assert len(project_bad_runs) == 1, project_after_bad
    assert project_bad_runs[0]["reviewer_fix_send_state"]["next_handoff_sent"] == "unknown", project_bad_runs[0]
    assert any("cannot prove" in item for item in project_bad_runs[0]["next_actions"]), project_bad_runs[0]

    accepted_run = json.loads(
        script(
            INIT_RUN,
            "--repo",
            str(repo),
            "--slug",
            "inbound-accepted",
            "--request",
            "test inbound reviewer accepted",
            "--print-json",
        ).stdout
    )
    accepted_run_dir = Path(str(accepted_run["run_dir"]))
    for actor, to, thread_id, run_status, summary in [
        ("M", "D1", "dev-thread", "manager_work_order", "work order recorded"),
        ("M", "D1", "dev-thread", "developer_running", "work order sent"),
        ("D1", "M", "manager-thread", "developer_done", "developer done"),
        ("M", "", "", "main_integration_check", "manager checkpoint"),
        ("M", "R1", "review-thread", "reviewer_running", "review request sent"),
    ]:
        append_status(
            accepted_run_dir,
            actor=actor,
            to=to,
            thread_id=thread_id,
            run_status=run_status,
            summary=summary,
        )
    accepted_payload = root / "reviewer-accepted.md"
    accepted_payload.write_text(
        """Start-work review result R1-001
Run ID: 20260101-000003-inbound-accepted
Team ID: team-inbound
From: R1
To: M
Status: accepted

Accepted scope:
Parser fix.

Checks reviewed:
python -m pytest tests/test_parser.py

Evidence references:
tests/test_parser.py

Non-blocking findings:
none

Residual risk:
none

Requested next action:
Manager final delivery.

Next handoff sent:
yes, Manager thread manager-thread.
""",
        encoding="utf-8",
    )
    accepted_recorded = json.loads(
        script(
            RECORD_INBOUND_HANDOFF,
            "--run-dir",
            str(accepted_run_dir),
            "--kind",
            "reviewer_accepted",
            "--body-file",
            str(accepted_payload),
            "--print-json",
        ).stdout
    )
    assert accepted_recorded["ok"] is True, accepted_recorded
    assert accepted_recorded["recorded_run_status"] == "review_done", accepted_recorded
    assert "accepted" in accepted_recorded["followup_status_command"], accepted_recorded
    accepted_inspected = json.loads(inspect_run(accepted_run_dir).stdout)
    assert accepted_inspected["current_status"] == "review_done", accepted_inspected
    accepted_followup = json.loads(run(accepted_recorded["followup_status_command"]).stdout)
    assert accepted_followup["run_status"] == "accepted", accepted_followup
    accepted_after_followup = json.loads(inspect_run(accepted_run_dir).stdout)
    assert accepted_after_followup["current_status"] == "accepted", accepted_after_followup


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
    assert "CODEX_BIN" in text, text
    assert "next_commands" in text, text
    assert "next_actions" in text, text
    assert "cli_check" in text, text
    assert "do not run eval and score in parallel" in text, text
    assert "run_trigger_eval_plan.py --plan" in text, text
    assert "score_trigger_evals.py --plan" in text, text
    assert "Empty artifacts, runner errors, and timeouts are inconclusive failures" in text, text
    assert "Expected behavior:" in text, text


def test_trigger_eval_cli_check_reports_launchability(root: Path) -> None:
    assert CHECK_TRIGGER_EVAL_CLI.exists(), CHECK_TRIGGER_EVAL_CLI
    ok = json.loads(
        script(
            CHECK_TRIGGER_EVAL_CLI,
            "--codex-bin",
            sys.executable,
            "--cwd",
            str(root),
            "--print-json",
        ).stdout
    )
    assert ok["ok"] is True, ok
    assert ok["returncode"] == 0, ok
    assert ok["command"] == [sys.executable, "--version"], ok
    assert any("dry_run" in item for item in ok["next_actions"]), ok

    env = os.environ.copy()
    env["CODEX_BIN"] = sys.executable
    env["PATH"] = ""
    auto = json.loads(
        script(
            CHECK_TRIGGER_EVAL_CLI,
            "--codex-bin",
            "auto",
            "--cwd",
            str(root),
            "--print-json",
            env=env,
        ).stdout
    )
    assert auto["ok"] is True, auto
    assert auto["codex_bin"] == sys.executable, auto
    assert auto["command"] == [sys.executable, "--version"], auto
    assert auto["candidate_paths"][0] == sys.executable, auto

    missing = script(
        CHECK_TRIGGER_EVAL_CLI,
        "--codex-bin",
        "definitely-missing-start-work-codex-bin",
        "--cwd",
        str(root),
        "--print-json",
        check=False,
    )
    assert missing.returncode != 0, missing.stdout
    missing_summary = json.loads(missing.stdout)
    assert missing_summary["ok"] is False, missing_summary
    assert "Executable not found" in missing_summary["error"], missing_summary
    assert any("--codex-bin" in item for item in missing_summary["next_actions"]), missing_summary


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
        script(
            PREPARE_TRIGGER_EVAL_WORKSPACE,
            "--output-dir",
            str(output_dir),
            "--codex-bin",
            sys.executable,
            "--print-json",
        ).stdout
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
    assert result["codex_bin"], result
    assert result["cli_check"]["ok"] is True, result
    assert all(item["command"][0] == result["codex_bin"] for item in plan), plan
    commands = result["next_commands"]
    assert commands["cli_check"][1].endswith("check_trigger_eval_cli.py"), commands
    assert commands["cli_check"][commands["cli_check"].index("--cwd") + 1] == str(repo), commands
    assert commands["dry_run"][-1] == "--dry-run", commands
    assert commands["run"][commands["run"].index("--plan") + 1] == str(plan_path), commands
    assert commands["score"][commands["score"].index("--plan") + 1] == str(plan_path), commands
    assert commands["focused_run"][-2:] == ["--id", "<eval-id>"], commands
    assert commands["focused_score"][-2:] == ["--id", "<eval-id>"], commands
    assert any("cli_check" in item for item in result["next_actions"]), result
    assert any("do not run eval and score in parallel" in item for item in result["next_actions"]), result
    assert result["artifacts_cleaned"] is True, result

    stale = Path(result["artifact_dir"]) / "stale.jsonl"
    stale.write_text(json.dumps({"start_work_triggered": True}) + "\n", encoding="utf-8")
    refreshed = json.loads(
        script(
            PREPARE_TRIGGER_EVAL_WORKSPACE,
            "--output-dir",
            str(output_dir),
            "--codex-bin",
            sys.executable,
            "--print-json",
        ).stdout
    )
    assert refreshed["artifacts_cleaned"] is True, refreshed
    assert refreshed["removed_artifact_entries"] >= 1, refreshed
    assert not stale.exists(), stale

    kept_stale = Path(refreshed["artifact_dir"]) / "kept.jsonl"
    kept_stale.write_text(json.dumps({"start_work_triggered": True}) + "\n", encoding="utf-8")
    kept = json.loads(
        script(
            PREPARE_TRIGGER_EVAL_WORKSPACE,
            "--output-dir",
            str(output_dir),
            "--codex-bin",
            sys.executable,
            "--keep-artifacts",
            "--print-json",
        ).stdout
    )
    assert kept["artifacts_cleaned"] is False, kept
    assert kept["removed_artifact_entries"] == 0, kept
    assert kept_stale.exists(), kept_stale


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
    timeout_event = json.loads(timeout_artifact.read_text(encoding="utf-8").splitlines()[-1])
    assert timeout_event["eval_error"] == "timeout", timeout_event

    launch_artifact = root / "artifacts" / "launch-failed.jsonl"
    launch_plan_path = root / "launch-failed-plan.json"
    launch_plan_path.write_text(
        json.dumps(
            [
                {
                    "id": "launch-failed-01",
                    "artifact": str(launch_artifact),
                    "cwd": str(repo),
                    "command": ["definitely-missing-start-work-eval-command"],
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    launch_failed = script(
        RUN_TRIGGER_EVAL_PLAN,
        "--plan",
        str(launch_plan_path),
        "--print-json",
        check=False,
    )
    assert launch_failed.returncode != 0, launch_failed.stdout
    launch_summary = json.loads(launch_failed.stdout)
    assert launch_summary["results"][0]["ok"] is False, launch_summary
    launch_event = json.loads(launch_artifact.read_text(encoding="utf-8").splitlines()[-1])
    assert launch_event["eval_error"] == "launch_failed", launch_event

    undecodable_artifact = root / "artifacts" / "undecodable.jsonl"
    undecodable_plan_path = root / "undecodable-plan.json"
    undecodable_plan_path.write_text(
        json.dumps(
            [
                {
                    "id": "undecodable-01",
                    "artifact": str(undecodable_artifact),
                    "cwd": str(repo),
                    "command": [
                        sys.executable,
                        "-c",
                        "import sys; sys.stderr.buffer.write(bytes([0xff, 0xfe, 0xfd])); sys.exit(1)",
                    ],
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    undecodable = script(
        RUN_TRIGGER_EVAL_PLAN,
        "--plan",
        str(undecodable_plan_path),
        "--print-json",
        check=False,
    )
    assert undecodable.returncode != 0, undecodable.stdout
    undecodable_summary = json.loads(undecodable.stdout)
    assert undecodable_summary["results"][0]["returncode"] == 1, undecodable_summary
    assert "stderr_tail" in undecodable_summary["results"][0], undecodable_summary
    undecodable_event = json.loads(undecodable_artifact.read_text(encoding="utf-8").splitlines()[-1])
    assert undecodable_event["eval_error"] == "command_failed", undecodable_event
    assert "stderr_tail" in undecodable_event, undecodable_event


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

    empty_artifact = relative_dir / "artifacts" / "empty.jsonl"
    empty_artifact.write_text("", encoding="utf-8")
    error_artifact = relative_dir / "artifacts" / "error.jsonl"
    error_artifact.write_text(json.dumps({"eval_error": "launch_failed"}) + "\n", encoding="utf-8")
    integrity_plan_path = relative_dir / "integrity-plan.json"
    integrity_plan_path.write_text(
        json.dumps(
            [
                {
                    "id": "empty-false",
                    "should_trigger": "false",
                    "focus": "integrity",
                    "artifact": "artifacts/empty.jsonl",
                },
                {
                    "id": "error-false",
                    "should_trigger": "false",
                    "focus": "integrity",
                    "artifact": "artifacts/error.jsonl",
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    integrity = script(
        SCORE_TRIGGER_EVALS,
        "--plan",
        str(integrity_plan_path),
        "--print-json",
        check=False,
    )
    assert integrity.returncode != 0, integrity.stdout
    integrity_summary = json.loads(integrity.stdout)
    assert integrity_summary["failed"] == 2, integrity_summary
    methods = {item["method"] for item in integrity_summary["results"]}
    assert {"empty", "error"} == methods, integrity_summary


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


FAST_TESTS = [
    test_team_id_is_stable,
    test_team_inspection_requires_acknowledgements,
    test_codex_thread_drill_plan_preserves_live_approval_gate,
    test_project_inspection_guides_preflight_without_team,
    test_direct_thread_happy_path,
    test_handoff_payload_validation,
    test_protocol_status_docs_match_contract,
]

ULTRA_FAST_TESTS = [
    test_team_id_is_stable,
    test_team_inspection_requires_acknowledgements,
    test_project_inspection_guides_preflight_without_team,
    test_codex_thread_drill_plan_preserves_live_approval_gate,
    test_direct_thread_happy_path,
    test_protocol_status_docs_match_contract,
]


QUICK_TESTS = [
    test_team_id_is_stable,
    test_team_inspection_requires_acknowledgements,
    test_team_inspection_rejects_broken_handoff_route,
    test_project_inspection_guides_preflight_without_team,
    test_codex_thread_drill_plan_preserves_live_approval_gate,
    test_codex_project_match_accepts_wsl_and_mount_equivalent_paths,
    test_project_inspection_summarizes_team_and_recent_runs,
    test_callback_only_rejected_for_direct_thread_mode,
    test_direct_thread_happy_path,
    test_full_fix_review_cycle_status_path,
    test_subagent_fallback_without_team,
    test_fallback_mode_requires_reason,
    test_reference_routing_is_progressive,
    test_handoff_payload_validation,
    test_prepare_outbound_handoff_records_and_routes,
    test_protocol_status_docs_match_contract,
]


ALL_TESTS = [
    test_team_id_is_stable,
    test_team_inspection_requires_acknowledgements,
    test_team_inspection_rejects_broken_handoff_route,
    test_project_inspection_guides_preflight_without_team,
    test_codex_thread_drill_plan_preserves_live_approval_gate,
    test_codex_project_match_accepts_wsl_and_mount_equivalent_paths,
    test_project_inspection_summarizes_team_and_recent_runs,
    test_callback_only_rejected_for_direct_thread_mode,
    test_direct_thread_happy_path,
    test_full_fix_review_cycle_status_path,
    test_run_json_status_mismatch_is_rejected,
    test_subagent_fallback_without_team,
    test_fallback_mode_requires_reason,
    test_reference_routing_is_progressive,
    test_handoff_payload_validation,
    test_prepare_outbound_handoff_records_and_routes,
    test_record_inbound_handoff_records_received_payloads,
    test_trigger_eval_prompts_are_balanced,
    test_trigger_eval_cli_check_reports_launchability,
    test_trigger_eval_plan_is_stable,
    test_prepare_trigger_eval_workspace,
    test_trigger_eval_runner_respects_cwd_and_artifact,
    test_trigger_eval_score_reads_jsonl_artifacts,
    test_shared_contract_matches_generated_routes,
    test_protocol_status_docs_match_contract,
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--ultra-fast",
        action="store_true",
        help="Run the minimal smoke subset for the fastest iteration.",
    )
    mode.add_argument(
        "--fast",
        action="store_true",
        help="Run a concise fast subset for iterative development.",
    )
    mode.add_argument(
        "--quick",
        action="store_true",
        help="Run a broader fast subset for quick validation.",
    )
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="Print available test names and exit.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only the named tests (comma-separated and repeatable).",
    )
    parser.add_argument("--profile", action="store_true", help="Print per-test runtime in seconds.")
    args = parser.parse_args()

    test_by_name = {test.__name__: test for test in ALL_TESTS}
    if args.ultra_fast and args.only:
        raise SystemExit("--ultra-fast cannot be combined with --only.")
    if args.fast and args.only:
        raise SystemExit("--fast cannot be combined with --only.")
    if args.quick and args.only:
        raise SystemExit("--quick cannot be combined with --only.")

    if args.only:
        selected = []
        seen = set[str]()
        for name in split_test_names(args.only):
            if name not in test_by_name:
                known = "\n".join(f"- {key}" for key in sorted(test_by_name))
                raise SystemExit(
                    f"Unknown test name: {name}\nKnown tests:\n{known}"
                )
            if name not in seen:
                selected.append(test_by_name[name])
                seen.add(name)
        tests = selected
    elif args.ultra_fast:
        tests = ULTRA_FAST_TESTS
    elif args.fast:
        tests = FAST_TESTS
    elif args.quick:
        tests = QUICK_TESTS
    else:
        tests = ALL_TESTS

    if args.list_tests:
        selected_names = [test.__name__ for test in tests]
        print("\n".join(selected_names))
        return 0

    timings = []
    with tempfile.TemporaryDirectory(prefix="start-work-tests-") as temp:
        root = Path(temp)
        for test in tests:
            start = time.perf_counter()
            test(root)
            elapsed = time.perf_counter() - start
            if args.profile:
                print(f"TIME {elapsed:0.3f}s {test.__name__}")
            timings.append((test.__name__, elapsed))
            print(f"PASS {test.__name__}")

    if args.profile:
        slowest = sorted(timings, key=lambda item: item[1], reverse=True)
        print("SLOWEST TESTS")
        for name, elapsed in slowest[:10]:
            print(f"  {elapsed:0.3f}s  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
