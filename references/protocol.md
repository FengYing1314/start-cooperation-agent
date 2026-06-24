# Start Work Protocol

## Table Of Contents

- Core invariant
- Team lifecycle
- Run directory
- State machine
- Mode-specific transport
- Event-driven handoffs
- Message ids
- Ownership
- Dirty work and conflicts
- Completion and blockage

## Core Invariant

Start-work has two ledgers:

- Team ledger: one per project, stored in `.agent-work/start-work/team/`.
- Run ledger: one per task, stored in `.agent-work/start-work/runs/<run-id>/`.

Manager owns both ledgers. Developer and Reviewer do not edit them directly.

The team roster is the source of truth for thread ids and callbacks. Every role must know the same roster before handoffs begin.

## Team Lifecycle

Initialize the team once per project:

```text
Manager creates or confirms long-lived Developer and Reviewer threads.
Manager records Manager, Developer, and Reviewer targets in team.json.
Manager sends standing instructions directly to Developer and Reviewer.
Developer and Reviewer send roster acknowledgements back to Manager.
```

Use `scripts/init_team.py` for the team registry. The script is idempotent and writes:

```text
<repo>/.agent-work/start-work/team/
  team.json
  team.md
  standing-developer.md
  standing-reviewer.md
  roster-update.md    # only when an existing roster changes
```

Use `scripts/ack_team.py` after Developer and Reviewer reply to standing instructions. A task run must not start until both `D1` and `R1` acknowledgements are recorded.

Required roster entries:

- `M`: Manager thread id or callback.
- `D1`: long-lived Developer thread id.
- `R1`: long-lived Reviewer thread id.

Direct `codex-thread` mode requires `M.thread_id`. If Manager has no stable thread id, record a callback only for manual relay fallback. When neither thread id nor callback exists, agent-to-Manager handoff is disabled.

Do not create new Developer or Reviewer threads for each task. Replace a thread only when it is unavailable, contaminated, or intentionally retired. After replacement, run `init_team.py` again, broadcast `roster-update.md`, and record fresh acknowledgements before more handoffs.

## Run Directory

Each task gets a run ledger:

```text
<repo>/.agent-work/start-work/runs/<run-id>/
  coordination.md
  run.json
  events.jsonl
  messages/
  artifacts/
  snapshots/
```

Use `scripts/init_run.py` to create a run. In `codex-thread` mode it must read `team/team.json`; if the team is missing, incomplete, unacknowledged, or lacks `M.thread_id` for direct mode, it must fail with a clear instruction to initialize or acknowledge the team first.

In `subagent` or `single-agent` mode, `init_run.py` can create a run without an initialized team, but `--fallback-reason` is required and must explain why the long-lived thread team is not being used.

The default ignore rule is `/.agent-work/` in `.git/info/exclude`, not `.gitignore`.

## State Machine

Use these run statuses:

```text
init
manager_work_order
developer_running
developer_done
main_integration_check
reviewer_running
review_done
fix_required
developer_fix_running
main_fixing
accepted
blocked
final_delivery
```

Normal flow:

```text
init
-> manager_work_order
-> developer_running
-> developer_done
-> main_integration_check
-> reviewer_running
-> review_done
-> accepted
-> final_delivery
```

Fix flow:

```text
review_done
-> fix_required
-> developer_fix_running or main_fixing
-> main_integration_check
-> reviewer_running
```

Use `scripts/append_event.py --run-status <status>` to advance status and append the event together. Each event records both its event status and run status so the ledger can be replayed later. The script rejects transitions outside these flows unless `--allow-status-jump` is used for recovery or audit corrections.

The smoke test must exercise the full fix-review loop as an executable invariant, not only isolated transitions.

## Mode-Specific Transport

Use the transport that the run mode and roster actually support:

- `codex-thread`: require Manager, Developer, and Reviewer thread ids; send role-to-role handoffs with `send_message_to_thread`.
- `callback/manual relay`: use only when Manager has no thread id; return the exact payload and target unless the callback is a real user-approved messaging route.
- `subagent` or `single-agent`: keep the fallback reason in the ledger, return results to the current caller, and do not claim that a thread message was sent unless one really was.

Direct-send running statuses such as `developer_running`, `reviewer_running`, and `developer_fix_running` prove a real message was sent. Do not use them for unsent fallback payloads. `append_event.py` rejects those statuses in fallback runs unless the caller passes `--allow-fallback-direct-status` with a concrete `--thread-id`.

## Event-Driven Handoffs

Normal communication is sender-pushed, role-to-role messaging. The sender uses the roster target and the available thread messaging tool, such as `send_message_to_thread`, to deliver the next handoff. Do not make Manager inspect another role thread as the normal way to collect results. Callback-only Manager targets are manual relay fallback and are not valid for direct `codex-thread` runs.

Direct codex-thread route:

```text
Manager -> Developer: direct work order message
Developer -> Manager: direct implementation-ready message
Manager -> Reviewer: direct review-ready message after integration check
Reviewer -> Developer: direct blocking fix request, plus separate Manager copy
Reviewer -> Manager: direct accepted or blocked status
Developer -> Manager: direct fix-ready message
```

Manager does not repeatedly poll other threads. Use `read_thread` only:

- to recover a missed direct handoff;
- to audit a thread after a user request;
- when the user asks for status;
- when an expected callback is missing after an agreed wait.

Reviewer-to-Developer fix handoffs are allowed only for blocking findings inside the assigned scope and must copy Manager by sending Manager a separate status message. Scope expansion, architecture decisions, or accepted residual risk must go to Manager.

Direct send sequence:

```text
1. Compose the handoff payload from the matching template.
2. Record the outbound payload with append_event.py, or record the received handoff as soon as it arrives.
3. Send the same payload to the roster target with send_message_to_thread.
4. If sending succeeds, append the next running status: `developer_running`, `reviewer_running`, or `developer_fix_running`.
5. If sending fails, record a blocker event with the unsent target and payload location and do not advance the run status.
```

## Message Ids

Use local message ids even when the platform does not expose per-message ids:

```text
M-001       Manager note or decision
D1-001      Developer work order or handoff
R1-001      Reviewer review or fix handoff
```

Manager writes outbound prompts to `messages/<msg-id>-<slug>.md`. Developer and Reviewer do not edit the Manager-owned ledger; their direct messages must include local message id, sender, receiver, run id, status, summary, checks, and requested next action so Manager can record the received handoff.

`append_event.py` must reject duplicate ids rather than overwrite payload files.

## Ownership

Assign ownership before implementation starts:

- One file or module has one writer at a time.
- Manager does not edit Developer-owned files while Developer is running.
- Reviewer is read-only unless Manager explicitly assigns a fix role.
- If two agents need the same file, serialize the work and record the handoff.
- If the authorized write scope is insufficient, Developer stops and requests expansion.

## Dirty Work And Conflicts

At run start, snapshot:

- `git status --short`
- current branch
- current `HEAD`
- optional diff stat

Treat pre-existing changes as user or other-agent work. Do not revert them unless the user explicitly asks.

If another thread changes an owned file unexpectedly:

1. Stop edits to that file.
2. Record the conflict in the ledger.
3. Decide whether to merge manually, reassign ownership, or ask the user.

## Completion And Blockage

The run can complete when:

- no blocking Reviewer findings remain;
- Manager has inspected the final diff;
- required checks have passed or failures are explained;
- final response includes changes, checks, risks, and run ledger path.

Mark the run blocked when the same blocker repeats three cycles and Manager cannot make meaningful progress without user input or external state changes.
