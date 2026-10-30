---
name: autopilot-step
description: Run one step of the poker-analyzer-mvp autopilot plan in a fresh chat, then write a report for the orchestrator. Use when a prompt says "autopilot step N".
---

# Autopilot step protocol

1. Read `autopilot/progress.md` (standing rules) and your `autopilot/prompts/step-N.md`. Do not read other steps.
2. `git checkout -b autopilot/step-N` from `main` (stop if the tree is dirty).
3. Do only what the prompt says. If a gate/threshold is involved, write it into a doc and commit it BEFORE producing data.
4. Run the backend tests (`cd backend; .venv\Scripts\python -m pytest -q`) and, if frontend changed, `npm run build` in `frontend`. Never claim a check you did not run.
5. Commit small, with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
6. Write `autopilot/reports/step-N.md`, max ~40 lines: what was done, commits, test results, numbers with intervals, what failed or was skipped, caveats, recommended next action. Commit it.
7. Do NOT merge, push, tag or delete branches. Stop. Your final message is the report's first 10 lines.

Environment notes: Windows; use Write/Edit for files (large Bash heredocs fail); run jobs over a few minutes detached via PowerShell `Start-Process`; free RAM is low, so use few workers.
