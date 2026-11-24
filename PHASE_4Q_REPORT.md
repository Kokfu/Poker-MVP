# Phase 4Q — River wager likelihood

**Verdict: reject the candidate; Phase 4Q did not meet acceptance.** The research candidate improves likelihood calibration, but loses 0.390 bb per decision under production inputs on the 143 scored holdout rows and has a 24.715 bb worst adjustment. A reproducible incumbent empty-range fallback invalidates the full-panel primary test and independently fails the integrity gate. Production strategy remains unchanged.

## Architecture audit (recorded before candidate changes)

Coach rebuilds the opponent profile from completed, publicly logged histories and passes its snapshot into the existing solver. Replay starts from the chart, traverses the previous streets, multiplies only the actor's weights on each observed action, masks board cards, and drops holdings below the relative reach cutoff at each solve. On the river, the average strategy column for each hypothetical holding gives the conditional distribution on the abstract actions. The observed wager selects one cell of that column. Multiplication, card compatibility and normalization give the posterior used at Hero's decision. An off-menu current action may lead to a second prune and re-solve at actual geometry; it does not apply the original observation twice.

| Question | Current source and limitations |
| --- | --- |
| Check versus bet | The solver learns probabilities for check and all aggressive actions. The optional river opening lock reads a smoothed aggregate bet rate and places check and aggression into complementary groups. |
| Individual size and shove | The standard opening menu offers half-pot, pot and the effective cap, dropping sizes at or above 85% of the cap. The aggregate opening lock does not separately fit each size or the closing wager. Closest-size mapping is in log chip distance; an explicit aggressive all-in maps to the cap. |
| Hand strength, value and bluff | The solve uses showdown outcomes and continuation incentives per holding; a profile strength-correlation adjustment can tilt lock groups using publicly observed showdowns. There is no probability model trained specifically on revealed value and bluff holdings for each opening size. Showdown samples are selected. |
| Stack constraints and closing calls | The abstract cap is the smaller reachable commitment. Replay separately recognizes an engine all-in that only covers the wager as a call. Once an aggressor is all-in or the reply would consume the remaining stack, no raise branch exists. A short-stack closure is a game constraint, while a deep overbet below both stacks can still be raised. |
| Opponent-specific tendencies and sparsity | The default adaptive solver reads public street statistics and uses discrete confidence bands; missing/unreliable cells do not lock. The optional size reads in the source govern replies to wagers, not openings. Global all-in counters do not become an opening-shove probability. Earlier bets/calls change reach and SPR but are not dedicated covariates of the opening-size lock. |

The **observed-action** model is the row at Villain's previous decision. **Future responses** are the subsequent per-hand fold/call/raise rows under each possible Hero aggression. They are separate inputs even though the live solver derives both through a coupled solve. They cannot explain a closing fold/cover error: that decision has no Villain response. Phase 4P reproduced the loss with an exact incoming prior and removed it by swapping only the observed-action row. Replay Bayes arithmetic is consistent on the audited historical lines. The strongest evidence points to an underidentified hand-by-size distribution, with the reach prior amplifying the error. Menu snapping and insufficient public context are additional limitations, and profile observation has known all-in call classification errors; those errors are not evidence that the closing opening row was multiplied incorrectly.

Sources: [Coach](backend/coach/service.py), [replay and range solve](backend/solver/bot.py), [betting tree](backend/solver/tree.py), [locks](backend/solver/exploit.py), [opponent observer](backend/simulation/opponent_model.py), [exact evaluator](backend/research/holdem/river_ev.py), [Phase 4P](PHASE_4P_REPORT.md).

## Reference validation and candidate

The research law, [river_wager_reference.py](backend/research/holdem/river_wager_reference.py), defines a bet rate followed by a conditional size distribution. It varies with made-hand tier, a suit blocker or busted flush marker, turn pressure, effective SPR and the reference opponent's tendencies. It places mass on exact chip targets on the shared finite menu. If 600 is in the pot, both stacks are 1,200 and a loose-aggressive opponent has no pair or blocker, the manual probabilities are 0.6600 check, 0.1598 for 300, 0.1020 for 600 and 0.0782 for 1,200. With both stacks at 400, the 600-chip intent rolls into the 400-chip shove for 0.1802 and 300 remains an ordinary bet. A 50-chip stack below the 100-chip minimum can still move all-in. A genuine bettor shove, a bet covering the defender and an overhanging all-in were verified separately from a pot-sized nonclosing bet. An engine all-in on the defending side can be the call, so the solver's all-in action label alone does not tell whether it is an aggression.

A second manual test assigns prior masses 0.8 and 0.2 to two legal holdings, with closing-wager probabilities 0.0782 and 0.423. Hero wins against the first holding only. The expected equity is 0.06256/(0.06256+0.08460), and the call is worth 3,000 times that equity minus 1,200 chips. Both independent posterior and terminal payoff calculations reproduce that result. The runner validates array probabilities, legal menus and payoff parity on every evaluated decision. Unequal stacks are deterministic geometry controls; the EV panel uses equal stacks and an opening wager.

[The candidate](backend/research/holdem/river_wager_calibration.py) combines eight production observations with capped pooled and context-specific counts and the available opponent counts. A context includes SPR, turn aggression and a hand group. Stack and pot determine available chip targets and the closure category. With no population or opponent evidence it returns the production law. Fitting uses only cards shown under a randomized Hero showdown protocol and downweights more frequently revealed actions by their known reveal propensity. No hidden deal, style identity or exact likelihood reaches candidate inference. The fixed simulation grid samples independent river holdings for training rather than replaying their reach through the earlier betting line. The count model is therefore a test of transfer across that covariate shift. Existing Coach logs have selected showdowns and unknown reveal propensities, and the experiment does not demonstrate that these counts can be obtained from those logs.

Development log loss improved from **1.940 to 1.032** (oracle 0.928), and Brier from **0.738 to 0.570** (oracle 0.517). Primary EV fell **0.502 bb per decision** across 16 decisions despite the likelihood gains, with two losses above 0.01 bb, a 6.361 bb worst loss and seven modal changes. The frozen candidate was evaluated unchanged. [Development data](benchmark-results/phase-4q-2026-11-18/development.json) · [Frozen protocol](PHASE_4Q_PROTOCOL.md) · [Input hashes](benchmark-results/phase-4q-2026-11-18/frozen-input-hashes.json)

## Historical failures

Hero held **Js 3c** on **2d Ah Jh 2h Kh** at 30 bb. Villain limped, called a raise to 300, checked through on the flop and called Hero's 300 turn bet. Hero checked the river and loose-aggressive Villain shoved 2,400 into 1,200. Folding is worth 0; covering is worth **−18.720313 bb** under the archived exact posterior. Risking 2,400 to contest 6,000 requires 40% equity. There is no future reply to either legal action.

| Incoming range | Production equity / modeled cover EV | Candidate equity / modeled cover EV | Oracle equity / modeled cover EV |
| --- | ---: | ---: | ---: |
| Production | 32.02% / −4.788 bb | 12.72% / −16.365 bb | 9.54% / −18.274 bb |
| True | 41.76% / +1.056 bb | 14.20% / −15.479 bb | 8.80% / −18.720 bb |

With production incoming weights all three mixes fold virtually always. With true incoming weights the production likelihood changes the ranking to cover and realizes about 18.720 bb of regret. The candidate and the oracle restore fold. A **21.291 bb** tight-passive exact-prior loss also reproduces: 8c 3d on 8s Ad Tc Ks 2s facing 2,500 into 1,000, where the production law with true prior gives 60.04% equity against a true 6.18%. The candidate restores fold with that same true prior. These archival repairs do not establish a holdout gain.

The table records the most relevant Phase 4P failure per archived row and the attribution from the reproduced factorial. Phase 4P's candidate adjusted the **incoming range**; Phase 4Q's candidate adjusts the **wager likelihood**. Old A/B/C/D letters used a different factorial.

| Deal / stream / style | Reproduced loss (bb) | Isolated mechanism |
| --- | ---: | --- |
| 5 / 111 / tight-passive | 3.571 | Altered prior crossed the half-pot equity threshold; true likelihood restored the call. |
| 5 / 111 / tight-aggressive | 8.360 | Same threshold crossing. Accurate replies and true incoming support classify shove above call. |
| 6 / 111 / tight-passive | 3.583 | The cover has positive exact EV. Production prior plus true likelihood still folds, while the fully true inputs cover. |
| 6 / 111 / loose-passive | 4.443 | The old adjusted prior crosses below the cover threshold even with both downstream oracles. |
| 6 / 112 / tight-passive | 4.426 | The old adjusted prior prices a call above the best shove with both downstream oracles. |
| 0 / 112 / tight-aggressive | 3.841 | The old candidate calls even with both downstream oracles. True incoming plus production likelihood can also call; either Phase 4Q likelihood substitution restores fold with the true prior. |
| 5 / 112 / loose-aggressive | 10.410 | Kh 6c facing 1,000 into 1,000. Old adjusted prior dropped below 33.33% with the modeled wager. The oracle restored cover; with Phase 4Q's unchanged prior all three arms cover. |
| 2 / 112 / tight-aggressive | 5.126 | Old adjusted prior folded against both oracles where the shove pays +5.127 bb. On production incoming/replies the Phase 4Q likelihood change recovers the shove. |
| 2 / 111 / tight-passive | 21.291 | Closing-shove likelihood misranked the call even with exact incoming weights. Response is irrelevant. |
| 1 / 111 / tight-aggressive | 3.396 | Production continuation still overvalues shove folds after the true incoming range and wager likelihood are supplied. With true replies the oracle folds. |

[Historical evidence](benchmark-results/phase-4q-2026-11-18/historical.json) contains each replayed deal, legal action targets, prior steps, exact and production likelihood for all 990 legal pairs, posterior vectors, all strategy mixes, modeled EV, exact EV and regret, and the nested Phase 4P replay. The two estimators use the original archival reference policy on these cases. None of the cases enter fitting or the promotion gate.

## Frozen holdout integrity gate

**Reject progression to gameplay validation.** The original frozen holdout run aborted under both hash seeds on a live Coach fallback, `ReplayError: empty range`. It therefore did not satisfy the predeclared zero-fallback gate and does not have a complete primary EV estimate. The source, parameters, split, case keys and thresholds were preserved. A separate [diagnostic runner](backend/research/holdem/phase_4q_diagnostics.py) verifies the original input hashes, records every failing case and scores the other frozen cases without modifying production or the candidate. Its results describe the evaluable decisions only, with a separate zero-change sensitivity for identical fallback behavior. They cannot reverse the integrity failure.

The initial runs both finished the two passive-style panels for stream 131 (24 rows) before aborting in the next style. Development and historical replay did not encounter this failure. Because the solver falls back before this experiment can substitute a wager likelihood, the failure belongs to the incumbent replay/solve path. Retaining the row matters independently of the calibration result.

The failing row is deal 4, tight-aggressive, stream 131, three previous hands. Hero held 3c 5c on Qc 3s Ks 8h 6s. Both started at 15 bb. Villain called an open to 250, led the flop for 250 and was called, checked the turn, then shoved 1,000 into 1,000. Replaying the turn check through the average strategy and retained solve columns reduced Villain from 1,119 positive holdings to one. The 6s then blocked that last holding. At the start of the river solve, before applying the wager, Villain had **zero positive incoming holdings** and Hero had 374. The observed wager model cannot repair an empty incoming range. [Failure trace](benchmark-results/phase-4q-2026-11-18/fallback-trace.txt)

## Likelihood calibration on 143 scored holdout decisions

| Metric | Production | Candidate | Wager oracle |
| --- | ---: | ---: | ---: |
| Expected categorical log loss | 1.809 | 0.971 | 0.859 |
| Expected multiclass Brier | 0.751 | 0.543 | 0.485 |
| Sampled event log loss | 1.841 | 0.998 | 0.869 |
| Combo posterior TV, production incoming | 0.724 | 0.674 | 0.661 |
| Combo posterior TV, true incoming | 0.349 | 0.139 | 0 |

Action scores integrate over the true pre-wager range and weight each scored public state equally. The sampled-event check uses one independent labeled draw per state. The oracle's nonzero proper scores reflect the intrinsic randomness of the reference, and the production extrapolation for pruned hands uses the same published reach-weighted extension in every configuration.

| Action, only where offered | True rate | Production rate / per-combo MAE | Candidate rate / per-combo MAE |
| --- | ---: | ---: | ---: |
| Check | 56.28% | 61.90% / 27.59 pp | 58.65% / 16.00 pp |
| Half-pot | 19.83% | 10.63% / 17.59 pp | 16.78% / 10.01 pp |
| Pot | 13.81% | 8.76% / 12.56 pp | 10.97% / 5.80 pp |
| Closing | 18.05% | 23.65% / 21.38 pp | 19.98% / 7.11 pp |

Each action has its own availability denominator. Closing-wager mean prediction bias for high-card, pair and two-pair-plus holdings moved from **+14.78 / +16.04 / −19.00** to **+2.38 / +3.77 / −1.66 percentage points**, respectively. Absolute errors moved from **18.56 / 19.69 / 26.23** to **6.41 / 7.30 / 7.21 points**. Production overweights low made-hand tiers and underweights stronger hands on average. Low tiers can include bluff candidates, but these are strength classes and do not measure betting intent directly.

| Stratum | Scored | Log loss, production → candidate | Closing MAE, production → candidate (pp) | A candidate / oracle ΔEV (bb) |
| --- | ---: | ---: | ---: | ---: |
| Tight-passive | 36 | 1.322 → 0.784 | 17.62 → 7.18 | −0.268 / +2.052 |
| Loose-passive | 36 | 1.265 → 0.774 | 17.32 → 5.58 | −0.359 / +1.393 |
| Tight-aggressive | 35 | 2.222 → 1.133 | 22.71 → 6.96 | −0.753 / −0.179 |
| Loose-aggressive | 36 | 2.438 → 1.196 | 27.92 → 8.71 | −0.190 / +0.077 |
| 0 observations | 36 | 2.124 → 0.950 | 15.17 → 7.16 | −2.022 / −0.649 |
| 3 observations | 35 | 1.993 → 0.990 | 23.15 → 7.67 | −1.252 / +0.714 |
| 30 observations | 36 | 1.667 → 1.006 | 22.38 → 6.88 | +1.321 / +2.885 |
| 100 observations | 36 | 1.456 → 0.938 | 24.88 → 6.73 | +0.370 / +0.418 |
| Effective behind ≤ 8 bb | 48 | 1.733 → 0.899 | 24.12 → 8.51 | +0.036 / +0.123 |
| Effective behind > 8 to 16 bb | 47 | 1.762 → 0.967 | 20.48 → 7.03 | −0.474 / −0.007 |
| Effective behind > 16 bb | 48 | 1.931 → 1.046 | 19.53 → 5.79 | −0.732 / +2.394 |
| SPR ≤ 1 | 71 | 1.569 → 0.851 | 22.84 → 8.57 | −0.457 / −0.127 |
| SPR > 1 to 2 | 24 | 2.359 → 1.196 | 22.84 → 5.83 | +3.154 / +3.991 |
| SPR > 2 | 48 | 1.889 → 1.035 | 18.50 → 5.59 | −2.061 / +0.703 |

Effective-stack bins coincide with the 9/15/30 bb starting-depth bins in this schedule. Candidate EV deltas by stream 131/132/133 are **+0.737 / −1.081 / −0.801 bb**. Pooled calibration is weakest in decision terms for profiles with zero or three observations, but the prefix strata also differ in case mix and incumbent Coach evidence. These comparisons do not identify a causal value per extra observation. The overall likelihood gain appears in every stratum above, while the EV gains concentrate in one SPR band and denser profiles. On the 99 observed closing shoves alone, log loss falls from 1.838 to 0.938 but EV falls 0.376 bb. The oracle adds 1.272 bb there.

## Exact EV and downside

These are complete-case diagnostic contrasts in bb per decision. The paired intervals use the frozen crossed board/stream method on the incomplete panel; one cell contains three styles rather than four. They are descriptive after the integrity abort.

| Inputs | Production EV | Candidate EV | Candidate delta [95% interval] | Oracle EV | Oracle delta [95% interval] |
| --- | ---: | ---: | ---: | ---: | ---: |
| A — production prior, production replies | 1.496 | 1.106 | **−0.390 [−2.599, +1.663]** | 2.339 | +0.843 [−0.691, +3.391] |
| B — production prior, true replies | 1.501 | 0.966 | −0.535 [−3.514, +1.750] | 2.172 | +0.671 [−1.833, +3.592] |
| C — true prior, production replies | 1.742 | 2.513 | +0.772 [+0.00001, +2.425] | 3.037 | +1.295 [+0.185, +3.621] |
| D — true prior, true replies | 2.210 | 3.157 | +0.947 [+0.127, +2.624] | 3.454 | +1.244 [+0.193, +3.587] |

Assigning zero paired change to the failed key as a sensitivity moves the A candidate delta to −0.387 bb and the oracle delta to +0.837 bb. With production replies, replacing the prior improves the **relative** candidate effect by 1.161 bb. With true replies the improvement is 1.482 bb. The 0.321 bb difference of differences confirms that the components interact; the sharp separation between A/B and C/D also shows why the true-input gains are unavailable to production. On 32 half-pot decisions the primary candidate/oracle deltas are −0.717/−0.226 bb; on 12 pot-sized decisions they are +0.370/+0.156 bb. No reply model has an effect on the 99 closing decisions.

| Setting | Production / candidate / oracle mean regret | Production / candidate / oracle max regret | Candidate harm > 1e−6 / > 0.01 bb | Candidate total harm / worst loss | Candidate modal changes |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1.958 / 2.348 / 1.115 | 24.846 / 24.846 / 16.220 | 33 / 23 | 165.822 / 24.715 | 37 |
| B | 1.954 / 2.489 / 1.282 | 24.846 / 24.846 / 17.980 | 31 / 23 | 191.715 / 24.715 | 42 |
| C | 1.713 / 0.941 / 0.417 | 23.735 / 16.220 / 13.263 | 24 / 2 | 12.438 / 7.924 | 17 |
| D | 1.244 / 0.297 / 0.00011 | 23.735 / 16.220 / 0.00036 | 9 / 0 | 0.00013 / 0.00003 | 24 |

The A candidate's aggregate mix moved fold from 48.18% to 46.15%, all-in from 48.63% to 49.65%, and call from 3.19% to 4.20%. All-in includes stack-covering calls and aggressive shoves. The wager oracle moved those shares to 53.85%, 42.66% and 3.50%. Raises below all-in had negligible mass in A. The A oracle itself harmed 17 decisions by more than 0.01 bb, costing 87.097 bb across all harms and losing 12.418 bb on its worst adjustment. A true likelihood cannot recover from every inaccurate incoming prior or future response.

The worst candidate case was **Kc As on Th 8s 4h Qs 7s**, tight-passive, stream 132, 30 bb start. Villain shoved 2,500 into 1,000 after calling the open, checking the flop and calling a turn bet. The break-even equity was 41.67%. Production assigned 23.44% and folded. Candidate weighting of the same incoming range assigned 54.93% and covered, while the wager oracle on that same range gave 8.51%. True cover EV was **−24.716 bb**. The candidate made the same fold-to-cover change across all four styles for this board and profile prefix, with losses of 11.269–24.715 bb. Even the wager oracle covered and lost against both aggressive styles with the production prior. That cluster is why the uncertainty method retains shared boards and streams. The failure modes are distinct: likelihood error explains the candidate's extra harm against the passive styles, while the incoming range is sufficient to produce harmful decisions with the correct likelihood against the aggressive styles.

The four rows account for 73.099 bb of harm. Excluding them would move the mean from −0.390 to +0.125 bb; the cluster remains in every reported main estimate. Removing any other single board leaves the mean negative. This sensitivity shows why average calibration and isolated improvements are insufficient for a change that controls near-terminal stack decisions. [Influence diagnostic](benchmark-results/phase-4q-2026-11-18/downside-influence.txt)

The diagnostic fails the primary point estimate, uncertainty, worst-loss, practical-harm-rate (23/143 = 16.1%) and every opponent-floor check. It clears the log loss and incremental array cost checks on the successful rows. No parameters changed. [Scored decisions and severe-case vectors](benchmark-results/phase-4q-2026-11-18/diagnostic-13.json) · [Strata and replay comparison](benchmark-results/phase-4q-2026-11-18/holdout-diagnostics.txt)

## Architecture checkpoint

| Possible limitation | What the evidence supports |
| --- | --- |
| A. Insufficient observable opponent information | Strong. The candidate sees more systematically revealed evidence than normal Coach histories supply. Even with known showdown exposure and a training population matched to the synthetic styles, different plausible hand-by-size laws can agree on aggregate openings. Unknown selection in ordinary histories makes the marginal rates easier to identify than the bluff/value mix or either style's per-combo shove odds. |
| B. Incorrect or restrictive abstraction | Real and separable. Mapping actual chips to a finite size menu and merging near-cap intent discard size information. The 18.72 and 21.291 bb failures both occur on an offered closing wager with the right terminal choices available. Phase 4L measured only 0.00487 bb average omitted-size regret on its separate panel; this does not bound the cost of off-menu bets in real games. |
| C. Interaction between probabilistic inputs and decision selection | Strong. Accurate incoming weights can make a biased likelihood cross a closing price threshold, and an accurate posterior can still feed an overly optimistic future-response model. The 80-step policy often assigns nearly all its mass to the action with the highest estimated EV, so smaller probability errors near a threshold can cause large realized losses. |
| D. Solver approximation or convergence | A secondary hypothesis. The live solver can lose support before the decision, which is different from payoff arithmetic or a lack of convergence iterations. Unrounded solver values match independent traversal on successful rows, and the common selector prices the fully true inputs close to their best supported action. Neither result validates convergence of the coupled live solver across all states. A bounded reach/pruning and iteration sweep can separate these effects. |
| E. Synthetic-to-gameplay mismatch | Strong external validity limit. Fixed public lines, four stylized opponents, randomized showdowns and scripted wager strata cannot establish gains in natural deal frequencies, unknown opposing styles or counter-adaptation. The holdout estimates conditional decision EV on this panel. |

Shift to a broader **river inference and decision design** rather than another isolated parameter sweep. First, design a replay audit that explains and prevents empty-support fallbacks on valid observed actions while preserving legitimate card removal. Then put the observed-action and future-response models behind separate interfaces with explicit legal support and uncertainty. Test whether a decision rule can retain the baseline in high-uncertainty spots while still accepting changes supported by independent paired payoffs. Compare that design with the current solver and stage-specific oracles across logged price and showdown-exposure strata before authorizing a separate duplicate-deal gameplay test. Preserve the current bet menu for the first architecture comparison; test a richer size model separately. The evidence does not justify a wholesale solver rewrite or another automatic Phase 4R.

## Verification and working tree

- The full backend regression passed **958 tests** in 1,456.45 s, preserving all 949 baseline tests and adding nine Phase 4Q cases. It reported eight existing dependency deprecation warnings. The suite used local loopback for the API tests; a bounded sandbox probe timed out opening a Windows socket pair, and the loopback-capable control passed. [Full backend tests](benchmark-results/phase-4q-2026-11-18/backend-tests.txt)
- Focused verification passed **21 tests** in 15.88 s. The research suite passed **137 tests** in 908.76 s, including 128 retained controls and nine new deterministic cases. Both reported seven existing dependency deprecation warnings. [Focused tests](benchmark-results/phase-4q-2026-11-18/focused-final.txt) · [Research tests](benchmark-results/phase-4q-2026-11-18/research-tests.txt)
- Both diagnostic runs matched all 143 deterministic scored rows, the failed row and all 28 frozen hashes under Python hash seeds 13 and 31. All successful rows checked legal targets, normalized policies, no extra fallback, replay chip conservation, independent Bayesian weighting and payoff agreement. The maximum live action-EV parity difference was 0.000700 chips. Independent reference payoffs matched traversal within 1e−10 bb.
- Incremental calibration took **0.398/0.381 ms** median and **226.2 KiB** maximum traced allocation. The diagnostic runs took **280.52/279.63 s** and peaked at **286.12/286.16 MiB** resident memory. The median live replay was **1.017/1.034 s**, with board grouping sharing equity caches. In an additional archived-board microbenchmark, rebuilding all 990 hand-group features from cached ranks before applying the candidate cost **9.05 ms** median and peaked at about **230 KiB** of traced memory. The primary budget applies to cached features as frozen in the protocol. [Performance breakdown](benchmark-results/phase-4q-2026-11-18/holdout-diagnostics.txt) · [Feature microbenchmark](benchmark-results/phase-4q-2026-11-18/feature-overhead.txt)
- `pip check`, the frontend production build and the Coach render test passed. The harness uses existing local dependencies. [Dependencies](benchmark-results/phase-4q-2026-11-18/pip-check.txt) · [Build](benchmark-results/phase-4q-2026-11-18/frontend-build.txt) · [Coach render](benchmark-results/phase-4q-2026-11-18/frontend-coach-test.txt)
- Git stays on `main` at `3e89367`, 19 commits ahead of local `origin/main`. Only seven Phase 4Q files were added to the pre-existing working-tree changes. All prior tracked modifications, untracked research files and historical evidence were retained. New evidence uses the existing ignored `benchmark-results/` directory. `git diff --check` and whitespace checks on the new files passed; Git printed the existing LF/CRLF advisory for `backend/test_poker.py`. Nothing was committed, pushed or deployed. [Starting status](benchmark-results/phase-4q-2026-11-18/initial-status.txt) · [Final status](benchmark-results/phase-4q-2026-11-18/final-status.txt)

## Reproduction

From the repository root, use an empty output directory for new results, the existing backend virtual environment and a single BLAS thread. No network service or deployment is used. The backend API tests require Windows local loopback.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phase4qPy = './.venv/Scripts/python.exe'
$phase4qOut = '../benchmark-results/phase-4q-reproduction'
$phase4qFrozen = '../benchmark-results/phase-4q-2026-11-18/frozen-input-hashes.json'
$phase4qBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:], timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phase4qOut -ErrorAction Stop | Out-Null
& $phase4qPy -c $phase4qBound 480 $phase4qPy -m research.holdem.phase_4q development "$phase4qOut/development.json"
& $phase4qPy -c $phase4qBound 480 $phase4qPy -m research.holdem.phase_4q historical "$phase4qOut/historical.json"
# The frozen holdout is expected to report the production fallback and exit nonzero.
& $phase4qPy -c $phase4qBound 1200 $phase4qPy -m research.holdem.phase_4q holdout "$phase4qOut/holdout-13.json"
& $phase4qPy -c $phase4qBound 1200 $phase4qPy -m research.holdem.phase_4q_diagnostics $phase4qFrozen "$phase4qOut/diagnostic-13.json"
$env:PYTHONHASHSEED = '31'
& $phase4qPy -c $phase4qBound 1200 $phase4qPy -m research.holdem.phase_4q_diagnostics $phase4qFrozen "$phase4qOut/diagnostic-31.json"
$env:PYTHONHASHSEED = '13'
& $phase4qPy -c $phase4qBound 3600 $phase4qPy -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
```

