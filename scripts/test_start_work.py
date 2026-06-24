#!/usr/bin/env python3
"""Self-contained smoke tests for start-work scripts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INIT_TEAM = SCRIPT_DIR / "init_team.py"
ACK_TEAM = SCRIPT_DIR / "ack_team.py"
INIT_RUN = SCRIPT_DIR / "init_run.py"
APPEND_EVENT = SCRIPT_DIR / "append_event.py"
SKILL_ROOT = SCRIPT_DIR.parent


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
    assert "quick_validate.py" in skill, skill
    assert not (SKILL_ROOT / "README.md").exists(), "README.md should not be in the skill package"
    assert "callback/manual relay fallback" in skill, skill
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

    roles = (SKILL_ROOT / "references" / "roles.md").read_text(encoding="utf-8")
    assert "## Transport Rules" in roles, roles
    assert "through the roster target" in roles, roles
    assert "Do not claim a handoff was sent unless a real message was sent" in roles, roles

    protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(encoding="utf-8")
    assert "## Mode-Specific Transport" in protocol, protocol
    assert "Direct codex-thread route" in protocol, protocol
    assert "do not claim that a thread message was sent unless one really was" in protocol, protocol
    assert "--allow-fallback-direct-status" in protocol, protocol
    assert "--allow-status-jump" in protocol, protocol
    assert "records both its event status and run status" in protocol, protocol
    assert "full fix-review loop as an executable invariant" in protocol, protocol

    openai_yaml = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "roster-routed" in openai_yaml, openai_yaml
    assert "callback/manual relay fallback" in openai_yaml, openai_yaml
    assert "direct-message development team" not in openai_yaml, openai_yaml


def main() -> int:
    tests = [
        test_team_id_is_stable,
        test_callback_only_rejected_for_direct_thread_mode,
        test_direct_thread_happy_path,
        test_full_fix_review_cycle_status_path,
        test_subagent_fallback_without_team,
        test_fallback_mode_requires_reason,
        test_reference_routing_is_progressive,
    ]
    with tempfile.TemporaryDirectory(prefix="start-work-tests-") as temp:
        root = Path(temp)
        for test in tests:
            test(root)
            print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
