#!/usr/bin/env python3
"""Initialize a project-local start-work run ledger using an existing team roster."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

IGNORE_RULE = "/.agent-work/"


def run_git(repo: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def resolve_repo(path: str) -> tuple[Path, bool]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise SystemExit(f"Repository path does not exist: {candidate}")

    code, out, _ = run_git(candidate, "rev-parse", "--show-toplevel")
    if code == 0 and out:
        return Path(out).expanduser().resolve(), True
    return candidate, False


def slugify(value: str, fallback: str = "task") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:64].strip("-") or fallback


def read_request(args: argparse.Namespace) -> str:
    if args.request_file:
        return Path(args.request_file).expanduser().read_text(encoding="utf-8").strip()
    if args.request:
        return args.request.strip()
    return ""


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def ensure_local_exclude(repo: Path, is_git_repo: bool) -> str | None:
    if not is_git_repo:
        return None

    code, out, err = run_git(repo, "rev-parse", "--git-path", "info/exclude")
    if code != 0 or not out:
        raise SystemExit(f"Unable to locate git info/exclude: {err}")

    exclude_path = Path(out)
    if not exclude_path.is_absolute():
        exclude_path = (repo / exclude_path).resolve()

    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    text = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    lines = [line.strip() for line in text.splitlines()]
    if IGNORE_RULE not in lines:
        prefix = "" if text.endswith("\n") or not text else "\n"
        with exclude_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{prefix}{IGNORE_RULE}\n")

    return str(exclude_path)


def git_value(repo: Path, is_git_repo: bool, *args: str, fallback: str = "unknown") -> str:
    if not is_git_repo:
        return fallback
    code, out, _ = run_git(repo, *args)
    return out if code == 0 and out else fallback


def collect_git_info(repo: Path, is_git_repo: bool) -> dict[str, str]:
    info = {
        "branch": git_value(repo, is_git_repo, "branch", "--show-current"),
        "head": git_value(repo, is_git_repo, "rev-parse", "--short", "HEAD"),
        "status_short": "",
        "diff_stat": "",
    }

    if is_git_repo:
        _, status, _ = run_git(repo, "status", "--short")
        _, diff_stat, _ = run_git(repo, "diff", "--stat")
        info["status_short"] = status
        info["diff_stat"] = diff_stat

    return info


def write_start_snapshots(run_dir: Path, git_info: dict[str, str], overwrite: bool = False) -> bool:
    snapshots = run_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)

    status_path = snapshots / "git-status-start.txt"
    diff_stat_path = snapshots / "git-diff-stat-start.txt"
    if not overwrite and status_path.exists() and diff_stat_path.exists():
        return False

    status_path.write_text(
        (git_info["status_short"] or "<clean>") + "\n",
        encoding="utf-8",
    )
    diff_stat_path.write_text(
        (git_info["diff_stat"] or "<no unstaged diff stat>") + "\n",
        encoding="utf-8",
    )
    return True


def team_path_for(repo: Path) -> Path:
    return repo / ".agent-work" / "start-work" / "team" / "team.json"


def fallback_team(repo: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "team_id": f"fallback-{slugify(repo.name, fallback='team')}",
        "repo": str(repo),
        "project_docs": [],
        "roster": {
            "M": {"role": "Manager", "thread_id": "", "callback": "", "status": "fallback"},
            "D1": {"role": "Developer", "thread_id": "", "callback": "", "status": "fallback"},
            "R1": {"role": "Reviewer", "thread_id": "", "callback": "", "status": "fallback"},
        },
        "handoff_route": [],
        "manager_direct_handoff": False,
    }


def load_team(repo: Path, *, required: bool) -> tuple[dict[str, object] | None, Path]:
    team_path = team_path_for(repo)
    team = load_json(team_path)
    if team is None and required:
        raise SystemExit(
            f"Start-work team is not initialized: {team_path}. "
            "Run scripts/init_team.py and record Manager, Developer, and Reviewer targets first."
        )
    return team, team_path


def validate_team(team: dict[str, object], repo: Path, team_path: Path, mode: str) -> None:
    if str(team.get("repo", "")) != str(repo):
        raise SystemExit(f"Team repo does not match current repo in {team_path}")

    roster = team.get("roster")
    if not isinstance(roster, dict):
        raise SystemExit(f"team.json roster must be an object: {team_path}")

    missing: list[str] = []
    for local_id in ("M", "D1", "R1"):
        entry = roster.get(local_id)
        if not isinstance(entry, dict):
            missing.append(f"{local_id} roster entry")
            continue
        if local_id in {"D1", "R1"} and not entry.get("thread_id"):
            missing.append(f"{local_id}.thread_id")
        if local_id == "M" and not (entry.get("thread_id") or entry.get("callback")):
            missing.append("M.thread_id or M.callback")

    if missing:
        raise SystemExit(
            f"Start-work team roster is incomplete in {team_path}: {', '.join(missing)}. "
            "Update it with scripts/init_team.py before creating a run."
        )

    manager_entry = roster.get("M", {})
    manager_thread = str(manager_entry.get("thread_id", "")) if isinstance(manager_entry, dict) else ""
    if mode == "codex-thread" and not manager_thread:
        raise SystemExit(
            f"Start-work direct codex-thread mode requires M.thread_id in {team_path}. "
            "Callback-only Manager targets require manual relay and must not be used for direct role-to-role runs. "
            "Update the roster with scripts/init_team.py --manager-thread-id <manager-thread-id>."
        )

    acknowledgements = team.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        raise SystemExit(
            f"Start-work team acknowledgements are missing in {team_path}. "
            "Run scripts/ack_team.py for D1 and R1 after sending standing instructions."
        )

    pending: list[str] = []
    for local_id in ("D1", "R1"):
        entry = acknowledgements.get(local_id)
        if not isinstance(entry, dict) or entry.get("status") != "acknowledged":
            pending.append(local_id)
            continue
        roster_entry = roster.get(local_id, {})
        roster_thread = str(roster_entry.get("thread_id", "")) if isinstance(roster_entry, dict) else ""
        ack_thread = str(entry.get("thread_id", ""))
        if roster_thread and ack_thread != roster_thread:
            pending.append(f"{local_id} ack thread mismatch")

    if pending:
        raise SystemExit(
            f"Start-work team acknowledgements are incomplete in {team_path}: {', '.join(pending)}. "
            "Send standing instructions and record acknowledgements with scripts/ack_team.py before creating a run."
        )


def validate_fallback_team(team: dict[str, object], repo: Path, team_path: Path) -> None:
    team_repo = str(team.get("repo", ""))
    if team_repo and team_repo != str(repo):
        raise SystemExit(f"Team repo does not match current repo in {team_path}")
    if "roster" in team and not isinstance(team.get("roster"), dict):
        raise SystemExit(f"team.json roster must be an object: {team_path}")


def roster_row(team: dict[str, object], local_id: str) -> str:
    roster = team.get("roster", {})
    entry = roster.get(local_id, {}) if isinstance(roster, dict) else {}
    return (
        f"| {local_id} | {entry.get('role', '')} | {entry.get('thread_id', '')} | "
        f"{entry.get('callback', '')} | {entry.get('status', '')} |"
    )


def project_docs_markdown(team: dict[str, object]) -> str:
    docs = team.get("project_docs", [])
    if isinstance(docs, list) and docs:
        return "\n".join(f"- {doc}" for doc in docs if isinstance(doc, str))
    return "- Nearest AGENTS.md and project instructions"


def route_markdown(team: dict[str, object]) -> str:
    route = team.get("handoff_route", [])
    if not isinstance(route, list):
        return ""
    return "\n".join(
        f"| {item.get('from', '')} | {item.get('to', '')} | {item.get('trigger', '')} | "
        f"{item.get('manager_copy', '')} | {item.get('notes', '')} |"
        for item in route
        if isinstance(item, dict)
    )


def coordination_template(
    *,
    run_id: str,
    repo: Path,
    run_dir: Path,
    mode: str,
    created_at: str,
    request: str,
    git_info: dict[str, str],
    team: dict[str, object],
    team_path: Path,
    fallback_reason: str,
) -> str:
    return f"""# Start Work Coordination

Run ID: {run_id}
Project Path: {repo}
Ledger Directory: {run_dir}
Mode: {mode}
Status: init
Created At: {created_at}
Base Branch: {git_info["branch"]}
Base HEAD: {git_info["head"]}
Team ID: {team.get("team_id", "")}
Team Registry: {team_path}
Manager Direct Handoff: {team.get("manager_direct_handoff", False)}
Fallback Reason: {fallback_reason}

## User Request

{request or "_Not recorded. Manager should fill this before delegation._"}

## Required Project Reading

{project_docs_markdown(team)}

## Team Roster

| Local ID | Role | Thread ID | Callback | Status |
| --- | --- | --- | --- | --- |
{roster_row(team, "M")}
{roster_row(team, "D1")}
{roster_row(team, "R1")}

## Work Order

Goal:
Non-goals:
Constraints:
Acceptance Criteria:
Required Checks:

## Ownership Map

| Path or Module | Owner | Status | Notes |
| --- | --- | --- | --- |

## Handoff Route

| From | To | Trigger | Manager Copy | Notes |
| --- | --- | --- | --- | --- |
{route_markdown(team)}

## Message Log

| Msg ID | To | Thread/Agent ID | File | Purpose | Status |
| --- | --- | --- | --- | --- | --- |

## Iteration Log

| Iteration | Developer Result | Manager Check | Reviewer Result | Decision |
| --- | --- | --- | --- | --- |

## Validation

Commands Run:
Results:

## Open Risks

## Event Log

| Time | ID | Kind | Actor | To | Thread | Status | Summary | File |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def mark_team_used(team_path: Path, team: dict[str, object], timestamp: str) -> None:
    team["last_used_at"] = timestamp
    team_path.write_text(json.dumps(team, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or any path inside it.")
    parser.add_argument("--slug", default="", help="Short task slug for generated run ids.")
    parser.add_argument("--run-id", default="", help="Explicit run id. Existing runs are reused.")
    parser.add_argument("--request", default="", help="User request text to place in coordination.md.")
    parser.add_argument("--request-file", default="", help="File containing user request text.")
    parser.add_argument(
        "--mode",
        choices=["codex-thread", "subagent", "single-agent"],
        default="codex-thread",
        help="Collaboration mode to record in the ledger.",
    )
    parser.add_argument(
        "--fallback-reason",
        default="",
        help="Required when --mode is subagent or single-agent; records why codex-thread mode was not used.",
    )
    parser.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="Overwrite existing start git snapshots for this run.",
    )
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable result.")
    args = parser.parse_args()

    repo, is_git_repo = resolve_repo(args.repo)
    fallback_reason = args.fallback_reason.strip()
    if args.mode != "codex-thread" and not fallback_reason:
        raise SystemExit("--fallback-reason is required when --mode is subagent or single-agent.")
    team, team_path = load_team(repo, required=args.mode == "codex-thread")
    if team is None:
        team = fallback_team(repo)
    if args.mode == "codex-thread":
        validate_team(team, repo, team_path, args.mode)
    else:
        validate_fallback_team(team, repo, team_path)
    request = read_request(args)
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    run_id = args.run_id.strip()
    if not run_id:
        suffix = slugify(args.slug or request[:48])
        run_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{suffix}"
    run_id = slugify(run_id, fallback="run")

    run_dir = repo / ".agent-work" / "start-work" / "runs" / run_id
    for child in ("messages", "artifacts", "snapshots"):
        (run_dir / child).mkdir(parents=True, exist_ok=True)

    coordination = run_dir / "coordination.md"
    created = not coordination.exists()
    exclude_path = ensure_local_exclude(repo, is_git_repo)
    git_info = collect_git_info(repo, is_git_repo)
    snapshots_written = write_start_snapshots(
        run_dir,
        git_info,
        overwrite=created or args.refresh_snapshot,
    )

    if created:
        coordination.write_text(
            coordination_template(
                run_id=run_id,
                repo=repo,
                run_dir=run_dir,
                mode=args.mode,
                created_at=now.isoformat(),
                request=request,
                git_info=git_info,
                team=team,
                team_path=team_path,
                fallback_reason=fallback_reason,
            ),
            encoding="utf-8",
        )

    metadata = {
        "run_id": run_id,
        "repo": str(repo),
        "run_dir": str(run_dir),
        "mode": args.mode,
        "created_at": now.isoformat(),
        "coordination": str(coordination),
        "git_repo": is_git_repo,
        "git_exclude": exclude_path,
        "ignore_rule": IGNORE_RULE,
        "base_git": {
            "branch": git_info["branch"],
            "head": git_info["head"],
        },
        "team": {
            "team_id": team.get("team_id"),
            "team_json": str(team_path),
            "manager_direct_handoff": team.get("manager_direct_handoff", False),
            "roster": team.get("roster", {}),
        },
        "fallback_reason": fallback_reason,
    }
    metadata_path = run_dir / "run.json"
    stored_metadata = load_json(metadata_path)
    metadata_created = False
    if stored_metadata is None:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        metadata_created = True
        stored_metadata = metadata

    if team_path.exists():
        mark_team_used(team_path, team, now.isoformat())

    result = {
        **stored_metadata,
        "created": created,
        "metadata_created": metadata_created,
        "snapshots_written": snapshots_written,
        "snapshot_refreshed": bool(args.refresh_snapshot and snapshots_written and not created),
        "invoked_at": now.isoformat(),
    }

    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        action = "created" if created else "reused"
        print(f"Start-work run {action}: {run_dir}")
        print(f"Team: {team.get('team_id')} ({team_path})")
        if snapshots_written:
            print("Start git snapshots written.")
        elif not args.refresh_snapshot:
            print("Existing start git snapshots preserved.")
        if exclude_path:
            print(f"Local git exclude ensured: {exclude_path} contains {IGNORE_RULE}")
        else:
            print("No git repository found; local exclude was not updated.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
