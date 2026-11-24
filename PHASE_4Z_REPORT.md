# Phase 4Z — Individual river action-EV advantage validation

**Decision C. Current action-EV estimates are too unreliable for exploitative recommendations.** On 72 frozen river decisions, the legacy and persistent paths ranked materially distinct action pairs correctly 58.6% and 65.5% of the time. The worst legacy recommendation gave up **24.180 bb** against the exact best action in its menu. The persistent path recommended a shove estimated at **+1.832 bb** over the incumbent call that actually cost **11.551 bb** against that call. Independent payoff repricing matched the solver under its own inputs within **0.000006 bb**. Opponent range and reply assumptions explain the large errors. Phase 5 should start with a read-only comparison of explicit action value, opponent input and recommendation selection. [Frozen protocol](PHASE_4Z_PROTOCOL.md) · [Fresh results](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

## How Coach advice becomes a specific action

Coach replays the public action line into the engine and passes the decision plus preceding completed-hand profile to the solver. The legacy path updates card-combo reach using the chart and previous street solves. The existing research flag builds a persistent public-conditioned belief, removes incompatible holdings, and projects it into one current-root solve. Villain's last public wager or check updates the belief. The future replies after a hypothetical Hero action are separate conditional probabilities derived from the average DCFR strategies and any applicable profile-based locks. Both paths price actions in the solved tree's discrete target-total menu. [Coach replay](backend/coach/service.py) · [Solver path](backend/solver/bot.py) · [Persistent belief replay](backend/research/holdem/live_persistent.py) · [Tree](backend/solver/tree.py) · [Profile locks](backend/solver/exploit.py)

`CFR.action_values` prices each first action by integrating the opponent's compatible reach and the locked final continuation, then adds back Hero's sunk contribution to report net chips from the decision. The frontend displays these individual EVs rounded to chips. Its explanation can compare the selected action to the highest displayed model EV. The diagnostic's incremental EV instead subtracts the EV of the incumbent's actual seeded action at the same decision. The displayed recommendation comes from a full-precision draw in tree order, followed by concrete legalization such as converting a stack-exhausting call to `all_in`. The audit uses chooser seed 917 to match the research archives. The default API uses seed 0. [Value traversal](backend/solver/cfr.py) · [Chooser](backend/solver/bot.py) · [Structured explanation](backend/coach/explain.py) · [Coach display](frontend/src/Coach.tsx)

| Quantity | Audit calculation |
| --- | --- |
| Mixed-policy EV | Sum of policy probabilities times corresponding action EVs |
| Individual action EV | Expected net bb conditional on taking that concrete action and using the specified continuation |
| Incremental advantage | Individual action EV minus the incumbent seeded action EV in the same state and model |
| Modal EV | Reference EV of the highest mass concrete action |
| Seeded recommendation EV | Reference EV of the concrete action returned by the existing chooser |
| Exact reference EV | Expected value across all compatible weighted holdings and fixed conditional reference replies |
| Realized outcome | Chip transfer on one completed trajectory. Used in the settlement controls |

## Independent payoff and range validation

The reference enumerates all 990 Hero- and board-compatible opponent holdings, conditions their weights on the public path, and ranks every showdown with Treys. For each concrete branch, an independent cash ledger transfers chips at the wager, refunds unmatched chips and awards the contested pot. The ledger prices checks, folds, calls, stack-exhausting covers, opening bets, and all-in and finite re-raise continuations. The audit checks showdown signs against the solver matrix, per-holding terminal values against tree traversal and each native action under the fold/call law against the separate `ExactRiverEV` evaluator. It also exhausts the legal integer wager targets under the unchanged fold/call law. The aggressive policy has branch-exact values on its specified finite continuation menu. Its off-menu raise tree is outside the reference scope. [Independent ledger](backend/research/holdem/action_ev_reference.py) · [Existing fold/call evaluator](backend/research/holdem/river_ev.py) · [Frozen protocol](PHASE_4Z_PROTOCOL.md)

Three completed engine paths with a bet, raise, reraise and closing cover agreed with the independent ledger for wins, ties and losses. The weighted sweep agreed with the existing exact evaluator on 2,808 legal raises across all four styles and both odd-chip positions, including offers above the opponent's collectible cap. The focused tests also cover blocker-conditioned mass, short calls that return unmatched chips, the odd chip, and the path from a sampled call to a displayed all-in cover. [Settlement controls](benchmark-results/phase-4z-2026-11-19/reference-controls.txt) · [Deterministic tests](backend/test_research_holdem_phase_4z.py)

## Historical recommendation failures

The original payoff law and research policies reproduced the six rows below. Exact action values are net bb from the decision. The evidence contains the full public line and legal targets, card-aligned estimated and exact range weights, estimated and reference reply vectors, model action EVs, mixes and both choices. The new fixed-continuation audit is attached to each archived replay alongside its original scoring. [Historical replays and action traces](benchmark-results/phase-4z-2026-11-19/historical-13.json)

| Case | Exact EV, bb | Reproduced discrepancy |
| --- | --- | --- |
| 4Y · 7c 7d on As Kh 9c 6s 5c | Fold 0, call −0.745, shove −8.949 | Incumbent drew call. The persistent path and 4X mix drew shove, losing **8.204 bb** versus call. The persistent solver priced shove **+1.028 bb** over call. Correcting the range alone made the increment −7.862 bb. Correcting replies alone on the full modeled range moved it to about −0.009 bb. |
| 4X / 4W · Ah 9c on Tc 8s 5d Kh Jd | Fold 0, call −4.773, shove −17.901 | The persistent mixed change was **−17.690 bb** versus incumbent. Persistent estimated shove **+0.362 bb** over fold. Giving its own range true replies moved this to **−11.789 bb**. The modeled fold forecast, 63.41%, barely cleared its 62.50% modeled threshold. Actual folds on the model's range were 30.15%. On the true range, folds were 17.54% against a 62.41% reference threshold. |
| 4X · Qd 8h on Ad As 5c 2c Kc | Fold 0, call +0.350, shove −9.639 | Incumbent and bounded mix had modal shove, with 55.26% and 52.99% shove mass. The same draw fell on incumbent fold and bounded-mix shove because their cumulative orders differed. Shove cost **9.639 bb** against the incumbent draw. The persistent estimator gave shove +7.328 bb over fold, and the range swap corrected its sign. |
| 4U · Td 3h on 9s 7s 3s 2h 7h | Fold 0, call −1.432, shove −3.136 | The 4U gate estimated **+3.440 bb** over the incumbent mix and accepted pure shove. The true mixed change was **−2.347 bb** and the seeded change from call was −1.704 bb. In the original gate's decomposition, the range correction alone reversed the proposal's sign. |
| 4U · Jd 4h on 2d 5h Kc Qd Js | Fold 0, cover +1.315 | The inherited conservative rule folded an already closing wager. The incumbent drew cover. The stored CFR estimate favored cover by +2.776 bb. |
| 4T · Qc 4s on 3s 7c 7h 4c Ks | Fold 0, cover +5.547 | The sensitivity rule removed the incumbent's profitable 50% cover mass, costing 2.774 bb of mixed EV. Both seeded actions folded. The legacy model priced cover at +10.970 bb. |

The failures trace to three different mechanisms. Ah 9c had spurious fold equity. Td 3h had the wrong modeled composition after the public wager. Qd 8h kept a large shove probability and drew a different action after changing cumulative sampling order. The two closing calls had zero future reply branches, which isolates the impact of selection and range on those replays. [Original 4Y traces](PHASE_4Y_REPORT.md) · [4X sampling diagnosis](PHASE_4X_REPORT.md) · [4U gate attribution](PHASE_4U_REPORT.md)

## Frozen holdout results

The six new boards were crossed with three training streams and four styles. Tightness enters public-path weighting. The response tables share a call schedule within each aggression group. The 72 decisions include 24 checked-to, 24 facing a live half-pot wager, and 24 facing a closing wager. Depth counts were 20 at 9 bb, 24 at 15 bb and 28 at 30 bb. Effective SPR ranged from 0.25 to 3.25. There were 16 rows with no profile, 20 each with 3 and 30 prior hands, and 16 with 100. The historical path was check/check on 40 rows, lead/check on 20, and check/call on 12, where each entry describes the flop or turn line. Reference top-two actions were within 0.05 bb on 2 of 72 native rows and more than 0.50 bb apart on 54. Each native path had 136 non-self contrasts against the incumbent draw. The checked-to sizing probe had 116 additional contrasts in its own menu. [Full case schedule](benchmark-results/phase-4z-2026-11-19/frozen.json) · [Per-action results](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

| Solver path | Predicted / exact mean advantage, bb | Signed error / MAE / max absolute error, bb | Ranking | Incorrect positive / negative |
| --- | --- | --- | --- | --- |
| Legacy | −4.429 / −2.298 | −2.131 / 5.047 / 56.463 | 129/220 (58.6%) | 15 of 26 positive / 31 of 97 negative |
| Persistent | −2.890 / −2.264 | −0.626 / 3.794 / 25.659 | 144/220 (65.5%) | 22 of 45 positive / 23 of 87 negative |
| Expanded checked-to probe | −0.243 / −0.231 | −0.012 / 1.170 / 7.032 | 259/378 (68.5%) | 10 of 33 positive / 25 of 74 negative |

Ranking counts pairs with a reference gap above 0.01 bb. Advantage signs use a ±0.01 bb deadband. The decision-weighted crossed 95% MAE intervals were [1.936, 15.199] bb for legacy and [1.586, 7.825] bb for persistent. The table pools non-self actions. Some recommendation baselines were themselves severely losing, so a negative mean across their available alternatives gives little information about whether the chooser picked well. The closeness of the expanded probe's mean signed error to zero also conceals material errors at individual wager sizes. [Frozen metrics and bootstrap](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

| Opponent | Contrasts per native path | Legacy MAE, bb | Persistent MAE, bb | Persistent false positive / negative |
| --- | ---: | ---: | ---: | ---: |
| Tight-passive | 34 | 5.684 | 4.520 | 4 / 5 |
| Loose-passive | 34 | 5.933 | 4.529 | 4 / 7 |
| Tight-aggressive | 34 | 4.392 | 3.326 | 9 / 6 |
| Loose-aggressive | 34 | 4.179 | 2.800 | 5 / 5 |

| Action category | Native persistent n | Native persistent predicted / exact / MAE, bb | Expanded checked-to n | Expanded predicted / exact / MAE, bb |
| --- | ---: | --- | ---: | --- |
| Small | 0 | — | 20 | +0.285 / −0.465 / 1.019 |
| Medium | 13 | −0.372 / −0.574 / 1.044 | 13 | −0.208 / −0.549 / 0.930 |
| Large | 0 | — | 20 | −0.288 / −0.159 / 0.702 |
| Pot | 18 | −0.195 / −0.897 / 1.962 | 14 | −0.510 / −0.068 / 1.091 |
| Overbet | 0 | — | 16 | −0.389 / +0.348 / 0.872 |
| Closing shove | 29 | +0.976 / −0.839 / 3.093 | 18 | +0.345 / +0.442 / 1.755 |
| Nonclosing call | 19 | −2.596 / −0.386 / 7.023 | 0 | — |
| Closing cover | 10 | −11.624 / −12.158 / 1.215 | 0 | — |
| Check | 15 | −1.224 / −1.316 / 1.885 | 15 | −1.221 / −1.316 / 1.897 |
| Fold | 32 | −7.160 / −3.477 / 6.358 | 0 | — |

An incumbent cover contributes its fold contrast to the fold row. Across all 24 closing decisions, MAE was 10.112 bb for legacy and 2.975 bb for persistent. Persistent MAE was 1.512 bb when checked to and 6.804 bb facing a nonclosing wager. Both paths took all eight profitable covers. Legacy took six of the 16 losing covers and persistent took zero. Historical profitable folds demonstrate the risk outside this six-board panel. The exact fold/call sweep scored 51,244 integer wager targets across the native decision rows, 30,824 of them in the checked-to subset. [Strata and per-target EVs](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

### Mixed, modal and seeded outcomes

| Path and choice | Mean exact EV, bb | Mean regret, bb | Regret >0.01 / >0.50 bb | Worst regret, bb |
| --- | ---: | ---: | ---: | ---: |
| Legacy mixed | 3.473 | 2.776 | 44 / 32 | 23.842 |
| Legacy modal | 3.308 | 2.941 | 33 / 30 | 24.180 |
| Legacy seeded | 3.311 | 2.937 | 33 / 28 | 24.180 |
| Persistent mixed | 4.030 | 2.216 | 32 / 21 | 22.430 |
| Persistent modal | 4.036 | 2.210 | 24 / 21 | 22.439 |
| Persistent seeded | 4.078 | 2.168 | 25 / 21 | 22.439 |
| Expanded checked-to seeded | 5.589 | 1.079 | 19 / 9 | 7.186 |

The crossed 95% intervals for mean seeded regret were [0.286, 7.489] bb for legacy and [0.093, 6.416] bb for persistent. Regret uses the exact best branch in each path's menu and holds the path's downstream Hero policy fixed. The expanded row covers 24 checked-to decisions. Its mean EV reflects this restricted population.

- **Worst legacy draw, board 5 / stream 341 / tight-passive.** Qc 5c on 9s 4d 8d Tc Qd faced a 25 bb cover into a 10 bb prior pot. With three profile hands, the model valued cover at +32.283 bb and drew it with 98.60% mass. Exact cover was −24.180 bb. The range swap alone reproduced the loss. The branch was already closing.
- **Worst persistent absolute regret, board 2 / stream 343 / tight-passive.** 7d 3h shoved on 6d 2s Jc Kc 2h. Estimated shove EV was +3.220 bb and exact shove EV was −22.439 bb. Fold was worth 0. The incumbent also drew shove, so the paired seeded change was zero on this case.
- **Worst persistent loss relative to incumbent, board 3 / stream 342 / tight-passive.** Qc 2d on 2s 5d 3h 7c 8h faced a 5 bb bet into 10 bb. Persistent gave shove 98.50% mass and priced it at +1.832 bb over call. Exact call and shove were −3.298 and −14.849 bb. The seeded and modal shove cost 11.551 bb relative to the incumbent call. Either the range swap or the reply swap reversed the predicted advantage. [Individual tail cases and attribution](benchmark-results/phase-4z-2026-11-19/attribution-and-tails.json) · [Full policies](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

### Range, replies, search budget and selection

| Fixed input substitution | Legacy MAE, bb | Legacy wrong top / 72 | Persistent MAE, bb | Persistent wrong top / 72 |
| --- | ---: | ---: | ---: | ---: |
| Actual projected solver estimate | 5.047 | 33 | 3.794 | 21 |
| A · full estimated range, estimated replies | 5.047 | 33 | 3.765 | 25 |
| B · true range, estimated replies | 2.267 | 21 | 2.488 | 18 |
| C · estimated range, true replies | 3.092 | 18 | 1.499 | 11 |
| D · true range, true replies | 0 | 0 | 0 | 0 |

The same argmax and the same concrete menu apply across cells. Of 33 wrong legacy solver tops, 11 were corrected only by the range swap, 15 only by the reply swap, four by either, and three needed both. Of 21 wrong persistent solver tops, five were corrected only by the range swap, 12 only by the reply swap, and four by either. Mean absolute interaction D−C−B+A was 1.229 bb for legacy and 0.638 bb for persistent. Average range TV fell from 0.678 to 0.467 with persistent beliefs. Reference mass outside the solver columns still averaged 44.4% and 28.4%, respectively. The factorial isolates input errors conditional on the rank-based extension for missing reply columns, which limits causal interpretation beyond the evaluated policies.

Switching persistent CFR from 896 to 384 columns moved action advantages by 0.861 bb on average and as much as 8.757 bb. It changed 12 advantage sign categories and 12 top actions. The reduction changes both projection and computed replies. Under a common fold/call reference, the exhaustive legal-size optimum beat the native menu by more than 0.50 bb on 10 rows, with maximum gap 1.234 bb. The expanded checked-to menu still left four such rows, with maximum gap 1.151 bb on its subset. Sizing and computational budget matter. The larger failure remains opponent inference, including closing calls with no future response.

Every native seed draw reconstructed the concrete returned recommendation, with explain values matching the rounded solver values. Legacy had six avoidable seeded misses and five modal misses on rows where its highest model EV was already a reference-best action within 0.01 bb. Persistent had five seeded misses and four modal misses under the same condition. These are effects of the action distributions and selection rule. The historical 4X ordering effect is a separate research sampler issue. [Swap and choice diagnostics](benchmark-results/phase-4z-2026-11-19/attribution-and-tails.json)

### Bluff break-even

For a fold/call branch let `F` be the net bb won if Villain folds, `C` the conditional net EV when called, and `I` the incumbent EV. The required fold rate is `(I−C)/(F−C)` when folding improves Hero's EV. This includes tied showdowns and only collectible chips. Facing a wager, the winning fold takes the current pot, while the called line includes Hero's cost to call plus any matched raise. Shove branches with an interior threshold and negative reference EV when called had a model-above/reference-below threshold crossover on 6/15 legacy contrasts and 11/16 persistent contrasts. On a common reference range, the absolute fold-frequency error averaged 22.0 and 22.5 percentage points for native closing shoves. The persistent forecast exceeded true folds by 14.4 points on average on those branches.

For the worst paired Qc 2d shove, the model's forecast was 62.40% versus its 57.51% threshold, a +4.89-point margin. Reference folds were 17.94% versus a 49.70% threshold, a −31.75-point margin. The forecast overstated the fold rate by 44.46 points. The conditional calling range also changed the threshold. Branches with a legal raise were priced from three reply outcomes. [Break-even traces](benchmark-results/phase-4z-2026-11-19/attribution-and-tails.json)

The frozen holdout had zero strictly profitable fold/call wagers with negative conditional EV when called, measured against checking or folding. A separate deterministic control covers both sides of that gap. With 3h 2d on As 9d 8c 7s Ks, the two compatible reference holdings always beat Hero. Shoving 7.5 bb into 5 bb requires 60% folds to match the incumbent's 5 bb bet, worth 0 under the stipulated reply laws. The exact shove advantage is +1.250 bb at 70% folds and −1.250 bb at 50%. The solver gives the shove the same +0.056 bb advantage under its unchanged public inputs. These constructed controls validate the calculation and expose a difference hidden by the public history. The fresh accuracy statistics exclude them. [Bluff controls](benchmark-results/phase-4z-2026-11-19/bluff-controls.json)

## Advantage uncertainty

The public-input envelope varies the estimated range, pooled reply law and, for persistent, working-set size. Its coverage was 75.0% legacy and 75.7% persistent across individual contrasts, with mean widths of 8.722 and 9.322 bb. Giving each decision equal weight brings coverage to 69.7% and 69.9%, with crossed 95% intervals of [43.5%, 91.7%] and [47.9%, 88.9%]. The envelope was decisively on the wrong side of zero in 9 of 58 decisive legacy contrasts and 2 of 54 decisive persistent contrasts. The evidence is insufficient to calibrate a per-action interval.

| Stratum | Persistent contrasts | Persistent coverage | Mean width, bb |
| --- | ---: | ---: | ---: |
| 0 profile hands | 36 | 75.0% | 14.017 |
| 3 profile hands | 32 | 43.8% | 11.866 |
| 30 profile hands | 32 | 96.9% | 5.191 |
| 100 profile hands | 36 | 86.1% | 6.039 |
| Prior check/check | 80 | 82.5% | 4.894 |
| Prior check/call | 28 | 85.7% | 13.759 |
| Prior lead/check | 28 | 46.4% | 17.536 |
| Checked to Hero | 60 | 95.0% | 6.189 |
| Facing a live wager | 52 | 65.4% | 13.906 |
| Facing a closing wager | 24 | 50.0% | 7.224 |
| Considering a closing shove | 29 | 93.1% | 11.257 |

The observed strata combine board, profile and betting history, so coverage changes are descriptive. The 100-hand profiles narrow the envelope relative to sparse profiles, and miss five of 36 persistent contrasts. Across all prefix sizes, 31/72 profiles supplied no observed river replies. Available reply counts sample pooled past behavior. The benchmark's true hand- and price-conditional law is distinct from the proxy training process. Range substitutions expose misspecification in the inferred current holding mix. Reply scenarios expose disagreement about continuation under public counts. The 384-column run separately demonstrates numerical sensitivity from the solve budget. The bootstrap measures uncertainty in aggregate results across boards and streams. It cannot calibrate an individual decision's scenario envelope. [Coverage by line, stack, SPR and size](benchmark-results/phase-4z-2026-11-19/holdout-13.json)

## Runtime, reproducibility and architecture verdict

| Advisor path | Seed 13 median / p95 / max, s | Seed 31 median / p95 / max, s |
| --- | --- | --- |
| Legacy | 2.597 / 9.315 / 13.911 | 2.472 / 10.025 / 14.657 |
| Persistent 896 | 0.339 / 3.881 / 6.339 | 0.374 / 4.296 / 5.663 |
| Expanded checked-to | 1.429 / 2.864 / 4.022 | 1.414 / 3.927 / 4.130 |

Both runs completed all 72 decisions and had zero unexpected fallbacks. All measured advisor calls stayed within 15 s with warmed board caches. The legacy working set reached 1,176 columns. The persistent path stayed at one decision solve and 896 or fewer columns per seat. The 384-column sensitivity solve took at most 1.439 s. A full offline audit row, which includes several separate advisors and the oracle accounting, took up to 21.744 s. Cold latency remains unmeasured in this phase. Both holdouts and all six historical replays agreed across hash seeds after excluding measured time. An initial manifest serialization check stopped before any fresh evaluation. On the first pass after that, an export key collision overlaid reference fold probabilities with threshold details. Both partial runs stopped after 28 rows, the export fields were corrected, and both complete runs used the same frozen 72 decisions and scoring rules. The partial journals and freeze snapshots are retained. [Seed 13](benchmark-results/phase-4z-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-4z-2026-11-19/holdout-31.json) · [Holdout parity](benchmark-results/phase-4z-2026-11-19/determinism.json) · [Historical parity](benchmark-results/phase-4z-2026-11-19/historical-determinism.json)

The solver's EV arithmetic and recommendation conversion behave as designed on the tested river paths. Their assumptions can still make a bad individual action look profitable by several bb. Both the closing-call errors and the fold-frequency failures would survive a mechanically correct rewrite of the payoff evaluator. A change to cumulative draw order would leave unsafe modal choices in place. The working-set and sizing diagnoses support narrower engineering comparisons, with range and reply measurement as the priority. Production Coach and Match retain the incumbent strategy and disabled research defaults.

## Phase 5 architecture comparison

The engineering estimates below assume one engineer, existing local replay fixtures and a research-only deliverable. Latency goals need a fresh benchmark on warm and cold paths before any integration.

| Option | Estimated engineering cost | Expected benefit and evidence | Offline runtime feasibility |
| --- | --- | --- | --- |
| Side-by-side exact river action evaluator with explicit opponent input | 3–5 engineering days for read-only integration and trace parity | Gives each legal action a reproducible value and comparator. Closing calls isolate range-equity risk. The ledger's agreement with the solver under matched inputs makes this mainly an observability and model-comparison improvement. | Price finite river continuations after a single solve. Benchmark marginal evaluator cost and total warm/cold p95 and max against 15 s. |
| River-specific decision engine using explicit range and response models | 2–4 weeks for an isolated prototype and independent price-stratified replay | Could improve hand-by-price prediction, especially at effective shoves, if the data identify the conditional reply law. Sparse and mature pooled counts plus the 4U interval failures leave this benefit unproven. | River payoffs are finite. The cost risk is repeated inference and fitting. Benchmark one shared posterior and batched per-action pricing before comparing strategies. |
| Replace the competitive strategy architecture across streets | 6–10 weeks for a bounded comparative prototype and local gameplay evidence | Could reduce sizing and continuation approximation. It still needs a defensible model of unknown replies. The large observed errors survive exact payoff accounting, so engine replacement has a weak causal rationale at this checkpoint. | Turn and flop increase runout and action-tree costs substantially. A 15 s decision ceiling is unverified. Limit any early comparison to offline replay. |

**Recommended milestone.** Build a read-only river action-value comparison harness. Replay the legacy, persistent, and independent explicit-input scorer on a new frozen panel and stratify closing equity and price-dependent reply evaluation. Include a second family of synthetic policies and any appropriately sampled local histories with documented exposure and reveal selection. Measure sign errors, per-action uncertainty failures, absolute selected-action regret, profitable-cover preservation and worst paired loss before discussing a policy. Use actual API seed 0 alongside the archived chooser seed, verify both warm and cold latency, and keep deterministic decision keys and an exact state-to-action ledger. Any later proposal must clear the existing individual and mixed-policy EV gates first. Its next gameplay milestone is a separate paired seat-swapped duplicate-deal match with the current competitive baseline and existing pool, evaluating whole independent sessions with zero illegal actions, chip-conservation violations and unexpected fallbacks. [Phase 4Y gates](PHASE_4Y_PROTOCOL.md) · [Duplicate-deal methodology](SIMULATION.md)

## Verification and Git status

- The full backend regression passed **1,030 tests** in 41m 42s with eight existing dependency deprecation warnings. [Full backend regression](benchmark-results/phase-4z-2026-11-19/backend-tests-loopback.txt)
- The focused settlement and Coach explanation run passed 31 tests under seed 13. All five new controls passed under seed 31, and the full research regression passed 209 tests under that seed in 826.56 seconds. Collection retained all 1,025 prior test IDs and added five. FastAPI TestClient used local Windows loopback. [Focused seed 13](benchmark-results/phase-4z-2026-11-19/focused-13.txt) · [Focused seed 31](benchmark-results/phase-4z-2026-11-19/focused-31.txt) · [Research regression](benchmark-results/phase-4z-2026-11-19/research-tests-31.txt) · [Collection and source checks](benchmark-results/phase-4z-2026-11-19/source-and-test-check.txt)
- The frontend production build and Coach, Match and Replay render checks passed. Local API smoke exercised Coach advice, persistent Match, Single Hand Replay and Persistent Match Replay under unset, explicit zero and enabled research flags. Unset matched explicit zero, and Match reproduced the prior flag-specific archives. Replayed events passed chip conservation and action legality. The dependency check passed. Runs used installed dependencies, local fixtures and loopback. [Build](benchmark-results/phase-4z-2026-11-19/frontend-build.txt) · [Coach render](benchmark-results/phase-4z-2026-11-19/frontend-coach.txt) · [Match and Replay renders](benchmark-results/phase-4z-2026-11-19/frontend-match-replay.txt) · [API smoke](benchmark-results/phase-4z-2026-11-19/api-smoke-loopback.txt) · [Dependency check](benchmark-results/phase-4z-2026-11-19/pip-check.txt)
- Git remains on `main` at `3e89367`, 19 commits ahead of local `origin/main`. The recorded worktree delta is the protocol, report, two offline research files and focused test file. Earlier changes are preserved. Evidence is in the existing ignored benchmark directory. The 4Y and final 4Z frozen source hashes match. All report links and whitespace checks passed, with the existing line-ending advisory on `backend/test_poker.py`. No commit, push or deployment was made. [Git status](benchmark-results/phase-4z-2026-11-19/final-status.txt) · [Worktree delta](benchmark-results/phase-4z-2026-11-19/status-delta.txt) · [Final source and link checks](benchmark-results/phase-4z-2026-11-19/final-source-and-link-check.txt)

## Reproduction

From `backend`, use the installed Python virtual environment, set OpenBLAS/OMP/MKL threads to one and choose a new output directory. Run these commands with `python -m research.holdem.phase_4z` as the prefix. The archived historical input files are required for `historical`.

| Operation | Arguments |
| --- | --- |
| Freeze | `freeze OUTPUT/frozen.json` |
| Historical under each hash seed | `historical OUTPUT/historical-SEED.json` |
| Fresh holdout under each hash seed | `holdout OUTPUT/holdout-SEED.json --manifest OUTPUT/frozen.json` |
| Fresh determinism check | `compare OUTPUT/determinism.json --runs OUTPUT/holdout-13.json OUTPUT/holdout-31.json` |

Set `$env:PYTHONHASHSEED` to `13` and `31` in separate PowerShell processes. Use a 1,200-second process deadline for each holdout, as in the recorded runs. The runner writes a new incremental JSONL decision log. [Runner](backend/research/holdem/phase_4z.py) · [Frozen inputs](benchmark-results/phase-4z-2026-11-19/frozen.json)
