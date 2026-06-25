---
name: start-work
description: Coordinate reusable project-level multi-agent software development in Codex App with a long-lived manager/developer/reviewer team, shared thread-id roster, roster-routed handoffs, direct role-to-role thread messaging when available, callback/manual relay fallback, project-local team registry, per-task run ledgers, Manager integration checkpoints, Reviewer acceptance, and repeated fix-review cycles. Use when the user asks to start work, initialize a multi-agent team, reuse developer and reviewer sessions, coordinate agent-to-agent development handoffs, or keep an auditable collaboration record.
---

# Start Work

Use this skill to run a reusable multi-agent development team for one project. The current conversation is the Manager by default. Developer and Reviewer are long-lived Codex threads recorded once in the project team roster, then reused across later tasks.

## Operating Contract

Follow the current collaboration mode and project instructions first. This skill coordinates work; it does not override repository `AGENTS.md`, user instructions, sandbox rules, review pipelines, or commit pipelines.

Do not store runtime state in project knowledge systems. Start-work runtime files belong under `.agent-work/start-work/`.

Use one project-level team roster and one per-task run ledger. Manager owns both ledgers. Developer and Reviewer do not edit ledgers directly.

Every team member must know the same roster: Manager, Developer, Reviewer thread ids or callbacks, roles, and handoff route. If a thread id changes, broadcast a roster update before more handoffs.

Use direct role-to-role handoffs over Manager polling. After Manager defines the route and work order, the current sender must push the next message to the target thread with the available thread messaging tool. Manager must not use `read_thread` as the normal communication path; read another thread only for recovery, audit, user-requested status, or when an expected direct callback is missing. Direct `codex-thread` mode requires a Manager thread id; callback-only Manager targets are manual relay fallback.

## Reference Routing

Load only the reference needed for the next action:

- `references/protocol.md` for team lifecycle, state machine, roster ownership, dirty work, ledger status, or handoff rules.
- `references/roles.md` for role-specific duties, review/fix contracts, and what each role must not do.
- `references/codex-thread-mode.md` for thread-tool discovery, project selection, thread creation, messaging, replacement, or fallback selection.
- `references/templates-team.md` for team roster, standing instructions, acknowledgements, or roster-update payloads.
- `references/templates-run.md` for selecting the right per-task template and applying direct-send status rules.
- `references/templates-work-order.md` for Manager work orders and Developer completion handoffs.
- `references/templates-review.md` for review requests, blocking fix handoffs, re-review, and acceptance payloads.
- `references/templates-final.md` for final user summaries.
- `references/trigger-eval-prompts.md` for forward-testing whether the skill triggers for start-work requests and stays idle for adjacent tasks.
- `references/templates.md` only when unsure which template file applies; it is an index and contains no payload bodies.

Prefer generated `team/*.md` and run ledger files over hand-writing payloads.

For a project-level resume or audit snapshot, inspect structured state first:

```bash
python3 <skill-dir>/scripts/inspect_project.py --repo <repo-root> --print-json
```

## Initialize Team Once

1. Read the nearest project `AGENTS.md` and project instructions.
2. Inspect enough repo context to identify project path, dirty work, and essential project docs.
3. Create or confirm long-lived Developer and Reviewer Codex threads.
4. Record the shared team roster:

```bash
python3 <skill-dir>/scripts/init_team.py --repo <repo-root> \
  --manager-thread-id <manager-thread-id-or-empty> \
  --manager-callback <manager-callback-if-needed> \
  --developer-thread-id <developer-thread-id> \
  --reviewer-thread-id <reviewer-thread-id> \
  --project-doc AGENTS.md
```

5. Send `team/standing-developer.md` directly to Developer and `team/standing-reviewer.md` directly to Reviewer.
6. Require both threads to send a roster acknowledgement back to Manager.
7. Record the acknowledgements before using the team for tasks:

```bash
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role D1
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role R1
```

8. Inspect readiness before starting or resuming task runs:

```bash
python3 <skill-dir>/scripts/inspect_team.py --repo <repo-root> --print-json
```

Direct `codex-thread` runs require `codex_thread_ready=true`. If the Manager thread id is unavailable, record a usable Manager callback only for manual relay fallback. If neither is available, do not enable agent-to-Manager handoffs.

## Start A Task

1. Initialize a run ledger, which automatically reuses the acknowledged team roster:

```bash
python3 <skill-dir>/scripts/init_run.py --repo <repo-root> --slug <work-slug> --request "<user request>"
```

This command fails in direct `codex-thread` mode when the roster has only a Manager callback. Update the team with `--manager-thread-id` before using direct thread handoffs.

2. To resume or audit an existing run, inspect the structured state first:

```bash
python3 <skill-dir>/scripts/inspect_run.py --run-dir <run-dir> --print-json
```

3. Manager writes the work order with goal, non-goals, ownership, acceptance criteria, and checks.
4. In direct `codex-thread` mode, Manager records the outbound work order in the run ledger, sends it directly to Developer with `send_message_to_thread`, then records `developer_running` after the send succeeds.
5. Developer implements and returns the completion handoff through the roster target: direct message to Manager in direct mode, or exact payload plus target for callback/manual relay or fallback mode.
6. Manager performs the integration checkpoint: inspect diff, run or record checks, then records and sends the review-ready package directly to Reviewer in direct mode, then records `reviewer_running` after the send succeeds.
7. Reviewer either accepts through the roster target, or sends blocking fix handoffs directly to Developer with a separate Manager copy or payload for relay when needed.
8. Developer fixes and returns the fix completion through the roster target. Repeat until accepted, blocked, or stopped by the user.
9. Final response includes changes, checks, Reviewer result, risks, and the run ledger path.

## Mode Selection

Default to Codex thread mode. Use long-lived Developer and Reviewer threads per project.

Do not create new Developer or Reviewer threads for every task. Replace a thread only when the old thread is unavailable, contaminated, or no longer fits the project; then update and broadcast the roster.

Use subagent or single-agent mode only when the user explicitly asks for it, thread tools are unavailable and the user approves fallback, or the task is too small to justify the long-lived team. Create those runs with `--mode subagent` or `--mode single-agent` and a required `--fallback-reason`; they can create a ledger without an initialized long-lived team. In fallback mode, record work and results in the ledger, return results to the current caller, and do not claim that a thread message was sent unless one really was.

For tiny tasks, explain that start-work overhead is unnecessary and handle the task directly unless the user still wants the full workflow.

## Validation

After editing scripts or handoff rules, run:

```bash
python3 scripts/validate_start_work.py
python3 <skill-creator-dir>/scripts/quick_validate.py <skill-dir>
```

`validate_start_work.py` compiles every local Python script, including `start_work_contract.py`, runs the smoke tests, and checks git whitespace/conflict markers when the skill is inside a git worktree.

These checks cover stable team ids, team readiness inspection, handoff route invariants, project status inspection, callback-only rejection for direct `codex-thread` mode, fallback run creation, fallback reason enforcement, direct run creation, structured run metadata, run inspection, send-state progression, full fix-review loop progression, event recording, trigger-eval prompt coverage and dry-run planning, contract/documentation drift, progressive reference routing, and skill metadata validity.
