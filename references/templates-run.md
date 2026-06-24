# Start Work Run Template Routing

This file is an index plus common run-message rules. Do not use it as a source payload for handoffs.

Load exactly the file needed for the next run action:

- `references/templates-work-order.md`: Manager sends a work order to Developer, or Developer reports implementation complete.
- `references/templates-review.md`: Manager requests review, Reviewer sends blocking fixes or acceptance, or Developer reports fixes complete.
- `references/templates-final.md`: Manager prepares the final user-facing summary.

Prefer generated ledgers and recorded messages:

- Use `scripts/init_run.py` for the coordination ledger shape.
- Use `scripts/append_event.py` for message and status records.
- In fallback mode, keep the fallback reason in the ledger, return results to the current caller, and do not claim that a thread message was sent.

## Direct Send Status Rule

For direct thread sends:

1. Write the outbound payload to a run `messages/` file.
2. Record it with `scripts/append_event.py --kind message --actor <sender> --to <target> --body-file <payload>`.
3. Call `send_message_to_thread` with the recipient thread id and the same payload.
4. Append `developer_running`, `reviewer_running`, or `developer_fix_running` only after the send succeeds.
5. If the send fails, record a blocker event and do not advance the run status.

In fallback mode, record work and results in the ledger, but skip direct-send running statuses unless a real message was sent.
