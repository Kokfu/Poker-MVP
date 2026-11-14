# Step 10 pre-registration (T1), written before any data

Source of gates: `DESIGN_OPPONENT_MODEL.md` section 4 (committed unchanged since approval; not edited here). `base` = `solver_adaptive` (main fa3b538 behaviour; main now also holds step 9, which leaves the default path byte-identical). `gated` = `solver_adaptive_gated`. Gate parameters (0.90 / 0.08 / 0.10) unchanged.

## Verbatim gates
- **T1a** (revised criterion kept): for all eight opponents the 95% interval of `gated` bb/100 has lower bound >0; 0 illegal actions, 0 fallbacks, 0 deal mismatches.
- **T1b** (no harm): the paired difference (gated minus base), pooled over the five non-degenerate opponents (tight, equity, expert, range_expert, solver; `adaptive` excluded as an exact copy of `expert`), has 95% lower bound > -25 bb/100, **and** no single opponent's paired lower bound is below -60 bb/100. If the observed pooled paired half-width exceeds 40 bb/100 the test is reported **inconclusive**, not passed.
- Aggressive and random differences are reported, not gated; a drop of more than 150 bb/100 against either is flagged as a cost.

## Design
Opponents: random, tight, aggressive, equity, expert, adaptive, range_expert, solver. Holdout seed set, **seed offset 6,000,000** (checked: not present in ROADMAP/benchmark-results/autopilot docs), 48 sessions x 60 hands, equity iterations 100, stacks 10,000, blinds 50/100, statistics seed 91,002, 2,000 bootstrap resamples, 2 workers. Both strategies run on identical seeds/deals via `duplicate_cli pair` (one run per strategy x opponent = 16 runs, sequential, ~1 h each), results `benchmark-results/phase-6/t1-<strategy>-<opp>.json`. Script: `autopilot/run-step-10.ps1`.

## Paired statistic (fixed now)
Per pair i and opponent: d_i = (net_a+net_b)_gated - (net_a+net_b)_base on the same seed, converted to bb/100 as in the harness (per-pair sum / hands / 100 chips-per-bb x 100). Per-opponent CI: percentile bootstrap over the 48 pairs, 2,000 resamples, seed 91,002. Pooled: for each pair, mean of d_i over the five gated opponents, bootstrapped the same way. Script `autopilot/analyze-step-10.py`. If seeds do not match between arms for any pair, the run is invalid and is reported as such.
Rerun rule: a killed run is restarted from the beginning of that run's file; no parameter changes after seeing data.
