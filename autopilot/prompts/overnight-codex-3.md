You are working overnight, unattended, in C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp. Nobody will answer until morning, so never stop to ask. When you need a decision, take the safe default, log it under "Decisions for the owner" and continue.

## Rule 1: the clock decides when you stop
- **Work until 07:00 MYT on November 27.** Finishing the backlog is not a reason to stop. Check `Get-Date` before you end a turn. Before 06:30, you are not finished.
- **Never wait idle for a scheduled step.** Last time the run sat idle from 21:47 to 06:30. Only the final regression waits for 06:30. Everything else starts as soon as the item before it is done.
- **Waiting:** sleep in steps of at most 10 minutes (`Start-Sleep -Seconds 600`), and only while a background job is running and no backlog item can be worked on.
- **If the backlog runs out,** add three items based on tonight's findings and do them.

## Setup
1. **Read these first:**
   - AGENTS.md;
   - the checklists `.claude/skills/{poker-regression,coach-ui-test,strength-gate}/SKILL.md`;
   - `autopilot/overnight/progress-2026-11-26.md` (only the Status block and the "Decisions for the owner" section);
   - `autopilot/overnight/coach-latency.md`.
2. **Create the branch.** `git status` must be clean on `main`, apart from this untracked prompt file. Create the branch `overnight/2026-11-27` from `main`.
   - I authorize commits on that branch only.
   - Never push, merge, tag or touch `main`, and don't delete any branch.
   - First commit: this prompt file.
3. **Set up the log.** Use `autopilot/overnight/progress-2026-11-27.md`.
   - At the top, keep a "Status" block of 5 lines. Rewrite it after every item: time, done so far, running jobs, next item.
   - Then add one entry per item: time, item, result (done, partial, failed or skipped), commits, test counts and timings, next step.
   - Commit after every item.
   - Also keep a "Handoff" block of 5 lines (branch, running jobs with their log paths, next item), so a new chat can continue if this one runs out of context.

## Rules
- **Data:** set `COACH_DB_PATH` to a copy in %TEMP%. Never touch `backend/data/coach.sqlite`.
- **Test servers:** API on 127.0.0.1:8014, web page on 5178. Ports 8000, 5173 and 8011–8013 may be in use; don't stop processes you didn't start.
- **Background jobs:**
  - at most 2 running at once, each with `OPENBLAS_NUM_THREADS=1`;
  - output goes to `autopilot/overnight/jobs/<name>.log`;
  - every job writes a start line and an exit line (or exception) to its log;
  - write each job's start time and estimated end time in Status.
- **Git hygiene:**
  - Add `.gitignore` rules so job `*.log`, `*.lock` and raw `*.jsonl` under `autopilot/*/jobs/` aren't committed.
  - Commit summaries and markdown reports only, and nothing over 200 KB.
- **Tests:** small commits, each with passing focused tests. Run the full backend suite once mid-night and once at 06:30.
- **Advice must not change silently:**
  - Any change to Coach speed must keep the full advice identical on the reference spot set (item 2).
  - If an idea can only reach the target by changing advice, keep it off by default and log it as an owner decision.
- **No "stronger" claims** without a strength-gate pre-registration committed before the run.
- If an item fails twice, log why and move on to the next one.
- **Save context:**
  - read only the tails of logs;
  - keep status lines short;
  - take screenshots only to verify a UI change.
- **Out of scope:**
  - reading the screen of, or clicking in, third-party poker sites or clients;
  - OCR;
  - real money;
  - poker-site integration.

## Backlog
Work in order, but start background jobs first.

**0. Start these background jobs now.** They take about 3 hours together.
- **(a) Agent learning at scale.** Use `simulation.agent_cli --profile-dir autopilot/overnight/jobs/profiles` against `expert`, then `range_expert`, each `--sessions 24 --session-hands 60`.
  - Use fresh seed offsets (grep the repo first; at least 25000, 27000, 41000, 44000, 47000, 50000, 61000 and 62000 are used; 100000 and up looks free).
  - Afterwards, report bb/100 for early vs late sessions with intervals, and whether learning helps. It is a diagnostic, not a strength claim.
- **(b) Full backend suite** on the starting commit, as a baseline.

**1. Practice-table keyboard keys.** Use the same keys as the Coach:
- F, C, B, A;
- digits + Enter for a typed total;
- N for the next hand;
- Enter on a focused button presses that button;
- no keys while a text field has focus.

Reuse the Coach's patterns: `useLayoutEffect` listeners and `isTypingTarget`. Show the key hints on the buttons. Add tests, then do a browser check at phone and desktop width using the key action.

**2. Reference spot set for advice.**
- Build `backend/coach/reference_spots.json`: about 200 fixed heads-up spots across preflop, flop, turn and river, with different stack depths and opponent histories.
- Store the full advice for each: action, amount, action probabilities and a hash.
- Add a script and a slow test that fail on any change.
- Also report how often the quick answer agrees with the full answer: the same action, and the same action and size.
- This guards item 4, so it must be done first.

**3. Back-button and tab sync.** The tabs must follow `hashchange`/`popstate`, so the browser's Back and Forward buttons switch tabs. Drills and My leaks need their own hash too (for example `#drills/leaks`). Add tests and do a browser check.

**4. Full flop, turn and river advice under 1 s.** Today the 95th percentile is about 1.1–3.4 s.
- Targets: 95th percentile under 1,000 ms per postflop request on a quiet machine, and identical advice on the reference set.
- Try these in order, measuring after each:
  - **(a) Speculative solving.** When the opponent's action or the next board card is being entered, solve the likely next hero spot in the background, cancelling it if the input changes.
  - **(b) A persistent on-disk cache** of exact solves, keyed with the same exact key as today's memory cache, so repeated spots are instant across restarts.
  - **(c) Profiling-led CFR and equity speed-ups** that are numerically identical.
- Update `coach-latency.md` with before and after numbers.
- If the quick answer agrees with the full one at least 95% of the time on the reference set, write that as an owner decision ("show quick as the main advice?"). Don't switch the default.

**5. Serve the finished app to the Wi-Fi, not the Vite dev server.**
- `scripts/start-coach.ps1` currently exposes the Vite development server to the LAN, and `npm audit` reports 3 high and 1 moderate advisories in Vite and its tools.
- Serve the built `frontend/dist` (for example FastAPI `StaticFiles` with a single-page-app fallback, after `npm run build` when sources changed), and upgrade Vite so `npm audit` reports 0.
- Keep these as they are:
  - loopback only on Public networks;
  - the same or smaller set of reachable endpoints;
  - rate limits per real client (today every friend shares one bucket because requests come through the proxy);
  - "Start/Stop Poker Coach.cmd" working.
- Test the launcher with `COACH_DB_PATH` pointing to a scratch copy. Write a short security note in SECURITY.md.

**6. Fast test run.** Mark the slow tests with the existing `slow` marker so `pytest -m "not slow"` runs in under 5 minutes, while the full run still covers everything. Document both commands in DEVELOPMENT.md. GitHub CI keeps running the full suite.

**7. Multiway ranges for 2–3 opponents.**
- Measure the 95th-percentile latency of `POKER_COACH_MULTIWAY_RANGES=1` for 2 and 3 opponents.
- Speed it up if needed, with a target of 1.5 s.
- If the target is met, propose turning it on by default for 3 or fewer opponents as an owner decision. Keep it off.

**8. Where we lose to the expert-style bots.**
- Use the agent JSONL from item 0 and earlier runs to break down `solver_adaptive` results against `expert`, `adaptive` and `range_expert` by street, position and spot type.
- Write `autopilot/overnight/expert-family-analysis.md` with ranked hypotheses and, for the best one, a pre-registration draft (strength-gate).
- Don't tune on holdout seeds, and don't run a holdout tonight.

**9. HTTPS for installing on a phone: notes only.**
- Write `docs/https-options.md` comparing a local certificate (mkcert), Tailscale Serve and a self-signed certificate. Cover the setup steps and the risks.
- Don't install anything.

**10. Docs.** README sections for the new keys, the built-app launcher, the fast test command and the reference set.

**11. More items.** Add three new items from tonight's findings and continue.

## At 06:30
- Collect the background job results.
- Run the full backend suite, `npx.cmd tsc -b`, the Node tests (`node --test` with each `test/*.test.mjs` file), `npm.cmd run build` and `npm.cmd audit`.
- Rewrite Status as the morning summary:
  - what's done, with numbers;
  - what failed;
  - decisions for the owner;
  - exact commands to try;
  - the branch;
  - the stop time.
- Commit and leave the working tree clean.
