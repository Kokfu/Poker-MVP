# Phase 4M — Effective bet-size-conditioned opponent responses

## Production response audit

| Input or decision | What live adaptive Coach does |
| --- | --- |
| Fold, call and raise | `OpponentModel` records coarse action frequencies from completed public histories. `node_lock` partially pools across postflop streets, smooths the observations and builds fold, passive and aggressive targets for each facing-wager node. `RangeSolver` blends a fitted strategy toward those targets, with confidence weights capped at 75%. Information from revealed showdowns adjusts how much the fitted action depends on the holding. |
| Small versus large wager | Wager size changes the legal tree, showdown price and discounted CFR incentives. The default empirical fold/call/raise targets pool prices. Coach instantiates `AdaptiveSolverBot` with `sized_reads` disabled. |
| Price relative to pot, effective stack and SPR | Pot, commitments and live stacks drive legal totals and payoffs. The production lock has no explicit price, effective stack fraction or SPR terms. The optional Proposal B buckets by the uncapped increase divided by the pot after matching the responder's existing commitment, pooling streets. It uses a separate unlocked solve when a cell is supported and was left disabled after its previous gameplay gate. |
| Stack exhaustion | The tree caps aggression at the lesser reachable street total, trims excess at settlement and removes aggression when either the offerer is all-in or the responder can only cover the call. In the tree, that closing response is a call. Engine histories can encode a closing call as `all_in`. The default `call_vs_bet` statistic counts only explicit calls, so an all-in call can enter its denominator without entering its numerator. The separate sized observer classifies these through the change in highest commitment. |
| Opponent tendencies | Decision-time evidence comes from action/opportunity counts and observed showdowns for the named opponent. The tight/loose and passive/aggressive classification is display metadata. The model may predict materially different behavior for the same profile at different prices through the coupled solve. |

[Coach replay](backend/coach/service.py#L139) · [History statistics](backend/simulation/opponent_model.py#L145) · [Locks](backend/solver/exploit.py#L106) · [CFR policy blending](backend/solver/cfr.py#L243) · [Tree legality](backend/solver/tree.py#L128) · [Proposal B results](autopilot/reports/step-19.md)

### Cause of the 40% modeled raise

The historical 250-chip bet left Hero 1,000 behind and Villain 1,250 behind. Villain could fold, call 250, or legally raise to a street total from 500 through 1,250. The abstract raising action was the 1,250-chip shove. A direct engine replay settled both Hero responses to that shove and conserved chips. After an opening shove the abstract reply had only fold and call. This establishes the stack semantics for the reproduced loss.

The 30-hand loose-aggressive profile recorded zero facing-wager raises across 18 postflop opportunities. Its only river opportunity, on seed 41300026, was an all-in call of 400 with no increase in the highest total. It entered the river denominator but registered no fold, call or raise. The pooled, smoothed lock for bet 250 had a 30% blend weight and targets of 45% fold, 45% call and 10% raise. The remaining weight came from the coupled solve. The Phase 4L raise branch contributed 5.576 bb to modeled bet EV because the model assigned it 40.04% probability and expected 13.926 bb conditional on the raise. The resulting 9.037 bb valuation outranked the shove. Smoothing and partial, price-pooled anchoring of the coupled strategy explain the discrepancy with this reference's zero raise frequency. The history encoding also weakened the call estimate. [Phase 4L branch evidence](benchmark-results/phase-4l-2026-11-18/historical-response-branches.json)

## Research model and frozen comparison

For a legal first reply, let the effective cap be the lesser reachable street total. The price is the lesser of offered total and effective cap, minus the responder's street commitment. The pre-aggression pot is prior-street contributions plus twice the responder's existing street commitment. The two continuous ratios divide price by that pot and by the effective cap less the responder's commitment. The latter denominator divided by the pre-aggression pot is SPR for this comparison. All-in calls, including short calls, share the legal fold/call menu.

Each opponent and seed has a three-level count table. It pools first by raise legality, then by price at or below pot versus over pot, then by whether the price consumes at least half the effective stack and whether the opponent is facing an opening bet or a raise. Each refinement uses 20 pseudo-observations from its parent. Missing cells back off to the parent. A same-legality sample of size `n` moves the live aggregate toward the smoothed estimate by `n / (n + 32)`. Zero same-legality observations return the production strategy. Existing frequency fitting rescales per-holding fold, call and raise groups under the fixed incoming reach. Within each group it preserves the live per-holding size split where defined. The pooled ablation uses the same samples and live anchor and omits the price, pressure and aggression refinements.

The public betting-state tree and sampled actions train the candidate. The offline simulator draws opponent holdings from the reference posterior only to generate outcomes. The estimate receives the opportunity context and action counts only. Six dedicated training boards at three depths give 38 wager opportunities per table. At 24 draws each, that is 912 observed first replies per reference and stream. Calibration uses four earlier Phase 4L boards and fresh stream 41. Holdout uses eight new boards and streams 51 and 52. The historical case is separate. The response opportunities are synthetic, densely sampled and matched to the tested references. The 30-hand production profiles are separate and contain naturally occurring opportunities. Changes against the controlled baseline therefore include the effect of acquiring targeted response evidence. The same-data pooled comparison isolates the additional context features as a bundle.

The controlled baseline, conditioned candidate, pooled ablation and response oracle all select from the same concrete menu with Phase 4L's 80-step fixed-value mix. The actual live mix and seeded advice are recorded separately. The four controlled arms use the very same read-only final-solve reach after Hero blocker removal. Later live continuation stays fixed. Exact EV scores each mix with the same reference posterior and first-reply policy. The response oracle uses reference first replies with estimated reach during selection. It can retain regret when range estimates distort value. For fold/call references the Phase 4L stack-receipt traversal is cross-checked against Phase 4J's independent terminal evaluator on every root action. The raising stress references can shove when legal, after which Hero uses the frozen live fold/call continuation. Regret is relative to the best supported action under that same reference continuation.

The calibration set was run before the holdout. Its 48 original-reference rows gained 0.067 bb per decision, with eight losses above 0.01 bb and a worst loss of 7.628 bb. Marginal Brier improved from 0.54093 to 0.52276. Across 24 raising stress rows, EV fell 0.324 bb and Brier worsened from 0.58423 to 0.59337. The frozen candidate and gates carried forward. [Protocol](PHASE_4M_PROTOCOL.md) · [Candidate and runner](backend/research/holdem/phase_4m.py) · [Calibration rows](benchmark-results/phase-4m-2026-11-18/calibration.json) · [Frozen input hashes](benchmark-results/phase-4m-2026-11-18/frozen-input-hashes.txt)

## Historical reproduction

Hero held Kd Td on Kh 7d 4s Qc 3h against loose-aggressive. The river pot was 500 chips with 1,250 behind for each player. The disabled Coach mix earned 7.074373 bb. The actual adaptive mix earned 5.895088 bb, reproducing the **1.179285 bb** loss.

Response probabilities are percentages in fold/call/raise order. The first four columns use the fixed estimated reach. The last uses the reference posterior for scoring.

| Action | Production | Conditioned | Pooled | Response oracle | True posterior |
| --- | --- | --- | --- | --- | --- |
| Bet 250 | 33.04/26.91/40.04 | 54.40/43.10/2.50 | 51.48/46.02/2.50 | 43.73/56.27/0 | 59.62/40.38/0 |
| Bet 500 | 38.07/28.30/33.63 | 54.71/43.18/2.10 | 51.79/46.10/2.10 | 43.73/56.27/0 | 59.62/40.38/0 |
| All-in 1,250 | 51.58/48.42/0 | 71.47/28.53/0 | 62.39/37.61/0 | 61.14/38.86/0 | 76.87/23.13/0 |

| Action EV in bb | Production | Conditioned | Pooled | Response oracle | True |
| --- | ---: | ---: | ---: | ---: | ---: |
| Check | 4.572 | 4.572 | 4.572 | 4.572 | 4.931 |
| Bet 250 | 9.037 | 5.880 | 5.927 | 5.563 | 5.895 |
| Bet 500 | 7.928 | 6.537 | 6.634 | 6.548 | 6.847 |
| All-in 1,250 | 8.712 | 7.074 | 7.781 | 7.436 | 7.610 |

| Policy | Check % | Bet 250 % | Bet 500 % | All-in % | Exact EV | Regret |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Disabled live | 0.0017 | 5.5347 | 57.7371 | 36.7265 | 7.074373 | 0.535326 |
| Adaptive live | 0.0006 | 99.9850 | 0.0018 | 0.0126 | 5.895088 | 1.714611 |
| Controlled baseline | 0.0006 | 99.9864 | 0.0012 | 0.0118 | 5.895068 | 1.714631 |
| Conditioned | 0.0006 | 0.0006 | 0.0024 | 99.9965 | 7.609657 | 0.000043 |
| Pooled | 0.0006 | 0.0006 | 0.0016 | 99.9973 | 7.609663 | 0.000036 |
| Response oracle | 0.0006 | 0.0006 | 0.0019 | 99.9970 | 7.609661 | 0.000039 |

The conditioned and pooled arms saw 480 raise-eligible opportunities with zero raises. Both cut the 250-chip bet's modeled raise probability to 2.50% and switched to the shove. The historical correction demonstrates the value of learning the reference's low raise rate. The price split made no material difference to selection in this case. [Historical rows](benchmark-results/phase-4m-2026-11-18/historical.json)

## Holdout response calibration

Each opportunity has the same weight. The three-class marginal Brier score integrates the expected squared probability error over the reference action distribution on the fixed estimated reach. Its oracle value is the irreducible action variance for that distribution. Holding-level Brier averages the corresponding scores for individual holdings. The underlying rows include marginal forecasts, absolute errors and Brier scores for every size. [Paired holdout rows](benchmark-results/phase-4m-2026-11-18/holdout.json)

| Reply opportunities | Count | Production Brier | Conditioned | Pooled | Oracle |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary, all | 400 | 0.52168 | 0.51126 | 0.50305 | 0.44710 |
| Pot-sized or smaller | 280 | 0.53532 | 0.51935 | 0.50738 | 0.45604 |
| Over pot | 120 | 0.48985 | 0.49239 | 0.49294 | 0.42625 |
| Under half the effective stack | 144 | 0.55267 | 0.51066 | 0.50444 | 0.43137 |
| Half the stack or more | 256 | 0.50425 | 0.51160 | 0.50226 | 0.45595 |
| Raise allowed | 208 | 0.54643 | 0.50778 | 0.50464 | 0.44629 |
| Raise unavailable | 192 | 0.49487 | 0.51503 | 0.50132 | 0.44797 |
| 9 bb | 104 | 0.52304 | 0.53236 | 0.50972 | 0.45523 |
| 15 bb | 136 | 0.52198 | 0.50885 | 0.50353 | 0.44193 |
| 30 bb | 160 | 0.52055 | 0.49959 | 0.49830 | 0.44622 |
| Tight-passive | 100 | 0.55424 | 0.52161 | 0.51022 | 0.43189 |
| Loose-passive | 100 | 0.50760 | 0.51481 | 0.49921 | 0.45422 |
| Tight-aggressive | 100 | 0.51009 | 0.48464 | 0.48982 | 0.43876 |
| Loose-aggressive | 100 | 0.51480 | 0.52398 | 0.51294 | 0.46354 |
| Raising stress, all | 200 | 0.53592 | 0.54223 | 0.54071 | 0.49311 |

On the primary panel the mean absolute fold/call/raise errors were **13.79/13.66/7.46** percentage points for production, **13.63/13.57/0.47** for conditioned, and **13.29/13.24/0.47** for pooled. The oracle had zero marginal probability error. Holding-level Brier was 0.48636, 0.44507, 0.43500 and 0.30235 respectively. Most of the marginal gain against production came from reducing erroneously predicted raises, which the pooled observations also did. In the raising stress panel the corresponding production errors were 12.07/10.03/3.63 points, versus 11.69/10.10/1.85 conditioned and 12.91/11.19/1.85 pooled. Holding-level Brier was 0.50573, 0.50048, 0.49910 and 0.39715 respectively.

All 120 primary over-pot opportunities were stack-capped with no raise available. Both price bands occur among stack-capped actions, while all raise-eligible prices in this menu are pot-sized or smaller. The test evaluates the joint feature bundle on the shipped menu. It leaves standalone SPR effects and over-pot bets with chips behind unresolved.

## Exact decision EV and downside

The primary panel comprised 192 paired rows, with 64 at 15 bb. The 96 stress rows use the same boards and the two raising variants. EV, regret, action-value MAE and cumulative harm cost are in bb. Harm compares with the controlled baseline and counts any decrease above 1e-6 bb. The practical threshold is 0.01 bb.

| Panel and policy | Mean EV | Paired change | Mean regret | Action EV MAE | Harm / practical harm | Harm cost | Worst change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Primary, controlled baseline | 6.624 | 0 | 0.412 | 1.682 | 0 / 0 | 0 | 0 |
| Primary, conditioned | 6.573 | −0.051 | 0.463 | 1.582 | 71 / 23 | 34.728 | −5.620 |
| Primary, pooled | 6.626 | +0.002 | 0.410 | 1.576 | 83 / 15 | 17.050 | −2.669 |
| Primary, response oracle | 6.761 | +0.137 | 0.275 | 1.325 | 69 / 10 | 6.999 | −3.318 |
| Primary, adaptive live mix | 6.634 | +0.010 | 0.402 | 1.682 | 103 / 28 | 18.880 | −3.353 |
| Stress, controlled baseline | 7.274 | 0 | 0.331 | 1.314 | 0 / 0 | 0 | 0 |
| Stress, conditioned | 7.230 | −0.044 | 0.375 | 1.242 | 41 / 12 | 19.917 | −4.214 |
| Stress, pooled | 7.202 | −0.072 | 0.403 | 1.249 | 49 / 10 | 16.155 | −3.686 |
| Stress, response oracle | 7.438 | +0.164 | 0.167 | 1.015 | 39 / 5 | 3.890 | −1.345 |
| Stress, adaptive live mix | 7.402 | +0.128 | 0.203 | 1.314 | 50 / 11 | 6.173 | −1.574 |

The primary **−0.051 bb** paired difference had a 95% board-block bootstrap interval of **[−0.231, +0.167]**. At 15 bb the difference was **−0.150 bb**, interval **[−0.410, +0.100]**. The raising stress difference was **−0.044 bb**, interval **[−0.265, +0.209]**. With observations held constant, conditioning changed EV by **−0.052 bb** versus pooling on the primary panel, interval **[−0.144, +0.026]**, and **+0.027 bb** on the stress panel, interval **[−0.087, +0.135]**. Board blocks retain both profile seeds, all depths and every opponent for the resampled board. Eight boards limit precision. Primary modal-action regret was 0.412 bb for production, 0.463 conditioned, 0.411 pooled and 0.275 for the response oracle. The conditioned mix improved 28 primary rows by more than 0.01 bb and harmed 23 by that threshold. Its total harm cost was roughly twice the pooled arm's.

| Stratum | Primary rows | Conditioned Δ | Pooled Δ | Response oracle Δ | Conditioned practical harms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 9 bb | 64 | −0.010 | −0.066 | +0.094 | 4 |
| 15 bb | 64 | −0.150 | +0.047 | +0.083 | 9 |
| 30 bb | 64 | +0.008 | +0.024 | +0.234 | 10 |
| Tight-passive | 48 | −0.232 | −0.029 | −0.005 | 7 |
| Loose-passive | 48 | +0.107 | −0.039 | +0.121 | 2 |
| Tight-aggressive | 48 | +0.159 | +0.129 | +0.253 | 4 |
| Loose-aggressive | 48 | −0.239 | −0.055 | +0.179 | 10 |

In the raising stress panel, conditioned changes were +0.040, −0.016 and −0.157 bb at 9, 15 and 30 bb respectively, and +0.062 and −0.151 bb for tight- and loose-aggressive. The detailed scores by action, stack, profile and response category are in the paired artifact.

| Primary action mass | Live mix | Controlled baseline | Conditioned | Pooled | Response oracle |
| --- | ---: | ---: | ---: | ---: | ---: |
| Check | 8.02% | 6.77% | 0.001% | 1.56% | <0.001% |
| Call | 20.98% | 17.19% | 13.54% | 12.00% | 19.79% |
| Bet below all-in | 5.30% | 3.65% | 18.22% | 9.38% | 23.44% |
| Raise below all-in | 0.85% | 0.001% | 3.65% | 3.13% | 1.05% |
| All-in | 64.80% | 72.39% | 64.59% | 73.93% | 55.72% |

Fold mass was 0.051% for live and below 0.002% in every controlled arm. In the raising stress panel conditioning shifted all-in mass from 80.21% to 67.72% and smaller bets from 2.08% to 18.73%.

### Harmful adjustments away from the historical case

- At 15 bb against tight-passive, Kc Jc faced 325 on 5s 8d Ah 7h 2c with 1,200 chips behind. The conditioned policy moved from 99.996% call to 99.988% shove. Its estimated shove EV rose from 3.405 to 4.523 bb, ahead of the common call EV of 4.190 bb. The true values were 0 for folding, −2.721 for calling and −8.342 for shoving. The estimated call value implies 59.5% showdown equity before any new response, versus 4.2% under the reference range. The pooled and response-oracle policies still called. The immediate adjustment cost 5.620 bb relative to baseline.
- At 15 bb with bottom pair against tight-passive, conditioning changed a 99.98% call to a 99.96% raise to 1,025, costing 4.637 bb. At the same spot the response oracle still preferred shoving under the frozen reach, despite true EVs of −3.593 bb for shoving and −0.274 bb for calling. The best supported action was fold. This gives a case where exact first replies still left a bad ranking.
- In the raising stress panel at 30 bb against loose-aggressive, bottom pair moved from call to shove with 99.99% probability and lost 4.214 bb. On the alternative raise to 1,025 the candidate's shove-over prediction was 9.81%, close to the fixed-reach oracle's 9.72%, while its prediction of folds to Hero's shove was 64.52% versus the oracle's 57.74%. The true shove earned −1.782 bb versus +2.432 bb for a call.
- The largest primary gain was 2.828 bb. Against tight-aggressive at 30 bb, a raise to 1,025 replaced a shove with bottom pair. The true EVs were +1.352 and −1.477 bb respectively, and the response oracle found a better call worth +2.357 bb. Gains and losses came from different actions across the same board family.

## Promotion and Phase 4N

**Retain the production model.** The candidate passed the primary marginal Brier and computational gates and missed both mean-EV thresholds, the paired interval gate, nonnegative performance in each depth and opponent, the raising stress mean, the 0.25 bb loss cap and the 10% practical-harm limit. Primary practical harm reached 23/192, or 12.0%. The interval spans both signs, so the outcome establishes failure to clear the frozen production gate under this design. It leaves the population-level EV effect uncertain. The matched synthetic response data, same-seat scripted lines and fixed continuation bound the scope of the conclusion.

Choose **C — investigate range estimation independently** for Phase 4N. Phase 4L found a larger 15 bb gain from substituting the range than from substituting the response. In the fresh Phase 4M panel, the exact response oracle still had 0.275 bb of mean supported regret with the estimated range, and the largest conditioned losses arose in decisions that already overvalued calling. Start with the posterior after an opponent bets on the river, tracing off-menu wager likelihoods, omitted compatible combo mass and inferred equity against known references. Freeze the response, action menu and root selector for the paired experiment. Use separate boards and profile streams, include both seat orientations, and compare the current range, a minimal range candidate and the true posterior. Require held-out EV and downside gates before integrating any change.

## Runtime, reliability and verification

The candidate repricing and common root conversion added a median 3.90 ms to primary decisions and 3.94 ms to stress decisions. The corresponding live trace medians were 1,514 and 1,437 ms. The measured incremental allocation peak was 178,112 bytes in both panels, using `tracemalloc` around a repeat repricing pass with the frozen tree and range already available. This excludes the offline acquisition of training observations and native allocations outside the tracer. The entire holdout process took 331.55 s and peaked at 374.53 MiB resident. The replay took 350.88 s and peaked at 374.03 MiB. This process measurement includes the solver, all evidence rows and offline scoring.

- Both holdout runs reproduced all 288 paired rows and non-performance summaries exactly under Python hash seeds 13 and 31. Each evaluated 192 distinct live decisions and reused 96 solves for the raising stress panel. The calibration run evaluated 48 live decisions with 24 stress comparisons, and the historical run evaluated two live decisions. All recommendations used legal targets and normalized probabilities, with zero unexpected solver fallbacks. The maximum independent payoff discrepancy against the live solver was 0.001392 chips per action. Every original-reference payoff also matched the Phase 4J evaluator within the 1e-10 bb tolerance. [Holdout replay](benchmark-results/phase-4m-2026-11-18/holdout-replay.json)
- The focused suites passed **19 tests** in 5.28 s. The research suite passed **112 tests** in 234.92 s. Both reported seven existing eval7 deprecation warnings. Five added tests cover censored short all-in prices and no-raise legality, sparse backoff, preserving within-raise size weights and fixed inputs, seeded reply training, and actual engine settlement after a legal shove over a bet. [Research regression log](benchmark-results/phase-4m-2026-11-18/research-tests.txt)
- The full backend suite passed **933 tests** in 815.44 s, covering the 928 existing cases and the five Phase 4M cases. It reported eight existing dependency deprecation warnings. The sandboxed Windows asyncio socket-pair probe timed out. The bounded full suite ran with loopback available for the local API tests. [Backend regression log](benchmark-results/phase-4m-2026-11-18/backend-tests.txt)
- The dependency check, frontend production build and Coach render smoke test passed.
- Git remains on `main` at `3e89367`, 19 commits ahead of local `origin/main`. Phase 4M adds this report, the frozen protocol, the offline runner and five regression cases. Prior tracked and untracked changes and benchmark evidence were preserved. `git diff --check` and whitespace checks on the new files passed with an existing LF/CRLF advisory on `backend/test_poker.py`. All work remains local and uncommitted.

## Reproduction

From the backend virtual environment, create a fresh output directory and run the panels in the recorded order. The runner creates output files exclusively.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phase4mPy = '.\.venv\Scripts\python.exe'
$phase4mBound = '../benchmark-results/phase-4h-2026-11-17/run_bounded.py'
$phase4mOut = '../benchmark-results/phase-4m-reproduction'
New-Item -Path $phase4mOut -ItemType Directory -ErrorAction Stop | Out-Null
& $phase4mPy $phase4mBound 240 $phase4mPy -m research.holdem.phase_4m historical "$phase4mOut/historical.json"
& $phase4mPy $phase4mBound 600 $phase4mPy -m research.holdem.phase_4m calibration "$phase4mOut/calibration.json"
& $phase4mPy $phase4mBound 1000 $phase4mPy -m research.holdem.phase_4m holdout "$phase4mOut/holdout.json"
$env:PYTHONHASHSEED = '31'
& $phase4mPy $phase4mBound 1000 $phase4mPy -m research.holdem.phase_4m holdout "$phase4mOut/holdout-replay.json"
```
