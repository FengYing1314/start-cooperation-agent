# Start Work Trigger Eval Prompts

Use these prompts for forward-testing whether `start-work` triggers when it should and stays idle for adjacent work. Prepare an isolated fixture with `scripts/prepare_trigger_eval_workspace.py --output-dir <tmp-dir> --print-json`, generate a dry-run command plan with `scripts/plan_trigger_evals.py --print-json`, and score captured JSONL traces with `scripts/score_trigger_evals.py --print-json`. Keep this list small; add real misses as they appear.

| ID | Should trigger | Focus | Prompt |
| --- | --- | --- | --- |
| trig-01 | true | explicit | Use `$start-work` to initialize a reusable Manager, Developer, and Reviewer team for this repository. |
| trig-02 | true | implicit | Set up a long-lived multi-agent development workflow for this project with a developer, reviewer, shared roster, and auditable task ledgers. |
| trig-03 | true | contextual | We already have a start-work team; resume the latest run, inspect the ledger, and continue the developer/reviewer fix loop. |
| trig-04 | true | routing | Coordinate this feature through role-to-role messages so the reviewer sends blocking findings directly to the developer and copies the manager. |
| trig-05 | false | tiny-task | Fix this typo in the README directly. No multi-agent workflow needed. |
| trig-06 | false | skill-authoring | Create a new Codex skill for editing PDFs. |
| trig-07 | false | ordinary-review | Review my current diff and list bugs; do not spin up other agents. |
| trig-08 | false | one-off-subagent | Use a temporary subagent once to inspect the parser module and summarize risks. |

Expected behavior:

- `true`: the skill should load or be a strong candidate because the request asks for reusable project-level multi-agent coordination, roster-routed handoffs, start-work resume, or auditable ledgers.
- `false`: the skill should not be selected by default; handle directly or use a more specific skill unless the user explicitly asks for the full start-work workflow.
