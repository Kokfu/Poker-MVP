# Overnight progress

## Morning summary

- Done: model audit and 336-hand sizing screen, exact Coach caches, one-click recent sizing, a 24-hand resumable simulation, and a browser-tested practice table.
- Failed: aggregate latency p95 still exceeds both targets. The single full backend run is collecting its final results after two compatibility failures surfaced.
- Decisions for the owner: keep size interpolation opt-in. Use synthetic temporary databases and the localhost browser for verification.
- Exact commands: see the task entries and AUTONOMOUS_AGENT.md.
- Branch: overnight/2026-11-25.

## Decisions for the owner

- Use temporary SQLite databases seeded with generated hands. No user records are required.

## Task log

### 02:02 +08:00 · A1 decision model audit · done

- Commits: this entry and the decision model audit.
- Evidence: four heads-up decisions, two preflop (504.66 ms cold, 0.83 ms repeat) and two flop (695.01 ms first, 359.67 ms repeat), with stable actions within each spot. Three 20,000-deal multiway diagnostics. No test suite required for the audit.
- Next: build the flagged postflop likelihood experiment. The API timing script is collecting the larger B1 baseline in autopilot/overnight/coach-baseline.json.


### 02:14 +08:00 · A2 off-tree sizing experiment · done

- Commits: this entry, the opt-in duplicate arm, focused tests and eight development reports.
- Tests: python -m pytest -q -p no:cacheprovider test_solver_interpolated.py test_simulation_duplicate_evaluation.py, 10 passed, 7 warnings, 3.29 s. Four opponents, 336 duplicate hands across both arms, zero illegal actions, fallbacks or deal mismatches.
- Next: keep the experiment off by default. No holdout or strength claim because only one matchup changed and its point estimate was negative. See model-experiment.md for commands and intervals.

### 02:21 +08:00 · B1 Coach advice latency · partial

- Commits: this entry, exact solve and derived profile caches, timing script and reports.
- Tests: original Coach/solver focused command 90 passed, 8 warnings, 128.21 s. After the profile cache, python -m pytest -q -p no:cacheprovider test_coach_advice_cache.py test_coach.py test_solver_phase_4h.py, 34 passed, 8 warnings, 21.06 s. All 48 normalized API responses matched.
- Results: repeat p95 17 ms preflop and 45 ms postflop; aggregate p95 1,514 and 2,274 ms, above both targets. First timing retry fixed Windows SQLite cleanup. Browser verification for the same advice path follows with B2.
- Next: retain exact caching. Investigate cold chart/lock and new-board solves separately if the targets must include first requests. Commands and raw outputs are in coach-latency.md and its accompanying JSON files.

### 02:24 +08:00 · B2 fewer steps per hand · done

- Commits: this entry, the Recent button, its test and browser evidence.
- Tests: npx.cmd tsc -b passed in 8.28 s. node --test test/coach-strategy.test.mjs passed 2/2 in 1.96 s. npm.cmd run build passed, 31 modules, Vite 412 ms. One end-to-end mobile browser hand passed with zero console errors, covering both B1 and B2.
- Result: one click reused a legal 375-chip raise from a synthetic opponent's history. Historical totals are scaled to the current blind and illegal sizes are skipped.
- Next: see coach-ui.md and coach-frontend.log. The browser lacks the raw CDP storage methods, so scratch-origin browser preference cleanup will use a test-only HTTP response during C3.

### 02:25 +08:00 · C1 autonomous agent design · done

- Commits: this entry and AUTONOMOUS_AGENT.md.
- Tests: design only. Checked the three adapters and observation, legal action, settlement and learning contracts against the existing simulator code. No tests run for this doc.
- Next: build the offline runner with a session-boundary ledger. Slumbot remains an independently invoked, optional network benchmark.

### 02:26 +08:00 · C2 resumable simulator CLI · done

- Commits: this entry, the offline CLI, interrupted-resume tests and synthetic run artifacts.
- Tests: python -m pytest -q -p no:cacheprovider test_simulation_agent_cli.py test_simulation_duplicate_evaluation.py, 10 passed, 7 warnings, 2.09 s. Tests covered an interrupted second session, a partial JSONL write and incompatible resume parameters.
- Smoke: 3 paired sessions × 4 hands per orientation, 24 hands, 20.62 s. +2.08 bb/100, 95% interval [−56.25, +62.50], zero illegal actions, fallbacks and deal mismatches. Reopening the completed run left its ledger byte-identical.
- Next: begin the LAN table prototype. Simulator command and log are in AUTONOMOUS_AGENT.md and autopilot/overnight/agent-smoke.log.

### 02:31 +08:00 · C3 one-human LAN practice table · done (prototype)

- Commits: this entry, the practice API, the browser page and focused evidence.
- Tests: python -m pytest -q -p no:cacheprovider test_practice_table.py test_simulation_decision_privacy.py test_simulation_history_privacy.py test_simulation_short_stack_legality.py, 33 passed, 8 warnings, 3.10 s. Final frontend type check, 2 Node tests and production build passed.
- Result: one loopback browser hand through a bot raise and flop bet, then fold settlement and hand 2. The bot seat was labelled and the console had zero errors. The scratch origin received a browser storage-clear response and the test server was stopped. A separate LAN device was unavailable.
- Next: try Practice table from the existing LAN launcher. Tables live in one server process and end on restart. Full backend regression runs once in the background with output to autopilot/overnight/full-backend.log.

### 02:35 +08:00 · regression follow-up for Coach custom providers · done

- Commits: this entry and the compatibility correction.
- Tests: python -m pytest -q -p no:cacheprovider test_research_holdem_phase_4v.py test_research_holdem_phase_4w.py test_coach_advice_cache.py test_solver_phase_4h.py. First recovery attempt 30 passed, 1 failed, 8 warnings, 22.68 s. Final focused run 31 passed, 8 warnings, 35.40 s.
- Result: preserve the previous solver factory and hands() contract when a caller supplies a custom history provider. This restores the research trace hooks while retaining exact caching on the SQLite path.
- Next: let the single already-running full suite finish and record its original result separately from the successful recheck.
