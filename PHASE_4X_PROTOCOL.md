# Phase 4X frozen river decision protocol

Frozen 19 November 2026 before running or inspecting the Phase 4X holdout. The Phase 4W panel is diagnostic data. The experiment runs offline. Coach and Match continue to default to their incumbent strategy.

## Policies

| Arm | Frozen execution |
| --- | --- |
| A | Incumbent replay and solver with the persistent-reach flag disabled |
| B | Phase 4W live replay, separately owned persistent beliefs and current-root DCFR with the flag enabled |
| C | Offline bounded mixture of A and B. On closing decisions, use the entire A policy and its seeded action. |

A and B use the same Coach replay, public profile and showdown model, original action menu, DCFR schedule, and chooser seed 917. For B retain the 0.005 relative cutoff and the nominal ranked projection capped at 896 columns per seat. Scratch buffers and selection never modify the persistent ranges. A keeps its historical relative cutoff and uncapped legacy projection. C uses the same legalized concrete menu union and the fixed 0.50 bb downside budget.

The candidate compares B with A after receiving both policies. For each of the three possible showdown outcomes, compute the worst net-chip change allowed by arbitrary per-action fold/call replies. Each aggressive action admits the immediate fold transfer and the fully matched showdown transfer for that outcome. Calls and folds have known transfers per outcome. Sum the smaller signed contribution for each action, then take the minimum across outcomes. This lower bound holds after averaging any compatible holding weights and fold/call reply probabilities. Mix in the maximum fraction of B whose lower bound is at least −0.50 bb. Leave closing decisions with A. Use A or B's original seeded recommendation when its entire policy is used. Otherwise sample the mixture in sorted concrete action order using the existing seed-917 chooser. Candidate code receives no reference opponent, future data or held cards. The bound applies to policy expectation under the scored fold/call continuation, with matched-stack refunds and the actual odd chip.

## Historical diagnosis

Recreate all 18 Phase 4W losses greater than 0.01 bb and the largest nonclosing and closing benefits. Require archived mix, chosen action, displayed values and independently scored payoff parity. Record actual global ranges and selected IDs for the worst case. Recompute river values using the final CFR policy, modeled compatible posterior and independent per-branch net transfers. For prior, last-wager likelihood and future-reply substitution use the full 2×2×2 cross. Hold the live CFR reply law fixed on its evaluated columns and extend it to omitted columns by nearest sampled showdown rank, averaging at equal rank. For the reference reply law use its fixed fold/call continuation. Compare the eight full-support value vectors and their greedy decisions with the actual A and B mixtures. Interpretation is conditional on the fixed continuation and shared menus. Use legal size endpoint checks under the piecewise reference law.

Run the ranked and weighted projection sensitivity matrix at 32, 128, 384 and 896 columns with weighted seeds 17 and 29. Test decision sampling seeds 917, 17, 29 and 53, half and fourfold river iterations, halved and doubled odds on losing holdings in the projected inputs, a grid mixing modeled and reference continuation values, plus depth and earlier raise-size changes where legal. Exact scoring stays fixed for same-state stress runs and is recomputed with the same reference laws on altered geometries. Preserve nominal historical outputs. Exclude all historical analyses and stresses from promotion statistics.

## Independent holdout

Use 12 fresh boards from deal seed 448202, three new training streams 321/322/323, and the four fixed Phase 4K synthetic opponent styles. Generate paths, depths and bet sizes via the Phase 4Q generator with orientation by stream index. Rotate 0/3/30/100-hand profiles using the executable schedule. Nonclosing states deliberately oversample three-hand profiles. Prior profile hands use the established separate training generator. No new bots or profile fit parameters enter the paired arms. The frozen manifest lists every scheduled row and SHA-256 hashes for all evaluated Python source, solver inputs and both protocols. Verify this manifest before each run.

Generate all policies before assembling the reference. Use the common Phase 4S synthetic posterior and the fixed style's fold/call reply law for all arms. Score full-precision normalized legal mixes on the same unique concrete menu per paired row. Independently cross-check the chip arithmetic for every candidate action. Report decision regret against the best action in the common menu, as well as mean, worst-case, and per-style paired EV, harmful row counts and profitable closing-call changes. The primary endpoint is C−A in bb per decision. Report B−A and C−B for context. Use a two-sided crossed 95% bootstrap interval with 10,000 resamples and seed 44003. Resample board indices and training streams independently while keeping all styles together in each crossed cell.

Use one BLAS thread and warmed matched board-equity caches. Alternate A/B timing order and reverse it in the second run. Time end-to-end replay and advice, excluding training and scoring. C's time is the sum of the required baseline replays and the measured policy-layer overhead. Closing C requires only A. Report median, nearest-rank p95, maximum, and process peak resident memory including training, caches, and all arms. Use Python hash seeds 13 and 31 in separate bounded processes, with 1,200 seconds per holdout. Compare all complete deterministic records and numerical summaries across seeds. Apply the resource gates in both runs.

## Promotion gates

- C−A mean at least +0.05 bb and crossed 95% lower bound strictly above zero.
- Worst C−A at least −0.50 bb. At most 10% of decisions may lose more than 0.01 bb.
- Every opponent's C−A mean at least −0.03 bb.
- Zero unexpected fallbacks, complete pairs, lawful concrete targets, finite normalized mixtures within 1e-12, identical scoring states, exact payoff agreement within 1e-10 bb, and at least one changed policy above 1e-12 total variation.
- Each positive-EV closing call keeps incumbent call mass within 1e-12 and incurs no new seed-selected fold.
- Individual maximum 15 s, C median no greater than twice A, and process peak at most 768 MiB. B stays within its frozen projection limit. Deterministic row and numerical summary parity across hash seeds and verified freeze manifests.

All gates apply. No retuning after the holdout. Passing would authorize planning a separate duplicate-deal and seat-swapped gameplay benchmark against the incumbent, adaptation disabled, and the existing equity baseline with independent fixed-profile seeds. Gameplay readiness requires that separate experiment. Both live flags remain opt-in.
