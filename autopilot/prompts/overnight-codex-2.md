You are working overnight, unattended, in C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp. Nobody will answer until morning, so never stop to ask. When you need a decision, take the safe default, log it under "Decisions for the owner" and continue.

## How long to work: the most important rule
- **Work until 07:00 local time.** Finishing the backlog is not a reason to stop. Only the clock is.
- Before you write a final message or end your turn, run `Get-Date`. If it is before 06:30, you are not finished:
  - take the next backlog item;
  - if the backlog is empty, add three new items based on what you found tonight, then do them.
- Last night's run stopped after 46 minutes because every task was done at a tiny scale. Don't repeat that:
  - use the run sizes given below;
  - run long jobs in the background, and do other items while they run;
  - check on them every 10–15 minutes, using `Start-Sleep -Seconds 600` when there is nothing else to do.
- **06:30–07:00:** collect the results of background jobs, run the full regression, and update the summary.

## Setup
1. **Read these first:**
   - AGENTS.md;
   - `autopilot/overnight/progress.md` (last night's log);
   - AUTONOMOUS_AGENT.md;
   - the checklists `.claude/skills/{poker-regression,coach-ui-test,strength-gate}/SKILL.md`.
2. **Create the branch.** Branch `overnight/2026-11-26` from `overnight/2026-11-25` (last night's work isn't on `main`).
   - I authorize commits on that branch only.
   - Never push, merge, tag or touch `main`.
   - First commit: this prompt file, `autopilot/prompts/overnight-codex-2.md`.
3. **Set up the log.** Use `autopilot/overnight/progress-2026-11-26.md`.
   - At the top, keep a "Status" block of 5 lines. Rewrite it after every item: time, done so far, running jobs, next item.
   - Then add one entry per item: time, item, result (done, partial, failed or skipped), commits, test counts and timings, next step.
   - Commit the log after every item.

## Rules
- Make small commits, each with passing focused tests.
- Use `COACH_DB_PATH` with a %TEMP% copy. Never touch `backend/data/coach.sqlite`.
- Background jobs:
  - at most 2 running at once, 2 workers each (RAM is low);
  - output goes to `autopilot/overnight/jobs/<name>.log`;
  - write each job's start time and estimated end time in Status.
- Don't claim a bot is stronger without a strength-gate pre-registration committed before the run.
- If an item fails twice, log why and move to the next one.
- Out of scope:
  - reading the screen of, or clicking in, third-party poker sites or clients;
  - OCR;
  - real money;
  - poker-site integration.

## Backlog
Work in order. Start long jobs as early as possible and work on other items while they run.

1. **Full backend regression, in the background.** Last night's full run had 2 failures that were fixed but never re-run in full.
2. **Long agent run, in the background (about 3 hours).**
   - Use `simulation.agent_cli`: one run per opponent (`tight`, `equity`, `expert`, `range_expert`), each `--sessions 24 --session-hands 60`.
   - That is 2,880 hands per opponent, about 40 minutes each at last night's 0.86 s per hand. Run them one after another in one background script.
   - Use a fresh `--seed-offset` per run (grep the repo first; 27000 is used).
   - Use `--resume` if a run is interrupted.
   - Report bb/100 with intervals, and illegal actions, fallbacks and deal mismatches.
   - It is a diagnostic, not a strength claim.
3. **Coach latency on the first request (cold).** Targets: 95th-percentile latency over all requests, not just repeats, under 300 ms preflop and 600 ms postflop.
   - Profile the cold path: charts and locks loading, a new-board solve.
   - Warm the caches when the server starts, and precompute common spots in a background thread.
   - Show with a test that the advice is identical on at least 48 spots.
   - Update `coach-latency.md` with before and after numbers.
4. **Practice table: timed play.**
   - Add a per-action timer (setting, default 20 s; auto check or fold when it runs out), as in the owner's timed online practice.
   - Show the Coach's advice after each hand, not during it.
   - Browser-test it at phone and desktop width.
5. **Practice table to Coach.**
   - Save every finished table hand to the Coach database under the opponent's name, so profiles learn from practice.
   - Add a "Review last session" view that lists the hands where the human's action differed from the advice, with the estimated cost.
6. **Agent learning across sessions.**
   - Opponent profiles persist between `agent_cli` runs.
   - Report bb/100 by session index (early vs late sessions) to show whether learning happens.
   - Add tests for profile persistence and resume.
7. **Practice table robustness.**
   - Reconnect after a page refresh.
   - Two tables at once.
   - A seat label "BOT" that can't be hidden.
   - Input validation and rate limits on table endpoints (the table is reachable on the LAN).
   - Write `docs/practice-table-lan-checklist.md` with the steps the owner follows to test from a second device.
8. **Multiway advice model.**
   - Today multiway uses equity plus pot odds. Behind a flag that is off by default, narrow each opponent's range by their actions (reuse Range Intelligence).
   - Check it against the published AA-vs-N equity table and with consistency tests.
   - No strength claim.
9. **Multiway engine design.** Write `DESIGN_MULTIWAY_ENGINE.md`: what it would take to run 3–6 seat games for the practice table and the agent without changing the accepted heads-up `HandEngine`. Design only.
10. **Review all code from both nights for bugs.** Fix real problems, each with a test.
11. **Docs.** README sections for the practice table, `agent_cli` and the timer, with exact commands.
12. **If time is left,** add three new items to the end of this list, based on tonight's findings, and continue.
13. **Exact solver performance.** Measure and reduce allocation overhead in the lock fitter and new-board path, require bit-for-bit numeric checks, and compare the 48 distinct Coach spots against the warmed control.
14. **Concurrent practice settlement.** Exercise simultaneous clients, including a stale action at timer expiry, database persistence, and independent progress at the other table. Fix any reproducible consistency issue with a regression.
15. **Diagnostic progress and recovery.** Turn the four-opponent commands into a reproducible PowerShell runner and report completed ledger coverage, integrity counters, throughput, and ETA without mutating an open run.
16. **Profile the postflop tail.** Reproduce the slowest fresh-board requests and measure how much time goes to equity, range CFR, and explanation. Remove any redundant calculation that can be verified against the 48 advice hashes.
17. **Coach requests that finish out of order.** Prevent obsolete advice or history from appearing after edits or deletes. Exercise the affected entry paths in the browser.
18. **Implementation preflight.** Run the full regression on the upgraded branch, investigate any failures, and retain the evidence before the separate morning check.

## At 06:30
- Collect the background job results.
- Run the full backend suite, `npx.cmd tsc -b`, `node --test test/coach-strategy.test.mjs` and `npm.cmd run build`.
- Rewrite Status as a morning summary:
  - what's done, with numbers;
  - what failed;
  - decisions for the owner;
  - exact commands to try;
  - the branch;
  - the time you stopped.
- Commit.
