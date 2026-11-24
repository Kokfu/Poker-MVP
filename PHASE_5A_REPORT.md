# Phase 5A — River action evaluator architecture comparison

**Select Option C, a hybrid architecture.** Keep CFR as the strategy generator and use a separate bounded tree to check concrete river action values. With known inputs, the bounded tree matched the independent ledger on all 280 actions and selected the best action in every case. With Coach inputs, it ranked the same 65.9% of materially distinct pairs correctly as CFR and chose the same action as CFR's EV-greedy selector on all 72 decisions. Its worst proposed switch cost **10.749 bb** in the matched model and **11.356 bb** under opponent mismatch. That rules out using the current point estimates to override advice. [Frozen protocol](PHASE_5A_PROTOCOL.md) · [Primary holdout](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

## Evaluators and common inputs

Coach reconstructs the public action history and obtains a profile from preceding completed hands when one is available. The incumbent solver updates combo reaches through the history and applies its postflop working-set filter, which drops weights below 0.005 of the maximum while retaining the acting Hero combo. This selection can remove mass when historical strategy is written back into the main range. The native postflop tree uses discrete targets, normally half pot and pot at opening depth, pot at first raise depth, then effective all-in choices. Earlier streets close into equity leaves. The river uses fixed-board outcomes. DCFR builds range strategies and the final value traversal propagates their reaches, evaluates terminals, and uses a compatible-reach denominator. A float32 showdown product is one source of numeric error. Profile locks can change the final strategy. The raw action values price a fixed final policy. They need no converged CFR solve once both continuation policies have been supplied. [Production solver](backend/solver/bot.py) · [Value traversal](backend/solver/cfr.py) · [Action abstraction](backend/solver/tree.py)

Coach samples the full-precision root mix using a deterministic draw and legalizes the selected action. For example, a call that exhausts Hero's stack can become `all_in` in the concrete menu. The display rounds action EVs separately. Phase 5A uses seed `917` to match the Phase 4 research witnesses. A greedy selector, the highest-mass action and the seeded draw are all scored independently, with the probability-weighted mix recorded as a separate endpoint. [Coach replay](backend/coach/service.py) · [Coach explanation](backend/coach/explain.py) · [Research runner](backend/research/holdem/phase_5a.py)

| Arm | Evaluator | Engineering footprint |
| --- | --- | --- |
| A | Current CFR action-value traversal. Known-model runs fix both continuations and train only Hero's actual root with DCFR. Estimated-model runs use the real Coach solve. | Reuses the production strategy generator and value code. Dense range strategy training and replay remain the costly parts of the native path. |
| B | `ExactRiverEV`, an independent enumerator for terminal actions and wagers with only immediate fold/call replies of positive mass. | Straightforward independent check, including short covers and overbet refunds. A raise reply makes the affected branch unsupported. |
| C | Bounded vectorized river tree traversal using the existing `holding_values`. Prices a supplied full finite response tree with raises and later Hero choices. | Reuses the existing menu and payoff interfaces. The estimated-input test gets its continuation from the actual Coach trace. Deployable independent inputs or integration would need their own work. |

All comparators receive the same public decision, normalized compatible range, and holding-specific conditional future response laws within each experiment. A's working-column reductions are measured as interventions. The public action likelihood used to build the incoming posterior and the reply probability after a candidate action are separate inputs. Exact EV is net cash change after refund and award, divided by the big blind. Five public and two Hero cards leave 990 compatible physical holdings. A reference action value is conditional on an explicit finite menu and a fixed subsequent Hero policy. The natural panel has synthetic cards, public paths and response laws. The source also contains independent price and accounting controls. [Frozen protocol](PHASE_5A_PROTOCOL.md) · [Independent cash ledger](backend/research/holdem/action_ev_reference.py) · [Exact enumerator](backend/research/holdem/river_ev.py) · [Bounded values](backend/research/holdem/reply_forecast.py)

## Independent validation

The ledger uses chip transfers and settles independently of the evaluator's terminal contributions. Treys independently ranks compatible holdings. The controls include check, fold, ordinary call, short cover and uncalled-chip refund, ties, legal raises and reraises, and exact price-grid bets through an overbet and effective shove. The pure-bluff grid fixes the caller to a holding that always wins at showdown, with 100 chips in the pot. A 25-chip bluff breaks even at 20% folds and earns 25 chips at 40%. A 50-chip bet earns 10 chips at 40%. A 100-chip bet loses 20 chips even at 40%. The bluff fixture also verifies that a Hero-blocked combo with large supplied weight contributes no mass. The separate short-call control pays 40 chips into a 120-chip contest, refunds the unmatched 20, and returns −28 or +8 chips at 10% or 40% win probability. The tied hold'em tree checks a bet to 25, raise to 100 and reraise to 250 before the call. [Deterministic evaluator tests](backend/test_research_holdem_phase_5a.py) · [Exact payoff tests](backend/test_research_holdem_river_ev.py) · [Engine settlement controls](backend/test_research_holdem_phase_4z.py)

A separate production replay played bet 125, raise 500, reraise 1,250 and call into an initial 500-chip pot. The engine, cash ledger, tree evaluator and CFR agreed at +1,750, +250 and −1,250 chips for Hero win, tie and loss. [Concrete reraise control](benchmark-results/phase-5a-2026-11-19/reraise-engine-control.json)

## Known-model evaluation

The 72 frozen decisions cross six board/Hero holdings, three training streams and four reference styles. Each style appears 18 times and each river geometry appears 24 times. Starting depths 9, 15 and 30 bb contribute 20, 24 and 28 decisions. Profile prefixes 0, 3, 30 and 100 contribute 16, 20, 20 and 16. The expanded root menu covers all frozen price buckets where stacks allow. The final tree has up to 71 nodes. The same explicit reply matrix and the same public Hero tail apply to all supported prices. Later Hero actions call at each decision in this experiment. The resulting oracle is conditional on that tail and the finite size menu. [Frozen schedule](benchmark-results/phase-5a-2026-11-19/frozen.json) · [Per-action ledger](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

| Evaluator | Scored actions | EV MAE (bb) | Correct pairs | Incorrect positive advantage | Seeded EV (bb) | Seeded regret mean / max (bb) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A · CFR, up to 896 Villain holdings | 280 | 0.119787 | 521/537 (97.0%) | 4/74 | 2.506957 | 0.002119 / 0.143894 |
| B · exact closing and fold/call | 224 | < 10⁻¹⁰ | 330/330 (100%) | 0/46 | 2.496051 | 0.013025 / 0.375144 |
| C · bounded tree | 280 | 0.000000 | 537/537 (100%) | 0/70 | 2.509076 | 0 / 0 |

Regret in the table uses the complete frozen menu. B had zero regret within its supported menu and omitted 56 actions that admitted raises with positive probability. On B's shared support, A had 0.139385 bb MAE and 317/330 correct pairs (96.1%). A's greedy, modal and seeded EV all averaged 2.506957 bb. Its mixed EV was 2.506782 bb with 0.002295 bb regret. The paired 95% interval for C's mean gain over A's draw was [0.000, 0.012] bb. The small decision difference here reflects a known conditional model and context-specific close choices. [Known results and intervals](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

The identical-column ledger comparison bounded A's numerical error to 0.000053 bb. A full-support zero-iteration value pass stayed within 0.000037 bb, showing that action-value traversal itself priced the prescribed play accurately without learning a root mix. The 896-column projection omitted up to 7.15% of compatible mass and moved one action value by 1.642 bb. Using the additional wager sizes under the same known range, replies and Hero tail improved the best supported EV by 0.023 bb on average and 0.364 bb at most. The largest gap was on board 4 / stream 543 versus loose-passive, where a 250-chip bet beat the best action in the native menu. [Projection and sizing evidence](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

The natural fold/call reduction produced zero pure-bluff actions with zero showdown equity among callers. Profitable and unprofitable pure bluffs are covered separately by the frozen grid. Every known-model chooser took all four profitable covers and passed on the other 20 closing decisions. With estimated inputs, all three seeded choices took only two of those four covers and took one of the other 20. Faster exact scoring with the same range estimates gives the same closing-call decisions. [Holdout actions](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json) · [Pure-bluff controls](backend/test_research_holdem_phase_5a.py)

## Estimated-model evaluation

The native menu gives 208 actions. The Coach trace supplies the same range and future policies to all arms. Its published root action supplies the seeded incumbent. Each concrete action is scored in expected net bb under the traced subsequent Hero policy. Harm counts compare the actual action EV to the seeded incumbent and use a 0.01 bb threshold. The incumbent's own harm count is zero by construction. A positive advantage is incorrect when actual advantage is at or below 0.01 bb. [Native menus, policies and results](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

| Matched profile style | Actions | EV MAE (bb) | Correct pairs | Incorrect positive advantage | Seeded EV (bb) | Seeded regret mean / max (bb) | Harm vs A |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A · incumbent CFR | 208 | 2.537 | 145/220 (65.9%) | 18/35 | 1.350 | 1.134 / 9.839 | 0/72 |
| B · supported exact | 168 | 2.552 | 79/120 (65.8%) | 7/18 | 1.567 | 0.917 / 10.749 | 8/72 |
| C · bounded tree | 208 | 2.537 | 145/220 (65.9%) | 18/35 | 1.469 | 1.015 / 10.749 | 9/72 |

B's shared-support comparison gives all evaluators 2.552 bb MAE and 79/120 correct pairs. B excludes 40 live wager branches on which the estimated opponent can raise. Its apparent mean regret gain over A is +0.217 bb with paired 95% interval [−0.150, +0.686] bb. C's mean gain is +0.119 bb [−0.374, +0.654]. Both intervals include zero. All intervals use the frozen crossed board/stream bootstrap. [Common-support metrics and crossed intervals](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

| Matched-profile selection | Mean true EV (bb) | Mean regret (bb) | Maximum regret (bb) | Harm vs A |
| --- | ---: | ---: | ---: | ---: |
| A · root mixture expectation | 1.349 | 1.136 | — | — |
| A · modal action | 1.383 | 1.102 | 10.749 | 8/72 |
| A · actual seeded action | 1.350 | 1.134 | 9.839 | 0/72 |
| A · greedy by displayed model before rounding | 1.469 | 1.015 | 10.749 | 9/72 |
| C · pure EV maximizer | 1.469 | 1.015 | 10.749 | 9/72 |

C differed from the incumbent draw in 24 cases. Its choices matched A's unrounded greedy choices in all 72. Any observed difference in choice between C and incumbent therefore comes from recommendation selection in this comparison. On board 3 / stream 542, a loose-aggressive case with an empty profile, Hero held J♣ K♦ on 2♦ 8♦ 9♦ 9♠ 3♣ and faced 500 into 1,000 chips. The model priced a fold at 0 and the incumbent shove at −1.564 bb. The independent reference priced the shove at +10.749 bb and the call at +7.119 bb. The greedy switch to folding therefore turned a predicted +1.564 bb gain into a −10.749 bb loss. [Matched worst switch](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

In the mismatched evaluation A and C both had 2.923 bb MAE, with 122/220 correct pairs (55.5%). C's 11 harmful switches included a move from fold to shove priced at +0.592 bb that lost 11.356 bb. This was board 0 / stream 542, a three-hand loose-aggressive profile scored against the tight-passive reference. B had 2.883 bb MAE and 73/120 correct pairs (60.8%) on the restricted support, the same ranking as A and C on that support. Seeded mean regret was 1.310 bb for incumbent, 1.455 bb for B and 1.440 bb for C. C's paired mean gain was −0.131 bb [−0.950, +0.409]. [Mismatched profiles and choices](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

### Error attribution

| Repricing of the same native tree and Hero tail | Matched action-weighted MAE (bb) |
| --- | ---: |
| Estimated range and replies | 2.537 |
| Oracle range, estimated replies | 0.931 |
| Estimated range, oracle replies | 2.783 |
| Oracle range and replies | 0.000 |

The incoming range had mean total variation 0.683 from the reference. The mean absolute interaction between range and reply substitutions was 0.900 bb. Oracle replies alone raised the MAE under the estimated range. This means the two errors can offset one another in a particular action value. The attribution holds the current reply and tail policies fixed in each relevant intervention. It does not predict the effect of training a different strategy on corrected data. Reweighting across the final native working-set boundary moved EV by less than 10⁻¹⁵ bb on average, because the estimated range had effectively already lost its mass outside those columns during replay. The raw CFR scoring error on those columns was at most 0.000006 bb. The separate oracle cap sensitivity shows that projection can matter when the input still has broad support. [Full four-cell attribution and projected inputs](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

| Price or action | Known count | A known MAE (bb) | Estimated count | C estimated MAE (bb) |
| --- | ---: | ---: | ---: | ---: |
| Small | 20 | 0.086 | 0 | — |
| Medium | 36 | 0.156 | 20 | 1.933 |
| Large below pot | 20 | 0.131 | 0 | — |
| Pot | 20 | 0.145 | 20 | 3.011 |
| Nonclosing overbet | 16 | 0.206 | 0 | — |
| Closing shove | 48 | 0.228 | 48 | 4.380 |
| Closing cover | 24 | 0.133 | 24 | 5.007 |
| Ordinary call | 24 | 0.094 | 24 | 2.621 |
| Check | 24 | 0.044 | 24 | 1.478 |
| Fold | 48 | < 0.001 | 48 | 0.000 |

| Profile style | A known MAE (bb) | C estimated MAE (bb) | A / C seeded regret with estimates (bb) |
| --- | ---: | ---: | ---: |
| Tight-passive | 0.170 | 2.897 | 1.336 / 0.646 |
| Loose-passive | 0.209 | 2.516 | 0.876 / 0.485 |
| Tight-aggressive | 0.058 | 2.412 | 0.983 / 1.418 |
| Loose-aggressive | 0.042 | 2.322 | 1.343 / 1.511 |

With matched styles, C's estimated MAE by 0, 3, 30 and 100 prior hands was 2.901, 3.283, 2.173 and 1.791 bb. The 100-hand mismatch still produced 2.801 bb MAE. Style, geometry and training-prefix effects are descriptive and based on six boards. [Per-style, price and prefix summaries](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json)

## Runtime, memory and reproducibility

The board-warmed holdout reports median, nearest-rank p95 and maximum in milliseconds. Known A includes the 80 iterations with both continuations fixed. Estimated A times the post-solve action-value pass. B includes its own re-enumeration and ranking of 990 physical holdings. C receives already prepared matchup outcomes and conditional replies. The separate Coach row measures the full native replay and advice, including the model production that B and C reuse in the estimated experiment. [Seed 13 timing](benchmark-results/phase-5a-2026-11-19/holdout-isolated-13.json) · [Seed 31 timing](benchmark-results/phase-5a-2026-11-19/holdout-isolated-31.json)

| Work unit | Hash seed 13 median / p95 / max (ms) | Hash seed 31 median / p95 / max (ms) |
| --- | ---: | ---: |
| Known A · locked DCFR | 58.020 / 342.352 / 406.749 | 69.599 / 465.552 / 592.063 |
| Known B · exact subset | 49.141 / 70.163 / 87.960 | 55.732 / 66.950 / 130.173 |
| Known C · bounded tree | 0.271 / 1.842 / 3.980 | 0.332 / 2.120 / 2.779 |
| Estimated A · native value pass | 4.305 / 14.503 / 18.199 | 4.616 / 17.563 / 20.179 |
| Estimated B · exact subset | 48.659 / 58.900 / 77.926 | 55.383 / 66.395 / 70.815 |
| Estimated C · bounded tree | 0.174 / 0.690 / 1.233 | 0.207 / 0.773 / 0.921 |
| Full native Coach advisor | 1,859.872 / 7,203.846 / 7,836.036 | 1,934.668 / 7,909.108 / 8,925.242 |

The one cold Coach sample per process took 0.900 s and 0.866 s. Those samples use the first frozen case and do not estimate a cold latency distribution. Combined holdout peak working sets were 214.9 and 215.6 MiB. The native solver used up to 1,176 columns per seat across the 216 street solves, with a maximum of 1,081 columns in the final river solve. Known A used one Hero column and at most 896 Villain columns. No unexpected solver fallback or invalid concrete action occurred in either complete run. Every one of the 72 decision records and all non-timing summary metrics matched exactly across hash seeds. [Two-seed parity](benchmark-results/phase-5a-2026-11-19/determinism.json)

The first attempt ran alongside the parallel backend suite and stopped at decision 22 because its advisor breached 15 seconds. It completed 21 decisions before that failure. The two isolated runs used the same manifest, source and schedule and completed below 15 seconds and 768 MiB. The concurrent run exposed a timing risk under machine contention. [Aborted run ledger](benchmark-results/phase-5a-2026-11-19/holdout-13.jsonl) · [Frozen manifest](benchmark-results/phase-5a-2026-11-19/frozen.json)

Fresh processes on the same fixed 95-node control measured peak memory for A/B/C at 58.6/65.6/55.8 MiB including imports and setup. The first 990-holding calls took 232.664/23.811/0.933 ms after shared input preparation. With the 990-holding input prepared, warm C took 0.711 ms median, 0.751 ms p95 and 0.751 ms max. B's 990-holding enumeration and ranking cost applies even when few holdings have positive mass. A's timing sweep was nonmonotonic across the full set of observations. Under fixed finite branching, C's cost grows with the number of holdings that need pricing and uses no dense range-by-range matchup solve. [CFR resource probe](benchmark-results/phase-5a-2026-11-19/performance-A.json) · [Exact subset resource probe](benchmark-results/phase-5a-2026-11-19/performance-B.json) · [Bounded tree resource probe](benchmark-results/phase-5a-2026-11-19/performance-C.json)

| Positive holdings | A warm median (ms) | B warm median (ms) | C warm median (ms) |
| ---: | ---: | ---: | ---: |
| 1 | 266.531 | 29.001 | 0.426 |
| 32 | 272.220 | 23.504 | 0.437 |
| 128 | 300.541 | 23.503 | 0.467 |
| 384 | 458.604 | 27.077 | 0.545 |
| 896 | 596.641 | 25.014 | 0.675 |
| 990 | 224.561 | 23.494 | 0.711 |

The measured scoring and memory of C fit an offline shadow river evaluator and B fits a bounded independent check. The end-to-end estimated path still pays for legacy range construction and CFR strategy generation. A faster scoring pass alone has little leverage on that latency. The study does not measure an independent live continuation generator or a replacement Coach workflow.

## Architecture decision and proposed Phase 5B

**Option C.** The CFR solver can value supplied river policies accurately. C makes the benchmark's complete finite response graph cheap to reprice and avoids oracle working-set truncation. B is independently useful for fold/call cross-checks but misses aggressive branches. An immediate evaluator replacement would give the same erroneous greedy action under the same estimates. The measured gaps give no basis for a full solver redesign. Retaining CFR alone would forgo a low-cost way to locate errors and audit individual recommendations. A hybrid can reuse the engine's legal action and target contract, with the integration risk concentrated in model export and decision interpretation. [Production traversal](backend/solver/cfr.py) · [Bounded evaluator](backend/research/holdem/reply_forecast.py)

1. Define a river snapshot for shadow evaluation that exports a versioned compatible range, the native concrete action menu, full-precision probabilities, and continuation provenance. Track removed support, prior versus observed-action likelihood, fallback reason, and the exact sampled action.
2. Price the native menu with C in shadow mode. Cross-check terminal and fold/call-only actions with B. Add timing, probability, legal-target and conservation assertions. Track both the value gap and the action gap without altering advice.
3. Freeze a new paired panel with natural states, aggressive reraises, the existing pure-bluff controls and independent positive and negative cover cases. Stress both posterior and future response laws jointly. Test whether the estimated advantage of a concrete override stays above the incumbent across plausible laws, especially in the observed large-loss cases.
4. Use the individual recommendation as the primary safety endpoint and report the mixed value separately. Retain the 15-second advisor ceiling and the previous severe-loss and profitable-cover checks. Require independent paired and seat-swapped gameplay against incumbent and `equity` before any promotion decision.

## Verification and Git status

- All **1,036 backend tests** passed across seven non-overlapping file groups in 663.6 seconds wall time, including the full 215-test research set. Collection retained all 1,030 Phase 4Z IDs and added six. The focused river evaluator suite passed 19 tests under each of hash seeds 13 and 31. Full test groups reported the existing dependency deprecation warnings. The dependency check passed. [Collection](benchmark-results/phase-5a-2026-11-19/collected.txt) · [Full test groups](benchmark-results/phase-5a-2026-11-19/) · [Focused seed 31](benchmark-results/phase-5a-2026-11-19/focused-31.txt) · [Dependencies](benchmark-results/phase-5a-2026-11-19/pip-check.txt)
- The frontend production build and Coach strategy rendering passed. Match, Single Hand Replay and Persistent Match Replay rendered with local histories. Local API smoke with unset, zero and enabled research flags reproduced the archived Match replays and passed Coach legality, fallback-count, chip conservation and history validation checks. Defaults matched explicit zero. [Production build](benchmark-results/phase-5a-2026-11-19/frontend-build.txt) · [Coach render](benchmark-results/phase-5a-2026-11-19/frontend-coach.txt) · [Match and Replay renders](benchmark-results/phase-5a-2026-11-19/frontend-match-replay.txt) · [Local API smoke](benchmark-results/phase-5a-2026-11-19/api-smoke-loopback.txt)
- `main` remains at `3e89367d88e32771f2789218640a0452443c21ed`, 19 ahead of local `origin/main`. The Phase 5A status delta is two Markdown documents, the research runner and its tests. All 191 archived Phase 4Z source and solver artifact hashes matched, and the 194-file Phase 5A source manifest was verified on both holdout runs. Git whitespace checks passed with the existing line-ending notice on `backend/test_poker.py`. Production behavior, research defaults and prior fixtures were preserved. [Git status](benchmark-results/phase-5a-2026-11-19/final-status.txt) · [Frozen manifest](benchmark-results/phase-5a-2026-11-19/frozen.json)

## Reproduction

From `backend`, use the installed `.venv` Python. Set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to `1`. Create a fresh output directory and use `python -m research.holdem.phase_5a` with the arguments below. Use `PYTHONHASHSEED=13` for the first holdout and `31` for the reversed run. Allow at most 1,200 seconds per holdout process. Run the resource probes in fresh processes with the same thread settings and finish the test suite before measuring latency.

| Operation | Arguments |
| --- | --- |
| Develop on the disjoint panel | `development OUT/development.json` |
| Freeze sources and case schedule | `freeze OUT/frozen.json` |
| Holdout seed 13 | `holdout OUT/holdout-13.json --manifest OUT/frozen.json` |
| Holdout seed 31 | `holdout OUT/holdout-31.json --manifest OUT/frozen.json --reverse` |
| Deterministic parity | `compare OUT/determinism.json --runs OUT/holdout-13.json OUT/holdout-31.json` |
| Resource probe for each arm | `benchmark OUT/performance-A.json --arm A` (repeat for `B` and `C`) |
