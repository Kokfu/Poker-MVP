# Step 13 pre-registration: proposal B (bet-size-conditioned reads), written before any B data

Status: DESIGN ONLY. Nothing here is built or run. Seed offset **7,000,000** checked unused (grep over ROADMAP, DESIGN docs, autopilot/, benchmark-results/: only the step 13 prompt mentions it; 1M-6M are taken).
Feasibility inputs: `autopilot/analyze-step-13.py` -> `benchmark-results/step-13-feasibility.txt` (6 existing Slumbot logs, 4,600 hands; no live runs). The local pairwise/tournament JSONs hold only aggregate action counts, no per-hand sizes, so they cannot be bucketed; local bots are heuristic archetypes, not balanced.

## Variants (fixed now, no tuning after data)
`base` = `solver_adaptive` (current default path). `sized` = `base` plus B:
- Cells: opponent response (fold/call/raise) to OUR bet/raise, by size bucket b in {<=0.5, 0.5-1.0, >1.0} of (our raise amount) / (pot after matching the opponent's bet), postflop streets pooled (preflop stays on the existing path: preflop sizing is almost fully determined by our own rules).
- Shrinkage: posterior frequency = (k_obs + m * p_eq(b)) / (n + m), prior strength m = 20 pseudo-observations, p_eq(b) = the solver's unlocked aggregate frequency at the node (same source as proposal A), not the all-streets mean.
- Lookup: the bucket matching the node's bet size; if a bucket has n < 10 the node is left unlocked (no fallback to the pooled cell, to avoid mis-shaped locks).
- Lock weight and caps otherwise as base. SQLite schema change = one new table keyed (opponent, street_class, bucket); old tables untouched; flag `solver_adaptive_sized` off by default; default path must stay byte-identical (golden-hand test as in step 9).

## Gates (T1-style, local, paired), run only if the owner approves a build
Same design as step 10: holdout **offset 7,000,000**, 48 sessions x 60 hands, 8 opponents, equity iterations 100, stacks 10,000, blinds 50/100, statistics seed 91,002, 2,000 resamples, 2 workers, identical seeds both arms (a fresh `base` arm is needed at this offset), paired percentile bootstrap, pooled over tight/equity/expert/range_expert/solver (`adaptive` excluded).
- **T1a** (revised criterion kept): all eight `sized` lower bounds > 0 (as step 10). 0 illegal, 0 fallbacks, 0 deal mismatches.
- **T1b** (no harm): pooled paired lower bound > -20 bb/100 (tightened from -25 using the observed step 10 pooled half-width 17.5) AND no single opponent paired lower bound below -60. If pooled half-width > 40: inconclusive.
- **T1c** (benefit, only needed to claim a win-rate gain): pooled paired lower bound > 0.
- Aggressive/random reported, flag a drop > 150.
- Decision: adopt only if T1a, T1b pass; "improves strength" claimed only if T1c also passes. Otherwise base stays.
- **T0** (offline, cheap, run before T1): leave-one-log-out prediction of Slumbot's fold/call/raise on postflop client bets from the existing six logs, comparing (i) size-blind street model and (ii) bucketed shrunk model (m = 20); metric log-loss. B proceeds to T1 only if (ii) beats (i) by a bootstrap (over hands) 95% lower bound > 0. Not run in this step.

## Power statement (honest)
Pooled paired half-width in step 10 was 17.5 bb/100, i.e. SE about 8.9. A one-sided 95% / 80%-power test detects a true pooled gain of about (1.64+0.84) x 8.9 = **22 bb/100** (two-sided T1c: about 25). Per opponent, step 10 half-widths were 17-130, so only effects of roughly 50-250 bb/100 are detectable per opponent. B is expected to change play only where an opponent's folding depends on size in a way a size-blind lock misses; local heuristic bots fold by pot odds, which a size-blind model approximates, so a true local gain below ~22 bb/100 would be reported as "not shown". Live Slumbot cannot test B: one 1,000-hand run has a 95% half-width of about 200 bb/100, so detecting 20 bb/100 would need roughly 100,000 hands (~170 h at 6 s/hand). The decision therefore rests on T0 plus no-harm.

## Rerun rule
Killed runs restart from the beginning of that run's file (as step 10); no parameter or gate changes after seeing data.
