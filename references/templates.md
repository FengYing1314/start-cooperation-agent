# Start Work Template Routing

This file is an index. Do not use it as a source payload for messages.

Load exactly the template file needed for the next action:

- `references/templates-team.md`: team roster, standing Developer/Reviewer instructions, acknowledgements, and roster updates.
- `references/templates-run.md`: choose the right run template and apply direct-send status rules.
- `references/templates-work-order.md`: Manager work orders and Developer completion handoffs.
- `references/templates-review.md`: review requests, blocking fix handoffs, fix completions, and acceptance payloads.
- `references/templates-final.md`: Manager final user summaries.

Runtime rules:

- Prefer generated files from `scripts/init_team.py` and `scripts/init_run.py` over hand-copying templates.
- Generated standing instructions already encode whether Manager has a real `thread_id` or only a callback/manual relay route.
- Do not replace generated callback-mode standing instructions with direct-only text.
- For direct sends, record the outbound payload, call `send_message_to_thread` with `prompt` set to the exact payload text, then append the next running status only after the send succeeds.
- If messaging is unavailable, stop and return the exact unsent payload and target instead of pretending the handoff happened.
