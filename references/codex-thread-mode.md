# Codex Thread Mode

Use Codex thread mode when the project should keep an independent, reusable Manager/Developer/Reviewer collaboration history.

## Contents

- Tool discovery
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
- `read_thread`
- `set_thread_title`
- `set_thread_archived`

If the tools remain unavailable, tell the user and ask before falling back to subagents.

## Project Selection

Use `list_projects` before creating long-lived role threads. Select the project that matches the current repository root. If multiple candidates match, prefer the one with the exact path.

For WSL projects, use the native Linux path in prompts even if the Codex app target was selected through a Windows path.

## Team Initialization

The current user-facing conversation is Manager unless the user assigns another coordinator.

Create or confirm one long-lived Developer thread and one long-lived Reviewer thread per project. Do not create new Developer or Reviewer threads for each task.

Recommended titles:

```text
SW Team <team-id> D1 Developer
SW Team <team-id> R1 Reviewer
```

After creating or confirming threads:

1. Record Manager, Developer, and Reviewer targets with `scripts/init_team.py`.
2. Send `team/standing-developer.md` directly to Developer with `send_message_to_thread`.
3. Send `team/standing-reviewer.md` directly to Reviewer with `send_message_to_thread`.
4. Require both agents to send a direct acknowledgement back to Manager.
5. Record acknowledgements with `scripts/ack_team.py --role D1` and `scripts/ack_team.py --role R1`.

Direct `codex-thread` runs require a Manager thread id. If the Manager thread id cannot be obtained, record a Manager callback only for manual relay fallback; do not create a direct `codex-thread` run from a callback-only roster.

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

Manager outbound prompts should be saved in the run `messages/` directory and recorded in the ledger before or immediately after sending. Developer and Reviewer must not edit Manager-owned ledgers; they include enough message metadata for Manager to record the received handoff.

Manager send sequence:

```text
1. Write the exact outbound payload from `references/templates-work-order.md` for Developer work or `references/templates-review.md` for Reviewer work.
2. Record it with `scripts/append_event.py --kind message --actor M --to <role> --body-file <payload>`.
3. Call `send_message_to_thread` with the recipient thread id from `team.json` and the same payload.
4. If the send succeeds, record the next running status with `scripts/append_event.py --kind status --run-status developer_running` for Developer work, or `--run-status reviewer_running` for Reviewer work.
5. If the send fails, record a blocker event and do not advance to the next run status.
```

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
