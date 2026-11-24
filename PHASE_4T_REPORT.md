# Phase 4T — Independent opponent-action likelihood and bounded CFR

**PHASE 4T NOT COMPLETE — promotion gates failed.** The research adapter makes persistent inference independent of the CFR working set and repairs the archived collapse. Over 96 fresh paired decisions, the combined arm gained **+0.511 bb per decision**, with a **95% interval of [−0.830, +1.915] bb** and a **−9.059 bb** worst adjustment. Both hash-seed runs reproduced the decision results, produced zero unexpected fallbacks and kept the combined maximum replay below 7.27 s. Production Coach and Match continue to use the incumbent.

## Where inference depended on CFR

Coach validates public actions, total targets and the visible board through the hand engine. The incumbent reconstructs the public betting line and applies chart probabilities before the flop. On each postflop street it clears the new board blockers and solves with columns above the relative reach cutoff. For each observed action, the incumbent writes the solved likelihood times prior reach only on those columns. A hand can acquire zero posterior mass solely because the solver did not evaluate it. The next street and the Hero-compatible range report normalize after those eliminations. In the Phase 4Q collapse, the turn projection reduced 1,119 positive Villain holdings to one and the river blocked that last combo. The subsequent solve fell back.

Phase 4S restored omitted support by crediting the tail with a weighted action average from selected columns. The chosen hands still determined the average, and changing those columns also changed the game that produced each selected hand's action likelihood. Selection was deterministic and concentrated on high model reach. The incumbent's sampled flop runouts introduced a separate approximation. Both effects matter when a conditional action probability is used as evidence. Near-zero equilibrium action probabilities could produce a narrow posterior from a single observation. Downstream normalization preserved the artificial zeros.

CFR also estimates future replies to Hero actions in a re-solve. Those forecasts enter the branching EV of nonclosing choices. Closing fold/cover choices have no future reply term. Openings in an observed replay and replies in a hypothetical continuation are evaluated separately here. [Coach replay](backend/coach/service.py) · [Incumbent solve and range update](backend/solver/bot.py) · [Phase 4S support adapter](backend/research/holdem/range_support.py)

## Architecture and invariants

Phase 4T normalizes each public seat range in the global 1,326-combo order. For legal hand h, the update is p′(h) = p(h)L(a|h) / Σ pL. A board reveal uses the same normalization after eliminating combinations containing the new cards. Zero evidence and zero compatible support raise explicit errors. Hero cards condition the reporting and sensitivity posterior. The public seat distributions used for counterfactual solving remain board-legal, with card compatibility enforced between the seats.

After the chart, the observed-action law uses actual street state and the board prefix visible at that action. It gives every board-legal holding a normalized distribution over the legal abstract menu. It uses made-hand tier, public price, sizing and, where available, historical public frequency targets fitted on the full current reach. It has no input for private Villain cards, later board cards, solver strategy or selected columns. The Hero public reach uses the same base law as a nuisance model. The three tiers and finite size buckets coarsen real hand selection, and a frequency fit cannot identify which holdings bluff or value bet. The chart models preflop play with its existing stack-depth and action abstractions.

The decision solve projects the already computed ranges to at most 896 holdings per seat, in global combo order. It reserves the actual Hero column and a compatible Villain column. Pruning and weight selection stay local to the final solve. The candidate uses the incumbent action menu, DCFR training, future-reply locks, concrete legalizer and chooser. Solving once from the actual state can change the policy relative to reaching a descendant of a street-root solve, so the architecture contrast includes that change alongside independent inference. The optional sensitivity pass uses the Phase 4S [1,2] odds envelope verbatim. [Frozen protocol](PHASE_4T_PROTOCOL.md) · [Implementation](backend/research/holdem/decoupled_replay.py)

## Replay and independent controls

The archived collapse and one fresh development board were each replayed with the 896 limit and three 32-column selections, including independent sampling seeds 17 and 29. All eight solves produced the same hand-specific likelihoods and posterior within their case, with maximum absolute likelihood difference **0** and posterior TV **0**. The alternate subsets omitted 82.1% to 94.8% of board-legal modeled mass. Each case retained 1,081 board-legal public Villain holdings and 990 after conditioning on Hero. The maximum reported normalization error was 2.2 × 10⁻¹⁶. The historical 6s blocker still removed 6s 7s. The focused tests also exercise repeated and edited Coach replays and changing the hidden Villain cards supplied to the replay engine. Advice and inference stayed identical for identical observable state.

A hand-computed three-combo update gives posterior weights .500, .125 and .375. Blocking the second holding then gives 4/7, 0 and 3/7. With no positive likelihood on the legal support the update raises and retains the prior. A river law with check, two bets and a closing shove produces the independently computed tier-specific probabilities and no blocked mass. Facing a shove with a shorter stack produces only fold and call probabilities, with a short all-in classified as a call. In two separate exact terminal controls the same 100-chip call into a 400-chip contested pot is worth +100 chips at 50% equity and −60 chips at 10%. The exact showdown evaluator and independent Bayes enumerator agree. These tests establish support, calculation and price invariants. EV is evaluated separately on the fresh panel. [Deterministic tests](backend/test_research_holdem_phase_4t.py) · [Selection audit](benchmark-results/phase-4t-2026-11-18/invariance.json) · [Audit rerun on the final source](benchmark-results/phase-4t-2026-11-18/invariance-final.txt)

## Historical replay

All EV figures are in big blinds at the decision. A is incumbent, B is Phase 4S architecture, C is Phase 4S combined, D is decoupled with the incumbent DCFR policy, and E adds the Phase 4S uncertainty rule to D.

| Hero | Exact closing cover EV | A | B | C | D | E |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3c 5c, archived collapse | −3.863 | 0, fallback | −0.001 | 0 | −0.00004 | 0 |
| Js 3c | −18.720 | −0.044 | −0.033 | 0 | −0.00021 | 0 |
| Kc As | −24.716 | −7.897 | −6.611 | 0 | −0.00027 | 0 |
| Jd 4h, Phase 4S profitable cover | +1.315 | +1.315 | +1.315 | 0 | +1.315 | 0 |

D produces legal solver advice on all four and retains 990 positive Hero-compatible hypotheses in each. Historical A fallback is expected and is excluded from fresh holdout inference. The severe losing outcomes refer to the exact archived reference values for covering. The mixed policies put different probability on that action. [Historical replay rows](benchmark-results/phase-4t-2026-11-18/historical.json) · [Phase 4S report and failed promotion](PHASE_4S_REPORT.md)

### Why the profitable cover was folded

On Jd 4h against loose-aggressive, the board was 2d 5h Kc Qd Js. The 9 bb start and 30-hand public profile were replayed with the original shove and stream 172. Hero must pay 550 chips for a contested 1,800 chips, a break-even equity of 30.56%. Exact equity is 37.86%. Folding yields 0 bb and covering yields +1.315 bb. All three parent policies cover with 99.9989% probability. C and E cover with 0%.

The D posterior has loss/tie/win mass 54.576%/1.359%/44.065%. Exact masses are 61.653%/0.970%/37.377%. D's full-posterior cover estimate is +2.554 bb, its restricted CFR estimate is +2.216 bb, and its paired sensitivity range is [−0.290, +5.596] bb. B's restricted estimate is +1.922 bb, with a full-posterior estimate of +2.229 bb and bounds [−0.556, +5.277] bb. The working set and the probability model change magnitudes while preserving the profitable call ranking on this case. Under D, substituting the exact incoming prior alone yields +1.465 bb with lower bound −1.169 bb. Substituting only the true wager likelihood yields +2.433 bb with lower bound −0.391 bb. Even with the exact posterior the [1,2] rule yields [−1.284, +4.358] bb and orders a fold.

This identifies excessive conservatism in the decision rule as sufficient to cause the 1.315 bb loss. The turn and river support were intact. Exact menu and chip pricing agree, and CFR had already allocated almost all mass to the profitable cover. Prior misspecification is also measurable. The D posterior TV is 0.500, and replacing its final wager law alone leaves TV 0.496. Using the true incoming prior with D's final law lowers that TV to 0.021. These substitutions are diagnostic and require reference information unavailable to the candidate. The same decision rule applies to every case. [Per-hand prior, likelihood and posterior vectors and sensitivity](benchmark-results/phase-4t-2026-11-18/historical.json)

## Independent likelihood and posterior accuracy

The holdout fixes the opponent families and all exact scoring laws. For each of the 96 rows, the candidate's full distribution over river opening actions was compared with the independent synthetic law at the same legal targets. Weighting by the true incoming range, mean action-law TV was 0.1805, excess Brier score was 0.0568, and mean absolute error on the actual observed action was 0.0990. Its mean likelihood of the observed option was 0.2127, compared with the reference 0.2432. Earlier observed-action mean absolute errors were 0.1887 on the flop and 0.2236 on the turn, assessed on final Hero-compatible holdings under the corresponding reconstructed reference reach.

| Posterior check | A | B | D |
| --- | ---: | ---: | ---: |
| Mean TV from independent reference | 0.7111 | 0.7053 | 0.5238 |
| Mean number of positive compatible holdings | 519.1 | 990 | 990 |
| Mean effective compatible size | 211.3 | 207.0 | 412.4 |
| Mean reference mass outside decision-solve reach | 46.47% | 48.95% | 31.16% |

D's mean incoming-prior TV was 0.4916. Giving D the exact prior for the final observation alone reduced mean posterior TV to 0.0908. Giving it only the exact wager likelihood left mean TV at 0.5022. That identifies upstream public reach as the larger average source of error on this panel. The prior covers both the chart and the earlier observations. The prior substitution is an oracle diagnostic. The end-to-end D posterior TV by public profile prefix 0, 3, 30 and 100 was 0.445, 0.571, 0.473 and 0.607, respectively. The prefix strata contain different decisions, so these means do not identify a causal effect of extra training hands. [Holdout row-level metrics](benchmark-results/phase-4t-2026-11-18/holdout-13.json)

Future replies have their own error. For the 32 nonclosing decisions, the mean first-reply excess Brier scores under the same exact posterior were 0.532 for A, 0.531 for B and 0.531 for D. Substituting true first replies while leaving the exact posterior and Hero continuation fixed moved individual D action values by up to 12.771 bb. This component is inactive in terminal fold/cover cases. The future-response model is still the incumbent CFR model under the candidate's decision solve.

## Exact river EV on the fresh holdout

Eight boards crossed with three independent training streams and four fixed reference styles yielded 96 paired decisions, 64 closing and 32 nonclosing. Depths were 9, 15 and 30 bb. A common finite action menu, independent Bayesian reference, exact showdown evaluator and separate betting-tree value check were used for all arms. The best supported action under exact reference inputs averaged 7.540 bb and is a diagnostic upper bound. Intervals use 10,000 crossed board and stream bootstrap resamples, keeping styles together within each cell. The four synthetic families are fixed and the panel estimates conditional river decision EV under their prescribed reference laws. Development was separate. It had 16 decisions, with D−A +1.404 bb and E−A +1.476 bb. [Protocol and seeds](PHASE_4T_PROTOCOL.md) · [Frozen input manifest](benchmark-results/phase-4t-2026-11-18/frozen.json) · [Development](benchmark-results/phase-4t-2026-11-18/development.json)

| Arm | Mean EV (bb) | Mean regret (bb) | Closing cover probability | Seeded profitable folds / 41 | Seeded losing folds / 23 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 5.815 | 1.725 | 57.44% | 15 | 19 |
| B | 5.720 | 1.819 | 56.72% | 14 | 19 |
| C | 5.666 | 1.873 | 43.50% | 20 | 20 |
| D | 6.328 | 1.212 | 70.31% | 3 | 16 |
| E | 6.326 | 1.214 | 54.69% | 8 | 21 |

Expected profitable covers foregone were 10.30, 10.74, 16.16, 3.00 and 8.00 for A–E. Expected losing covers avoided were 16.94, 16.96, 20.00, 16.00 and 21.00. Both counts sum mixed-policy fold probability on the corresponding truth category. D's mean change relative to A was +0.983 bb on closing decisions and −0.428 bb on other decisions. E's closing change was +0.980 bb with the same nonclosing change. The uncertainty rule moved roughly five profitable and five losing cases from cover to fold relative to D. Its sensitivity envelope included the true cover EV in 37/64 cases for E and 25/64 for C. Both are descriptive coverage of a fixed odds envelope. [Exact values, policy frequencies and bounds](benchmark-results/phase-4t-2026-11-18/holdout-13.json)

| Contrast | Mean (bb/decision) | Paired 95% interval | Losses > 0.01 bb | Total harm (bb) | Worst change (bb) |
| --- | ---: | ---: | ---: | ---: | ---: |
| B − A | −0.095 | [−0.552, +0.157] | 4 | 13.547 | −13.287 |
| C − A | −0.149 | [−1.020, +0.561] | 11 | 34.456 | −14.726 |
| D − A | +0.513 | [−0.987, +1.937] | 21 | 58.368 | −9.059 |
| **E − A** | **+0.511** | **[−0.830, +1.915]** | **20** | **48.146** | **−9.059** |
| D − B | +0.608 | [−0.950, +1.928] | 21 | 58.714 | −9.059 |
| E − D | −0.002 | [−0.555, +0.665] | 5 | 19.182 | −8.960 |
| E − C | +0.660 | [−0.638, +1.948] | 17 | 45.108 | −9.059 |
| Uncertainty interaction | +0.052 | [−0.405, +0.659] | 10 | 31.009 | −8.707 |

Total harm sums the magnitudes of all strictly negative paired differences. Loss counts use the frozen 0.01 bb materiality threshold. The primary E−A harm rate was 20.8%.

| Reference opponent | B − A | C − A | D − A | E − A |
| --- | ---: | ---: | ---: | ---: |
| Tight-passive | −0.000 | +0.259 | −0.064 | +0.364 |
| Loose-passive | −0.537 | −0.618 | +0.588 | +0.514 |
| Tight-aggressive | +0.003 | −0.403 | +0.293 | +0.090 |
| Loose-aggressive | +0.156 | +0.167 | +1.234 | +1.075 |

### Severe losses and attribution

- **Shared D/E nonclosing loss of 9.059 bb.** Js Kh on Qh 5d Qc 5s Jd at 15 bb, loose-aggressive, stream 191. A gave shoving 94.18% and D/E gave calling 94.23%. The exact reference values are +5.681 bb for call, +12.972 bb for raise to 1,000 and +15.313 bb for shove. D valued call highest at +5.255 bb and valued shove at +4.987 bb. Restoring D's omitted holdings with the evaluator's existing nearest-rank reply extension changed each action EV by under 0.001 bb. With the full D posterior held fixed, substituting exact replies restored shove as best at +13.794 bb. Supplying the exact posterior alone moved the best modeled response to the smaller raise and valued shove only at +5.860 bb. The largest loss is tied to future-reply misspecification and occurs on the same board and stream against all four styles.
- **Worst D closing change of −6.354 bb.** 8s Qh on 9c Ah 3c 5s Kc at 9 bb, tight-passive, stream 191. The working-set estimate for cover was +0.0116 bb, the full model gave −0.0022 bb, and exact cover EV was −6.468 bb. The small projection difference flipped the near-zero nominal ranking. Both upstream prior and final wager error overstated equity. Either truth substitution restored a negative call EV. E folded on this case.
- **Worst E closing change against A of −2.774 bb.** Qc 4s on 3s 7c 7h 4c Ks at 15 bb, tight-aggressive, stream 192. The exact cover value was +5.547 bb. A covered 50%, D covered almost always, and E covered 0% because its lower bound was −0.730 bb. This loss involved both prior error and the sensitivity rule. On Js Kh against loose-passive, 9 bb, stream 192, E gave up 8.960 bb relative to D by folding a profitable cover that D took almost always. D estimated +1.978 bb and E's lower bound was −0.777 bb.
- **Phase 4S comparison-arm downside.** Ad As on Kd 9d 9c 7h Jh at 15 bb, loose-passive, stream 192. The exact cover value was +14.826 bb. A covered 99.32%, B covered 9.70% and C folded always. B and C lost 13.287 bb and 14.726 bb relative to A on this fresh decision. These reruns do not supersede the Phase 4S panel or its original failed promotion.

The diagnostics hold the decision menu fixed and use oracle inputs only to attribute errors after scoring. [Severe-case substitutions](benchmark-results/phase-4t-2026-11-18/severe-case-diagnostic.json) · [Full paired holdout](benchmark-results/phase-4t-2026-11-18/holdout-13.json)

## Runtime, memory and iteration budgets

Full replay timing starts before the traced Coach replay and ends at reconstructed advice. Both runners warm board-equity entries before each board block. Profile-chart locks warm as keys are encountered. Percentiles use all 96 rows per arm and seed. The runs used one BLAS thread on a shared machine.

| Arm | Seed 13 median / p95 / max (s) | Seed 31 median / p95 / max (s) |
| --- | ---: | ---: |
| A | 2.081 / 6.496 / 10.239 | 0.828 / 3.799 / 7.226 |
| B | 1.931 / 6.885 / 10.059 | 0.787 / 3.707 / 11.151 |
| C | 1.931 / 6.886 / 10.060 | 0.788 / 3.707 / 11.152 |
| D | 0.232 / 3.299 / 5.215 | 0.105 / 1.321 / 7.263 |
| E | 0.232 / 3.299 / 5.215 | 0.105 / 1.321 / 7.263 |

All 960 arm timings were within the 15 s warm replay cap. Holdout runner peaks were 255.85 and 277.17 MiB. Runs completed in 612.57 and 338.09 s within the 1,200 s process bound. D used exactly 80 postflop iterations per decision, or 7,680 total, compared with 210 per decision and 20,160 total for each of A and B. Maximum working width per seat was 1,176 for A and 896 for B and D. D's median final widths were 520 for the button-index seat and 364.5 for the big-blind-index seat. C and E reuse their parent's solve. [Seed 13 timings](benchmark-results/phase-4t-2026-11-18/holdout-13.json) · [Seed 31 timings](benchmark-results/phase-4t-2026-11-18/holdout-31.json)

Seed 13 D medians were 0.24 ms for replay reconstruction, 1.17 ms for the preflop chart path, 4.52 ms for likelihood evaluation, 4.34 ms for posterior updates, 0.66 ms for selection, 162.44 ms for the final solve and 10.51 ms for explanation. The maxima were affected by cold preflop chart locks. The two slowest D replays spent 4.74 and 6.82 s in the preflop path and 0.43 and 0.37 s in the final solve. In the separate warm profiler trace on one development spot, A and B spent 4.46 and 4.87 s in CFR iterations across three streets, including 0.97 and 1.00 s in terminal values. D spent 0.30 s in CFR iterations, 0.24 s of that in terminal values, and 0.05 s evaluating all earlier and final observations. Removing earlier street solves eliminates the large inference expense. Caching board tier vectors and reusing the current board equity in the explanation reduce duplicate work. DCFR retains its float32 terminal matrix products, bounded projections, and existing equity approximations on flop and turn decisions. [Profile A](benchmark-results/phase-4t-2026-11-18/profile-A.json) · [Profile B](benchmark-results/phase-4t-2026-11-18/profile-B.json) · [Profile D](benchmark-results/phase-4t-2026-11-18/profile-D.json)

Cold spot checks include equity and chart preparation. D took 5.24 s cold and 0.59–0.70 s warm on the archived Phase 4S slow key. It took 1.07–5.93 s cold on the three slowest seed-13 D keys. The separate one-case development profile measured 18.99 s cold for A, 7.24 s for B and 1.13 s for D, with process peaks of 145.17, 88.98 and 96.62 MiB. A's cold profile exceeded 15 s. The formal gate applies to the frozen warm-board holdout, with cold timing reported separately. [Archived slow-key profile](benchmark-results/phase-4t-2026-11-18/4s-slow-key-profile.json) · [Fresh cold spot checks](benchmark-results/phase-4t-2026-11-18/fresh-cold-slow-keys.json)

## Frozen promotion gates

| Gate | B | C | D | E |
| --- | --- | --- | --- | --- |
| Mean gain ≥ 0.05 bb and lower 95% bound > 0 | Fail | Fail | Fail | Fail |
| Worst paired loss ≤ 0.50 bb | Fail | Fail | Fail | Fail |
| At most 10% losses over 0.01 bb | Pass | Fail | Fail | Fail |
| Every opponent mean ≥ −0.03 bb | Fail | Fail | Fail | Pass |
| Legal normalized actions, independent exact-payoff checks, zero unexpected fallbacks | Pass | Pass | Pass | Pass |
| Median ≤ 2× A and maximum ≤ 15 s on both seeds | Pass | Pass | Pass | Pass |
| Runner peak memory ≤ 768 MiB on both seeds | Pass | Pass | Pass | Pass |

The initial incomplete runner was stopped during code review before any fresh result was read. That review corrected the treatment of refundable overhang for a short call. The same equal-stack schedule and coefficients were frozen again. Both completed runs verified the final 98 source hashes and case schedule. All 96 rows, strategies and deterministic statistics matched exactly after excluding timing and memory fields. The Phase 4S combined arm's original gain of +0.817 bb and −1.315 bb profitable-cover loss remain archived with its failed promotion. Phase 4T uses the original 0.50 bb downside and 15 s replay limits. [Initial freeze](benchmark-results/phase-4t-2026-11-18/pre-short-call-review-frozen.json) · [Final freeze](benchmark-results/phase-4t-2026-11-18/frozen.json) · [Determinism comparison](benchmark-results/phase-4t-2026-11-18/determinism.json) · [Phase 4S verdict](PHASE_4S_REPORT.md)

## Phase 4U recommendation

**Run paired decision validation with independent future-reply forecasts.** Keep Phase 4T's inference and CFR budget fixed. Use public response evidence to build and validate a separate price-conditioned fold, call and raise model, then test changes in action EV against the incumbent using the same candidate posterior. Use reference substitutions to check independently whether the response law or posterior is driving severe disagreements. Compare a paired advantage rule that retains the incumbent mix when supported models disagree with the proposed adjustment. Include closing calls in that same paired decision test with the response branch absent and separate plausible prior and wager likelihood inputs. This directly tests the observed failure modes. Replacing replies repaired the largest nonclosing loss, and a fold-only worst-case rule discarded profitable closing calls even with an exact posterior on the archived hand. A candidate should clear the existing downside and runtime gates on fresh decisions before duplicate-deal, seat-swapped gameplay validation.

## Verification and Git

- The full backend regression passed **998 tests** in 1,315.67 s, retaining all 992 Phase 4S tests and adding six Phase 4T controls. It reported eight existing dependency deprecation warnings. [Full backend regression](benchmark-results/phase-4t-2026-11-18/backend-loopback.txt)
- Six deterministic Phase 4T tests passed under each of hash seeds 13 and 31. The research regression passed all 177 tests in 691.79 s. [Focused seed 13](benchmark-results/phase-4t-2026-11-18/focused-13-final.txt) · [Focused seed 31](benchmark-results/phase-4t-2026-11-18/focused-31.txt) · [Research regression](benchmark-results/phase-4t-2026-11-18/research-tests.txt)
- All 31 Coach API and explanation tests passed in 23.84 s. The frontend production build and Coach solver/fallback rendering test passed. The dependency check reported no broken requirements. All runs used the installed local dependencies. Windows local loopback was required for FastAPI tests after the sandboxed socket-pair probe timed out. [Coach backend](benchmark-results/phase-4t-2026-11-18/coach-loopback.txt) · [Frontend build](benchmark-results/phase-4t-2026-11-18/frontend-build.txt) · [Coach rendering](benchmark-results/phase-4t-2026-11-18/frontend-coach.txt) · [Dependency check](benchmark-results/phase-4t-2026-11-18/pip-check.txt)
- All 28 Phase 4Q, 93 Phase 4R and 95 Phase 4S frozen input hashes match their archived manifests. [Archived hash checks](benchmark-results/phase-4t-2026-11-18/historical-hashes.txt)
- Git is on main at 3e89367, 19 commits ahead of the local origin/main. Git and whitespace checks passed, with the existing line-ending advisory for `backend/test_poker.py`. The five additions are local and uncommitted. All Phase 4S status entries are still present. Evidence lives under the existing ignored benchmark-results directory. [Final Git status](benchmark-results/phase-4t-2026-11-18/final-status.txt)

| Added file | Purpose |
| --- | --- |
| [PHASE_4T_PROTOCOL.md](PHASE_4T_PROTOCOL.md) | Coupling audit, frozen design and acceptance criteria |
| [PHASE_4T_REPORT.md](PHASE_4T_REPORT.md) | Results, diagnostics and readiness decision |
| [decoupled_replay.py](backend/research/holdem/decoupled_replay.py) | Persistent range model, observation law and bounded solve projection |
| [phase_4t.py](backend/research/holdem/phase_4t.py) | Offline paired benchmark, frozen inputs and profiles |
| [test_research_holdem_phase_4t.py](backend/test_research_holdem_phase_4t.py) | Six deterministic research tests |

## Reproduction

From the repository root, run with Python 3.11.9 and NumPy 1.26.4. Choose an empty evidence directory. The existing manifest verifies the exact 98 source inputs on each final run.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$phase4tPy = './.venv/Scripts/python.exe'
$phase4tOut = '../benchmark-results/phase-4t-reproduction'
$phase4tFreeze = '../benchmark-results/phase-4t-2026-11-18/frozen.json'
$phase4tBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:],timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phase4tOut -ErrorAction Stop | Out-Null
$env:PYTHONHASHSEED = '13'
& $phase4tPy -c $phase4tBound 480 $phase4tPy -m research.holdem.phase_4t development "$phase4tOut/development.json"
& $phase4tPy -c $phase4tBound 480 $phase4tPy -m research.holdem.phase_4t historical "$phase4tOut/historical.json"
foreach ($phase4tHash in @('13','31')) {
    $env:PYTHONHASHSEED = $phase4tHash
    & $phase4tPy -c $phase4tBound 1200 $phase4tPy -m research.holdem.phase_4t holdout "$phase4tOut/holdout-$phase4tHash.json" --manifest $phase4tFreeze
    if ($LASTEXITCODE -ne 0) { throw "Phase 4T holdout $phase4tHash failed" }
}
$env:PYTHONHASHSEED = '13'
& $phase4tPy -c $phase4tBound 3600 $phase4tPy -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
```
