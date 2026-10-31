# Step 5 pre-registration (written before any data)

**Question.** Step 3 (16 sessions, offset 4,000,000) gave expert -7, adaptive -7, range_expert -22, tight +29 bb/100, versus +110/+110/+117/+82 in the 48-session final test (offset 3,000,000). Noise or regression?

**Test.** `solver_adaptive` at `main` 4e191b3 (no strategy changes) vs each of `random, tight, aggressive, equity, expert, adaptive, range_expert`; holdout seed set, **seed offset 5,000,000 (never used before)**, `--pairs 48 --session-hands 60` (5,760 hands/opponent), 100 equity iterations, stacks 10,000, blinds 50/100, statistics seed 91,002, 2,000 bootstrap resamples; same `duplicate_cli pair` harness as the final test. Workers reduced to 2 (does not affect results). Outputs: `benchmark-results/phase-5/final-h2h-offset5m-<opponent>.json`.

**Pass rule (revised criterion).** All seven 95% lower bounds > 0 AND 0 illegal actions AND 0 deal mismatches.

**Interpretation table (fixed now).**
| Outcome | Reading |
|---|---|
| Pass | Step 3 weakness was seed noise; no regression evidence. |
| Fail only on expert-family (expert/adaptive/range_expert) or tight, with lower bound <= 0 but point estimates > 0 | Underpowered/ambiguous; still not a pass. Report as unresolved, lean noise if estimates are within the offset-3M intervals. |
| Expert-family point estimate <= 0, or lower bound <= 0 with estimate well below offset-3M interval | Treat as regression. Suspect commits to bisect (separate step, NOT here): the perf-solver merge (4987a71, array CFR; known non-bit-identical action flips) and later solver/main merges; compare against b3be891. |
| Failure on random/aggressive/equity | Serious regression; same bisect list, higher priority. |
| Any illegal action or deal mismatch | Fail regardless of intervals; investigate before anything else. |
Note: `adaptive` is expected to equal `expert` exactly (its exploit engine never activates), so they are not independent.
