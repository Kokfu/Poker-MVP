# Phase 4P — Frozen preflop weight experiment

## Estimand and split

The primary estimand is the equally weighted paired difference in exact conditional river EV, in bb per facing-bet decision, between calibrated and production preflop weights with production downstream models. Keep the actual legal menu and production bet-size abstraction, frozen postflop likelihoods and response strategy, modeled Hero continuation, and Phase 4L's 80-step fixed-value selector. Score every policy under the same exact synthetic posterior and exact reference replies. Keep live Coach advice as a parity and legality control.

Development uses deal seed 436101, four boards and stream 101. Holdout uses independent deal seed 436102, twelve boards, each crossed with all four Phase 4K opponent styles and two independent streams 111 and 112, for 96 rows. Rotate preflop paths, depths (9/15/30 bb), histories and 3/30/100-completed-hand Coach profiles by the schedule in the runner. A board can appear under different preflop paths in different streams. The four lines are BB call of an open, SB limp and call of an isolation raise, BB three-bet followed by Hero call, and SB open and call of Hero's three-bet. Earlier streets can check through or include one bet and call. River wagers are half-pot or shove and must be on the existing production menu. This is a stratified conditional experiment with fixed styles and scripted Hero actions.

The separate historical diagnostic replays the Phase 4O worst exact-prior loss on deal 11, loose-aggressive profile stream 91 at 30 hands. Keep the historical preflop and downstream synthetic laws for truth. Candidate calibration uses separate stream 103 under the new law. Historical results never enter the gate.

## Independent law and calibration

Use uniform unordered legal pairs before Villain acts. The preflop panel masks Hero's known hole cards only (1,225 pairs). At the river mask public board cards as well (990 pairs). For each observed Villain action multiply the hand's conditional action probability given the public prefix. A limp and a call of the isolation raise apply two distinct terms. A scripted Hero action supplies no additional likelihood about Villain's holding. The synthetic law assigns a contest rate and then an aggression probability conditional on contesting. Fold, passive and aggressive masses are 1 − contest, contest × (1 − aggression) and contest × aggression. The BB option after a limp gives fold zero and the passive branch is a check. The reference uses the explicit depth and suitedness adjustments and opponent-style coefficients in the runner, and supports opening, isolation and three-bet and four-bet branches. Aggressive groups have a single scheduled observed target per opportunity. The reference is conditional on the specified geometry and assumes no further within-group size signal preflop. Postflop laws reuse Phase 4O's rank and actual-price reference and Phase 4N's river size law, including all-in collisions. Exact river enumeration must agree with the independent Bayesian posterior and tree payoff traversal. The hand-calculated regression uses two legal hypothetical pairs after a limp and call.

The candidate uses chart probabilities, the existing five starting-hand categories and a single count model. Generate four, 32 or 128 labeled opportunities per position/action-history/depth cell for the respective profile prefixes. Use an isolated RNG seeded by 63000000 + 100 × stream + style index. At later SB opportunities condition training holding draws on the earlier SB action. Labeled holdings are available in this synthetic training sampler. The estimator sees only grouped action counts and the production chart, and no ground-truth probabilities, style label, held-out holding or future board. Standard production profile training uses the existing Phase 4K completed-history runner on disjoint seeds and remains fixed across arms. Labeled synthetic training is a deliberately more informative data source than real-world shown hands.

For each combo and public context, add local category counts to eight pseudo-observations distributed according to the production chart's fold/passive/aggression groups. Add cross-depth counts scaled by 8 / (total cross-depth category count + 8). Project empirical pseudo-counts onto nonzero chart groups, normalize, and divide an aggressive group among sizes by the original chart proportions. With zero evidence the likelihood is the chart. Apply once per observed Villain action. At the end of preflop compute the candidate/production probability ratio. Multiply the captured production incoming river reach by this ratio and normalize. This counterfactual holds earlier postflop action likelihoods and every production prune fixed, so the candidate changes weights on identical support. It measures the effect of preflop likelihood reweighting through a fixed pipeline.

## River factorial

| Configuration | Observed river wager likelihood | Villain response to Hero |
| --- | --- | --- |
| A | Production | Production |
| B | Exact reference | Production |
| C | Production | Exact reference |
| D | Exact reference | Exact reference |

Run baseline, candidate and exact incoming oracle in each. For the oracle outside first-river-solve support, share Phase 4O's compatible reach-weighted extension for production wager probabilities. For missing production response columns, use the existing Phase 4L nearest-rank extension for every arm. The exact incoming oracle includes true preflop, flop and turn weights up to the observed river wager. The D oracle computes values under both true inputs. Scores reflect the finite-step selector and the best common legal action is the regret benchmark. Report each factor's effect in both settings and the difference of differences. Retain full combo vectors, likelihoods, responses and action values for the archived case and candidate losses of at least 0.50 bb in any configuration.

## Metrics and gate

Use 10,000 percentile board-block bootstrap samples with seed 4349. Each resample retains every paired row on a board across style and stream. Inference conditions on the sampled training streams and styles. Report stream-specific estimates for sensitivity. The study does not estimate population uncertainty across opponents or training streams from two sampled streams.

- A mean gain ≥ +0.05 bb and paired 95% lower bound > 0.
- A worst loss ≤ 0.50 bb and no more than 10% of rows with loss > 0.01 bb. Report count and total cost at a 0.000001 bb threshold.
- Every matched opponent mean in A ≥ −0.03 bb.
- Mean final-preflop TV improves by ≥ 0.01 on identical support. Report error contribution and weight by five starting-hand categories, and high-card, pair and two-pair-plus mass on river posteriors as a value/bluff composition proxy. Regret, support coverage, density, action frequencies and subgroup deltas are descriptive alongside the gate.
- Median incremental reweighting time < 5 ms and peak traced allocation < 256 KiB on captured arrays, excluding offline count fitting and the common live replay. Zero invalid distributions, illegal recommendations or unexpected fallbacks.
- A candidate that clears every gate is eligible only for a separately proposed duplicate-deal and seat-swapped gameplay evaluation with frozen profiles, adaptation-disabled and current production controls, paired bb/100, illegal action and fallback counts. Any failed gate rejects progression.

Replay under Python hash seeds 13 and 31, single-threaded BLAS. Compare all deterministic fields, excluding time and memory. Preserve the frozen inputs and all results. Development and historical run before holdout. Record SHA-256 of the protocol, runner, tests, chart data and reused reference runners before holdout.
