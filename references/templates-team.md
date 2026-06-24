# Start Work Team Templates

Use these only when generating files manually or repairing generated output. Prefer `scripts/init_team.py`, which writes `team/team.md`, `team/standing-developer.md`, `team/standing-reviewer.md`, and `team/roster-update.md`.

## Contents

- Team roster
- Standing instruction rules
- Direct Manager route
- Callback/manual relay route
- Ack record
- Roster update

## Team Roster

```markdown
# Start Work Team

Team ID: <team-id>
Project Path: <repo>
Created At: <iso-time>
Updated At: <iso-time>
Manager Direct Handoff: <true-or-false>
Roster Complete: <true-or-false>
Acknowledgements Complete: <true-or-false>

## Roster

| Local ID | Role | Thread ID | Callback | Status |
| --- | --- | --- | --- | --- |
| M | Manager | <manager-thread-id-or-empty> | <manager-callback-or-empty> | active |
| D1 | Developer | <developer-thread-id> |  | active |
| R1 | Reviewer | <reviewer-thread-id> |  | active |

## Project Reading

- <nearest-project-instructions>
- <relevant-project-docs>

## Handoff Route

| From | To | Trigger | Manager Copy | Notes |
| --- | --- | --- | --- | --- |
| M | D1 | work order ready | n/a | Manager sends the work order directly to Developer. |
| D1 | <M-or-manual-relay> | implementation ready | n/a | Developer sends completion for Manager integration check. |
| M | R1 | review-ready package | n/a | Manager sends the review package directly to Reviewer. |
| R1 | D1 | blocking findings | yes | Reviewer sends fix request directly to Developer and sends Manager a separate copy. |
| R1 | <M-or-manual-relay> | accepted or blocked | n/a | Reviewer sends the result for Manager final delivery. |

## Acknowledgements

| Local ID | Ack Status | Thread ID | Acknowledged At | Notes |
| --- | --- | --- | --- | --- |
| D1 | pending | <developer-thread-id> |  |  |
| R1 | pending | <reviewer-thread-id> |  |  |
```

## Standing Instruction Rules

Every standing instruction must include:

- target identity: `D1 (Developer)` or `R1 (Reviewer)`;
- project path and required project reading;
- shared roster with Manager, Developer, and Reviewer targets;
- default handoff route;
- no-revert, no-history-rewrite, no-ledger-edit rules;
- exact acknowledgement line: `ACK roster saved for <D1-or-R1>, team <team-id>.`

Use the direct route only when `Manager Direct Handoff: true` and `M.thread_id` is present. Use callback/manual relay wording when Manager lacks a thread id.

## Direct Manager Route

Use this fragment when `M.thread_id` is present:

```markdown
Transport rules:
- Send handoffs directly to the roster target thread with the available thread messaging tool.
- If thread messaging tools are not visible, call tool_search for Codex app thread send message tools.
- Do not wait for Manager to read your thread as the normal communication path.
- If direct thread messaging is unavailable, end with the exact handoff payload and target.
```

Developer role fragment:

```markdown
- Implement only assigned work orders.
- Stay inside assigned ownership.
- Send completion handoffs directly to Manager after implementation or fixes are ready.
- If Reviewer sends blocking findings, fix only those findings unless Manager expands scope.
```

Reviewer role fragment:

```markdown
- Review integrated repository state only after Manager sends or authorizes a review-ready package.
- Stay read-only unless Manager explicitly changes your role.
- Send blocking fix handoffs directly to Developer and send Manager a separate status copy.
- Send accepted or blocked status directly to Manager.
```

## Callback Or Manual Relay Route

Use this fragment when Manager has no `thread_id`:

```markdown
Transport rules:
- Manager has no thread_id in this roster; this team cannot run direct codex-thread tasks until Manager supplies one.
- For handoffs to Manager, use the recorded callback only if it is an actual user-approved messaging route.
- If the callback is not directly callable, end with the exact handoff payload and target for manual relay.
- Do not wait for Manager to read your thread as the normal communication path.
```

Developer role fragment:

```markdown
- Implement only assigned work orders.
- Stay inside assigned ownership.
- Prepare completion handoffs for Manager through the recorded callback or manual relay.
- If Reviewer sends blocking findings, fix only those findings unless Manager expands scope.
```

Reviewer role fragment:

```markdown
- Review integrated repository state only after Manager sends or authorizes a review-ready package.
- Stay read-only unless Manager explicitly changes your role.
- Send blocking fix handoffs directly to Developer and prepare the Manager copy through callback or manual relay.
- Prepare accepted or blocked status for Manager through the recorded callback or manual relay.
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

Record acknowledgements with:

```bash
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role D1 --thread-id <developer-thread-id>
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role R1 --thread-id <reviewer-thread-id>
```

## Roster Update

```markdown
Start-work roster update for team <team-id>.

Changes:
- <change>

Current roster:
- M: Manager thread_id=<manager-thread-id-or-none> callback=<manager-callback-or-none>
- D1: Developer thread_id=<developer-thread-id> callback=<none>
- R1: Reviewer thread_id=<reviewer-thread-id> callback=<none>

Use this roster for all future handoffs. Acknowledge after updating your local context.
```

After sending a roster update, record fresh D1 and R1 acknowledgements before creating or continuing task runs.
