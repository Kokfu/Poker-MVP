# Overnight progress

## Morning summary

- Done in setup: clean baseline `5da9913`, overnight branch created.
- Failed: no tasks attempted yet.
- Decisions for the owner: use synthetic Coach data in temporary SQLite files.
- Exact commands: see task entries as work is validated.
- Branch: `overnight/2026-11-25`.

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
