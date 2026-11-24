# Phase 4N — Bet-conditioned river range estimation

**Research complete; candidate rejected.** In 288 matched holdout comparisons, the new range improved average posterior accuracy and reduced mean regret. With production replies it gained **+0.197 bb per decision** (paired 95% interval **[−0.131, +0.594]**) and lost **8.633 bb** in the worst case. Both the confidence and downside gates failed. The largest gain occurred with zero size evidence. Production remains unchanged.

## Production range audit

| Step | Current Coach behavior |
| --- | --- |
| Public replay and profile | Coach replays Hero's cards, the public board and the entered action sequence through `HandEngine`. For a named opponent, it reconstructs a profile from completed histories. `OpponentModel` counts actions and opportunities; `ShowdownModel` uses only legitimately revealed cards. The displayed opponent type is descriptive. |
| Preflop prior | Both players start with uniform weight per combination. The nearest stack-depth chart, optionally re-solved with preflop locks, provides the per-combo probability of every observed action. The solver multiplies the actor's reach by that probability. |
| Earlier streets | Each newly revealed board card removes incompatible pairs. The street solve trims weights below or equal to 0.5% of the highest weight, preserves Hero's actual holding, and uses the street's equity matrix. The flop and turn policies condition the ranges again. The first river solve receives that accumulated reach. |
| Observed bet | The solver multiplies Villain's pre-bet weight by the per-combo probability of the mapped bet or shove at the appropriate node. The likelihood is already hand specific. Different hands can bet for value or as bluffs in the solved policy; there is no explicit classification of betting intent. Board texture affects ranks, blockers and incentives through the board-specific equity matrix. |
| Observed size | On-menu bets use their action row. Off-menu bets use the nearest abstract aggression in log target space. The solver then re-solves at the actual chips and commitments but keeps the likelihood from the first mapping. Two actual sizes in the same mapping cell therefore lead to the same initial range update on the same public prefix. The next solve can trim it again. |
| Confidence and support | The default adaptive locks partially pool postflop action frequencies across streets, back off when observations are sparse, and cap the lock weight at 75%. They anchor overall aggression/facing-wager groups, with strength dependence informed by selected showdown samples. They do not identify exact-size probabilities by hand. Profile size summaries and the optional facing-size lock do not supply that likelihood in default Coach. Pruning makes some legal combos impossible in the model. If no eligible Villain mass reaches a solve, it raises a replay error and the bot can use its existing fallback. |
| Stack, blockers and advice | The solver replays street-total actions and distinguishes a stack-closing call from an increase in the highest commitment. The tree caps aggression at the effective reachable total and does not permit a raise against an opponent who is already all-in. Hero blockers enter compatibility in the EV traversal and the explicit mask in the range report. The reported range is taken before any final off-menu re-prune. The solver selects from concrete legal targets using Hero's average strategy. |

[Coach replay and profile](backend/coach/service.py) · [Production reach and action mapping](backend/solver/bot.py) · [Locks](backend/solver/exploit.py) · [Profile](backend/simulation/opponent_model.py) · [Showdown evidence](backend/solver/showdown.py) · [Tree and stack rules](backend/solver/tree.py)

The simulator also has a separate [heuristic range updater](backend/simulation/range_intelligence.py). It uses made hands, draws, pot-fraction bands and a weight floor when a bot requests range intelligence. It does not generate the conditioned reach used by the Coach solver; Phase 4N reuses the solver's own reach and likelihood rows.

**Confirmed behavior and model limits.** The research trace verified the action multiplier on final positive solver support, so there is no missing Bayes update or equal-bet-probability assumption in the tested range path. The off-menu mapping and re-pruning are confirmed approximations. The separate display range can differ from the exact range used for modeled action EV after an off-menu re-solve. No arithmetic, card removal or legalization defect was reproduced in that core update. An inaccurate posterior by itself does not establish a code defect.

**Confirmed profile defect.** The existing Phase 4M issue is that a stack-closing `all_in` enters the facing-wager denominator and is omitted from the call numerator. Phase 4N also reproduced misclassification in the strength evidence: `ShowdownModel` groups the same action with aggressive showdowns even when the highest commitment does not increase. On tight-passive training seed 41071073, Villain's only river action matched 700 behind and left the highest commitment at 700. It supplied one aggressive reveal and no river call reveal; reclassifying that event at the observer boundary yielded zero aggressive reveals and raised total call reveals from three to four. Aggressive strength correlation changed from 0.938 to the 1.000 no-sample prior in this one-hand control. Across eight 100-hand profile streams there were 46 such stack-closing calls, 24 on the river. This can affect the priors and likelihoods through learned strength correlation. Its EV contribution was not isolated, and both comparators retain the existing observations. [Action-level control](benchmark-results/phase-4n-2026-11-18/all-in-example.txt) · [Profile audit](benchmark-results/phase-4n-2026-11-18/all-in-profile-audit.txt)

## Independent reference and candidate

The reference enumerates the 990 unordered pairs left after removing Hero's two cards and the five board cards. It gives each pair one unit of starting mass, multiplies by the reference probability of Villain's earlier observed actions, then applies the likelihood of the observed river action at that exact size. It normalizes in log space. Zero compatible likelihood is an impossible observation and raises. The known fold/call law uses the actual effective price, including an exact or short all-in call. The opening law sums the mass of sizes that collide at the minimum or stack cap. The full posterior is cross-checked against direct multiplication and independent Treys enumeration through the Phase 4J evaluator.

In the manual blocker control, 44 of 990 holdings contain Ts on As Ks Qs Js 2d when Hero holds 9s 3c. Betting twice as often with those 44 holdings gives them `88/1034` of the posterior and leaves Hero equity `946/1034`. Two-combo controls verify unequal prior weights after a check, bet, shove and fold. Separate controls cover zero likelihood, positive mass too small to multiply directly, a short all-in call, and coalescing three reference sizes into one shove.

The candidate starts from the existing pre-action reach on the first river solve's support. It forms the posterior for any opening wager and a second posterior using the same solver's neighboring size rows, interpolated in log target space. It preserves 5% of the incoming prior, then blends the two betting posteriors in the remaining 95%. Local size share is `n/(n+20)` for `n` observed river opening bets. With no local mass it uses the pooled bet; with no pooled mass it keeps the prior. It cannot recover a combo removed by the first solve. It can keep a legal combo that production's mapped bet or second prune removed. It sees no opponent hole cards, reference likelihoods or style labels. It does not change the production range or add a solver.

## Controlled experiment

See the [frozen protocol](PHASE_4N_PROTOCOL.md). Within each row the decision node, exact concrete menu, Hero's modeled continuation after an opponent re-raise, and 80-step decision converter are fixed. The three arms differ only in range: production final reach, research candidate, and true posterior. Under **true replies** all arms get the same reference fold/call matrix. Under **production replies** all arms get the same frozen production policy, including legal re-raises. As in Phase 4L, a combo outside the final production solver's support gets a response averaged over the nearest retained showdown ranks. This extension is shared and cannot affect the baseline, which puts zero weight there. All policies are scored under the true posterior and true responses. Regret is measured against the best action on the common menu.

The sampled profile deals, calibration deals and holdout deals use separate seeds. Real Phase 4K histories provide 3, 30 and 100 completed-hand prefixes. Their legacy fixed/capped bet sizing supplies no matched hand-by-size labels for this reference extension. The holdout changes both Hero position and chip geometry and includes 50%, 80% and 135% pot bets plus shoves. Postflop checks and preflop paths are scripted. The mismatch panel pairs a range based on the opposite opponent profile with the same true scoring law. Board-block intervals group all seats and profile prefixes from a deal and condition on the two realized holdout profile streams. These comparisons identify effects within this synthetic panel, not performance across live opponents or all river lines.

Calibration used 48 matched and 48 mismatch comparisons on four deals. Matched TV fell from 0.6733 to 0.6595. With production replies exact EV changed by +0.022 bb, with six losses above 0.01 bb and a worst loss of 3.215 bb. With true replies it changed by −0.098 bb with three such losses and a worst loss of 2.788 bb. The candidate and gates went into holdout unchanged.

Combo total variation is half the sum of absolute probability errors. The expected multiclass Brier score minus the reference's irreducible variance is the sum of squared combo probability errors; zero is best for both. Equity counts Hero wins plus half of ties, without assuming any further betting. Normalized support and inverse concentration (`1 / sum(p²)`) tell different stories: weights can be dispersed over many combos and still give zero to important legal hands.

## Holdout range accuracy

| Range arm | Combo TV | Excess Brier | Hero equity | Equity MAE | True mass absent | Effective combos | High card / pair / two pair+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Production | 0.639 | 0.00940 | 69.57% | 17.79 pp | 32.44% | 435 | 23.24 / 41.28 / 35.48% |
| Candidate | 0.620 | 0.00764 | 67.98% | 15.98 pp | 28.54% | 475 | 22.44 / 41.32 / 36.24% |
| True posterior | 0 | 0 | 59.56% | 0 | 0 | 403 | 11.83 / 38.02 / 50.15% |

All distributions excluded blocked cards and normalized to one. The candidate improved TV on 192/288 rows. It reduced concentration in the most collapsed estimate: minimum effective combos rose from 16.77 to 26.02. On average both estimates still allocated too much to high card and too little to two pair or better. However, on the paired board behind the largest gains, the baseline assigned **100%** to two pair or better while the true posterior assigned **26.60%**. Hand class is a strength proxy; on a paired board the high-card bucket is empty even when the opponent can bluff. Pooled composition can obscure errors in both directions.

| Diagnostic substitution | TV against the corresponding truth | Equity MAE |
| --- | ---: | ---: |
| Incoming production prior, before first river prune (against true prior) | 0.521 | 8.47 pp |
| Incoming production prior, on first river solve support (against true prior) | 0.522 | 8.48 pp |
| Production mapped bet, before re-prune (against true posterior) | 0.637 | 17.71 pp |
| Estimated prior × true bet likelihood (against true posterior) | 0.545 | 9.87 pp |
| True prior × candidate likelihood (against true posterior) | 0.422 | 12.16 pp |

The incoming prior was already inaccurate. By the first river betting node, 27.85% of true pre-bet mass was outside production support, versus 22.58% before its first river prune. Skipping the second prune restores 3.90 points of true posterior support, but barely moves TV. Restoring the true prior gives the larger posterior TV improvement of the two hybrid diagnostics. Restoring the true likelihood instead gives the smaller equity error. This implicates both inputs. The true-prior hybrid uses the candidate's floor for combos missing from the live likelihood grid, so it is a diagnostic rather than an estimate of the effect of any deployable prior.

## Exact EV, regret and harm

All values are bb. Harm counts differences below −0.000001 bb versus baseline within the same reply setting. Practical harm uses −0.01 bb. Total cost sums the losses on harmful rows.

| Fixed reply policy | Range arm | Mean EV | Paired gain | Mean regret | Harm / practical harm | Total harm cost | Worst change |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| True | Production | 6.105 | — | 0.969 | — | — | — |
| True | Candidate | 6.179 | +0.074 | 0.894 | 63 / 8 | 10.508 | −4.674 |
| True | True posterior | 7.074 | +0.969 | 0.00012 | 48 / 0 | 0.001 | −0.00017 |
| Production | Production | 5.740 | — | 1.333 | — | — | — |
| Production | Candidate | 5.937 | +0.197 | 1.136 | 81 / 23 | 62.231 | −8.633 |
| Production | True posterior | 6.699 | +0.959 | 0.375 | 68 / 23 | 41.209 | −8.129 |

The board-block 95% intervals for the candidate are **[−0.017, +0.204]** with true replies and **[−0.131, +0.594]** with production replies. With both oracle inputs, the fixed converter leaves only 0.00012 bb of supported regret. With the production continuation, even the true posterior leaves 0.375 bb and can make a severe loss. This shows response interaction; the oracle gain is a diagnostic ceiling with true replies, not a practical estimator result. The menu restricts what can be learned about alternate legal sizes.

With true replies the candidate switched the modal action in 26 rows. Average fold/call/raise/all-in frequencies moved from **15.97/5.21/15.96/62.86%** to **15.28/6.95/13.58/64.19%**. With production replies, 43 rows switched and the same frequencies went from **14.93/8.72/4.11/72.24%** to **12.50/18.66/2.51/66.33%**. All-in includes an all-in call when required by the engine. On 16 of 23 practical production-response losses both TV and absolute equity error improved; the corresponding count was four of eight with true replies. Better range calibration did not assure better decisions.

## Profile sparsity and public geometry

| Profile prefix | Rows | Mean observed river bets | Mean size share | TV: production → candidate | Exact EV gain, true replies | Exact EV gain, production replies |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 hands | 96 | 0.12 | 0.60% | 0.772 → 0.738 | +0.170 | +0.714 |
| 30 hands | 96 | 1.50 | 6.83% | 0.599 → 0.582 | +0.044 | −0.083 |
| 100 hands | 96 | 4.62 | 18.42% | 0.545 → 0.541 | +0.009 | −0.040 |

The 3-hand prefix had 17 of the 23 practical harms with production replies, while the 30- and 100-hand prefixes had five and one. The 96 rows with no size weight gained +0.705 bb with production replies; the 192 with positive weight lost 0.057 bb. These are different profiles and decisions, so the contrast does not estimate the causal effect of size weighting. Both largest gains use the zero-weight backoff. Excluding their shared board leaves a descriptive gain of +0.044 bb with production replies and +0.019 with true replies. The holdout supports a benefit from regularizing collapsed distributions in some cases; it does not establish a benefit from interpolation itself.

| Stratum | Rows | Gain, true replies | Gain, production replies |
| --- | ---: | ---: | ---: |
| Tight-passive | 72 | −0.059 | +0.037 |
| Loose-passive | 72 | +0.054 | +0.038 |
| Tight-aggressive | 72 | +0.184 | +0.366 |
| Loose-aggressive | 72 | +0.118 | +0.346 |
| Opposite profile | 288 | +0.055 | +0.034 |
| 9 / 15 / 30 bb | 96 each | −0.035 / +0.199 / +0.059 | −0.137 / +0.069 / +0.659 |
| 50% / 80% / 135% pot / shove | 72 each | +0.083 / +0.227 / −0.013 / 0 | −0.201 / +0.510 / +0.479 / 0 |

Opposite profiles worsened absolute calibration: candidate TV 0.661 versus 0.620 matched, and the production-response gain fell to +0.034 bb. Half-pot bets and shoves mapped on grid. All 80% and 135% wagers mapped off grid; 24 of the 72 overbets inherited a shove likelihood while Villain still had chips. The 135% group lost EV with true replies despite improving TV from 0.661 to 0.640. Under production replies the on-grid group lost 0.101 bb and the off-grid group gained 0.495 bb. At pots of 400–440, 460–500, and 600–640 chips the production-response deltas were +0.139, +0.510 and zero. The biggest pots in this layout are the shove cases; the pot, action, and texture cuts are descriptive and do not isolate a pot or SPR effect.

## Largest changes

The table summarizes the ranges before and after the observed bet. Triples are high card / one pair / two pair or better, as percentages. Full distributions on all 990 legal pairs, top combos, modeled action EVs, selected mixes and first-reply frequencies are in the linked evidence.

| Reply setting and case | Production prior | True prior | Production posterior | Candidate posterior | True posterior |
| --- | --- | --- | --- | --- | --- |
| True, largest gain | 0/57.74/42.26 | 0/81.20/18.80 | 0/0/100 | 0/26.21/73.79 | 0/73.40/26.60 |
| Production, largest gain | 0/72.13/27.87 | 0/81.20/18.80 | 0/0/100 | 0/10.52/89.48 | 0/73.40/26.60 |
| True, largest loss | 59.77/39.39/0.83 | 35.00/55.40/9.60 | 35.67/63.25/1.08 | 44.36/54.49/1.15 | 12.27/28.79/58.94 |
| Production, largest loss | 37.06/50.16/12.78 | 35.00/55.40/9.60 | 32.30/56.43/11.27 | 26.75/60.83/12.42 | 12.27/28.79/58.94 |

- **Largest gain with true replies, +7.772 bb.** Js 6c on 6h Tc Td Kd 4c, 15 bb on the button, faced 368 into 460 against loose-aggressive with a 3-hand profile. The 460-chip mapped row and final prune concentrated the baseline on strong hands: zero Hero equity and 96.56% of reference mass absent. Pooled betting and the weight floor lifted estimated equity to 31.51%; true equity was 95.80%. The baseline folded 99.997%, the candidate called 99.920%, and the true posterior shoved 99.998%. Their modeled fold probabilities to Hero's shove were 1.00%, 7.55% and 19.35%, respectively, from the same per-hand reply law. True fold/call/shove values were 0/+7.778/+14.309 bb. Candidate regret was still 6.537 bb. Replacing only the bet likelihood recovered the shove using the original prior.
- **Largest gain with production replies, +21.301 bb.** Same cards and wager, 30 bb from the big blind, the other 3-hand profile. Estimated equity was 0% baseline, 13.56% candidate and 95.80% true. Production fold forecasts facing a shove were 76.03% on the baseline range, 78.74% on the candidate and 91.17% on the true range; the actual reference fold rate was 35.83%. The baseline folded 99.991%, the candidate shoved 99.997%, and the true range with production replies raised to 1,564 at 94.30%. True fold/call/raise/shove values were 0/+7.778/+16.436/+21.303 bb. Candidate regret was 0.00032 bb. With true replies the candidate still folded, so the apparent full recovery depended on the production continuation overestimating folds. The true-likelihood hybrid with true replies recovered the shove.
- **Largest loss with true replies, −4.674 bb.** Ad 4h on 6s 5d Th 3c Qd, 15 bb on the button, faced 567 into 420 against tight-passive with 3 hands. The bet mapped to 420. Equity was 35.66% baseline, 44.35% candidate, and 6.41% true, against a 36.49% break-even calling threshold. Baseline and true posterior folded above 99.99%; the candidate called 99.999%. The same per-hand reply law gave shove fold forecasts of 45.32%, 51.03% and 17.72%. True fold/call/shove EVs were 0/−4.674/−8.634 bb, and candidate regret was 4.674 bb. The estimated prior already omitted 79.14% of true posterior mass. With true replies, correcting only the likelihood still called; correcting the prior while keeping candidate likelihood folded. This is evidence of a prior and support failure with sparse observations.
- **Largest loss with production replies, −8.633 bb.** Same cards, position and wager with the 30-hand prefix, still with zero observed opening bets. Baseline folded 99.999%; the candidate shoved 99.999%; the true range folded 99.999%. The candidate improved both TV (0.883 → 0.759) and equity error, but its range shifted the production shove fold forecast from 48.43% to 64.10% (34.38% under the true range and production replies, 17.72% in the reference). Modeled shove EV moved from −0.586 to +2.760 bb; the exact shove loses 8.634 bb. The candidate folded with true replies. Candidate regret of 8.633 bb here reflects the interaction of the estimated posterior with the frozen response.

## Promotion and Phase 4O

The candidate met the two mean EV thresholds, range calibration, mismatch, practical harm frequency (2.8% and 8.0%), and incremental compute limits. It missed three hard gates: the primary interval lower bound was negative, tight-passive fell more than 0.03 bb with true replies, and the worst loss far exceeded 0.50 bb in both settings. Reject promotion. The result leaves the expected gain uncertain even against these reference opponents. The high variance and severe loss also make deployment inappropriate on the observed panel alone.

**Choose A — improve the range prior.** The tested solver enters the river with TV 0.522 and 27.85% of the true prior mass outside support. The true-prior substitution reduced combo TV more than the true-likelihood substitution and corrected the severe sparse loss that persisted even with a true betting likelihood. Start Phase 4O with one support-preserving research prior built from the existing preflop and earlier-street information. Hold the observed betting likelihood and the response fixed while changing that prior. Preregister a fresh panel with varied earlier-street lines and report how much of the restored support improves exact EV and how much creates new tail risk. The larger equity benefit of true likelihoods and the gains on the paired board keep uncertainty about the remaining likelihood error; they do not justify promotion of this candidate or reviving Phase 4M.

## Verification and Git status

- Focused tests: **17 passed** in 2.77 s. Research regression: **121 passed** in 339.82 s. Full backend suite: **942 passed** in 891.71 s, retaining all 933 baseline tests and adding nine Bayesian and range cases. The full suite ran with local loopback available for the API tests. Existing dependency deprecation warnings numbered seven in focused/research and eight in the full run.
- The two holdout runs reproduced all 576 matched and mismatch rows and non-performance summaries exactly under Python hash seeds 13 and 31. Each run used 288 live solves, with no unexpected solver fallbacks, invalid advice, blocked combos or invalid distributions. Exact reference payoffs matched independent tree traversal within 1e-10 bb. The largest discrepancy against the production solver's unrounded payoff was 0.000929 chips. The historical Phase 4M adaptive-minus-disabled loss reproduced at −1.179285 bb.
- The update took a median **0.135 ms** and peaked at **56,768 traced bytes** (55.4 KiB); the replay measured 0.141 ms and the same peak. This covers the update on already extracted arrays; it excludes trace instrumentation, profile collection, tree solving and native allocations outside the tracer. Median live tracing was 1.330 s. The entire holdout took 507.90 s and peaked at 351.70 MiB resident; replay took 510.91 s and 351.61 MiB.
- `pip check`, the frontend production build and the Coach render smoke test passed. `git diff --check` passed with the pre-existing LF/CRLF advisory in `backend/test_poker.py`. Git remains on `main` at `3e89367`, 19 commits ahead of local `origin/main`. Aside from this report, protocol, three research modules and the test file, the prior working-tree status is unchanged. Historical fixtures and evidence were preserved. No commit, push or deploy was made.

[Holdout rows and full extreme distributions](benchmark-results/phase-4n-2026-11-18/holdout.json) · [Replay](benchmark-results/phase-4n-2026-11-18/holdout-replay.json) · [Case diagnostics](benchmark-results/phase-4n-2026-11-18/holdout-diagnostics.txt) · [Full regression](benchmark-results/phase-4n-2026-11-18/backend-tests.txt) · [Research regression](benchmark-results/phase-4n-2026-11-18/research-tests.txt)

## Reproduction

From the project root, start with a fresh output directory. The solver and all input generation run offline. The runner refuses to overwrite results. The bounded launcher is the retained Phase 4H wrapper.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phase4nPy = '.\.venv\Scripts\python.exe'
$phase4nBound = '../benchmark-results/phase-4h-2026-11-17/run_bounded.py'
$phase4nOut = '../benchmark-results/phase-4n-reproduction'
New-Item -Path $phase4nOut -ItemType Directory -ErrorAction Stop | Out-Null
& $phase4nPy $phase4nBound 420 $phase4nPy -m research.holdem.phase_4n calibration "$phase4nOut/calibration.json"
& $phase4nPy $phase4nBound 1600 $phase4nPy -m research.holdem.phase_4n holdout "$phase4nOut/holdout.json"
$env:PYTHONHASHSEED = '31'
& $phase4nPy $phase4nBound 1600 $phase4nPy -m research.holdem.phase_4n holdout "$phase4nOut/holdout-replay.json"
& $phase4nPy -c "import runpy; runpy.run_path('../benchmark-results/phase-4n-2026-11-18/inspect_evidence.py',run_name='__main__')" "$phase4nOut/holdout.json" "$phase4nOut/holdout-replay.json"
& $phase4nPy -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0 test_research_holdem_phase_4n.py test_research_holdem_river_ev.py
& $phase4nPy $phase4nBound 2400 $phase4nPy -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
```

[Frozen input hashes](benchmark-results/phase-4n-2026-11-18/frozen-input-hashes.txt) · [Calibration](benchmark-results/phase-4n-2026-11-18/calibration.json) · [Phase 4M historical control](benchmark-results/phase-4n-2026-11-18/historical-control.json)
