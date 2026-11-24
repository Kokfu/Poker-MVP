You are working overnight, unattended, in C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp. Nobody will answer questions until morning, so never stop to ask. When you need a decision, take the safe default, write it under "Decisions for the owner" in the progress log, and continue.

## Setup
1. Read these first:
   - AGENTS.md
   - DEVELOPMENT.md (the status section at the end)
   - the "Current status" section of ROADMAP.md
   - the checklists `.claude/skills/poker-regression/SKILL.md`, `coach-ui-test/SKILL.md` and `strength-gate/SKILL.md`. Follow them as written. If you have no browser tool, replace the UI checks with `npx tsc -b`, `npm run build` and API calls, and say so in the log.
2. If tracked files have uncommitted changes, stop and write that down. Otherwise create the branch `overnight/2026-11-25` from `main`. I authorize commits on that branch only. Do not push, merge, tag or change `main`.
3. Create `autopilot/overnight/progress.md`. Update and commit it after every task. Keep a 5-line "Morning summary" at the top. Then add one entry per task:
   - time;
   - task;
   - result: done, partial, failed or skipped;
   - commits;
   - test results with counts;
   - next step.

## Rules
- Make small commits. Each commit passes its focused tests. The full backend suite runs once before the final summary.
- Never use `backend/data/coach.sqlite`. Set `COACH_DB_PATH` to a copy in %TEMP%.
- Run any job longer than 10 minutes in the background, with its output going to a file. Write that file's path in the log. Use at most 2 workers, because RAM is low.
- Don't claim a bot is "stronger" without the strength-gate. Run a holdout test tonight only if it is estimated at 4 hours or less. Otherwise, commit the pre-registration and leave the exact command for me.
- If a task fails twice, log why and move on to the next task.
- Out of scope:
  - reading the screen of, or clicking in, any third-party poker site or client;
  - OCR;
  - real money;
  - poker-site integration.
- Stop starting new work 7 hours after you begin. Use the last hour for the full regression and the morning summary.

## Tasks
Do them in order. Each one ends with a commit and a log entry.

**A. The decision model**

**A1. Find where the model is weakest.** Measure:
- the time per decision;
- where the advice is weakest:
  - multiway, which uses only equity and pot odds, with no solver;
  - bet sizing;
  - opponent-read confidence.

Write up the findings and a ranked list of proposals (expected gain against cost).

**A2. Build the top proposal.** Put it behind a flag that is off by default, and add tests.
- Screen it on development seeds with `simulation.duplicate_cli pair` against a few opponents.
- If it looks promising, pre-register a holdout test (strength-gate). Run it if it fits the time budget. Otherwise, leave the command.

**B. Speed and usability**

**B1. Make Coach advice faster.** `/api/coach/advise` takes about 0.6–1.3 s today.
- Targets: 95th percentile under 300 ms preflop and under 600 ms postflop.
- Write a timing script and measure first.
- Then use caching, precomputing or fewer equity iterations, but only where a test shows the advice is identical, or within a tolerance you state.

**B2. Fewer steps per hand.** Keyboard entry already exists; see "Fast entry in the Coach" in the README. Examples:
- quick villain sizes taken from the opponent's history;
- a faster Review;
- the phone layout;
- the "Start Poker Coach" start-up time.

Verify each change. Save screenshots or outputs to `autopilot/overnight/`.

**C. Autonomous agent: a plan and a first build**

I want an agent that plays whole hands by itself with no manual input. It may run only where bots are allowed.

**C1. Write `AUTONOMOUS_AGENT.md`.** Design the loop:
- observe the state;
- decide with `solver_adaptive` and the opponent profiles;
- act;
- learn.

It runs unattended against three kinds of opponent:
- (a) the simulator bots;
- (b) Slumbot through its public API (`simulation.slumbot_cli`, needs the network, optional);
- (c) a practice table hosted by this app on the LAN. Friends join from a browser, and the bot sits in a seat clearly labelled as a bot.

State that screen-reading or auto-clicking third-party poker sites is excluded.

**C2. Build (a).** Make a CLI, for example `simulation.agent_cli`, that:
- runs N sessions unattended;
- resumes after an interruption;
- writes JSONL logs, plus a summary in bb/100 with an interval, to `benchmark-results/agent/`.

Run a short session tonight and log the result.

**C3. If time is left, start (c).** Build backend table endpoints and a minimal page for one human seat and one bot seat, with tests. If there isn't time, leave the design and a task list.

## Morning summary
Put this at the top of progress.md:
- what's done, with numbers;
- what failed;
- decisions for the owner;
- exact commands to try;
- the branch name.
