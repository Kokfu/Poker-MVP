# Phase 4Y — River reply forecasts and individual recommendation safety

**Strategy promotion no-go.** Future-reply error alone reversed the historical bluff ranking. The Phase 4X mixture also produced a severe displayed-action loss for a different reason. It retained the incumbent's high shove probability and changed the order used to sample the mix. On 64 fresh pairs, its worst mixed adjustment was −0.191 bb. Its worst seeded adjustment was **−8.204 bb**, and its mean seeded change was **−0.110 bb**. Phase 4W had a larger mean mixed gain and also failed individual downside. Phase 4Y did not introduce a strategy candidate. The Coach and Match retain their incumbent defaults. [Frozen protocol](PHASE_4Y_PROTOCOL.md) · [Fresh paired evidence](benchmark-results/phase-4y-2026-11-19/holdout-13.json)

## How Coach advice becomes one action

1. Coach replays public actions through the engine and supplies the public decision state and earlier completed-hand profile to the advisor. In Phase 4W, chart reach and public observation likelihoods construct the persistent opponent belief. Legacy replay uses the earlier solver policies for postflop reach updates. The last Villain bet is **observed evidence** for range inference. It is separate from a forecast of what Villain will do after a potential new Hero action. [Coach service](backend/coach/service.py) · [Persistent beliefs](backend/research/holdem/live_persistent.py) · [Public observation likelihood](backend/research/holdem/decoupled_replay.py)
2. The river tree assigns discrete concrete targets using the exact pot, commitments, effective stacks, minimum raise, and all-in merge rules. DCFR supplies hand-dependent replies and a Hero policy from the same bounded game. Default confidence-weighted locks fit pooled response statistics at matching nodes when supported, with optional showdown-driven strength dependence. At zero relevant evidence the solver's reply comes from equilibrium in the modeled game. It can be precise about the geometry and severely wrong about this opponent. This experiment uses the default unsized reads. [Tree](backend/solver/tree.py) · [DCFR](backend/solver/cfr.py) · [Opponent locks](backend/solver/exploit.py)
3. The Coach river advisor samples the full-precision average strategy in tree order, then legalizes the selected action. The SHA-256 seed includes the advisor seed, match and hand identity, street and public action count. The API uses seed 0 by default. The replay experiments use the frozen seed 917. The frontend displays the returned concrete action and shows the rounded frequencies and estimated EVs in its explanation. Neither the rounded frequencies nor maximum-frequency action are used to select the displayed recommendation. Match uses the same solver family with its own independent feature flag. [Chooser and legalization](backend/solver/bot.py) · [Coach explanation](backend/coach/explain.py) · [Coach display](frontend/src/Coach.tsx) · [Match factory](backend/simulation/match_service.py)

Mixed-policy EV is the inner product of the concrete probabilities and exact reference action values. Modal EV is the reference value of the most probable concrete action. Seeded EV is the reference value of the concrete action actually drawn. Each action value integrates over all 990 compatible hypothetical opponent holdings and the reference replies. A realized chip result would require a played trajectory with one holding and one response. The replay EVs in this report are conditional expectations. Settlement tests independently exercise actual completed engine histories. [Exact river evaluator](backend/research/holdem/river_ev.py) · [Action-risk scorer](backend/research/holdem/phase_4y.py)

## Historical reproductions

The original 4W −17.690 bb adjustment and the 4X −17.690 bb diagnosis are the same tight-passive case. All historical policies and reported actions were reproduced against their archives. Aligned holding weights, effective ranges, observed-wager likelihoods, full action mixes, seeded and modal choices, absolute regret and public action logs are in the five replays. [Historical replays](benchmark-results/phase-4y-2026-11-19/historical-final-13.json) · [Phase 4W report](PHASE_4W_REPORT.md) · [Phase 4X report](PHASE_4X_REPORT.md)

| Hero and board | Public river position, chips | Exact menu EV, bb | Archived failure |
| --- | --- | --- | --- |
| Ah 9c · Tc 8s 5d Kh Jd | Villain bet 500 into 1,000. Hero 2,500 behind, Villain 2,000 behind | Fold 0, call −4.773, shove −17.901 | B mixed −17.690 vs A. B seeded and modal shove vs A fold, −17.901 |
| Qd 8h · Ad As 5c 2c Kc | Villain bet 500 into 1,000. Hero 2,500 behind, Villain 2,000 behind | Fold 0, call +0.350, shove −9.639 | 4X C mixed +0.230 vs A. C seeded shove vs A fold, −9.639 |
| Td 3h · 9s 7s 3s 2h 7h | Villain bet 600 into 1,200. Hero 900 behind, Villain 300 behind | Fold 0, call −1.432, shove −3.136 | 4U gate accepted pure shove. Mixed −2.347 and seeded −1.704 vs A |
| Jd 4h · 2d 5h Kc Qd Js | Villain shoved 550 into 700. Hero can cover 550 | Fold 0, cover +1.315 | Earlier conservative rule always folded. A and the 4U gate drew cover |
| Qc 4s · 3s 7c 7h 4c Ks | Villain shoved 1,000 into 1,000. Hero can cover 1,000 | Fold 0, cover +5.547 | 4T sensitivity rule removed A's 50% cover mass, costing −2.774 mixed. A also drew fold, so the paired seeded difference was zero. Both folds had 5.547 bb regret |

**Ah 9c.** On B's projected range, the solver predicted 63.41% folds, 36.59% calls and zero raises to the 2,500-chip shove. The exact reply law on those same holdings gave 30.15% folds and 69.85% calls. The reference's own posterior gave 17.54% folds. Replacing only the future reply law moved shove EV from +0.362 to −11.789 bb. Then replacing the posterior with the reference's moved it to −17.901 bb. The model had zero prior river reply opportunities. The one-pair group contributed +31.45 percentage points of the common projected-range fold bias. Full posterior TV from the reference was 0.736 for A and 0.508 for B. B assigned 98.94% to the shove. A assigned 99.83% to fold. The projected reply and action arithmetic agree with 3,960 independently completed and validated engine histories. [Aligned reply and prior factors](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json) · [Engine settlement rerun](benchmark-results/phase-4y-2026-11-19/engine-settlement.txt)

**The edge was thin even under the modeled range.** Interpolating 2.98% of the way from B's reply law to the reference law on the same projected holdings is enough to erase the +0.362 bb edge over fold. That moves the marginal fold forecast about 0.99 percentage points, from 63.41% to 62.41%. Call remains −1.808 bb in that test. The pure-bluff breakeven rate when every call loses is 62.5% for risking 25 bb to win 15 bb. In the crossed audit, changing the observed-wager likelihood alone also reverted the choice to fold, as did changing the incoming prior alone. These are component interventions inside the reference experiment. [Historical substitution grid](benchmark-results/phase-4y-2026-11-19/historical-final-13.json)

**Qd 8h.** C's shove mass was **52.99%**, down from A's **55.26%**. Both modal actions were shove. A's order was fold, call, all-in. C used all-in, call, fold. The same seeded uniform draw, **0.192833**, landed in A's 22.37% fold interval and C's 52.99% shove interval. Resampling the identical C weights in A's order gives fold. The −9.639 bb result follows from the research sampler's ordering and the mix's large inherited weight on an unsafe action. The published action conversion correctly reflected each draw. C's reference regret on the shove was 9.989 bb against the +0.350 bb call. B mostly called, with 99.987% call mass. A and B both overpredicted folds on their own projected ranges, at 49.08% vs 1.12% for A and 77.46% vs 14.36% for B. B's predicted shove remained positive (+10.526 bb) after a reply-only correction on its own range. Its posterior TV was 0.497. This case also needed range correction to identify the true action value. [Recorded draws, distributions and forecasts](benchmark-results/phase-4y-2026-11-19/historical-final-13.json)

**Td 3h and terminal calls.** On Td 3h, 4U estimated the call at +5.510 bb and the shove at +6.452 bb. Its 85-scenario interval favored the switch, [+1.187, +15.332] bb. The reply model called the shove 83.44% on its own range and 88.60% on the true range. The reference called 97.04%. Substituting replies alone kept a positive adjustment on the modeled range (+2.232 bb). Substituting only the range flipped the improvement to −0.423 bb. Modeled range TV was 0.650. For Jd 4h and Qc 4s, the legal response to the opponent's already-committed shove closes the hand and has no Villain reply. The earlier conservative rules lost profitable calls even when the model's central call estimate was positive. The Jd 4h diagnostic also reproduced a fold under that rule with the exact posterior supplied. Blanket shove-folding or using uncertainty width as a reason to override a profitable incumbent call would repeat that failure. [Phase 4U decomposition](benchmark-results/phase-4u-2026-11-18/holdout-harm-diagnostics.json) · [Phase 4T closing controls](PHASE_4T_REPORT.md)

## Wager-size calibration

Native A/B forecasts were audited on every offered wager, including unchosen ones. A native pot-size reply could legally reraise. The Phase 4K paired reference continuation uses fold/call only. The grid adds the separate hand-dependent Phase 4M shove reply when legal, crossing each price with 0.75 and 3.0 starting SPR where the action fits. In each controlled grid, public-path reference weights remain fixed while the offered price changes. All probabilities use the same reference posterior within each row in these tables. Native EV error includes the chosen solver's range error. The JSON also contains same-range EV errors, reply-only EV substitutions, reference mass outside the CFR working set, counts, geometry and blocker-stratified fold bias. [Native and grid row data](benchmark-results/phase-4y-2026-11-19/holdout-13.json)

| Native arm and size | Branches | Fold / call / raise predicted, % | Reference, % | Holding excess Brier | Log loss / reference | EV MAE / max / usage-weighted, bb |
| --- | ---: | --- | --- | ---: | --- | --- |
| A pot | 4 | 46.30 / 31.94 / 21.76 | 33.31 / 66.69 / 0 | 0.476 | 2.483 / 0.464 | 0.780 / 1.210 / 0.766 |
| B pot | 4 | 56.60 / 24.95 / 18.44 | 33.31 / 66.69 / 0 | 0.629 | 2.820 / 0.464 | 1.143 / 1.448 / 1.143 |
| A closing shove | 20 | 50.21 / 49.79 / 0 | 27.79 / 72.21 / 0 | 0.317 | 1.532 / 0.416 | 4.359 / 18.816 / 3.377 |
| B closing shove | 20 | 58.08 / 41.92 / 0 | 27.79 / 72.21 / 0 | 0.435 | 1.760 / 0.416 | 4.807 / 15.677 / 4.932 |

B overpredicted closing shove folds in each style. Its predicted vs reference rates were 43.76% vs 21.63% tight-passive, 48.92% vs 21.85% loose-passive, 67.80% vs 33.78% tight-aggressive, and 71.83% vs 33.91% loose-aggressive. Thirty of 64 rows, including 12 of 16 three-hand profiles, had zero river reply opportunities. Accurate exact sizing and compatible holdings do not identify hand-by-price response behavior with those profiles. The larger error on high-stakes branches matters even when the average probability score improves. [Native style and coverage strata](benchmark-results/phase-4y-2026-11-19/holdout-13.json)

The frozen native rows aligned profile length with betting path. At three prior hands, all 16 native shoves followed limp-call preflop and a half-pot river opening. At 30 prior hands, all four followed a big-blind three-bet and a pot-sized river opening. The respective B fold biases were +27.00 and +43.42 percentage points. These are joint strata. The paths, precise prices, and profile lengths cannot be attributed separately in that comparison. In the controlled grid, closing-shove EV MAE was 1.459 bb at 0.75 SPR and 3.958 bb at 3.0 SPR, so the pooled category conceals large price and risk differences. [Conditional strata](benchmark-results/phase-4y-2026-11-19/conditioning-strata.json)

A post-holdout check used all four profile lengths for each fixed public case and style. It scored 80 B replays and 256 grid runs on the same corresponding reference posteriors. B recomputes both its range and replies when the earlier profile changes. For the grid, only the input counts change. This diagnostic uses the same boards and supplies no additional promotion evidence.

| Prior hands | B native shove fold, % | B EV MAE, bb | Grid shove fold, % | Grid EV MAE, bb |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 59.30 | 5.059 | 55.34 | 4.151 |
| 3 | 58.18 | 5.186 | 54.49 | 3.976 |
| 30 | 49.80 | 4.063 | 39.73 | 2.310 |
| 100 | 35.70 | 3.523 | 25.55 | 1.779 |
| Reference fold, % | 27.79 | | 31.15 | |

More prior evidence narrowed some errors. At 100 hands, the grid underpredicted mean folds, B still overpredicted them, and both retained substantial action pricing errors. The result is scoped to the simulated reference styles and the observed profile generator. [Crossed profile evidence](benchmark-results/phase-4y-2026-11-19/profile-cross.json)

| Phase 4U forecast on controlled grid | Branches | Fold / call / raise predicted, % | Reference, % | Holding excess Brier | Log loss / reference | EV MAE / max, bb |
| --- | ---: | --- | --- | ---: | --- | --- |
| Small | 128 | 25.12 / 64.51 / 10.37 | 22.35 / 58.48 / 19.17 | 0.075 | 0.869 / 0.731 | 0.844 / 3.565 |
| Medium | 128 | 33.70 / 57.98 / 8.32 | 22.35 / 58.48 / 19.17 | 0.093 | 0.918 / 0.731 | 1.340 / 4.983 |
| Pot | 64 | 41.29 / 51.03 / 7.68 | 22.35 / 58.48 / 19.17 | 0.129 | 0.974 / 0.731 | 2.524 / 7.632 |
| Overbet | 64 | 44.84 / 48.58 / 6.57 | 37.01 / 53.40 / 9.59 | 0.090 | 0.814 / 0.677 | 2.256 / 7.952 |
| Closing shove | 128 | 43.80 / 56.20 / 0 | 31.15 / 68.85 / 0 | 0.109 | 0.531 / 0.382 | 2.709 / 14.401 |

| Grid EV MAE by style, bb | Small | Medium | Pot | Overbet | Closing shove |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tight-passive | 0.679 | 1.111 | 2.272 | 2.012 | 2.372 |
| Loose-passive | 0.977 | 1.683 | 3.268 | 2.934 | 3.639 |
| Tight-aggressive | 0.887 | 1.332 | 2.334 | 2.128 | 2.502 |
| Loose-aggressive | 0.832 | 1.236 | 2.221 | 1.949 | 2.321 |

The independent forecast passes price and legality controls. It uses collectible call cost, the pot and the effective stack, board-derived hand tiers, and pooled reads. It tilts continuation odds smoothly with price and scales conditional aggression with stack pressure. The reference only changes its call rates across a pot-size boundary and raises strongly with value when legal. In this benchmark the price tilt and pooled aggression prior missed that behavior. Native and grid rows use different geometries and reference continuations, so their numbers do not establish a model ranking. Blockers remove impossible holdings and influence posterior and showdown strength. The reference reply law has no direct card-blocker term within a strength tier. Earlier public bets affect the native action state and reaches, and observed actions update both model and reference ranges. The grid holds that range fixed, so it cannot identify a separate causal effect of earlier action history or a direct blocker effect. [Independent forecast](backend/research/holdem/reply_forecast.py) · [Reference continuation](backend/research/holdem/phase_4m.py)

Short all-in calls use the matched amount and return the uncollectible overhang. In a 600-chip offer into 400 against 300 behind, the collector charges 300, returns 300 and settles a 1,000-chip contest. Both forecasts assign zero raise mass in a closing branch. A reachable legal reraise appears in the controlled grid, and independent chip-transfer formulas agree with the tree traversal for every grid branch. [Phase 4Y tests](backend/test_research_holdem_phase_4y.py) · [Engine short-call and flag regressions](backend/test_research_holdem_phase_4w.py)

A supplemental exact sweep scored all integer engine-legal raise targets, alongside fold, call and all-in as applicable. It included 1,503 actions each for the deep Ah 9c and Qd 8h cases and confirmed the best actions were fold and call, respectively. The deep cases allowed a raise to 1,000–2,500 total. On Td 3h the minimum raise exceeded Hero's 900-chip ceiling, so its only aggression was a short all-in raise. Jd 4h and Qc 4s had only fold and cover. On the fresh panel, 17,748 concrete actions were scored under the same fold/call reference. Two rows had a better target outside the CFR menu. Raising to 1,000 improved on the best menu value by 1.561 bb against tight-aggressive and 1.484 bb against loose-aggressive, both on the deep 7c 7d line. The sweep quantifies menu coverage. The frozen paired statistics use the common native menu. [All legal target values](benchmark-results/phase-4y-2026-11-19/exact-target-sweep.json)

## Fresh holdout and promotion gates

All 64 scheduled rows completed under both seeds, with eight independent boards, two profile streams, and four styles. All methods were scored on the same concrete actions in each pair. The estimates use the frozen crossed 95% bootstrap. Two training streams limit the interval's resolution. Values and changes are in bb per decision. [Seed 13](benchmark-results/phase-4y-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-4y-2026-11-19/holdout-31.json)

| Comparison | Endpoint | Mean Δ vs A | 95% interval | Worst Δ | Losses >0.01 / >0.50 bb |
| --- | --- | ---: | --- | ---: | ---: |
| B · Phase 4W | Mixed | +1.129 | [+0.070, +3.708] | −4.987 | 5 / 4 |
| B | Seeded action | +0.960 | [−0.159, +3.368] | −8.204 | 5 / 4 |
| B | Modal action | +1.199 | [0.000, +3.910] | −5.316 | 4 / 3 |
| C · Phase 4X | Mixed | +0.016 | [0.000, +0.045] | −0.191 | 3 / 0 |
| C | Seeded action | −0.110 | [−0.541, +0.102] | −8.204 | 2 / 1 |
| C | Modal action | 0.000 | [0.000, 0.000] | 0.000 | 0 / 0 |

| Individual risk metric | A | B | C |
| --- | ---: | ---: | ---: |
| Mean mixed / seeded exact EV, bb | 4.445 / 4.647 | 5.574 / 5.608 | 4.461 / 4.537 |
| Max mixed / seeded regret, bb | 24.332 / 24.333 | 8.947 / 8.949 | 24.332 / 24.333 |
| Max regret of an action with positive mass, bb | 30.857 | 30.857 | 30.857 |
| Mean / max mass more than 0.50 bb worse than A's seeded action | 4.02% / 75.31% | 6.25% / 100.00% | 4.01% / 77.53% |
| Draw differs from mode | 7 | 4 | 6 |
| Mixed downside passes and seeded downside fails | 0 | 0 | 1 |

C changed 19 mixes and three draws. Its draw-vs-mixed paired delta correlation was 0.427. Modal C had the same actions as modal A on all 64 rows, so switching the display to modal would have offered no improvement here and would still have displayed the historical losing Qd 8h shove. B recovered positive closing calls but lost 4.987 bb mixed on a different closing call with no future-reply term. A and C drew fold on four of the 16 exact-profitable closing calls. B drew fold on zero and added no per-row profitable-call regressions on this panel. C preserved every closing mix and choice. Of 28 losing closing calls, A and C drew fold on 23 and B on 26. [Row-level actions, showdowns and risk](benchmark-results/phase-4y-2026-11-19/holdout-13.json)

**Worst fresh seeded change.** On 7c 7d / As Kh 9c 6s 5c, A drew a −0.745 bb call. B and C drew a −8.949 bb shove. B put 99.97% on shove and C put 77.53%, with A at 75.31%. B priced shove at +6.687 bb. True replies on B's projected weights still priced it at +5.650 bb, while B replies on the exact posterior priced it at −8.607 bb. This is a range-driven sign reversal with additional fold bias. On the exact posterior, multiplying the reference fold odds by 0.8–1.25 moved shove EV from −9.528 to −8.289 bb. On B's full posterior the same schedule gave +5.516 to +5.825 bb. The range error dominated the perturbation. A different row, Qh 9d against loose-aggressive, crossed zero for shove as fold probability moved from 17.10% to 20.09%. The positive call still beat it. A sign change versus fold is weaker evidence than a change in the best legal action. [Forecast swaps and stress rows](benchmark-results/phase-4y-2026-11-19/holdout-13.json)

| Frozen promotion requirement | B | C |
| --- | --- | --- |
| Mixed mean ≥ +0.05 bb and lower bound > 0 | Pass | **Fail** |
| Seeded mean ≥ +0.05 bb and lower bound > 0 | **Fail** | **Fail** |
| Worst mixed ≥ −0.50 bb | **Fail** | Pass |
| Worst seeded ≥ −0.50 bb | **Fail** | **Fail** |
| Both harmful-adjustment rates at most 10% | Pass | Pass |
| Mixed mean ≥ −0.03 bb per style | Pass | Pass |
| Changed policy, no profitable-call regression | Pass | Pass |
| Legal normalized advice, exact settlement cross-check, zero unexpected fallbacks | Pass | Pass |
| Runtime, memory, working set and reproducibility | Pass | Pass |

| Arm | Seed 13 median / p95 / max, s | Seed 31 median / p95 / max, s |
| --- | --- | --- |
| A | 0.590 / 1.509 / 1.812 | 0.576 / 2.030 / 2.573 |
| B | 0.055 / 0.684 / 1.004 | 0.068 / 0.622 / 0.955 |
| C | 0.602 / 1.544 / 2.351 | 0.578 / 2.050 / 2.573 |

Peak whole-process RSS was 248.56 MiB and 276.89 MiB. B used one current-root solve with at most 896 columns per seat. There were zero unexpected fallbacks and zero lost rows. On separate probes of each arm's slowest warm row from seed 13, clearing the equity cache before end-to-end advice gave 2.636 s for A, 3.425 s for B and 4.823 s for C. Mixes and draws matched the warm run. Both hash seeds verified the 192-file freeze, and all 64 deterministic decision rows and derived statistics matched after excluding timing and memory. All five historical replays also reproduced deterministically. [Cold-cache probes](benchmark-results/phase-4y-2026-11-19/cold-cache-probes.json) · [Frozen inputs](benchmark-results/phase-4y-2026-11-19/frozen.json) · [Determinism](benchmark-results/phase-4y-2026-11-19/determinism.json)

## Architecture decision

Keep persistent range ownership available for tracing and retain the incumbent's single-action strategy. Errors in future replies and in the range inferred from observed actions can each move the apparent action advantage across zero. A defensible new chooser would need a reliably signed advantage for the proposed concrete action against the incumbent's displayed action, with calibrated errors for both the range and continuation. The Phase 4U example shows how a range-and-reply envelope can share a wrong sign. The Phase 4X example shows why the same safety budget on a mixture cannot certify its draw. Changing the action order alone fixes the reproduced draw on one case and leaves its modal shove in place. The evidence does not establish a rule that improves recommendations while preserving profitable calls, so this phase adds no candidate.

The Phase 4Z or Phase 5 direction is a trace-only exercise for evaluating paired concrete-action advantages on independently covered price, SPR and hand-strength strata, with separate closing-call equity diagnostics. The milestone for considering an action change should be out-of-sample coverage of adverse action EV and positive action advantage for the same proposed replacements. Current public counts leave too much of the hand-by-price response law unidentified. A future policy passing both exact-EV gates still requires the separate paired duplicate-deal and seat-swapped gameplay benchmark before any promotion.

## Verification and reproduction

The full backend suite passed 1,025 tests in 26m 09s with eight dependency deprecation warnings. Collection preserved all 1,021 Phase 4X test IDs and added four deterministic controls. FastAPI TestClient used Windows loopback because the default sandbox blocked its local asyncio socket path. The research suite passed 204 tests under hash seed 31. The 21 focused exact-EV, range-flag, and safety tests passed under each hash seed. [Backend test log](benchmark-results/phase-4y-2026-11-19/backend-tests-loopback.txt) · [Test collection](benchmark-results/phase-4y-2026-11-19/collected.txt) · [Research tests](benchmark-results/phase-4y-2026-11-19/research-tests-31.txt) · [Focused seed 13](benchmark-results/phase-4y-2026-11-19/focused-13.txt) · [Focused seed 31](benchmark-results/phase-4y-2026-11-19/focused-31.txt)

The frontend production build, Coach strategy rendering, and Match and both Replay renders passed. Local API smoke passed advice, Match and both Replay modes with unset, explicit zero and enabled flags. Unset flags matched explicit zero. Match replays reproduced both Phase 4X documents and passed event-by-event chip conservation. The focused suite exercises independent flags, short all-in refunds and lawful normalized probabilities. All research inputs and application smoke traffic were local. [API smoke](benchmark-results/phase-4y-2026-11-19/api-smoke.txt) · [Frontend build](benchmark-results/phase-4y-2026-11-19/frontend-build.txt) · [Coach render](benchmark-results/phase-4y-2026-11-19/frontend-coach.txt) · [Match and Replay render](benchmark-results/phase-4y-2026-11-19/frontend-match-replay.txt)

The backend dependency check passed. Git is on `main` at `3e89367`, 19 commits ahead of local `origin/main`. The status delta from Phase 4X consists of the protocol, this report, the offline runner and the regression tests. The 189 archived Phase 4X hashes still match. Git and new-file whitespace checks passed, with the existing line-ending advisory on `backend/test_poker.py`. No commit, push or deployment was made. [Dependency check](benchmark-results/phase-4y-2026-11-19/pip-check.txt) · [Git status](benchmark-results/phase-4y-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-4y-2026-11-19/status-delta.txt) · [Source and link checks](benchmark-results/phase-4y-2026-11-19/source-and-link-check.txt)

Use the installed backend environment from the backend directory, set BLAS/OMP/MKL threads to one, and create a fresh output directory. Use `python -m research.holdem.phase_4y freeze OUTPUT/frozen.json`. Run `historical OUTPUT/historical-13.json` with `PYTHONHASHSEED=13`. Run `holdout OUTPUT/holdout-13.json --manifest OUTPUT/frozen.json` under hash seed 13 and the same under seed 31 with `--reverse`. Run `compare OUTPUT/determinism.json --runs OUTPUT/holdout-13.json OUTPUT/holdout-31.json` with the same module. Each holdout has a 1,200-second process timeout and an incremental .jsonl ledger. [Runner](backend/research/holdem/phase_4y.py)
