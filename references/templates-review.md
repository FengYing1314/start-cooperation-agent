# Start Work Review Templates

Use these for Manager review requests, Reviewer decisions, and Developer fix-completion handoffs. These payloads assume direct `codex-thread` mode unless a section says otherwise. Prepare Manager-originated review requests with `scripts/prepare_outbound_handoff.py`; record received Developer completions, Reviewer fix copies, and Reviewer decisions with `scripts/record_inbound_handoff.py` when practical.

## Contents

- Review ready package
- Reviewer fix handoff
- Developer fix completion
- Reviewer accepted

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

Evidence references:

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
Evidence references:
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

Evidence references:

Requested next action:
Fix only the blocking findings, then hand off to Manager for checkpoint.

Next handoff sent:
yes | no, plus target thread or unsent target.
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

Evidence references:

Remaining risk:

Requested next action:
Manager checkpoint and send re-review if ready.

Next handoff sent:
yes | no, plus target thread or unsent target.
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

Evidence references:

Non-blocking findings:

Residual risk:

Requested next action:
Manager final delivery.

Next handoff sent:
yes | no, plus target thread or unsent target.
```
