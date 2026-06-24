# Start Work Run Templates

Use these when preparing per-task ledgers and handoffs. Prefer `scripts/init_run.py` for the coordination ledger shape and `scripts/append_event.py` for message/event recording.

These payloads assume direct `codex-thread` mode unless a section says otherwise. In `subagent` or `single-agent` fallback mode, keep the fallback reason in the ledger, return results to the current caller, and do not claim that a thread message was sent.

## Contents

- Coordination ledger
- Manager work order
- Developer completion handoff
- Review ready package
- Reviewer fix handoff
- Developer fix completion
- Reviewer accepted
- Manager final summary
- Direct send status rule

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
Fallback Reason:

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
- In direct codex-thread mode, send a completion handoff directly to Manager using the roster target.
- In fallback mode, return the completion payload to the caller and leave `Next handoff sent:` as `no`.
- Do not wait for Manager to inspect your thread as the normal direct-thread delivery path.
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

## Direct Send Status Rule

For direct thread sends:

1. Write the outbound payload to a run `messages/` file.
2. Record it with `scripts/append_event.py --kind message --actor <sender> --to <target> --body-file <payload>`.
3. Call `send_message_to_thread` with the recipient thread id and the same payload.
4. Append `developer_running`, `reviewer_running`, or `developer_fix_running` only after the send succeeds.
5. If the send fails, record a blocker event and do not advance the run status.

In fallback mode, record work and results in the ledger, but skip direct-send running statuses unless a real message was sent.
