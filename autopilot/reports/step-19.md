# Step 19 report: T1 for proposal B (`solver_adaptive_sized` vs fresh `solver_adaptive`, offset 7M)

**Verdict: T1a FAIL, T1b FAIL, T1c FAIL -> keep base (B not adopted).** The sized bot is clearly worse than base, not just "not shown": pooled paired difference **-92.4 [-123.4, -62.1] bb/100**. Gates, parameters and script were committed before any data (ca57116; prereg `autopilot/prereg-step-19.md` points at `prereg-step-13.md`, unchanged). Branch `autopilot/step-19`; not merged, not pushed.

## Run
16 `duplicate_cli pair` runs (holdout, offset 7,000,000, 48 sessions x 60 hands, equity iterations 100, stats seed 91,002, 2,000 resamples, 2 workers, identical seeds in both arms, asserted by the analysis). Started 14 Nov 22:39, finished 16 Nov 10:21 (about 35.7 h). **No restarts or killed runs.** Per-run minutes (base/sized): tight 107/66, equity 177/207, expert 97/145, range_expert 118/174, solver 360/206, adaptive 70/68, aggressive 108/119, random 42/74. Episodes of low free RAM (170-700 MB) and a slower CPU rate around 15 Nov 15:00-15:40 and 19:00-21:30 were seen; no run failed. All 16 outputs: 0 illegal, 0 fallbacks, 0 deal mismatches.

## Results (bb/100, 95% CI; paired = sized minus base, 48 pairs)
| Opponent | sized | base | paired diff |
|---|---|---|---|
| random | +438.2 [+335.1, +538.3] | +476.2 | -37.9 [-96.6, +24.2] |
| tight | +51.1 [+26.5, +76.4] | +52.5 | -1.4 [-21.3, +18.6] |
| aggressive | +543.7 [+459.2, +632.0] | +1098.1 | **-554.4 [-657.6, -449.6]** |
| equity | +148.8 [+85.8, +213.4] | +427.4 | **-278.6 [-352.0, -209.7]** |
| expert | +55.0 [+11.0, +96.9] | +80.0 | -25.0 [-70.3, +20.7] |
| adaptive | +56.0 [+12.8, +97.8] | +81.1 | -25.1 [-69.9, +19.6] |
| range_expert | +22.1 [-22.0, +63.7] | +55.8 | -33.7 [-81.7, +12.3] |
| solver | -32.0 [-86.6, +19.4] | +91.4 | **-123.4 [-191.9, -58.7]** |

- **T1a (all eight sized lower bounds > 0): FAIL** (range_expert -22.0, solver -86.6; also solver's point estimate is negative).
- **T1b (pooled paired lower bound > -20 and no single opponent below -60, over tight/equity/expert/range_expert/solver): FAIL.** Pooled -92.4 [-123.4, -62.1], half-width 30.6 (< 40, so not "inconclusive"); worst single lower bound -352.0 (equity); solver -191.9 also below -60.
- **T1c (pooled lower bound > 0): FAIL** (the whole interval is below zero).
- Flag (not a gate): aggressive drop -554 exceeds the 150 threshold.
- Decision rule: keep `solver_adaptive`; `solver_adaptive_sized` stays available, off by default.

## Power statement
Pooled half-width was 30.6 bb/100 here (17.5 in step 10), so only effects of about 35+ bb/100 would have been detectable one-sided at 80% power; a +22 bb/100 gain (the gate's design effect) would have been "not shown". That question is moot: the observed effect is a large harm, far outside the interval of zero, against opponents with 48 pairs each. Not corrected for multiplicity; one run per arm and seed set.

## Why it might be so bad (unverified, not a result)
Hypotheses only, nothing tested and no tuning done: the bucket cells aggregate our bets over all streets and our whole range, so they mismatch the opponent's per-street response at specific nodes; the lock weight and the `n >= 10` rule let thin cells lock quickly; the unlocked-aggregate shrinkage could pull aggressive/equity opponents toward fold-heavy responses; the 0.54 small-blind strength quirk (step 17a) is shared with base so it does not explain the gap. A diagnosis step (step 17a style) on aggressive/equity, where the loss is largest, would be needed before anyone fixes B; the pre-registered rule says base stays regardless.

## Checks
Backend suite on this branch (no code changed since step 18): **873 passed, 8 warnings, 1,497 s**. No frontend change. Output files: `benchmark-results/phase-7/` (16 result JSONs, logs, `t1-analysis.json`, `t1-analysis.txt`), force-added.

## Recommended next
Close proposal B as not adopted; document in ROADMAP/DESIGN (step 20 per the queue). Optional: a diagnosis of the aggressive/equity losses if the owner wants to understand them; otherwise stop spending on opponent-model changes (A and B both failed pre-registered no-harm tests).
