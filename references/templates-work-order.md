# Start Work Work-Order Templates

Use these for Manager-to-Developer work orders and Developer-to-Manager completion handoffs. These payloads assume direct `codex-thread` mode unless a section says otherwise. Prepare outbound work orders with `scripts/prepare_outbound_handoff.py`; validate received or manual-relay payloads with `scripts/validate_handoff.py` when practical.

## Contents

- Manager work order
- Developer completion handoff

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

Next handoff sent:
yes | no, plus target thread or unsent target.
```
