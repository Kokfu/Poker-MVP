---
name: poker-regression
description: Standard regression check for poker-analyzer-mvp (the workflow AGENTS.md refers to). Use before calling any milestone, feature or fix done, and before committing changes to backend or frontend code.
---

# Regression workflow

Run the checks below, from smallest to largest. Report every result exactly as you saw it, and never claim a check you did not run.

1. **Run the focused tests first.** Pick the suites that cover the files you changed. From `backend`:
   `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_coach.py test_coach_learning.py`
   Coach files map to `test_coach*.py`. Bots and rules map to `test_simulation_*.py`. The solver maps to `test_research_*` and `solver/`.
2. **Run the full backend suite:** `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`.
   - It takes several minutes. If it runs longer than about 2 minutes, start it in the background.
   - Compare the pass count with the last count recorded in `autopilot/reports/`. A lower count needs an explanation.
   - `-p no:cacheprovider` avoids a cache-permission warning caused by OneDrive.
3. **Frontend** (only if `frontend/` changed), from `frontend`:
   - `npx.cmd tsc -b` for type errors;
   - `node --test test/coach-strategy.test.mjs`;
   - `npm.cmd run build` before a release or a commit that touches the build.
4. **If you changed a UI flow,** check it in the browser with the `coach-ui-test` skill.
5. **Check the invariants in AGENTS.md:**
   - legal actions only, with bet and raise amounts as totals;
   - chips are conserved;
   - no look-ahead;
   - runs are deterministic for a given seed;
   - research code stays separate from production bots;
   - stable schemas are unchanged.
6. **If a bot's strength could have changed,** don't call it better from these tests. Use the `strength-gate` skill.

When you report, give the command, the pass/fail counts, the time it took and any skipped suites. A milestone is COMPLETE only with evidence for its acceptance criteria. Otherwise, say what evidence is missing.
