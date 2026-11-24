# Phase 4O — Incoming range prior accuracy and support recovery

**Candidate rejected.** Production's 0.5% relative-reach cutoff removed 27.08% of the true incoming mass on 288 matched holdout decisions. Carrying positive weights through pruning restored all missing support and changed no modal decisions. Mean exact EV under production replies moved by **−0.0000020 bb per decision** with a paired 95% interval **[−0.00000481, +0.000000012] bb**. Substituting exact incoming weights gained **+0.226 bb** under the same replies, with a worst loss of **18.720 bb**. Prior weighting accounts for a meaningful part of modeled regret on this panel. The tested support repair leaves the production strategy in place.

## Incoming range architecture

| Step | Production behavior | Audit implication |
| --- | --- | --- |
| Public replay and profile | Coach reconstructs commitments, order of action, stack depth and public streets with the hand engine. When supplied, the opponent profile comes from completed histories, with strength information from legitimately revealed showdowns. The opponent-type label describes the profile. | No current Villain card enters the estimator. The same frozen profile is used at each solve. |
| Preflop | Both players start uniform over 1,326 combos. The nearest log-distance effective-depth chart has 15/30/60/100/200 bb anchors. The charts treat postflop realization as raw equity. The solver walks the heads-up position-specific chart and multiplies the observed actor's combo reach by the selected action probability. Observed raise targets map to the nearest abstract target. Profile locks can rerun the class solve and change the action rows. | A 9 bb spot uses the 15 bb chart. A chart policy can give a legal calling hand zero probability in the model. Expansion gives each combo its class row; six pair, four suited and twelve offsuit combos therefore carry their correct multiplicities. |
| Flop and turn | Board masks remove public blockers. Each solve keeps only reaches above 0.5% of that player's maximum weight and ensures the actual Hero holding is present. Applying an observed action copies the product `old reach × action probability` back only for kept combos. Hand strengths, board texture, blockers and stack geometry influence the solved policy. | A low positive weight dropped before Villain acts becomes exactly zero at the first observed Villain action. Subsequent solves have no way to restore it. A covered action's exact zero is a distinct source of support loss. |
| River before and after the wager | The first river solve trims again. The compatible pre-bet reach is the incoming prior. The solver applies the observed wager's mapped action row once. Off-menu replay can re-solve and trim at the actual commitments after the wager. | The prior and posterior for the controlled fresh panel match production reach on the relevant solve supports. Off-menu historical controls record the final trim separately. |
| Profile locks | The adaptive solver partially pools opportunity and action counts across postflop streets, smooths observed frequencies and limits the degree of locking. Strength correlation is learned from selected shown hands. No exact-size read enters default Coach. | Reusing an historical profile as a model parameter across solves is distinct from counting the current action twice. The trace aligns one update per actual Villain event. Phase 4M/4N showed that stack-closing calls enter the facing-bet denominator without entering the ordinary call numerator and can contaminate aggressive showdown evidence. This phase leaves that input fixed. |

The audit conditions the evaluated distributions on the same 990 legal river pairs. Hero's two cards leave 1,225 possible pairs before the board, followed by 1,081 after the flop, 1,035 after the turn and 990 after the river. Those card removals are legitimate and carry zero reference mass on the final legal cohort. The earlier-street action models themselves are solved using the board then visible. Production uses compatibility in the equity traversal and masks Hero blockers in the range report. The pruning maximum is taken over the board-compatible public range before conditioning on Hero's blockers. Unnormalized reach products are proportional to their normalized equivalents, and the relative-to-max pruning decision is scale invariant. The heuristic simulator's separate range updater is outside this Coach path. [Coach replay](backend/coach/service.py) · [Production replay and range supports](backend/solver/bot.py) · [Preflop charts](backend/solver/preflop.py) · [Profile locks](backend/solver/exploit.py) · [Range intelligence](backend/simulation/range_intelligence.py) · [Phase 4N observer audit](PHASE_4N_REPORT.md)

## Independent reference and research candidate

The reference enumerates unordered legal pairs with one unit of prior weight and multiplies independent probabilities for Villain's observed public actions. Tight opponents participate at 0.85 with pairs or AT+ and at 0.09 otherwise. Loose opponents participate at 0.88. The script includes one paid call on the button line or two when Villain limps and calls a big-blind raise. Checks use the complement of the type's opening probability. Earlier leads use that opening rate and the explicit size probability. Facing a wager uses the type's call probability at its actual effective price. A check followed by a call contributes two distinct terms. Hero's scripted choices add no Villain-dependent likelihood. The river bet uses the independently specified Phase 4N size law including coalescing sizes at the stack cap, and only enters the posterior.

The runner cross-checks the log-normalized Bayesian reference with direct multiplication and the exact river evaluator's independent combo and payoff traversal. The hand-computed regression assigns two legal hypothetical holdings masses of `0.85 × 0.92 × 0.78` and `0.09 × 0.98 × 0.12` after a paid call, check and small-price call. Dividing by their sum yields approximately 98.29% and 1.71%. A separate control checks a retained action zero, a positive pruned weight, a chart zero, and a blocked donor. These controls exercise normalization, legal support and single application of action evidence. [Reference and candidate implementation](backend/research/holdem/phase_4o.py) · [Regression controls](backend/test_research_holdem_phase_4o.py)

The candidate keeps positive preflop chart reach through all previous Villain actions. Where a solved probability exists, use it. Where the solver has trimmed a column, assign that action the retained compatible range's reach-weighted probability. This is the production prediction for an unclassified holding conditional on membership in the retained donor population. It is a deterministic pooled estimate based on the action actually observed. It introduces no tuned floor and preserves chart zeros and known action zeros. Earlier donor compatibility uses Hero's cards and the public board as it stood on each street. The river likelihood uses the same extension for every arm, so changes to that likelihood cannot explain the candidate versus production contrast. The estimator uses no holdout type label, future action or private Villain information. A zero-observation profile cell follows the existing production fallback and supplies no added candidate evidence.

For hands that survive production pruning, the candidate uses the same sequence of multiplicative action weights. Their relative weights stay fixed before and after the wager. The candidate's TV from production is therefore exactly the candidate probability allocated to recovered hands. This bounds how much the candidate can improve TV against the reference. Restoring many hands with tiny weights can remove a large support deficit and have very little effect on the distribution used for EV.

The reference and production responses are each frozen per holding and action, including the production model's existing nearest-rank continuation for hands without a response column. For A, B and C, the river likelihood, 80-step fixed-value selector, concrete legal menu and Hero continuation remain fixed. C substitutes only the exact incoming prior. Its posterior and decision EV can still be wrong. All realized EVs score against the independent true posterior and true replies. All percentages below for high card, one pair and two pair or better describe strength. They cannot directly identify betting intent. [Frozen protocol](PHASE_4O_PROTOCOL.md)

On 72 independent matched development comparisons, missing prior mass fell from 35.46% to zero and prior TV moved from 0.645 to 0.640. Candidate EV moved by +0.00006 bb with reference replies and +0.00004 bb with production replies. All matched modal decisions stayed the same. With the true incoming prior, EV gained +0.194 bb with reference replies and moved by −0.006 bb with production replies. The development data and historical control used separate deal and profile seeds from the final holdout. [Development rows](benchmark-results/phase-4o-2026-11-18/development.json)

## Phase 4N loss reconstruction

**Ad 4h on 6s 5d Th 3c Qd.** At 15 bb on the button, Hero faced a 567-chip bet into 420 against tight-passive. Production mapped the wager to its 420-chip action row. At the actual price, the exact values were fold **0**, call **−4.674 bb**, shove **−8.634 bb**. Calling required **36.49%** equity and the exact posterior gave Hero **6.41%**.

| 3-hand profile, first disappearance | Pairs | True incoming mass | True post-bet mass | Examples |
| --- | ---: | ---: | ---: | --- |
| Preflop call row | 0 | 0% | 0% | All pairs had positive chart reach |
| Flop prune | 47 | 17.07% | 7.29% | As Qs, Ah Qh, Ac Qc, As Ts |
| Turn prune | 58 | 11.01% | 13.15% | Qs Qh, Qs Qc, Ah Ts |
| First river prune | 486 | 46.95% | 58.70% | Qh Qc, all three 33 combos, 5s 5h |
| **Before observed bet** | **591** | **75.03%** | **79.14%** | Flop/turn actions added no exact policy zeros |

The candidate restores all 591 legal omitted holdings and assigns them 0.623% of its incoming probability versus 75.03% in the reference. Each missed QQ combo carried 0.510% of the true prior and 3.127% of the true posterior. The candidate gives Qs Qh about 0.000318% of its prior and Qh Qc about 0.000025%. Incoming TV moves from 0.84194 to 0.83598. Under the shared mapped wager, Hero's estimated equity moves from 35.703% to 35.705%. Phase 4N's reweighted posterior gave 44.347% and chose the losing call with reference replies. Substituting the true prior under its Phase 4N likelihood gave 29.098% and recovered the reference-response fold. Phase 4O's candidate also folds with reference replies, as does the controlled production range. With production replies the estimated shove wins 0.269 bb before support recovery and 0.283 bb afterward. Both controlled policies shove and the live seeded recommendation is also a shove. The recovered support therefore leaves the loss mechanism active under production replies.

At 30 hands, all 38 pre-bet omissions occur at the first river trim, costing 11.03% of true incoming mass and 4.47% of true post-bet mass. Actual production's off-menu re-solve leaves 230 combos and misses 82.48% of the true posterior. Phase 4N replaced that final estimate with its 952-combo updated range and shoved because the production continuation forecast a 64.10% fold rate and +2.760 bb shove EV. The true fold rate when facing that shove was 17.72%. The Phase 4O candidate and the pre-reprune controlled production range both fold. Restoring the oracle prior under the fixed mapped likelihood still picks the shove in both response settings. This is a distinct example of likelihood error interacting with accurate incoming weights. [Full per-combo case evidence](benchmark-results/phase-4o-2026-11-18/historical.json) · [Historical diagnostics](benchmark-results/phase-4o-2026-11-18/historical-diagnostics.txt)

## Holdout support attribution and calibration

The frozen holdout contains 12 independent boards, crossed with two independent profile streams, two seats per board, four opponent styles and 3/30/100-hand profiles. The 288 matched comparisons share those 12 board blocks. Inference conditions on the two sampled streams. An additional 288 comparisons use the opposite profile on both style axes. Positions, depths and action histories are sampled by schedule. The synthetic betting and response laws, scripted paths and half-pot/shove restriction bound the inference to this panel.

| First exclusion, matched holdout | Mean legal combos lost | True incoming mass lost | True posterior mass ultimately missing from that source |
| --- | ---: | ---: | ---: |
| Preflop chart rows | 0.00 | 0.00% | 0.00% |
| First flop solve | 112.13 | 15.48% | 15.26% |
| First turn solve | 28.31 | 3.47% | 3.53% |
| First river solve | 94.19 | 8.13% | 8.24% |
| Covered flop/turn action rows | 0.00 | 0.00% | 0.00% |
| **Total** | **234.63** | **27.08%** | **27.03%** |

These losses are mutually exclusive and use final reference weights. All 432 observed Villain preflop call rows left chart support positive, including for unlocked chart controls, and 204 of 288 modeled profiles used a locked chart. Chart weighting was already far from the synthetic action laws. Mean combo TV across individual paid preflop updates was 0.446 and it was 0.473 after the last preflop call on each row. Stage TV averaged 0.473 at the flop prune, 0.541 at the turn prune and 0.601 on the incoming river support. In the applicable histories the modeled flop lead and turn call reached mean prefix TV of 0.647 and 0.638, respectively. These are comparisons on the relevant history subsets. Earlier action weighting can worsen range accuracy while retaining positive likelihoods for every covered hand. Pruning then turns those low inferred weights into exact exclusions. The explicit card masks, raw through-street products and final production posterior all passed the causal replay checks.

| Distribution | Combo TV | Missing true mass | Excess Brier | Mean absolute Hero equity error | High card / pair / two pair+ |
| --- | ---: | ---: | ---: | ---: | --- |
| A incoming | 0.60071 | 27.08% | 0.009463 | 12.47 pp | 14.13 / 47.11 / 38.76% |
| B incoming | 0.59887 | 0.00% | 0.009339 | 12.44 pp | 14.13 / 47.10 / 38.76% |
| Exact incoming | 0 | 0% | 0 | 0 | 9.36 / 40.96 / 49.67% |
| A after wager | 0.68282 | 27.03% | 0.016394 | 15.22 pp | 12.83 / 42.50 / 44.67% |
| B after wager | 0.68116 | 0.00% | 0.016228 | 15.19 pp | 12.83 / 42.50 / 44.66% |
| C after wager | 0.31370 | 0.00% | 0.003921 | 7.54 pp | 8.54 / 38.98 / 52.48% |
| Exact posterior | 0 | 0% | 0 | 0 | 5.03 / 27.25 / 67.72% |

The reference laws give every legal combo positive mass on these lines. For false inclusion, the measured concern is excess weight on holdings with reference probability below 1/990. B covers an average of 679 of these prior holdings versus 510 for A. Their excess allocation falls slightly from 50.21% to 50.08% of probability. In the posterior the covered count rises from 541 to 716 and excess allocation falls from 57.94% to 57.82%. The candidate leaves the large overweights largely intact. Exact incoming weights under the mapped likelihood give 0.314 posterior TV. The production prior under the true wager likelihood gives 0.589 TV and 10.92 points of equity error. Both inputs matter on this panel. [Holdout rows and stage audit](benchmark-results/phase-4o-2026-11-18/holdout.json) · [Holdout diagnostics](benchmark-results/phase-4o-2026-11-18/holdout-diagnostics.txt)

## Exact EV and downside

All actions are scored against the same true posterior and true replies. Regret uses the best action available on the common concrete menu. Harm counts compare each arm with A and use the frozen 0.000001 bb reporting threshold and 0.01 bb practical threshold.

| Replies used for selection | Arm | Mean EV, bb | Mean regret, bb | ΔEV vs A, bb | Harm / practical harm | Total harmful cost, bb | Worst ΔEV, bb |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reference | A production prior | 6.834724 | 0.649391 | 0 | 0 / 0 | 0 | 0 |
| Reference | B support recovery | 6.834726 | 0.649389 | +0.0000022 | 8 / 0 | 0.000495 | −0.000423 |
| Reference | C exact prior | 7.205817 | 0.278298 | +0.371093 | 63 / 13 | 40.668 | −18.720 |
| Production | A production prior | 6.804987 | 0.679128 | 0 | 0 / 0 | 0 | 0 |
| Production | B support recovery | 6.804985 | 0.679130 | −0.0000020 | 15 / 0 | 0.000645 | −0.000205 |
| Production | C exact prior | 7.030878 | 0.453237 | +0.225891 | 56 / 16 | 56.859 | −18.720 |

The paired board-block interval with reference replies was [−0.00000281, +0.00000703] bb. B made zero modal changes in both settings. Aggregate fold, call, non-all-in raise and shove frequencies each moved by less than 0.001 percentage points. C changed the modal action on 46 rows with reference replies and 41 with production replies. With production replies it moved fold frequency from 19.44% to 27.78% and shove frequency from 75.81% to 65.21%. On this holdout C removed 57.1% of A's mean regret with reference replies and 33.3% with production replies. Its worst loss shows that accurate incoming weights can still amplify downstream likelihood and response errors. These gains measure the oracle substitution with the frozen likelihood and continuation extension. [Paired decisions and oracle policies](benchmark-results/phase-4o-2026-11-18/holdout.json)

### Largest new candidate losses

- **Reference replies, −0.000423 bb.** Js 3c on 2d Ah Jh 2h Kh, 9 bb on the button, faced a 200-chip bet into 400 after two check-through streets against a tight-aggressive three-hand profile. Pruning removed 236 pairs carrying 15.76% of true incoming mass. The research posterior gave Hero 24.44% equity versus 24.46% in A and 58.63% in the reference. Fold remained modal, modeled call EV moved from −0.0431 to −0.0451 bb, and a small drop in call frequency from 0.1774% to 0.1617% reduced realized EV. The exact call and shove earned +2.690 and +2.870 bb. Even the exact incoming prior under the mapped bet gave only 17.76% equity. The true wager likelihood substantially moved the posterior in this spot.
- **Production replies, −0.000205 bb.** As Qs on Qh 4d Td 4s 3c, 30 bb on the button, faced 400 into 800 after calling Villain's flop bet and checking through the turn against a tight-aggressive three-hand profile. A excluded 92.01% of true incoming mass. B restored those holdings and the estimated posterior still held 99.41% two pair or better on this paired board. Estimated equity moved from 79.73% to 79.68% versus 91.85% true. The model valued raise to 2,000 above shove under both priors, and the modal raise stayed fixed. The exact raise and shove earned 21.377 and 22.270 bb. The production continuation assigned 28.64% to a re-raise after Hero raised to 2,000 under A and 28.84% under B. That response is absent from the synthetic law. With reference replies, both A and B preferred the shove. [Full extreme vectors and action values](benchmark-results/phase-4o-2026-11-18/holdout.json)

C's worst row used Js 3c on the same 2d Ah Jh 2h Kh board but at 30 bb from the big blind, against a 30-hand loose-aggressive profile. Villain shoved 2,400 into 1,200 after calling Hero's turn bet. Equity needed to cover the shove was 40%. The mapped likelihood produced 32.02% equity under A and B, 41.76% under C, and the true posterior gave 8.80%. C covered the shove and lost 18.720 bb relative to A in both settings. No further Villain response was possible, which isolates the interaction of accurate incoming weights with the erroneous shove likelihood. [Holdout decision rows](benchmark-results/phase-4o-2026-11-18/holdout.json)

## Profile, stack and line sensitivity

Every matched subgroup reached full true prior support with B. Candidate EV deltas below are in millionths of a bb per decision.

| Matched group | Comparisons | Prior mass omitted by A | Prior TV A → B | Reference replies ΔEV | Production replies ΔEV |
| --- | ---: | ---: | --- | ---: | ---: |
| Tight-passive | 72 | 34.83% | 0.8043 → 0.8023 | +1.50 | −2.15 |
| Loose-passive | 72 | 15.96% | 0.3891 → 0.3880 | +6.91 | −1.21 |
| Tight-aggressive | 72 | 36.85% | 0.7701 → 0.7674 | −4.25 | −4.24 |
| Loose-aggressive | 72 | 20.69% | 0.4393 → 0.4378 | +4.69 | −0.41 |
| 3 completed hands | 96 | 64.17% | 0.7530 → 0.7490 | +7.14 | −6.11 |
| 30 completed hands | 96 | 15.65% | 0.5622 → 0.5607 | −0.50 | +0.10 |
| 100 completed hands | 96 | 1.42% | 0.4870 → 0.4869 | +0.00 | +0.01 |
| Zero observed river opening bets | 84 | 66.46% | 0.7738 → 0.7697 | +7.72 | −6.87 |
| 9 bb | 96 | 22.13% | 0.5482 → 0.5466 | +3.21 | +0.13 |
| 15 bb | 96 | 32.06% | 0.6343 → 0.6323 | +2.21 | −0.81 |
| 30 bb | 96 | 27.06% | 0.6196 → 0.6177 | +1.21 | −5.32 |
| Check-through flop and turn | 96 | 20.16% | 0.5051 → 0.5045 | −1.41 | +0.17 |
| Villain flop bet, checked turn | 96 | 28.34% | 0.6575 → 0.6546 | +5.86 | −5.23 |
| Checked flop, Villain calls turn bet | 96 | 32.75% | 0.6395 → 0.6374 | +2.19 | −0.94 |

The big-blind line with a Villain limp and then call omitted 33.02% of incoming mass, versus 21.14% on the button line with a single Villain call. On observed river shoves candidate EV equaled A in both settings. Mismatched profiles showed the same lack of practical EV movement. Mean candidate changes were +0.0000053 bb with reference replies and −0.0000027 bb with production replies. Neither setting had a mismatch loss over 0.01 bb. Large support deficits were concentrated in sparse profiles, and their repair produced no material improvement even there.

## Gate decision and Phase 4P

**Retain production.** B failed the +0.05 bb production-response mean, the positive lower bound, the +0.02 bb reference-response mean, and both 0.01 TV improvement thresholds. It passed the downside, matched-opponent, mismatch, calibration non-regression and performance checks. No holdout observations were used to adjust the candidate. [Frozen thresholds](PHASE_4O_PROTOCOL.md) · [Recorded gate](benchmark-results/phase-4o-2026-11-18/holdout.json)

Phase 4P should test one calibrated incoming-weight model for the preflop response to a raise, keyed by position, effective stack and whether Villain has already limped. This is where substantial weight error appears before later actions compound it. Use fresh completed histories and independently known synthetic participation laws for validation, with the same prior-only exact-EV test and separate likelihood and response controls. A candidate should improve held-out mass calibration for the specific hands that production underweights and clear the same practical loss gates. The exact-prior losses show why a calibration win alone gives insufficient evidence for gameplay validation.

## Verification and Git status

- Full backend regression passed **945 tests** in 1,793.74 s with local Windows loopback available for the API tests. This retains all 942 existing tests and adds three Phase 4O tests. The run reported eight existing dependency deprecation warnings. [Full backend regression](benchmark-results/phase-4o-2026-11-18/backend-tests.txt)
- Focused regression passed **20 tests** in 21.44 s and the research suite passed **124 tests** in 578.34 s. Each reported seven existing eval7 dependency warnings. The three new deterministic controls cover compatible donor pooling and zero preservation, first-loss attribution and hand-computed prior normalization. [Focused regression](benchmark-results/phase-4o-2026-11-18/focused.log) · [Research regression](benchmark-results/phase-4o-2026-11-18/research-tests.txt)
- Both holdout runs reproduced all 576 matched and mismatch decision rows, complete extreme vectors, statistical outputs and gate results exactly after timing and peak memory were excluded. Each ran 288 live Coach replays. Reference checks found zero unexpected fallbacks, invalid probability mass, illegal recommendations or blocked combos. Exact reference action values agreed with independent traversal within 1e-10 bb. Maximum discrepancy from the unrounded production solver payoff was 0.001016 chips. The runner checked replay chip conservation and used completed-history validation for training. Frozen inputs matched their recorded SHA-256 hashes. [Holdout replay](benchmark-results/phase-4o-2026-11-18/holdout-replay.json) · [Frozen inputs](benchmark-results/phase-4o-2026-11-18/frozen-input-hashes.txt)
- Median incremental prior update was 0.239 ms with a 53.0 KiB peak traced allocation, versus 0.249 ms and the same peak on replay. This times pooling and the update from captured policy arrays. Live replay including solve had a 2.814 s median on the first run. Entire runs took 1,069.81 and 1,069.93 s, with process peaks of 493.50 and 493.86 MiB. The process figures include the solvers, reference calculations and stored audit rows. The first development attempt exceeded its 480 s process bound. A monitored rerun completed in 275.92 s with the same estimator, seeds and input schedule. [Development progress](benchmark-results/phase-4o-2026-11-18/development.log)
- `pip check`, the frontend production build and the Coach strategy render test passed. The experiment uses local code and pre-existing dependencies and can run offline.
- Git remains on `main` at `3e89367`, 19 commits ahead of local `origin/main`. The four new Git-visible files are the report, protocol, isolated offline runner and tests. Benchmark evidence is in the existing ignored `benchmark-results/` directory. Prior working-tree edits and historical fixtures and evidence were preserved. `git diff --check` passed with the existing LF/CRLF advisory for `backend/test_poker.py`. [Starting status](benchmark-results/phase-4o-2026-11-18/initial-status.txt) · [Final status](benchmark-results/phase-4o-2026-11-18/final-status.txt)

### Reproduction

From the project root, use the existing backend environment and a fresh output directory. The runner refuses to overwrite results. Local loopback is needed for the API tests.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phase4oPython = '.\.venv\Scripts\python.exe'
$phase4oDir = '../benchmark-results/phase-4o-reproduction'
New-Item -Path $phase4oDir -ItemType Directory -ErrorAction Stop | Out-Null
& $phase4oPython -m research.holdem.phase_4o historical "$phase4oDir/historical.json"
& $phase4oPython -m research.holdem.phase_4o development "$phase4oDir/development.json"
& $phase4oPython -m research.holdem.phase_4o holdout "$phase4oDir/holdout.json"
$env:PYTHONHASHSEED = '31'
& $phase4oPython -m research.holdem.phase_4o holdout "$phase4oDir/holdout-replay.json"
& $phase4oPython ../benchmark-results/phase-4o-2026-11-18/inspect_evidence.py "$phase4oDir/holdout.json" "$phase4oDir/holdout-replay.json"
& $phase4oPython -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
```
