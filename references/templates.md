# Start Work Templates

Use these templates as source shapes. Fill project-specific values before sending them to another thread.

## Team Roster

```markdown
# Start Work Team

Team ID: <team-id>
Project Path: <repo>
Manager Direct Handoff: <true-or-false>
Acknowledgements Complete: <true-or-false>

## Roster

| Local ID | Role | Thread ID | Callback | Status |
| --- | --- | --- | --- | --- |
| M | Manager | <manager-thread-id> | <manager-callback> | active |
| D1 | Developer | <developer-thread-id> |  | active |
| R1 | Reviewer | <reviewer-thread-id> |  | active |

## Project Reading

- <nearest-project-instructions>
- <relevant-project-docs>

## Default Handoff Route

| From | To | Trigger | Manager Copy |
| --- | --- | --- | --- |
| M | D1 | work order ready | n/a |
| D1 | M | implementation ready | n/a |
| M | R1 | review-ready package | n/a |
| R1 | D1 | blocking findings | yes |
| R1 | M | accepted or blocked | n/a |

## Acknowledgements

| Local ID | Ack Status | Thread ID | Acknowledged At | Notes |
| --- | --- | --- | --- | --- |
| D1 | pending | <developer-thread-id> |  |  |
| R1 | pending | <reviewer-thread-id> |  |  |
```

## Standing Developer Instruction

```markdown
You are Developer D1 for start-work team <team-id>.

Project path:
<repo>

Shared roster:
- M: Manager, thread_id=<manager-thread-id>, callback=<manager-callback>
- D1: Developer, thread_id=<developer-thread-id>
- R1: Reviewer, thread_id=<reviewer-thread-id>

Project reading:
- <nearest-project-instructions>
- <relevant-project-docs>

Default handoff route:
- M -> D1: work order ready
- D1 -> M: implementation ready
- M -> R1: review-ready package
- R1 -> D1 with Manager copied: blocking findings
- R1 -> M: accepted or blocked

Standing rules:
- Read project instructions before editing.
- Implement only assigned work orders.
- Stay inside assigned ownership.
- Send handoffs directly to the roster target thread; do not wait for Manager to read your thread.
- Do not edit Manager-owned ledger files unless explicitly assigned.
- Do not revert unrelated changes.
- Do not stage, commit, push, or rewrite history unless the user explicitly asks.
- If any thread id changes, wait for a roster update before sending handoffs.
- When implementation or fixes are ready, send a completion handoff directly to Manager.
- If direct thread messaging is unavailable, end with the exact handoff payload and target.

Reply exactly:
ACK roster saved for D1, team <team-id>.
```

## Standing Reviewer Instruction

```markdown
You are Reviewer R1 for start-work team <team-id>.

Project path:
<repo>

Shared roster:
- M: Manager, thread_id=<manager-thread-id>, callback=<manager-callback>
- D1: Developer, thread_id=<developer-thread-id>
- R1: Reviewer, thread_id=<reviewer-thread-id>

Project reading:
- <nearest-project-instructions>
- <relevant-project-docs>

Default handoff route:
- M -> D1: work order ready
- D1 -> M: implementation ready
- M -> R1: review-ready package
- R1 -> D1 with Manager copied: blocking findings
- R1 -> M: accepted or blocked

Standing rules:
- Read project instructions before reviewing.
- Stay read-only unless Manager explicitly changes your role.
- Review only after Manager sends or authorizes a review-ready package.
- Prioritize correctness, regressions, project-rule violations, missing checks, and scope drift.
- Send blocking fix handoffs directly to Developer and send a separate Manager copy.
- Send accepted or blocked status directly to Manager.
- Do not wait for Manager to read your thread as the normal handoff path.
- If any thread id changes, wait for a roster update before sending handoffs.
- If direct thread messaging is unavailable, end with the exact handoff payload and target.

Reply exactly:
ACK roster saved for R1, team <team-id>.
```

## Ack Record

```markdown
Start-work team ack
Team ID:
From:
Thread ID:
Ack:
Notes:
```

Record this ack with:

```bash
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role D1 --thread-id <developer-thread-id>
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role R1 --thread-id <reviewer-thread-id>
```

## Roster Update

```markdown
Start-work roster update
Team ID:
Reason:

Current roster:
- M: Manager, thread_id=<manager-thread-id>, callback=<manager-callback>
- D1: Developer, thread_id=<developer-thread-id>
- R1: Reviewer, thread_id=<reviewer-thread-id>

Use this roster for all future handoffs. Direct codex-thread tasks require an actual Manager thread id; callback-only Manager targets require manual relay. Acknowledge before continuing task work.
```

After sending a roster update, record fresh D1 and R1 acknowledgements with `scripts/ack_team.py` before creating or continuing task runs.

## Coordination Ledger

```markdown
# Start Work Coordination

Run ID:
Project Path:
Ledger Directory:
Mode: codex-thread
Status: init
Created At:
Base Branch:
Base HEAD:
Team ID:
Team Registry:
Manager Direct Handoff:

## User Request

## Required Project Reading

- <nearest-project-instructions>

## Team Roster

| Local ID | Role | Thread ID | Callback | Status |
| --- | --- | --- | --- | --- |
| M | Manager | <manager-thread-id> | <manager-callback> | active |
| D1 | Developer | <developer-thread-id> |  | active |
| R1 | Reviewer | <reviewer-thread-id> |  | active |

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
```

Update `Status:` through `scripts/append_event.py --run-status <status>` when recording state transitions.

## Manager Work Order

```markdown
Start-work work order <msg-id>
Run ID:
Team ID:
From: M
To: D1
Manager Thread:
Developer Thread:
Reviewer Thread:
Project Path:

Read first:
- <nearest-project-instructions>
- <relevant-project-docs>

User goal:

Non-goals:

Ownership:

Do not edit:

Acceptance criteria:

Required checks:

Current repository notes:
- Existing dirty work:
- Known constraints:

Rules:
- Stay inside assigned ownership.
- Do not revert unrelated changes.
- Do not stage, commit, push, or rewrite history unless explicitly requested.
- Stop and report if scope must expand.
- When ready, send a completion handoff directly to Manager using the roster target.
- Do not wait for Manager to inspect your thread as the normal delivery path.
- If thread messaging is unavailable, end with the exact handoff payload and target.

Developer response format:
Status: complete | blocked
Changed files:
Implementation summary:
Checks run:
Checks not run:
Risks or follow-ups:
Scope changes requested:
Next handoff sent:
Handoff payload if not sent:
```

## Developer Completion Handoff

```markdown
Start-work handoff <msg-id>
Run ID:
Team ID:
From: D1
To: M
Manager copy: n/a
Status: complete | blocked

Summary:

Changed files:

Checks:

Scope changes requested:

Blocking issues:

Requested next action:
Manager checkpoint and send to Reviewer if ready.
```

## Review Ready Package

```markdown
Start-work review request <msg-id>
Run ID:
Team ID:
From: M
To: R1
Developer Thread:
Reviewer Thread:
Project Path:

Read first:
- <nearest-project-instructions>
- <relevant-project-docs>

User goal:

Acceptance criteria:

Review scope:

Manager checkpoint:
- Status inspected:
- Diff inspected:
- Checks run:
- Checks not run:
- Integration notes:

Changed files:

Developer summary:

Reviewer rules:
- Stay read-only.
- Review integrated repository state.
- Report evidence-backed blocking issues first.
- If blocking fixes are required, send a fix handoff directly to D1 and send a separate Manager copy.
- If accepted or blocked, send the result directly to Manager.
- Do not wait for Manager to inspect your thread as the normal delivery path.
- Do not final-accept unless this Manager checkpoint is sufficient.

Reviewer report format:
Conclusion: accepted | changes required | blocked
Blocking findings:
Non-blocking findings:
Checks reviewed:
Suggested additional checks:
Residual risk:
Next handoff sent:
Handoff payload if not sent:
```

## Reviewer Fix Handoff

```markdown
Start-work fix handoff <msg-id>
Run ID:
Team ID:
From: R1
To: D1
Manager copy: M
Status: changes required

Blocking findings:

Allowed fix scope:

Do not change:

Checks or evidence:

Requested next action:
Fix only the blocking findings, then hand off to Manager for checkpoint.
```

## Developer Fix Completion

```markdown
Start-work fix completion <msg-id>
Run ID:
Team ID:
From: D1
To: M
Status: complete | blocked

Fixed findings:

Changed files:

Checks run:

Remaining risk:

Requested next action:
Manager checkpoint and send re-review if ready.
```

## Reviewer Accepted

```markdown
Start-work review result <msg-id>
Run ID:
Team ID:
From: R1
To: M
Status: accepted

Accepted scope:

Checks reviewed:

Non-blocking findings:

Residual risk:

Requested next action:
Manager final delivery.
```

## Manager Final Summary

```markdown
Implemented:
Validated:
Reviewer result:
Remaining risks:
Run ledger:
```
