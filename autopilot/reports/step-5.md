# Step 5 report: 48-session offset-5M test of solver_adaptive

**Verdict: PASS (revised criterion).** All seven 95% lower bounds > 0, 0 illegal actions, 0 fallbacks, 0 deal mismatches over 40,320 hands. Step 3's weak expert-family result is read as seed noise, not a regression.

Setup (pre-registered in `autopilot/prereg-step-5.md`, commit 1090190, before any data): `main` 4e191b3, no strategy changes, holdout seed offset 5,000,000 (new), 48 sessions x 60 hands per opponent, stats seed 91,002, 2,000 bootstrap resamples, 2 workers. Run via `autopilot/run-step-5.ps1`; results `benchmark-results/phase-5/final-h2h-offset5m-<opp>.json` (~1h per opponent, ~7h total).

| Opponent | offset-5M bb/100 [95% CI] | offset-3M final test | step 3 (16 sess, 4M) |
|---|---|---|---|
| random | +595.0 [+499.8, +686.4] | +539.6 | +603 |
| tight | +49.7 [+25.5, +73.8] | +81.7 | +29 |
| aggressive | +1,061.1 [+977.8, +1,142.6] | +1,124.7 | +1,047 |
| equity | +418.0 [+337.2, +495.1] | +438.8 | +392 |
| expert | +74.2 [+24.7, +124.8] | +110.1 | -7 |
| adaptive | +75.3 [+25.6, +126.4] | +110.1 | -7 |
| range_expert | +78.8 [+28.2, +131.5] | +117.1 | -22 |

Interpretation (per table): pass => noise reading. Caveats: the expert family point estimates are ~35-40 bb/100 below the offset-3M estimates (tight -32), every one inside the offset-3M intervals, and the lower bounds (+25 to +29) are well above zero but lower than before; this is consistent with noise plus modest regression to the mean, but a small real decline can't be excluded. Step 3's -7 sits well below this interval, so that holdout was an unusually bad draw. Combining 3M/5M the expert-family edge is roughly +75 to +115 bb/100.
Other notes: `adaptive` is now 1.1 bb/100 off `expert` (not byte-identical as at offset 3M), so its exploit engine activated rarely here; treat the two as non-independent anyway. Only one run per seed set; no multiplicity correction across seven opponents.

Not done: backend tests and frontend build not run (no code changed; only a doc, a run script and result files added). No bisect (not requested). Nothing merged or pushed. Branch `autopilot/step-5`.

Recommended next: accept; no regression action needed. Optionally record the 5M result in ROADMAP.
