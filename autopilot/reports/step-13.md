# Step 13 report: offline feasibility of proposal B (bet-size-conditioned reads)

**Verdict: technically feasible, benefit untestable at available budgets; pre-registration written, nothing built or run. Recommendation: do not build unless the owner wants B for its own sake; run the cheap offline T0 first.** Branch `autopilot/step-13`, branched from `autopilot/step-12` (93c36f3) because `main` does not contain step 12 (steps 9, 10, 12 unmerged). Not merged, not pushed. Seed offset 7,000,000 verified unused.

## What was done
- `autopilot/analyze-step-13.py` (stdlib + repo's own `beta_interval`, no SciPy) reads six existing Slumbot logs (4,600 hands: learning-clean, instrumented, adaptive-learning, adaptive-long, expert, solver; killed partial files excluded). It reconstructs pots from the action strings (street-level bet-to amounts; checked: 0 fold-settlement mismatches against logged winnings) and buckets each of OUR bets/raises by size / pot, then tallies Slumbot's response. Output: `benchmark-results/step-13-feasibility.txt`.
- `autopilot/prereg-step-13.md`: variants, shrinkage (m=20 toward unlocked equilibrium frequency), gates T0/T1a/T1b/T1c, power statement. Commit 1 precedes any B data (there is none).
- Local benchmark JSONs hold only aggregate action counts, so they could not be bucketed (said so, not guessed).

## Numbers (Slumbot, 4,853 answered bets/raises; 95% Beta intervals)
Fold rate by bucket (<=0.5 / 0.5-1.0 / >1.0): all streets 29% [27,30] / 70% [66,73] / 93% [92,95]; flop 35 / 58 / 94; turn 33 / 50 / 88; river 37 / 52 / 88. Chi-square homogeneity across buckets p<0.0001 on every street. So buckets are clearly distinguishable; a size-blind flop fold rate (53%) would be wrong in shape for every bucket.
Opportunities per 1,000 hands, postflop: <=0.5 about 474, 0.5-1.0 about 112, >1.0 about 178 (flop 291/52/121, turn 114/38/32, river 69/22/25).

## Caveats (why this is not a green light)
- The size effect is largely mechanical (pot odds; MDF-style), and confounded by our own bot's range at each size. Fold at >1.0 (88-94%) exceeds MDF, but I did not test deviation from equilibrium; that is exactly what T0 would check.
- Volumes depend on our bot's sizing: in some 1,000-hand logs the 0.5-1.0 bucket has only 7-11 postflop cases (other logs 100-300). Per-session cells there stay thin; the n>=10 rule would leave those nodes unlocked.
- Per-hand logs are one bot-vs-Slumbot sample each; no multiplicity correction; chi-square p-values are crude (Wilson-Hilferty tail).
- Power: local pooled half-width 17.5 means only a true pooled gain >= ~22 bb/100 is detectable; live Slumbot needs ~100,000 hands (~170 h) to detect 20 bb/100. So even a real B gain would likely be reported "not shown", and T1 mainly tests no-harm (step 10 showed that even a mild change cost ~12 bb/100).
- No tests run: no production code changed (docs, one analysis script, one output file).

## Cost if approved
T0 offline replay script: ~1-2 h, no live runs. Build (schema, lookup, flag, golden-file equivalence, tests): ~6-8 h. T1 run: 16 runs (fresh base arm needed at 7M), ~40 h wall, as step 10. Total about 50 h, one test only able to detect >= ~22 bb/100.

## Recommended next
Owner choice: (a) stop here and take the cheaper alternative (docs consolidation, Coach polish); or (b) run T0 only (1-2 h) and build B only if it passes. I recommend (a) or (b), not a full build.
