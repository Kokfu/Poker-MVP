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
19. **Exact solver traversal.** Check whether reusing an unchanged player's reach calculations reduces CFR time. Keep it only if numerical checks, advice hashes, and timing support the change.
20. **Partial diagnostic intervals.** Add a read-only CLI view of committed sessions so an interrupted or still-running ledger can report bb/100 and uncertainty without rewriting its results.
21. **Practice proxy identity.** Verify that the LAN launcher gives the practice rate limiter a trustworthy client address. Keep changes confined to local deployment and add a configuration check.
22. **Release finished solver state.** Verify that a settled practice hand releases its per-hand solver matrices while keeping the opponent model for its next hand.
23. **Update privacy and practice architecture.** Bring the existing documentation in line with timed turns, the seat capability, saved practice hands, and the flagged multiway model.
24. **Quiet-machine Coach benchmark.** After the ordered agent workload finishes, repeat all 48 cold spots with warmup off and on under comparable load. Record both p95s and the advice check.

25. **Concurrent Coach startup.** Verify that startup warmup and the first request share an identical pending locked preflop solve. Preserve exact advice, allow distinct keys to work independently, and verify recovery after a solve fails.
26. **Representative cold benchmark.** Add a deterministic 48-spot workload with independent boards, multiple depths and action paths. Report latencies by street and preserve the existing benchmark and hash checks.
27. **Interrupted diagnostic visibility.** Have the read-only runner status identify stale progress without requiring an exit marker. Report missing sessions and the last write time, preserve accurate complete and failed states, and verify that status never mutates a ledger.

28. **Locked preflop misses.** Profile the slow representative preflop requests by chart depth and profile. Test a narrowly scoped startup or solver change if it can preserve all advice hashes and improve first-use timing.
29. **Exact runout batching.** Compare bounded batches of integer rank tallies with the existing per-runout loop. Keep it only if equity matrices match bit for bit and both the microbenchmarks and advice timings support it.
30. **Local HTTP cold latency.** Measure the representative workload through an isolated Uvicorn process on loopback. Check advice hashes and record how its latency compares with the in-process benchmark.

31. **Postflop request overlap.** Measure actual duplicate work for advice requests on the same board. If useful, share exact pending matrix or street work while keeping different keys independent and preserving failure recovery.
32. **Later-street replay cost.** Compare independent turns and rivers with the same decisions reached after prior street requests. Attribute latency to replay, equity, and new-street CFR using the representative fixtures.
33. **Numerical worker reproducibility.** Check the wider workload at fixed one and two workers and distinguish solver changes from worker-count differences. Document how to reproduce each advice comparison.

34. **Diagnostic summary validation.** A finished ledger with an empty or mismatched summary needs a distinct status. Validate the summary against run identity, ledger coverage, and integrity counts while keeping status read-only.
35. **Reproducible later-street profiling.** Preserve the alternating isolated-versus-sequential timing driver using the shared representative fixture and check it through the documented command.
36. **Broader exact rank coverage.** Cross-check board ranks against direct eval7 calls on a seeded distribution, and compare random square and rectangular matrices bit for bit with the previous board-ranking implementation.

37. **Parallel loopback advice.** Compare the 48 representative responses with the sequential reference while two clients submit different requests concurrently. Verify process cleanup and consistent exact advice.
38. **Benchmark error teardown.** Interrupt the isolated benchmark with an invalid request and verify that it closes its own Uvicorn process and releases its scratch database.
39. **Resumed change audit.** Review the exact cache, benchmark, and diagnostic status changes made during the resumed run. Fix reproducible errors and verify the final baseline for the 06:30 regression.

40. **Quick advice request ordering.** Verify that a quick response appears only for the current request, that a late preview cannot replace full advice, and that preview errors leave full advice available.
41. **River preview latency under load.** Time 48 independent river spots facing bets while their full requests run. Verify the legal recommendation and report p95 and maximum.
42. **Supervisor exception proof.** Exercise an isolated missing-worker launch and verify both logged exception and exit markers, retry handling, and the resulting read-only failure status.

43. **Durable worker checkpoint messages.** Log each committed session separately from the JSON summary. Verify messages occur only after persistence and resume reports only new sessions.
44. **Quick advice calibration.** Compare the approximate preview with exact uniform-river equity on the facing-bet fixture and with full solver actions. Record what the preview can tell the user.
45. **Full solve tail profile.** Isolate the remaining slow sequential turn and river requests by stage, and test one exact optimization only if the profile supports it.

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
