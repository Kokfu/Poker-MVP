# A1 decision model audit

## Multiway

The advisor samples random hands, splits ties, and compares equity with fixed pot-odds thresholds. It never observes which players bet or called, their positions or their ranges. Its bet and raise suggestions also lack a target and fold-equity model.

River stress case: As Jd on Ah 8d 7s 4c 2h, facing 200 into a pot of 300 (40% required). With 20,000 trials and seed 73, the default advisor outputs:

| Random opponents | Equity | Advice | Time |
| --- | ---: | --- | ---: |
| 2 | 73.85% | Raise | 259 ms |
| 4 | 52.70% | Raise | 385 ms |
| 8 | 27.21% | Fold | 556 ms |

For a targeted counterexample, fix one opponent to Ad Qd and deal all other opponents randomly. Hero's share is exactly zero, since the board is complete and AQ always outranks AJ. This measures sensitivity to the random-range assumption, with no claim that a typical betting range is exclusively AQ.

## Heads-up bet sizing

The standard first postflop bet menu contains half-pot and pot targets. On a 500-chip pot with those targets unclipped, a 353-chip bet maps to 250 and a 354-chip bet maps to 500. This follows from the geometric midpoint of 250 and 500 (353.55) and the existing log-distance rule. The re-solve still uses the exact pot and commitments, but the estimated betting range changes buckets in one chip and carries into later streets. This is a discontinuity in inferred likelihood, with no EV or strength estimate attached.

Earlier size-conditioned opponent locks are a separate intervention. Their existing holdout reported a pooled paired difference of -92.4 [-123.4, -62.1] bb/100 in Step 19. Reusing those locks has adverse evidence.

## Opponent-read confidence

Confidence rises from very low to low at 5 opportunities, medium at 20, and high at 50. With all relevant estimates crossing together, the lock weights jump from 0 to 0.30, 0.55, and 0.75 respectively. The standard error of a simple 50% Bernoulli frequency is about 22, 11, and 7 percentage points at those respective sample sizes, before accounting for variation by position or size. The preflop blind-correlation mismatch from Step 17a is already fixed in the baseline's shared `_facing_wager` predicate. Previously tested deviation gating failed its prospective no-harm rule.

## Ranked proposals

| Rank | Proposal | Expected gain and cost |
| --- | --- | --- |
| 1 | Interpolate opponent action likelihoods for postflop sizes between two compatible tree actions | Removes a concrete range discontinuity for a small, reversible heads-up change. Existing duplicate sessions can screen it. Exact sizing continues to come from the engine. Win-rate effect is unknown. |
| 2 | Add configurable, position/action-conditioned ranges to multiway Coach | Addresses the largest approximation error in the example. Requires explicit inputs, collision-aware weighted sampling and separate calibration data. The current heads-up duplicate runner cannot evaluate it. |
| 3 | Calibrate lock confidence by context and validate on held-out public actions | Could reduce mismatched pooling and thin-read overreaction. Prior gate failures and lack of prospective calibration make this more costly and uncertain. |
