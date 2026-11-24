# Phase 4O — Frozen incoming-prior evaluation protocol

## Design

Reuse the existing Coach replay, earlier street solves, mapped river wager, fixed 80-step value converter, concrete decision menu and modeled Hero continuation. Start each replay with equal stacks and 50/100 blinds. Hold Villain responses fixed per holding in each setting. Score policies under the same independently enumerated posterior and reference replies. Reference replies allow fold and call, using Phase 4K's effective-price rule. The production response arm uses the unchanged final production continuation, with Phase 4L's nearest-rank extension for combos without a response column. This extension is shared by all three policies.

| Arm | Pre-bet prior | Observed river likelihood |
| --- | --- | --- |
| A | Production reach on first river solve support | Production mapped action |
| B | Positive chart reach, carried through observed earlier actions | Same fixed likelihood |
| C | Exact synthetic incoming distribution | Same fixed likelihood |

B starts with the actual locked or unlocked preflop chart product and uses the exact per-holding production action probability where the solver has a column. For a pruned column, use the reach-weighted mean of that action's probabilities on retained holdings compatible with Hero and the board visible on that street. The pooled estimate introduces no fitted constants and uses the same fixed action frequency for all unavailable holdings. Carry any resulting positive weight to the next action without applying the solver's numerical trim. Explicit zero probabilities from the chart or covered actions continue to exclude holdings. Earlier solve inputs and strategies are frozen. For the river likelihood, fill unavailable columns by the same pooling rule from the first river solve for every arm. The retained columns are unchanged. Candidates see no synthetic labels, future actions, or private Villain information.

The fresh panels use half-pot bets and shoves, which are on the production menu in the scheduled geometries. Assert that A matches the actual final production reach after the bet. Historical Phase 4N diagnostics are off-menu and may involve an extra prune. There, compare A/B/C under a common mapped likelihood before extra pruning, and audit actual production reach and the archived Phase 4N posterior rule separately. Diagnostics that substitute the synthetic wager law assess remaining likelihood error and do not enter the promotion gate.

## Reference and schedule

Reference action histories are selected by design, with each held-out group scored under the conditional distribution for that line. Uniform unordered combo mass is conditioned on Hero and public board blockers. Use Phase 4K's tight/loose paid participation, aggressive/passive preflop raise probability, made-hand-dependent opening rates, and facing-wager call rates. The paid preflop call law applies once when Villain calls a button open, twice for a Villain limp and call of the big blind's raise. Half-pot earlier-street leads and final wagers use the Phase 4N conditional opening-size law and combine collisions at minimum and all-in. Each earlier check uses one minus the opening rate. Including a check and call on the same street requires multiplying both observations. Hero's fixed scripted actions add no likelihood. On the river use all five public cards; the incoming prior stops before the Villain wager.

Tenet for sparse evidence: profiles come from 3, 30 and 100 completed hands in each independently generated stream. Reuse production default locking and its existing backoff for absent cells. The candidate has no profile-dependent tuning, so an unobserved cell needs no new fitted rate. Report the zero-observed-river-opening-bet subset separately. These completed histories use the older Phase 4K opener with fixed/capped sizing. They do not provide labels from the explicit size law used to score the panel.

Development uses deal seed 435101, six deals, stream 81. Holdout uses deal seed 435102, twelve fresh independent deals, streams 91/92, opposite seats per shared deal, four styles and three profile prefixes. The 288 matched decisions form the primary panel. Score the 288 opposite-profile comparisons separately. Assign 9/15/30 bb depths, 200/250/300-chip preflop targets, and check/check, flop aggression followed by a turn check-through, or checked flop followed by a called turn bet using the deterministic schedule in the frozen runner. Neither equal weighting of the lines nor the observed legal geometry estimates their frequency in play.

## Metrics and gate

Primary measure is candidate minus A mean paired exact EV per facing-bet decision in bb under production responses. First calculate outcomes with reference responses to isolate prior error; then apply production responses. Use 10,000 percentile board-block resamples seeded at 3349, preserving all seats, depths, profiles and streams within each of twelve blocks. Intervals condition on the two sampled profile streams. Use the Phase 4N thresholds for comparability, plus a prior-specific criterion.

- Production-response gain ≥ +0.05 bb and lower bound of the paired 95% interval > 0. Reference-response gain ≥ +0.02 bb.
- Each matched opponent mean ≥ −0.03 bb in both settings. Production-response mismatch mean ≥ −0.05 bb.
- Worst loss ≤ 0.50 bb and at most 10% of matched decisions lose more than 0.01 bb in each setting. Also report incidence and total cost for losses exceeding 0.000001 bb.
- Mean prior TV improves by ≥ 0.01 and missing prior mass does not increase. Mean posterior TV improves by ≥ 0.01 with no regression in excess Brier or absolute equity error. Report hand-strength composition as a proxy and excess allocation to holdings below uniform reference mass, plus regret against the best common action.
- Zero unexpected fallbacks, blocked combinations, invalid probability mass or illegal recommendations. Evaluate independent action payoff parity against the existing exact reference evaluator. Median incremental update < 5 ms and peak traced allocation < 256 KiB. Measure pooling and the replay update on captured production arrays. Report live solve time and process resident memory separately.

Preserve the frozen implementation and all holdout results after evaluation. A missed gate rejects the candidate for further gameplay validation. Repeat the same holdout under two Python hash seeds and compare every non-performance field. Use disjoint deal and profile seeds for development and holdout, and treat the two archived profiles as historical case studies.
