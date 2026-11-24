# Phase 4U protocol

## Decision and information boundary

The primary comparison is the exact paired river EV of E minus A in big blinds per decision. Production Coach and Match use their existing strategies. All new code runs in the offline research layer.

An observed Villain action updates Phase 4T's persistent range through its full-support likelihood at the historical state and board prefix. A future reply is a conditional distribution over the legal children of a proposed Hero action. The exact scoring law is a third component. It uses the archived independent Bayesian posterior and the four fixed Phase 4K synthetic call laws. The reference is available only to scoring and historical diagnostics. It supplies neither forecasts, posterior scenarios, proposals nor gate decisions. Current hidden Villain cards and later board cards are unavailable to the policy.

## Arms and inputs

| Arm | Strategy |
| --- | --- |
| A | Incumbent production solver and chooser, instrumented through the existing Coach replay probe |
| B | Phase 4T independent observed-action likelihood and current-decision-only DCFR, with its original mix |
| C | B with independent reply repricing and a nominal best-EV proposal when a reply can occur. A terminal decision proposes B unchanged. |
| D | B with the inherited Phase 4S closing rule, which suppresses calls when the lower endpoint of its closing-call EV is nonpositive |
| E | C's proposal, accepted only when its incremental EV over A is positive in every specified model. Otherwise use A's original mix. |

All arms use the same concrete root menu, cards, deal lines, public profiles and chooser seed. Hero's downstream strategy is frozen at B's solved continuation, across both compared root mixes and all model scenarios. This can depend on the working set. The future Villain reply law and range do not. B uses the existing DCFR iteration schedule, 0.005 relative reach cutoff and maximum 896 combinations per seat. A uses its incumbent cutoffs. All terminal payoffs use net chips relative to the root with refunds and the engine's odd-chip rule. When a nonclosing C action is selected by reprice, keep B's mix on numerical ties within 1e-9 chips, otherwise propose the first maximum in tree order. To identify response effects separately from greedy selection and full-range repricing, also report the nonclosing C result versus CFR replies with the same full range, fixed Hero continuation and proposal rule. The inherited nearest-rank fill is used only for that CFR research diagnostic.

## Frozen forecast and sensitivity model

Use public **river** counts from completed, independently played training hands. Fold and aggressive-raise counts share the facing-wager denominator. Subtract them from the denominator to count continuations without raising, including short all-in calls. The beta-binomial working model assumes these continuation and conditional-raise events are exchangeable for the purpose of estimating intercepts. Anchor the continuation odds at a half-pot wager. Use Beta(1,1) for continuation and Beta(1,7) for raising conditional on continuing. The latter has mode zero and mean 1/8, encoding aggression as the less frequent continuation with modest prior weight. Use posterior means under these assumptions. River histories mix bet sizes, checks followed by bets, raises and all-ins. Their intercepts are pooled approximations, and the model's credible intervals do not account for context, bluff selection, or serial dependence.

At a reply node let P be the pot before the wager increment and c the collectible cost to call, capped by effective stack. Use the public geometry to remove any refundable overhang. Multiply the anchor continuation odds by (P+c)/(3c), the ratio of the modeled price odds to the half-pot anchor. Multiply continuation and conditional raise odds by 1/3, 1, or 3 for the inherited board-only high-card, pair, or stronger tiers. Under a legal raise, discount conditional raise odds by 1/(1+c/S) where S is the effective stack at risk before the wager. Split raise probability equally over legal raise sizes and shoves. With no aggression available, assign all continuation to the legal call. Internal tree calls are legalized to engine all-in covers when needed. Closing Hero calls have no Villain reply. These hand gradients, price elasticity and raise split are structural assumptions.

For each of the two beta marginals use equal-tailed 97.5% endpoints. Under the stated binomial assumptions the rectangle has at least 95% joint posterior mass by the union bound. The decision test uses the **finite model scenarios** below. The joint credible-mass statement attaches to the intercept rectangle alone, with no coverage claim for the scenarios, the final EV interval or opponent behavior.

- Use the nominal forecast and all 16 combinations of the two marginal endpoints, a flat versus the nominal strength gradient, and smallest versus largest legal aggression. Move intercept choices together across reply nodes. Omit response variants at decisions that end the hand.
- Evaluate each forecast against the nominal full posterior, a uniform preflop prior with the same postflop likelihood factors, and a separate fixed-factor omission for each observed postflop Villain action. Hold the other estimated factors fixed. These stress a categorical uncertainty about one evidence source, motivated by the earlier prior and likelihood failures, and have no assigned posterior probability.
- Evaluate the **same** difference, proposal minus incumbent, under every combination. Report the minimum and maximum. The interval also covers finite convex mixtures of these complete joint models by linearity. It does not cover independently chosen parameters per node, every continuous parameter setting within the beta rectangle, joint omission of multiple evidence sources, or arbitrary real opponents. Require the minimum to exceed 1e-9 chips. A disagreement or a tie retains the incumbent. No penalty is applied to calling.

## Frozen samples, analysis and gates

Development uses deal seed 441201, four boards, and training stream 201. Holdout uses deal seed 441202, eight boards crossed with streams 211, 212 and 213 and all four unchanged Phase 4K opponent families, for 96 decisions. For each stream use the existing per-style independent training seeds and the Phase 4Q case factory with orientation by stream index. The 0/3/30/100 profile prefixes rotate by board and stream, with starting depths 9/15/30 bb. Replays have preselected Hero/Villain actions. Reference replies in this fresh panel fold or call. Legal raises and unequal-stack refund cases are exercised in independent toy fixtures. Historical fixtures and development rows cannot count toward promotion. Keep the same opponents, metrics and acceptance gates after outcome access.

Use 10,000 crossed percentile bootstrap resamples, seed 44003, resampling whole boards and whole training streams independently. Keep the four fixed styles together in each crossed cell. Report two-sided 95% paired intervals and per-style means. A complete matched result is required. Report all contrasts from A, E versus C, and the matched nonclosing reply-only control. Additional summaries are median and maximum regret versus the best supported reference action, losses greater than 0.01 bb, maximum loss, closing-call mass and seeded counts, proposal acceptance, first-reply marginal excess Brier and hand-weighted Brier, and fallback frequency. Calibration is oracle-scored under the same reference posterior across forecasts and is descriptive.

E must pass every gate in both hash-seed runs.

- Mean E−A at least +0.05 bb and a strictly positive lower paired 95% endpoint.
- Worst E−A at least −0.50 bb and at most 10% of decisions losing more than 0.01 bb.
- Every fixed opponent's E−A at least −0.03 bb.
- All matched policies legal and normalized, with zero unexpected solver fallbacks and exact payoff agreement.
- At least one actual adjustment accepted. No closing call with positive exact EV loses call mass beyond rounding error of 1e-12, and no new seeded fold on such a call.
- Maximum replay 15 s, median no more than 2× A, runner peak resident memory at most 768 MiB. Measure warm replays with the same board caches and alternating A/B order. Charge E both replay paths and its policy work. Score references, train profiles and warm board caches outside the replay timer. The peak is runner-wide and includes those stages.
- Match all deterministic rows and summaries across Python hash seeds 13 and 31. Exclude only time, memory and their corresponding gate fields from this comparison. Use one BLAS thread, with 1,200 s maximum per holdout process. Check the frozen source and generated-case manifest before each replay. Re-run the working-set and hidden-card probes.

Passing these gates would justify a separate duplicate-deal, seat-swapped gameplay validation with independent seeds, incumbent and adaptation-disabled controls. Failing any gate yields a research no-go for this candidate. Historical results can identify mechanisms that the fresh panel does not cover. Full live multi-street replay equivalence is outside this current-decision experiment.
