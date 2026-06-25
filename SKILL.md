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
- `references/codex-thread-mode.md` for thread-tool discovery, non-destructive Codex App preflight, project selection, thread creation, messaging, replacement, or fallback selection.
- `references/templates-team.md` for team roster, standing instructions, acknowledgements, or roster-update payloads.
- `references/templates-run.md` for selecting the right per-task template and applying direct-send status rules.
- `references/templates-work-order.md` for Manager work orders and Developer completion handoffs.
- `references/templates-review.md` for review requests, blocking fix handoffs, re-review, and acceptance payloads.
- `references/templates-final.md` for final user summaries.
- `references/trigger-eval-prompts.md` for forward-testing whether the skill triggers for start-work requests and stays idle for adjacent tasks.
- `references/templates.md` only when unsure which template file applies; it is an index and contains no payload bodies.

Prefer generated `team/*.md` and run ledger files over hand-writing payloads.

Keep handoff messages short. Put bulky logs, diffs, traces, screenshots, or reports in run `artifacts/` and list their paths, commands, or event ids under `Evidence references:`.

When a script returns `next_commands` or `next_actions`, follow those structured hints instead of reconstructing equivalent commands from prose.

If `inspect_run.py` or `inspect_project.py` returns `pending_outbound`, finish that exact send first: read `pending_outbound.payload_file`, call `send_message_to_thread` with `threadId=pending_outbound.send_to_thread_id` and `prompt=<exact file contents>`, then run the returned finalize command for success or failure. Include `--send-evidence` or `--send-evidence-file` with the sent finalize command when the tool returns a useful receipt. Do not send only the file path as the prompt, and do not compose a replacement payload unless the pending send is explicitly failed or obsolete.

Before Manager sends an outbound work order or review request, use the prepare/finalize helpers:

```bash
python3 <skill-dir>/scripts/prepare_outbound_handoff.py --run-dir <run-dir> --kind <outbound-kind> --body-file <payload.md> --print-json
python3 <skill-dir>/scripts/finalize_outbound_handoff.py --run-dir <run-dir> --kind <outbound-kind> --event-id <event-id> --result sent --print-json
```

Outbound kinds: `work_order`, `review_request`. Reviewer fix handoffs are Reviewer-originated; Manager records the separate copy with inbound kind `reviewer_fix`.

After receiving a direct Codex App thread handoff from Developer or Reviewer, record the exact payload:

```bash
python3 <skill-dir>/scripts/record_inbound_handoff.py --run-dir <run-dir> --kind <inbound-kind> --body-file <payload.md> --print-json
```

Inbound kinds: `developer_completion`, `developer_fix_completion`, `reviewer_fix`, `reviewer_accepted`. `reviewer_fix` records the Manager copy of an R1 -> D1 blocking fix handoff. If `Next handoff sent:` starts with `yes`, follow its returned commands in order. If it starts with `no`, read the returned `unsent_handoff.payload_file`, send its exact contents to D1 with `send_message_to_thread`, optionally run `unsent_handoff.after_send_evidence_command` when the tool returns a useful receipt, then run `unsent_handoff.after_send_status_commands` only after the real send succeeds. If the send fails, run `unsent_handoff.after_send_failed_command` with a concrete send error and do not advance the run status.

For other received or manually relayed handoffs, validate the exact payload when practical:

```bash
python3 <skill-dir>/scripts/validate_handoff.py --kind <handoff-kind> --body-file <payload.md> --print-json
```

Kinds: `work_order`, `developer_completion`, `review_request`, `reviewer_fix`, `developer_fix_completion`, `reviewer_accepted`.

For a project-level resume or audit snapshot, inspect structured state first:

```bash
python3 <skill-dir>/scripts/inspect_project.py --repo <repo-root> --print-json
```

For a Codex App live-message drill plan that must not create threads or send messages yet, run:

```bash
python3 <skill-dir>/scripts/plan_codex_thread_drill.py --repo <repo-root> --print-json
```

After `list_projects`, rerun it with repeated `--codex-project "<projectId>=<path>"` entries so the plan can prove whether the Codex App project target exactly matches the repo.

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
4. In direct `codex-thread` mode, Manager prepares the outbound work order with `prepare_outbound_handoff.py`, reads the returned payload file, sends its exact contents directly to Developer with `send_message_to_thread`, then runs the returned `finalize_sent_command` after the send succeeds or `finalize_failed_command` after send failure.
5. Developer implements and returns the completion handoff through the roster target: direct message to Manager in direct mode, or exact payload plus target for callback/manual relay or fallback mode. Manager records the received payload with `record_inbound_handoff.py`.
6. Manager performs the integration checkpoint: inspect diff, run or record checks, then prepares the review-ready package with `prepare_outbound_handoff.py`, sends the returned payload file directly to Reviewer in direct mode, then runs the returned finalize command for success or failure.
7. Reviewer either accepts through the roster target, or sends blocking fix handoffs directly to Developer with a separate Manager copy or payload for relay when needed.
8. Developer fixes and returns the fix completion through the roster target. Manager records received completion or acceptance payloads with `record_inbound_handoff.py`. Repeat until accepted, blocked, or stopped by the user.
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

For trigger behavior forward-tests, load `references/trigger-eval-prompts.md`, prepare an isolated fixture, run `scripts/check_trigger_eval_cli.py` or the returned `cli_check`, execute the generated plan with `scripts/run_trigger_eval_plan.py`, then score the artifacts.

`validate_start_work.py` compiles every local Python script, including `start_work_contract.py`, runs the smoke tests, and checks git whitespace/conflict markers when the skill is inside a git worktree.

These checks cover stable team ids, team next-step hints, team readiness inspection, Codex App live-drill planning, handoff route invariants, handoff payload validation, outbound handoff send preparation and finalization, inbound handoff recording, project status inspection, project/run resume next-step hints, reviewer fix send-state project resume, callback-only rejection for direct `codex-thread` mode, fallback run creation, fallback reason enforcement, direct run creation, run next-step hints, structured run metadata, run inspection, send-state progression, full fix-review loop progression, event recording, trigger-eval prompt coverage, CLI launch checks, fixture preparation and artifact cleanup, trigger-eval step hints, dry-run planning, plan execution, UTF-8-safe runner failure artifacts, trace scoring, contract/documentation drift, progressive reference routing, and skill metadata validity.
