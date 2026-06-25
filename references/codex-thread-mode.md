# Codex Thread Mode

Use Codex thread mode when the project should keep an independent, reusable Manager/Developer/Reviewer collaboration history.

## Contents

- Tool discovery
- Non-destructive preflight
- Live drill gate
- Project selection
- Team initialization
- Roster rules
- Task messaging
- Event-driven route
- Manager checkpoint
- Replacement and archiving

## Tool Discovery

If thread tools are not visible, call `tool_search` for:

```text
Codex app thread create read send message title archive list projects
```

Expected capabilities include:

- `list_projects`
- `create_thread`
- `send_message_to_thread`
- `list_threads`
- `read_thread`
- `set_thread_title`
- `set_thread_archived`

Current Codex App thread tool shape:

- `list_projects()` returns project ids for repo-scoped background threads.
- `list_threads({query?, limit?})` is for exact lookup or audit, not normal handoff delivery.
- `create_thread({prompt, target})` creates a separate user-owned thread. For project work, pass `target={type:"project", projectId, environment:{type:"local"}}` or an explicit worktree environment. Omit `model` and `thinking` unless the user explicitly requests overrides.
- `send_message_to_thread({threadId, prompt})` sends a follow-up to an existing thread. Use the exact payload text as `prompt`; do not pass only a file path. Omit `model` and `thinking` unless the user explicitly requests overrides.

If no tool exposes the current Manager thread id, do not infer or guess it. Use a user-provided exact thread id, a verified exact match, or record a Manager callback for manual relay fallback.

If the tools remain unavailable, tell the user and ask before falling back to subagents.

Codex CLI is not a substitute for Codex App thread transport unless a future CLI command explicitly exposes the same thread messaging operation. Use CLI for trigger evals, local validation, or launching the app; do not use `codex exec`/`resume` as proof that a role-to-role Codex App thread message was sent.

## Non-Destructive Preflight

Use this path when the user asks to audit state, check readiness, review the call chain, or decide whether Codex App thread mode is possible. Preflight must not create threads, send messages, or inspect another role's conversation history as a substitute for direct handoffs.

Allowed preflight actions:

1. Confirm thread tools with `tool_search` if they are not already visible.
2. Call `list_projects` and identify the project whose path exactly matches the current repo.
3. Call `list_threads` only to locate already-named role threads or to verify an exact user-provided Manager thread id.
4. Run `scripts/inspect_project.py --repo <repo-root> --print-json` and prefer its `team`, `latest_runs`, `pending_outbound`, and `next_actions` fields.
5. Run `scripts/inspect_team.py --repo <repo-root> --print-json` when team readiness or route validity is the question.

Forbidden in preflight:

- do not call `create_thread` unless the user has asked to initialize, start, or replace a long-lived team thread;
- do not call `send_message_to_thread` until there is a prepared payload or standing instruction that should really be delivered;
- do not call `read_thread` unless this is recovery, audit on user request, or verification of an exact known thread.

End preflight with a readiness summary: project match, available thread tools, known or missing Manager/Developer/Reviewer targets, ledger readiness, pending outbound sends, and the next safe command.

## Live Drill Gate

Use `scripts/plan_codex_thread_drill.py --repo <repo-root> --print-json` when asked to prove the Codex App role-to-role loop but the user has not explicitly approved live thread creation or message sends.

The plan is intentionally non-destructive. It may include `tool_search`, `list_projects`, exact `list_threads`, `inspect_project.py`, and `inspect_team.py` as safe preflight steps. After `list_projects`, pass each relevant candidate back into the plan as `--codex-project "<projectId>=<path>"`; use `codex_project_match` as the evidence for whether the Codex App project target exactly matches the repo. The match normalizes common WSL UNC paths such as `\\wsl.localhost\<distro>\home\...` against native Linux paths such as `/home/...`. It must list `create_thread`, `send_message_to_thread`, and normal `read_thread` usage under `blocked_without_approval` until there is an explicit live-drill or team-initialization request.

Treat `ledger_ready_for_live_drill=true` as local roster/run readiness only. Treat `ready_for_live_drill=true` as local readiness plus exact Codex App project match, not consent. After approval, the drill should prove:

1. Manager sends an exact prepared work-order payload to D1.
2. D1 sends `developer_completion` directly to Manager.
3. Manager checks the integrated diff and sends an exact review request to R1.
4. R1 sends `reviewer_accepted` to Manager, or sends `reviewer_fix` directly to D1 with a separate Manager copy.
5. Manager records received payloads from direct messages and does not use Manager polling as the normal transport.

If the plan reports pending outbound sends or an unsent reviewer fix, resolve those first. A live drill must not create duplicate handoffs while the ledger already has an unfinished send.

If `codex_project_match.checked=true` and `matched=false`, stop before thread creation and add/open the correct Codex App project. Do not create long-lived D1/R1 threads under a different project target.

Before claiming the live drill passed, check the plan's `live_drill_success_criteria` and `completion_evidence_contract`. The completion evidence must include the matched project target, ready acknowledged roster, Manager outbound send finalization for work and review, inbound Developer/Reviewer handoff recording, and confirmation that Manager did not use polling as normal transport.

## Project Selection

Use `list_projects` before creating long-lived role threads. Select the project that matches the current repository root. If multiple candidates match, prefer the one with the exact path.

For WSL projects, use the native Linux path in prompts even if the Codex app target was selected through a Windows path.

## Team Initialization

The current user-facing conversation is Manager unless the user assigns another coordinator.

Create or confirm one long-lived Developer thread and one long-lived Reviewer thread per project only after the user has asked to initialize, start, reuse, or repair the team. If the user only asked for a status review, stop after preflight and structured ledger inspection. Do not create new Developer or Reviewer threads for each task.

Recommended titles:

```text
SW Team <team-id> D1 Developer
SW Team <team-id> R1 Reviewer
```

After creating or confirming threads:

1. Record Manager, Developer, and Reviewer targets with `scripts/init_team.py`.
2. Read `team/standing-developer.md` and send its exact contents directly to Developer with `send_message_to_thread`.
3. Read `team/standing-reviewer.md` and send its exact contents directly to Reviewer with `send_message_to_thread`.
4. Require both agents to send a direct acknowledgement back to Manager.
5. Record acknowledgements with `scripts/ack_team.py --role D1` and `scripts/ack_team.py --role R1`.

Direct `codex-thread` runs require a Manager thread id. If the Manager thread id cannot be obtained, record a Manager callback only for manual relay fallback; do not create a direct `codex-thread` run from a callback-only roster.

Do not use `list_threads` as a fuzzy way to choose the Manager thread. A listed thread may be stale or unrelated; use it only when the exact current Manager thread is known and verified.

When falling back because thread tools are unavailable or the task is too small for a long-lived team, create the ledger with `scripts/init_run.py --mode subagent --fallback-reason "<reason>"` or `--mode single-agent --fallback-reason "<reason>"`.

## Roster Rules

Every role must know the same roster:

- Manager `M`
- Developer `D1`
- Reviewer `R1`

The roster must include thread ids for Manager, Developer, and Reviewer before direct `codex-thread` runs. A callback-only Manager target is valid only for manual relay fallback.

If any role thread changes, update the team with `scripts/init_team.py`, send `team/roster-update.md` to all active role threads, and record fresh acknowledgements before continuing work.

## Task Messaging

For each task, Manager creates a new run ledger with `scripts/init_run.py`. The script imports the long-lived team roster from `team.json` and refuses to start if `D1` or `R1` has not acknowledged the current roster.

Normal transport is direct thread messaging, not Manager reading other agent threads. The sender must send the next handoff to the roster target with `send_message_to_thread`. If Manager must be copied, send a separate message to Manager. If the messaging tool is unavailable, the sender stops and returns the exact unsent payload and target.

Treat thread messages as the transport layer and the run ledger as the recovery layer. Important payloads must be persisted under the run `messages/` directory so a later Manager can resume without relying on another thread's visible history.

Manager outbound prompts should be prepared with `scripts/prepare_outbound_handoff.py`, sent with `send_message_to_thread`, then finalized with `scripts/finalize_outbound_handoff.py`. The current Codex App send tool takes `threadId` and `prompt`; read the prepared `payload_file` as UTF-8 and pass its exact contents as `prompt`. Do not pass only the file path. Developer and Reviewer must not edit Manager-owned ledgers; they include enough message metadata for Manager to record the received handoff with `scripts/record_inbound_handoff.py`.

Manager send sequence:

```text
1. Write the exact outbound payload from `references/templates-work-order.md` for Developer work or `references/templates-review.md` for Reviewer work.
2. Run `scripts/prepare_outbound_handoff.py --kind work_order` or `--kind review_request` with that payload.
3. If resuming and `inspect_run.py` reports `pending_outbound`, reuse that payload instead of preparing a duplicate.
4. Call `send_message_to_thread` with `threadId=<send_to_thread_id>` and `prompt=<exact contents of payload_file>`.
5. If the send succeeds, run the returned `finalize_sent_command`; include `--send-evidence` or `--send-evidence-file` when the thread tool returns a useful receipt or result.
6. If the send fails, run the returned `finalize_failed_command` with the concrete send error; do not advance to the next run status.
```

Reviewer fix handoffs are Reviewer-originated. Reviewer sends the fix payload directly to D1 and sends Manager a separate copy. Manager records that copy with `scripts/record_inbound_handoff.py --kind reviewer_fix`. If `Next handoff sent:` starts with `yes`, follow the returned status commands in order. If it starts with `no`, read `unsent_handoff.payload_file`, send its exact contents to D1 with `send_message_to_thread`, optionally replace `<send evidence>` in `unsent_handoff.after_send_evidence_command` with the tool receipt and run it, then run `unsent_handoff.after_send_status_commands` only after the real send succeeds. If that send fails, replace `<send error>` in `unsent_handoff.after_send_failed_command` with the concrete failure, run it, and do not advance the run status. Do not mark `fix_required` or `developer_fix_running` before the real send succeeds.

Message payloads must include:

- run id;
- sender and receiver;
- project path;
- required project reading;
- roster or referenced team id;
- ownership or review scope;
- expected next handoff;
- no-revert and no-history-rewrite rules;
- final response format.

## Event-Driven Route

Default route:

1. Manager sends work order directly to Developer.
2. Developer completes implementation and sends the completion handoff directly to Manager.
3. Manager performs diff and check checkpoint.
4. Manager sends the review-ready package directly to Reviewer.
5. Reviewer accepts or blocks directly to Manager, or sends a blocking fix handoff directly to Developer with a separate Manager copy.
6. Developer fixes and sends the fix completion directly to Manager.
7. Manager repeats checkpoint and review until accepted, blocked, or stopped.

Do not use Manager polling as the normal control loop. Manager reads other threads only to recover a missed direct handoff, audit on user request, or investigate a missing callback.

## Manager Checkpoint

Before Reviewer receives a review request, Manager must:

- inspect `git status --short`;
- inspect the relevant diff;
- run the smallest useful check or record why it was not run;
- update `coordination.md` with changed files and validation status.

Reviewer reviews the integrated repository state, not only Developer's summary.

## Replacement And Archiving

Replace a long-lived thread only when it is unavailable, contaminated, retired, or no longer fits the project. Record why the replacement happened.

Do not archive Developer or Reviewer threads automatically after a task. Archive only when the user asks or the project team is intentionally retired.
