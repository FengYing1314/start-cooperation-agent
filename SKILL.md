---
name: start-work
description: Coordinate reusable project-level multi-agent software development in Codex App with a long-lived manager/developer/reviewer team, shared thread-id roster, project-local team registry, per-task run ledgers, event-driven handoffs, Manager integration checkpoints, Reviewer acceptance, and repeated fix-review cycles. Use when the user asks to start work, initialize a multi-agent team, reuse developer and reviewer sessions, coordinate agent-to-agent development handoffs, or keep an auditable collaboration record.
---

# Start Work

Use this skill to run a reusable multi-agent development team for one project. The current conversation is the Manager by default. Developer and Reviewer are long-lived Codex threads recorded once in the project team roster, then reused across later tasks.

## Operating Contract

Follow the current collaboration mode and project instructions first. This skill coordinates work; it does not override repository `AGENTS.md`, user instructions, sandbox rules, review pipelines, or commit pipelines.

Do not store runtime state in project knowledge systems. Start-work runtime files belong under `.agent-work/start-work/`.

Use one project-level team roster and one per-task run ledger. Manager owns both ledgers. Developer and Reviewer do not edit ledgers directly.

Every team member must know the same roster: Manager, Developer, Reviewer thread ids or callbacks, roles, and handoff route. If a thread id changes, broadcast a roster update before more handoffs.

Prefer event-driven handoffs over Manager polling. After Manager defines the route and work order, each role sends the next handoff when its stage is complete. Manager reads other threads only at handoff checkpoints, on user request, or when a callback is missing.

## Required References

Read these before starting real work:

- `references/protocol.md` for team lifecycle, state machine, roster, ownership, and handoff rules.
- `references/roles.md` for Manager, Developer, and Reviewer responsibilities.
- `references/templates.md` when preparing standing instructions, work orders, roster updates, or handoffs.
- `references/codex-thread-mode.md` when creating or messaging long-lived Codex threads.

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

5. Send `team/standing-developer.md` to Developer and `team/standing-reviewer.md` to Reviewer.
6. Require both threads to reply with roster acknowledgement.
7. Record the acknowledgements before using the team for tasks:

```bash
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role D1
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role R1
```

If the Manager thread id is unavailable, record a usable Manager callback. If neither is available, do not enable direct agent-to-Manager handoffs.

## Start A Task

1. Initialize a run ledger, which automatically reuses the acknowledged team roster:

```bash
python3 <skill-dir>/scripts/init_run.py --repo <repo-root> --slug <work-slug> --request "<user request>"
```

2. Manager writes the work order with goal, non-goals, ownership, acceptance criteria, and checks.
3. Manager sends the work order to Developer.
4. Developer implements and sends a completion handoff to Manager.
5. Manager performs the integration checkpoint: inspect diff, run or record checks, then send the review-ready package to Reviewer.
6. Reviewer either accepts or sends blocking fix handoffs to Developer with Manager copied.
7. Developer fixes and hands back to Manager. Repeat until accepted, blocked, or stopped by the user.
8. Final response includes changes, checks, Reviewer result, risks, and the run ledger path.

## Mode Selection

Default to Codex thread mode. Use long-lived Developer and Reviewer threads per project.

Do not create new Developer or Reviewer threads for every task. Replace a thread only when the old thread is unavailable, contaminated, or no longer fits the project; then update and broadcast the roster.

Use subagent mode only when the user explicitly asks for subagents, the thread tools are unavailable and the user approves fallback, or the task is too small to justify the long-lived team. Record any fallback reason in the run ledger.

For tiny tasks, explain that start-work overhead is unnecessary and handle the task directly unless the user still wants the full workflow.
