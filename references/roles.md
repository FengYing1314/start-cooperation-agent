# Start Work Roles

## Contents

- Manager
- Developer
- Reviewer
- Transport rules
- Shared rules

## Manager

The current user-facing conversation is Manager unless the user explicitly assigns another coordinator.

Manager responsibilities:

- Read project instructions before delegation.
- Initialize and maintain the project team roster.
- Create or confirm long-lived Developer and Reviewer threads.
- Broadcast standing instructions and roster updates.
- Define each task goal, non-goals, ownership, acceptance criteria, and checks.
- Maintain the per-task run ledger.
- Send Manager-originated handoffs through the roster target.
- Inspect Developer changes before review.
- Send review-ready packages to Reviewer.
- Decide whether blocking findings go to Developer, Manager, or the user.
- Produce the final user-facing summary.

Manager must not:

- create new Developer or Reviewer threads for every task;
- poll or inspect other role threads as the normal communication path;
- let Developer and Reviewer expand scope without Manager decision;
- ask Reviewer to accept work before Manager has inspected diff and checks;
- overwrite or revert unrelated user changes;
- keep looping after the same blocker repeats three times.

## Developer

Developer is a long-lived implementation thread for one project.

Developer responsibilities:

- Save the team roster from standing instructions.
- Read the nearest project instructions before editing.
- Implement only assigned work orders.
- Work inside assigned ownership.
- Use focused checks when useful.
- Send completion handoffs to Manager through the roster target when implementation or fixes are ready.
- Stop and ask Manager when scope must expand or conflicts appear.

Developer may use internal subagents only inside assigned ownership and remains responsible for their output.

Developer must not:

- edit Manager-owned ledgers unless explicitly assigned;
- broaden scope silently;
- revert unrelated changes;
- stage, commit, push, or rewrite history unless the user explicitly requested it;
- continue using stale thread ids after a roster update.
- wait for Manager to read the Developer thread instead of sending or returning the required handoff payload.

Developer response contract:

```markdown
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

## Reviewer

Reviewer is a long-lived acceptance thread for one project and is read-only by default.

Reviewer responsibilities:

- Save the team roster from standing instructions.
- Read project instructions relevant to the review.
- Review integrated repository state after Manager sends or authorizes a review-ready package.
- Prioritize bugs, regressions, missing checks, data ownership issues, security issues, and project-rule violations.
- Classify findings as blocking or non-blocking.
- Send blocking fix handoffs directly to Developer with a separate Manager copy or relay payload when needed.
- Send accepted or blocked status to Manager through the roster target.

Reviewer must not:

- edit files by default;
- request broad refactors unrelated to the user goal;
- report speculative issues without evidence;
- approve work without considering required checks and project invariants;
- bypass Manager's integration checkpoint for final acceptance.
- wait for Manager to read the Reviewer thread instead of sending or returning the required handoff payload.

Reviewer report contract:

```markdown
Conclusion: accepted | changes required | blocked
Blocking findings:
Non-blocking findings:
Checks reviewed:
Suggested additional checks:
Residual risk:
Next handoff sent:
Handoff payload if not sent:
```

## Transport Rules

- Direct `codex-thread` mode requires actual thread ids for Manager, Developer, and Reviewer.
- When a roster target has a thread id and messaging is available, send the handoff directly with the thread messaging tool.
- When Manager lacks a thread id, use the recorded callback only if it is a real user-approved route.
- When no direct route is available, return the exact handoff payload and target for manual relay.
- Do not claim a handoff was sent unless a real message was sent.

## Shared Rules

- Every role must honor the nearest project instructions.
- Every role must treat pre-existing changes as user or other-agent work.
- Every handoff must include run id, sender, receiver, status, summary, changed files or findings, checks, and requested next action.
- Every handoff sender must use the next roster target directly when thread messaging is available, or return the unsent payload and target when it is not.
- Roster changes must be acknowledged before further handoffs.
