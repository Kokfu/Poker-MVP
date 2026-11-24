# Phase 5D — Opponent range and future reply reliability

**Recommendation — improve the opponent-profile data model.** Incoming range error caused the largest individual loss and the largest average action-EV error. Reply error remained consequential with the correct incoming range, particularly on closing or large wagers. Existing public logs can distinguish some of those price effects, but the incumbent pooled profile cannot. The 96 frozen decisions reproduced under both hash seeds.

## Opponent modeling architecture

| Stage | Incumbent computation | Observable inputs and assumptions |
| --- | --- | --- |
| Profile | Coach replays completed stored hands into `OpponentModel` and, for adaptive advice, `ShowdownModel`. | Public actions, targets, pots, legal opportunities and street. Showdown strength features use only revealed hands and are subject to selection bias. Profile counts are separately maintained from the current hand. |
| Prior | Legacy replay starts with uniform combination reaches. The nearest-depth preflop chart supplies a policy at each abstract node. An adaptive profile can change chart locks and trigger a chart re-solve. | Position, effective starting depth, blinds, stack and observed preflop actions. The learned chart and the mapping from off-tree targets are modeling assumptions. |
| Past-action likelihood | Preflop replay multiplies by the mapped chart row. Legacy postflop replay solves each street and multiplies by the average CFR strategy of the mapped action on retained columns. | Public prefixes, board, approximated sizing and profile-based locks. The likelihood of an already observed action is a distinct quantity from the response to a hypothetical next action. In the legacy path, the same strategy machinery supplies both. |
| Incoming range | The legacy path normalizes reach after applying Hero/card blockers for advice and tracing. The opt-in persistent replay maintains separate board-legal reaches and a Hero-conditioned posterior, with a standalone postflop likelihood law. | The physical blocker mask is determined by Hero's cards and the public board. The relative weights of compatible unseen holdings depend on the model. Retained columns set to zero during legacy updates can propagate loss of support into later streets. |
| Working set | Legacy CFR selects columns by relative reach. Opt-in persistent replay creates scratch projections and freezes the full posterior. | Numerical optimization and range approximation. Full-support shadow pricing extends off-column replies by nearest showdown rank. That extension is another research assumption. |
| Future reply | CFR's average policy gives Villain's conditional reply probabilities in the finite tree. Coach's default adaptive path applies pooled street locks with confidence and showdown-strength weighting. The count-based research forecast applies fixed hand and size tilts to pooled river continuation and raise counts. | Concrete menu, price, effective stack, legality, observed profile and assumptions about how behavior changes with holding and wager. The sized proposal has coarse internal postflop buckets. The incumbent adaptive Coach uses pooled street locks. |
| Value and choice | CFR prices the projected tree. Coach draws from the incumbent policy using its seeded chooser. The bounded shadow traverses the same fixed tree and continuation for private research. | Production values and probabilities are observable for diagnosis. The reference-only quantities are the full conditional law of the hypothetical opponent, their future counterfactual replies, and exact regret under those assumptions. |

The four-arm audit changes inputs to a common cash ledger after the production recommendation has been made. It retains the native root actions, every concrete target, Treys showdown outcomes and the same recorded Hero continuation. A versus B and A versus C therefore isolate substitutions **within this finite decision problem**. D establishes the best available action in that problem. Its value cannot establish the best action in an unrestricted sizing game. The expanded probe solves an alternate menu solely to measure probability forecasts on a common incoming reference range. [Coach service](backend/coach/service.py) · [Solver replay and selection](backend/solver/bot.py) · [Profile](backend/simulation/opponent_model.py) · [Persistent beliefs](backend/research/holdem/live_persistent.py) · [Forecast](backend/research/holdem/reply_forecast.py) · [Cash ledger](backend/research/holdem/action_ev_reference.py)

## Independent experiment

The frozen schedule crosses four styles, six river geometries and four profile lengths over 96 distinct deals and independent training streams. Public paths include both positions, limps, single raises and three-bets, multiple flop/turn lines and 9, 15 and 30 bb starts. Reference posteriors use exact products of documented synthetic action likelihoods. All scores integrate the reference distribution directly, with clipping used only to keep log scoring finite. Reported intervals resample whole decisions within style and public wager strata. They quantify schedule-specific uncertainty under the specified laws. Held-out decisions use same-style legacy training histories, so profile-length results include transfer across response laws. The separately generated paired-history experiment measures identifiability under a matched data-generating design. [Protocol](PHASE_5D_PROTOCOL.md) · [Frozen manifest](benchmark-results/phase-5d-2026-11-19/frozen.json) · [Runner](backend/research/holdem/phase_5d.py)

## Independent range accuracy

Range accuracy is scored against exact conditional weights over every compatible pair. The street rows use only cards and actions available by that prefix. The river projection row measures the current solve's truncation against the same river truth. Earlier legacy truncation can already be present in the incoming river row.

| Stage | TV | Missing reference mass | Mean combo error × 1,000 | Effective size estimated / reference | Brier | Log loss | Excess log loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Starting prior | 0.000 | 0.0% | 0.000 | 1225.0 / 1225.0 | 0.99918 | 7.111 | 0.000 |
| After preflop | 0.443 | 0.0% | 0.723 | 688.9 / 893.6 | 1.00142 | 10.468 | 3.661 |
| After flop | 0.516 | 30.0% | 0.954 | 494.8 / 760.3 | 1.00602 | 13.515 | 6.842 |
| After turn | 0.593 | 36.5% | 1.146 | 369.5 / 704.2 | 1.01268 | 14.913 | 8.302 |
| After river prefix | 0.659 | 42.7% | 1.330 | 280.7 / 565.2 | 1.02341 | 15.963 | 9.508 |
| River CFR projection | 0.661 | 45.2% | 1.334 | 280.4 / 565.2 | 1.02369 | 16.383 | 9.928 |

The uniform starting prior matches the uniform-deal reference before actions. No card conflicts were found at any prefix. The per-street posterior shifts below hold each row's street-start deal and profile fixed. Earlier evidence carries through each stage. The binary likelihood scores apply to the realized **past action category** on the reference incoming mixture. Legacy assigns zero likelihood outside the columns available to its update. A chart action mapped to one target and the reference's broader preflop action class can have different granularity.

| Street | Opponent actions | Likelihood absolute error | Estimated / reference event probability | Incoming estimated mass off columns | TV change from street entry [95% interval] |
| --- | --- | --- | --- | --- | --- |
| flop | 96 | 34.2% | 36.3% / 59.5% | 0.2% | 0.073 [0.057, 0.090] |
| preflop | 128 | 28.4% | 36.9% / 39.7% | 0.0% | 0.443 [0.400, 0.487] |
| river | 86 | 13.1% | 8.5% / 12.0% | 0.2% | 0.066 [0.053, 0.079] |
| turn | 104 | 39.1% | 32.4% / 61.3% | 0.1% | 0.077 [0.057, 0.098] |

At the river the estimated high-card / pair / two-pair-or-better masses averaged 19.6% / 40.3% / 40.1%. The respective reference masses were 11.9% / 42.7% / 45.4%. Mean absolute error in Hero's win mass was 17.2%. Reference mass at zero and near-zero predictions drives the log-loss penalty. The river bin below 0.01% contained about 48% of all holding rows. Its mean predicted probability per holding was 0.00063%, versus 0.103% under the reference. In the 1%–5% bin the means were 1.89% estimated and 0.148% reference. The largest TV increment entered with preflop action conditioning. Later streets increased TV while legacy updates shed support. Current-street projection added another 0.002 TV on average.

River TV by Hero position was big blind 0.683, button 0.634. By preflop path it was bb threebet 0.708, limp call 0.635, limped 0.573, open call 0.609, sb call threebet 0.854. Working-set projections at caps of 64, 384 and 896 preserved both public reaches and the immutable Hero-conditioned vector in the six audit rows. The independent refund and blocker controls also passed. [Range and stage scores](benchmark-results/phase-5d-2026-11-19/summary.json)

## Independent future reply accuracy

Every forecast below is scored with reference incoming weights. At later nodes the common conditional weights also use the reference probabilities of prior branch actions. Native CFR was originally solved on its estimated ranges. The expanded probe independently re-solves the legal quarter-, half-, pot-, overbet- and all-in menu on common reference Villain weights and a uniform board-legal Hero range. The pooled-count forecast uses the same reply nodes and weighting. This separates scoring on the correct range from recomputing CFR with it.

The native forecast was scored at **172** reachable nodes. Mean multiclass Brier was 0.673, excess Brier 0.294 and log loss 1.730 nats. Each action's holding-weighted MAE averages its error before marginalizing over holdings. An all-in raise is distinct from a call that exhausts the caller's stack.

| Reply | Nodes offering it | Estimated | Reference | Holding-weighted MAE |
| --- | --- | --- | --- | --- |
| all in | 64 | 14.7% | 9.0% | 13.4% |
| bet | 10 | 18.5% | 28.2% | 28.8% |
| call | 54 | 41.4% | 55.7% | 29.8% |
| check | 10 | 62.0% | 62.1% | 26.9% |
| closing call | 108 | 50.6% | 64.7% | 29.0% |
| fold | 162 | 47.2% | 35.2% | 28.8% |
| raise | 13 | 7.6% | 2.6% | 6.7% |

| Collectible wager | Nodes | Fixed-range CFR fold bias (pp) | Pooled-count fold bias (pp) | CFR / pooled excess Brier | CFR / pooled log loss |
| --- | --- | --- | --- | --- | --- |
| quarter | 12 | -5.6 | -0.6 | 0.330 / 0.030 | 2.562 / 0.918 |
| half | 30 | +3.7 | +2.5 | 0.277 / 0.062 | 2.102 / 0.899 |
| pot | 38 | +20.9 | +6.8 | 0.379 / 0.084 | 2.202 / 0.869 |
| overbet | 9 | +6.5 | +2.1 | 0.224 / 0.054 | 1.943 / 0.830 |
| closing | 107 | +29.9 | +5.7 | 0.437 / 0.070 | 1.733 / 0.553 |

Wager buckets use the collectible price divided by the matched pot before the call. Min-bet clipping and all-in merging can move or eliminate a proposed size. The short all-in control offered 900 chips to an opponent with 400 behind. It verified a 400-chip collectible amount, a 500-chip refund and a legal fold/call menu. The table gives each reachable node equal weight. Later closing nodes often have low reference reach. Restricting to immediate replies still gave fixed-range CFR fold bias of +14.1 pp across 16 closing offers and +8.8 pp across ten pot-sized offers. The expanded half-pot set contained 11 legal reraise nodes. Their fixed-range CFR reraise forecast averaged 7.4% versus 3.1% reference. In the native probability bin from 80% through 100%, the mean forecast was 94.6% against 58.0% actual reference frequency. The pooled-count forecast scored better on every tested facing-wager size on the expanded tree. Its fixed hand and price tilts remain structural assumptions, and the result is specific to the synthetic laws and probe menu.

| Candidate against best passive | Wagers | Mean fold bias (pp) | Fold MAE | Crossing sign errors | Within 5 pp of true break-even |
| --- | --- | --- | --- | --- | --- |
| bluff | 77 | +6.1 | 21.2% | 24/71 | 3/13 |
| value or neutral | 49 | +18.0 | 24.2% | 0/0 | 0/0 |

A fold-dependent bluff loses to the best passive alternative at its reference conditional nonfold EV. The value-or-neutral group retains wagers that meet the passive alternative without that fold contribution. A crossing is scored only when both models have a threshold in [0, 1]. The threshold holds each model's nonfold composition fixed. [Fixed-range reply and wager results](benchmark-results/phase-5d-2026-11-19/summary.json)

## Four-arm exact EV and individual decisions

| Arm | Per-action MAE (bb) | Material rank pairs correct | False aggressive advantages | Mean regret (bb) | Harmful choices | Mean harm (bb) | Max regret (bb) | High / severe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 2.914 | 243/344 | 13 | 1.524 | 37 | 3.953 | 20.920 | 20 / 5 |
| B | 1.382 | 276/344 | 14 | 1.061 | 23 | 4.429 | 19.310 | 13 / 4 |
| C | 2.545 | 280/344 | 12 | 1.081 | 27 | 3.845 | 20.920 | 15 / 3 |
| D | 0.000 | 344/344 | 0 | 0.000 | 0 | — | 0.000 | 0 / 0 |
| seeded | — | — | — | 1.767 | 41 | 4.136 | 20.920 | 24 / 7 |
| modal | — | — | — | 1.623 | 40 | 3.895 | 17.808 | 21 / 7 |

A through D select greedily inside each cell. The table weights action-level MAE by actions. The paired MAE intervals below weight each decision equally. Seeded and modal selection use the actual production policy mix. Every regret is priced in D. High means at least 2 bb and severe means at least 8 bb. False advantage counts aggressive actions rated materially better than passive that scored materially worse in D.

| Paired change from A | Estimate (bb) | 95% stratified bootstrap interval |
| --- | --- | --- |
| B-A MAE | -1.778 | [-2.338, -1.275] |
| B-A regret | -0.462 | [-1.233, 0.242] |
| C-A MAE | -0.331 | [-0.569, -0.112] |
| C-A regret | -0.442 | [-0.802, -0.131] |

Among A's harmful picks, single-component corrections recovered a reference-optimal choice in 20 range-only, 8 reply-only and 5 either-alone cases. 4 required both substitutions to fully remove material regret. B, C and D changed 40, 19 and 37 A choices, respectively. Within-wager sizing changes numbered 3, 4 and 3. The absolute interaction D−B−C+A averaged 0.838 bb per action and reached 11.622 bb. The projected CFR-to-ledger residual peaked at 0.00000559 bb. Pricing the full eligible range instead of the CFR working columns changed a value by up to 0.508 bb under the estimated policy.

| Reference opportunity | Available | Seeded choice |
| --- | --- | --- |
| profitable bluff | 27 | 10 |
| unprofitable bluff | 50 | 10 |
| profitable call | 44 | 13 |
| unprofitable call | 36 | 7 |

Closing-call opportunities include 5 profitable and 11 unprofitable calls. Bluff opportunities count concrete wagers and can occur twice in a decision. Calls count decisions. The opportunity statistics compare calls to folding. Another legal action can still be better than a positive call. [Action values and rank summaries](benchmark-results/phase-5d-2026-11-19/summary.json)

| Worst seeded cases | Geometry | Seeded action | D best | Regret | A / B / C EV of seeded action |
| --- | --- | --- | --- | --- | --- |
| 31 | tight aggressive · closing · 30 bb · 100 hands | all_in | fold | 20.920 | 7.364 / -20.920 / 7.364 |
| 9 | loose aggressive · overbet · 30 bb · 0 hands | fold | all_in | 17.808 | 0.000 / 0.000 / 0.000 |
| 19 | tight aggressive · overbet · 30 bb · 0 hands | call | all_in | 14.409 | 6.111 / 6.723 / 6.111 |
| 7 | tight aggressive · pot · 30 bb · 0 hands | all_in | fold | 9.818 | 0.318 / 0.340 / 0.353 |
| 2 | loose aggressive · pot · 30 bb · 3 hands | fold | all_in | 9.681 | 0.000 / 0.000 / 0.000 |

B and C retain the recorded Hero continuation and A's menu. B also holds the original CFR replies fixed, including their extension to unrepresented compatible hands. The swaps quantify component error in the tested decision. Re-solving either changed model could produce different betting responses or choices.

Of the seven severe seeded choices, B selected the reference-best action on four and C did so on two. Row 31 was the largest loss. Using a 100-hand profile, Coach still estimated +7.364 bb for covering a shove that lost 20.920 bb. The call closed betting, so only the incoming range could move that value. Row 9 folded away a shove worth 17.808 bb. Its range TV was 0.975, and the range substitution recovered the shove. On row 19 the reply substitution recovered a shove worth 14.409 bb more than the call. Row 7's seeded shove was 9.818 bb behind folding. Both single swaps still valued it above fold, and A's own greedy choice was call. This row combines a policy draw with a joint model failure.

The range correction eliminated more harmful choices and produced the larger EV error reduction. Its paired mean-regret interval includes zero. The reply correction had a smaller EV error reduction and a paired regret interval below zero on this synthetic panel. Range-only correction also **increased** mean regret in the overbet slice from 2.303 to 3.576 bb while improving EV MAE there. These findings support testing both components independently and reject additivity as a description of the tails.

## Wager, style, stack and profile slices

| Public river state | Decisions | River TV | A / B / C EV MAE (bb) | A / B / C mean regret (bb) | Seeded mean regret (bb) |
| --- | --- | --- | --- | --- | --- |
| checked | 16 | 0.687 | 2.244 / 1.819 / 1.778 | 0.886 / 0.591 / 0.305 | 1.287 |
| closing | 16 | 0.661 | 3.605 / 0.000 / 3.605 | 2.192 / 0.000 / 2.192 | 2.223 |
| half | 16 | 0.672 | 1.727 / 1.136 / 1.360 | 0.995 / 0.029 / 0.692 | 0.748 |
| overbet | 16 | 0.652 | 4.019 / 2.098 / 3.351 | 2.303 / 3.576 / 1.519 | 2.463 |
| pot | 16 | 0.614 | 3.753 / 1.248 / 3.481 | 1.691 / 0.925 / 1.181 | 2.937 |
| quarter | 16 | 0.665 | 2.439 / 1.379 / 2.158 | 1.074 / 1.245 / 0.599 | 0.942 |

| Opponent style | Decisions | River TV | A / B / C EV MAE (bb) | A / B / C mean regret (bb) | Seeded mean regret (bb) |
| --- | --- | --- | --- | --- | --- |
| loose aggressive | 24 | 0.577 | 2.778 / 0.977 / 2.791 | 1.654 / 0.635 / 1.666 | 2.140 |
| loose passive | 24 | 0.575 | 2.832 / 1.676 / 1.988 | 0.891 / 1.769 / 0.446 | 0.873 |
| tight aggressive | 24 | 0.749 | 3.350 / 1.485 / 2.736 | 2.592 / 1.363 / 1.539 | 3.076 |
| tight passive | 24 | 0.735 | 2.694 / 1.370 / 2.699 | 0.957 / 0.478 / 0.674 | 0.977 |

| Starting depth (bb) | Decisions | River TV | A / B / C EV MAE (bb) | A / B / C mean regret (bb) | Seeded mean regret (bb) |
| --- | --- | --- | --- | --- | --- |
| 9 | 20 | 0.758 | 2.520 / 0.638 / 2.323 | 0.792 / 0.234 / 0.634 | 1.172 |
| 15 | 29 | 0.648 | 1.838 / 0.902 / 1.541 | 1.055 / 0.214 / 0.687 | 1.177 |
| 30 | 47 | 0.622 | 3.683 / 1.935 / 3.209 | 2.124 / 1.936 / 1.515 | 2.384 |

| History hands | Decisions with river reply evidence | Mean river reply opportunities | River TV | Native reply excess Brier | Native reply log loss |
| --- | --- | --- | --- | --- | --- |
| 0 | 0/24 | 0.000 | 0.856 | 0.362 | 2.305 |
| 3 | 8/24 | 0.375 | 0.798 | 0.377 | 2.614 |
| 30 | 20/24 | 3.292 | 0.538 | 0.326 | 1.258 |
| 100 | 24/24 | 11.333 | 0.442 | 0.113 | 0.776 |

The profile slices use independent evaluation deals. They are descriptive across matched style labels and differing response laws. They do not isolate the effect of adding hands on the same deal. The paired public-history test below holds the input design fixed. [Subgroup results](benchmark-results/phase-5d-2026-11-19/summary.json)

## Observable limits

The paired experiment generated complete, legal engine histories for two response policies that swapped quarter-pot and closing-shove fold propensities on identical deals. Both profiles contain 409 folds and 591 calls after 1,000 logged hands. At each measured prefix their public profile summaries are identical. The implied pooled estimate is 40.9% fold for each policy, even with 500 opportunities at each price. The internal sized buckets and the actual river price plus closure in the logs distinguish the policies.

| Logged hands per policy | Quarter-pot folds, policy 1 | Closing folds, policy 1 | Closing folds, policy 2 |
| ---: | ---: | ---: | ---: |
| 0 | 0/0 | 0/0 | 0/0 |
| 4 | 0/2 | 0/2 | 0/2 |
| 30 | 4/15 | 2/15 | 4/15 |
| 100 | 29/50 | 17/50 | 29/50 |
| 1,000 | 301/500 | 108/500 | 301/500 |

At 1,000 hands the Beta(1,1) posterior fold rates at the closing price are 21.7% [18.2%, 25.4%] and 60.2% [55.8%, 64.4%]. The exact conditional fold frequencies over these sampled deals are 21.7% and 61.7%. The intervals describe the deliberately balanced synthetic price cells. Quarter pot and closure vary together in this construction. Estimating their separate effects requires histories with overlapping prices and different stack geometry. Logged opportunities in ordinary play may be rarer, correlated or concentrated in a different price/stack mix. The internal proposal-B sized buckets separate this simple example because the two prices fall into different buckets. They pool streets and do not distinguish closure, position, how many raises have occurred or collectible cost once the offered amount overhangs. [Identification evidence](benchmark-results/phase-5d-2026-11-19/identification.json)

Public action frequencies at adequately sampled contexts are identifiable. Strength-dependent replies, the composition of hands that fold, and counterfactual answers to wagers rarely made remain underidentified. Showdowns provide information about a selected subset of continuing hands. A precise aggregate fold rate cannot recover a missing price effect or separate weak-hand folding from strong-hand rarity. Historical actions and future choices can both inherit a common error from the same pooled lock. That dependency makes a second estimator using the same collapsed observations an inadequate independent check.


## Historical severe losses and warning errors

These are separate replays using the archived policies and reference laws. The table uses bb relative to the listed alternative. Where an older experiment used a mixed or reordered policy, the concrete decision is shown separately. The detailed record retains compatible holdings, estimated and reference weights, conditional reply vectors, policies, draws and per-action EVs.

| Archived decision | Estimated EV and reference EV | Recommendation and failure |
| --- | --- | --- |
| 4X / 4Y, A♥ 9♣ | Persistent shove +0.362 vs fold, reference −17.901. Estimated folding 63.41% and same-range reference 30.15%. The reference posterior gave 17.54% folds. | The persistent variant shoved, for −17.690 bb mixed delta. Reference replies alone moved the shove to −11.789 bb. An incoming-range correction could also reverse the ranking. |
| 4Y, Q♦ 8♥ | Legacy model shove −5.356 and call −4.885. Reference shove −9.639 and call +0.350. | Incumbent drew fold but placed 55.26% on the harmful modal shove. The research adjustment still had 52.99% shove mass and its changed cumulative order drew it. The persistent model's estimated shove was +7.328 and its range TV was 0.497. The replay implicates both belief error and policy-to-action conversion. |
| 4Z, Q♣ 2♦ | Persistent shove +0.918, call −0.913. Reference shove −14.849, call −3.298 and fold 0. | The persistent policy switched from the legacy call to shove, costing 11.551 bb versus that call. Either component substitution removed the false shove advantage. |
| 4Z, 7♣ 7♦ | Persistent shove +6.687, call +5.659. Reference shove −8.949, call −0.745 and fold 0. | Archived display switched from call to shove. Reference range correction reversed the ranking. All Phase 5C stresses on the legacy inputs still preferred the shove. |
| 4Z, T♦ 3♥ | The historical adjustment saw +6.452 for shove and +5.510 for call. Reference shove −3.136, call −1.432 and fold 0. | Reference replies alone left a positive modeled adjustment. Correcting the range reversed its sign. |
| 4Y / 4Z, J♦ 4♥ and Q♣ 4♠ | Legacy estimated closing calls at +2.776 and +10.970. The reference values were +1.315 and +5.547. | Conservative research rules rejected profitable calls. The Q♣ 4♠ incumbent also drew fold from a 50/50 policy despite its positive EV estimate. Neither hand has a future Villain reply. |
| 5C row 21, A♦ Q♦ | Closing call +5.372 estimated, −2.721 reference. Fold 0. Posterior TV 0.626. | Coach called. All stresses continued to favor that action. The missed high-regret case came from a range error and has no reply term. It falls below the 8 bb severe threshold. |
| 5C row 24, Q♣ 4♣ | Estimated shove −0.011, call −1.698 and fold 0. Reference shove +7.416 and call +6.273. Posterior TV 0.835. | Coach drew the reference-optimal shove. Its sensitivity alert was a false positive. |
| 5C row 46, 2♥ T♥ | Estimated shove +8.329, call −8.422 and fold 0. Reference shove −22.755 and call −14.656. Posterior TV 0.458. | Coach shoved. The indicator detected the loss. The seven severe cases in Phase 5C were all detected. The 7♣ 7♦ historical witness supplies a separate severe miss. |

The false-negative closing call and profitable rejected calls require separate explanations. A distorted incoming range can make a losing call look profitable. A policy rule or sampler can also reject a call whose estimated advantage is already positive. The 63.41% bluff case requires a price-specific reply forecast and a posterior that reflects the opponent's preceding wager. Counterfactual substitutions can each move a thin margin across zero in the same case. [Historical detail](benchmark-results/phase-5d-2026-11-19/historical.json) · [Phase 4X](PHASE_4X_REPORT.md) · [Phase 4Y](PHASE_4Y_REPORT.md) · [Phase 4Z](PHASE_4Z_REPORT.md) · [Phase 5C](PHASE_5C_REPORT.md)

## Runtime, reproducibility and reliability

Both hash seeds scored all 96 decisions and 302 concrete actions, with exact equality across canonical records. The rerun reversed order and observer pairing order. Twelve enabled/disabled pairs preserved the public advice, full-precision policy, seeded draw and CFR input fingerprints. All scored native decisions came from CFR with zero unexpected production fallbacks. The independent cash ledger matched shadow values within 1e-10 bb on common inputs.

| Measurement | Seed 13 median / p95 / max | Seed 31 median / p95 / max |
| --- | ---: | ---: |
| Coach under concurrent workload, s | 7.831 / 20.823 / 32.175 | 7.242 / 21.198 / 28.583 |
| Native observer on completed traces, ms | 28.84 / 75.81 / 127.00 | 26.78 / 58.04 / 100.18 |
| Offline scoring including expanded probe, s | 0.248 / 7.116 / 17.354 | 0.205 / 5.417 / 24.733 |
| Peak worker memory, MiB | 254.53 | 282.80 |

Parallel solves and regression processes competed for CPU. The first heavily parallel launch stopped on deadline failures. In the resumed runs, 13 seed-13 and 14 seed-31 calls exceeded the native observer's end-to-end deadline. The recovery driver retained each timeout and priced the already-computed production solution offline using the same snapshot, legal tree, probabilities and payoff ledger. The 27 recovered outcomes participate in the numerical results and determinism comparison. Their native timeouts still count against the reliability gate. Timing excludes generating the simulated historical hands. The precomputed snapshots stand in for the live storage replay cost. [Run summary](benchmark-results/phase-5d-2026-11-19/summary.json) · [Recovery driver](benchmark-results/phase-5d-2026-11-19/resume.py) · [Seed 13 timeout recovery](benchmark-results/phase-5d-2026-11-19/offline-recovery-13.jsonl) · [Seed 31 timeout recovery](benchmark-results/phase-5d-2026-11-19/offline-recovery-31.jsonl)

The 33 isolated rechecks included every unique row that exceeded any runtime budget and a control for each public wager class. Thirty-two completed on their first isolated attempt with canonical results matching the holdout. Their worst Coach, observer and offline scoring times were 13.733 s, 47.56 ms and 10.397 s. Peak memory was 306.05 MiB. The remaining row, 78, took 10.388 s to reach the observer and then timed out at 150.16 ms. Its isolated retry reproduced the outcome in 8.065 s end to end, with a 47.68 ms observer and 3.142 s of offline scoring. [Isolated runtime](benchmark-results/phase-5d-2026-11-19/runtime-isolated.json) · [Isolated retry](benchmark-results/phase-5d-2026-11-19/runtime-isolated-retry.json)

**PHASE 5D NOT COMPLETE under the frozen runtime and zero-shadow-failure gates.** The independent model accuracy and regret results cover the full schedule. The timing failures limit the observer reliability claim under the tested conditions.

## Architecture recommendation

**Direction C — improve the opponent-profile data model.** The first Phase 5E deliverable should be an offline comparison of pooled reads with contextual exposure and outcome counts: street, position, collectible price relative to the matched pot, whether the wager closes betting, and aggression depth. Build those features from events already retained in completed histories. Preserve denominators and measure how often each context has observed support. Keep revealed-hand data explicitly marked as showdown-selected.

| Consideration | Implication |
| --- | --- |
| Expected benefit | Recover size and closure effects lost by pooling. Separate observation support from extrapolation when a forecast depends on little evidence. These are prerequisites for meaningful future reply improvements; they will only partly address the composition of unshown hands. |
| Engineering cost | Moderate. Derive and reconcile contexts from public event geometry, handle historical records and short-call refunds consistently, and reuse the current replay and history validation. A parallel offline read model can test feasibility without touching charts or CFR. |
| Offline feasibility | Existing event records contain street, common-pot geometry, stack commitments, legal actions and resulting actions. A feature extractor can replay them locally and validate counts against engine fixtures. Data with no opportunities in the target context cannot establish an effect there. |
| Validation | Freeze matchup/player and time separation, contextual support minima, exact probability scores and no-look-ahead checks. Test same-law learning and transfer to differently sized policies. Measure price and closure reliability, profitable-call preservation and action-level EV and severe regret on a fresh exact-EV panel. Use paired or clustered uncertainty. A successful feature audit would justify an estimator experiment, with separate strategy acceptance evidence. |

## Reproduction

From `backend` in the existing virtual environment, use `python -m research.holdem.phase_5d` for the protocol's `freeze` and `holdout` commands. Run four shards per hash seed with `--shard I 4` for I = 0 through 3. For summary collection, name the eight completed files `holdout-SEED-I.json` in the same output directory and run `python -m phase_5d_evidence summary OUT/summary.json`. Use that same evidence module for `historical OUT/historical.json` and `identification OUT/identification.json`. [Primary seed evidence](benchmark-results/phase-5d-2026-11-19/holdout-13-0.json) · [Reverse seed evidence](benchmark-results/phase-5d-2026-11-19/holdout-31-0.json)

## Regression evidence and Git status

- All 1,052 Phase 5C test IDs remain in the backend collection. All **1,056 backend tests** passed across nine disjoint file groups, including all 235 research tests. The four focused tests also passed under hash seed 31. The sandboxed TestClient stalls were rerun with local socket access. The passing groups report existing Pyparsing and Starlette deprecation warnings. [Group evidence](benchmark-results/phase-5d-2026-11-19/verified-backend-summary.json) · [Focused seed 31](benchmark-results/phase-5d-2026-11-19/focused-31.txt)
- The frontend production build and Coach strategy rendering test passed. The offline API matrix passed Coach, Match, single Replay and Match Replay with shadow unset, zero and enabled, crossed with both persistent flags off or on. The smoke verifies identical public outputs within each persistence setting, legal recommendations, conserved chips, safe private trace behavior and unchanged RNG state. Vite rendered all four screens and Replay events from the new API histories. [Build](benchmark-results/phase-5d-2026-11-19/frontend-build.txt) · [API smoke](benchmark-results/phase-5d-2026-11-19/api-smoke.txt) · [Frontend smoke](benchmark-results/phase-5d-2026-11-19/frontend-match-replay.txt) · [Dependency check](benchmark-results/phase-5d-2026-11-19/pip-check.txt)
- Work remains on `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. The Phase 5D work adds two documents, the offline experiment, its evidence analysis and deterministic tests. The tracked diff matches the Phase 5D entry snapshot byte for byte. Production sources, default flags and prior research files were preserved. `git diff --check` passed with the existing CRLF advisory for `backend/test_poker.py`. [Git status](benchmark-results/phase-5d-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-5d-2026-11-19/status-delta.txt) · [Manifest checks](benchmark-results/phase-5d-2026-11-19/manifest-verification.txt)
