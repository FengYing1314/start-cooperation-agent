# Codex Thread Mode

Use Codex thread mode when the project should keep an independent, reusable Manager/Developer/Reviewer collaboration history.

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
2. Send `team/standing-developer.md` to Developer.
3. Send `team/standing-reviewer.md` to Reviewer.
4. Require both agents to acknowledge the roster.
5. Record acknowledgements with `scripts/ack_team.py --role D1` and `scripts/ack_team.py --role R1`.

If the Manager thread id cannot be obtained, record a Manager callback. If neither a Manager thread id nor callback is available, direct agent-to-Manager handoff is disabled and Manager must relay messages.

## Roster Rules

Every role must know the same roster:

- Manager `M`
- Developer `D1`
- Reviewer `R1`

The roster must include thread ids for Developer and Reviewer. Manager must have either a thread id or a callback that agents can use to report back.

If any role thread changes, update the team with `scripts/init_team.py`, send `team/roster-update.md` to all active role threads, and record fresh acknowledgements before continuing work.

## Task Messaging

For each task, Manager creates a new run ledger with `scripts/init_run.py`. The script imports the long-lived team roster from `team.json` and refuses to start if `D1` or `R1` has not acknowledged the current roster.

Every outbound prompt should be saved in the run `messages/` directory and recorded in the ledger before or immediately after sending. Large command output belongs in `artifacts/` only when needed.

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

1. Manager sends work order to Developer.
2. Developer completes implementation and hands off to Manager.
3. Manager performs diff and check checkpoint.
4. Manager sends review-ready package to Reviewer.
5. Reviewer accepts, blocks, or sends blocking fix handoff to Developer with Manager copied.
6. Developer fixes and hands off to Manager.
7. Manager repeats checkpoint and review until accepted, blocked, or stopped.

Do not use continuous Manager polling as the normal control loop. Manager reads other threads at handoff checkpoints, when a callback is missing, or when the user asks for status.

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
