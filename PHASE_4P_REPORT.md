# Phase 4P — Preflop range weights and downstream error isolation

## Production range audit

| Stage | Current implementation | Consequence |
| --- | --- | --- |
| Starting distribution | The solver initializes all 1,326 unordered holdings with unit reach for each player. The 169-class chart expands onto the individual combos, preserving the six/four/twelve multiplicities of pairs, suited and offsuit classes. | Position changes action likelihood through the heads-up tree and acting seat. The cards dealt to either seat start with the same uniform law. |
| Stack and price | Effective starting stack in big blinds selects the nearest chart in log depth at 15/30/60/100/200 bb. Stack caps and the abstract menu change which raises are available. A public raise maps to the closest available aggression target. | Production uses discrete selection. There is no chart interpolation to distort weights. Chart equilibrium pays raw equity when a flop is seen, and nearby actual stacks can change charts abruptly. |
| Limp and raises | Replay walks every preflop action. Against a limp the BB can check or raise. An SB limp and later call multiply two distinct probabilities. The same actual action updates only its actor's range once. | With fixed policy rows, normalized Bayes updates and unnormalized reach products give the same ratios. Both the mapped price and the modeled action probabilities can misweight a combo. |
| Opponent profile | Coach uses completed public histories and publicly shown holdings. Preflop targets partially blend toward smoothed aggregate statistics. Missing or very-low-confidence cells leave locks off. Confidence bands start at 5/20/50 opportunities and allow 30/55/75% locking. The displayed style label carries no strategy input. | Reviewed stats pool across depth, position and histories. A five-opportunity threshold can move a lock abruptly. The eight-showdown prior dampens selective shown-hand strength evidence, which remains conditional on reaching showdown. |
| Flop to river | Coach and the research baseline use the same replay, chart rows and live postflop solves via a read-only probe. Board masks and traversal compatibility remove blocked holdings. The solver's 0.5% relative-reach threshold prunes low positive weights before postflop actions. | Legitimate card removal and model-induced support loss are measurable separately. Current public action evidence enters once per observed actor action. Profile reuse supplies policy parameters across solves. The separate heuristic `PublicRangeTracker` used by simulation range intelligence follows different update logic. |
| River decision | The final solve uses the modeled wager row and a coupled strategy. The experiment holds the continuation and concrete menu fixed and uses the existing 80-step fixed-value selector. | Policy EV differences isolate range inputs at a fixed solve. Live advice remains an independent parity and legality control. |

[Preflop charts](backend/solver/preflop.py) · [Production replay](backend/solver/bot.py) · [Coach](backend/coach/service.py) · [Heuristic range intelligence](backend/simulation/range_intelligence.py)

### Confirmed defects

- The preflop showdown percentile computes a strict ordinal rank even when estimated equity is tied. All 169 classes contain suit-equivalent combos with different percentiles. AKo As Kd and Ah Kc score 0.949849 and 0.946078 respectively on the same class strength. The largest within-class spread is 0.008296. Tied ranks should have the same percentile. This perturbs the observed strength-correlation input to profile locks. Its contribution to decision EV was not isolated.
- The limp opportunity predicate also admits a BB check after an SB limp. The check has zero price, the BB's commitment already equals the blind, and there has been no raise, so the BB check adds a failed limp to the denominator. The preflop lock uses that rate for the SB first-to-act node. Separately, a closing all-in call can enter the preflop raise-opportunity denominator because the legal list contains `all_in` even when the action cannot increase the highest commitment. The previously established river call and showdown classification defects remain relevant downstream.
- Lock construction can take a residual from rates with different denominators. A synthetic accumulator state with 8/10 limps and 16/20 raises yields independently smoothed rates of 0.750 and 0.773. The computed fold residual is negative and the rounding/floor/renormalization produces targets of 49.67% aggression, 49.67% limp and 0.66% fold. The final probabilities are valid. The residual lacks a joint opportunity interpretation.

[Opponent observer](backend/simulation/opponent_model.py) · [Lock targets](backend/solver/exploit.py) · [Showdown percentiles](backend/solver/showdown.py) · [All-in legality](backend/simulation/engine.py) · [Production defect reproductions](benchmark-results/phase-4p-2026-11-18/production-audit.txt)

### Modeling limitations

The first-raise and three-bet statistics pool public contexts. A raise after an SB limp is aggression depth one in the chart, so the SB facing an isolation raise receives the same fold/three-bet lock inputs as the BB facing an open. At higher aggression depth, the lock anchors fold versus total continuation and leaves the call/reraise split to the chart. The standard profile trains at 15 bb, so its learned statistics give no separately identified deep or short-stack rates. Small samples and discarded unshown holdings are especially weak evidence about per-combo weights. The two postflop solvers can assign tiny probabilities to genuinely plausible holdings. The audit found breakpoint discontinuities, contextual pooling and sizable probability errors within legal support. It found no duplicate application of the same preflop event along the controlled paths.

## Reference and candidate

The offline reference enumerates legal unordered pairs and directly multiplies known synthetic action probabilities by position, actual effective depth and previous action. Exact preflop measurement uses Hero blockers only. The river evaluation conditions on Hero and board blockers and carries the reference law through the observed flop/turn actions. The two-combo manual control uses As Ah and 7s 2d against tight-passive at 15 bb after a limp and call. The respective likelihoods are `(0.93 × 0.7456) × (0.86 × 0.9184)` and `(0.43 × 0.9184) × (0.35 × 0.976)`. Normalization gives about 80.2% and 19.8%. Tests separately cover check and raise laws, observations at different depths, support projection, deterministic count prefixes and both blocker cohorts. The independent Bayesian river enumerator agrees with direct exact enumeration, and independent action payoff calculations agree with the fixed tree traversal within 1e-10 bb on every comparison.

The candidate estimates fold, passive and aggression for each existing hand category in a public context. It adds local synthetic action counts, up to eight cross-depth pseudo-observations and eight chart pseudo-observations per category/holding. It projects back onto production support and preserves the chart's within-group size split. With zero count evidence it recovers the chart. It applies the resulting preflop likelihood ratio to captured river reach, leaving earlier postflop action rows, production pruning and the decision menu fixed. The estimated probability for a hand depends on the recorded public action prefix and independent sampled training counts. The training source has synthetic holding labels, including for opportunities without a showdown. Transfer to public-history-only data and re-solving upstream policies with different reach are separate research questions. The production histories use the legacy Phase 4K preflop law for the corresponding style, while the calibration sampler uses the new law. This gives the candidate more directly matched evidence. The experiment measures the prospective value of better weights in this setup, and does not identify the incremental value of the context variables independently of the added labeled evidence.

Development comprised 16 decisions. Preflop TV moved from 0.47079 to 0.42489, with 100% preflop coverage in both arms. Mean exact EV with production downstream models moved by −0.20591 bb per decision, driven by a 3.29458 bb loss on one modal change. The protocol and input hashes were recorded before the independent holdout.

[Frozen protocol](PHASE_4P_PROTOCOL.md) · [Runner](backend/research/holdem/phase_4p.py) · [Manual and deterministic tests](backend/test_research_holdem_phase_4p.py) · [Development evidence](benchmark-results/phase-4p-2026-11-18/development.json) · [Frozen input hashes](benchmark-results/phase-4p-2026-11-18/frozen-input-hashes.json)

## Historical 18.72 bb loss

Hero held **Js 3c** in the BB at **30 bb** on **2d Ah Jh 2h Kh**, against loose-aggressive after a 30-hand profile from stream 91. Villain limped, Hero raised to 300 chips, Villain called, the flop checked through, and Hero bet 300 on the turn and was called. Hero checked the river. Villain shoved 2,400 into 1,200. The tree's `all_in` recommendation meant covering the shove. True EVs were **0 bb for fold** and **−18.720313 bb for calling**. Covering needed 40% equity. True post-wager equity was 8.7995%.

| Incoming estimate | Posterior Hero equity with production wager law | Modeled cover EV | Cover frequency | True policy regret |
| --- | ---: | ---: | ---: | ---: |
| Production | 32.0203% | −4.7878 bb | 0.00111% | 0.000207 bb |
| Calibrated | 35.1091% | −2.9345 bb | 0.00111% | 0.000207 bb |
| Exact incoming | 41.7599% | +1.0559 bb | 99.99889% | 18.720105 bb |

The exact incoming prior crossed the call threshold after the production shove likelihood weighted it. Using the true shove likelihood yielded 9.5438%, 11.5316% and 8.7995% equity respectively. All three policies then folded 99.99889% of the time. Neither supported action led to a Villain reply, so changing the response model had zero effect. The archived evidence includes all 990 incoming combo weights for all three estimates, both shove likelihood vectors, the reference posterior, empty reply menus and full policy mixes for A–D. Live Coach recommended fold.

[Complete historical case](benchmark-results/phase-4p-2026-11-18/historical.json) · [Original loss](PHASE_4O_REPORT.md)

## Holdout preflop calibration

All 96 rows retained all 1,225 preflop-compatible holdings. Mean combo TV improved by **0.08738**, from **0.48763 to 0.40026**. The unlocked-chart control had TV 0.63774. Effective combo count moved from 629.69 to 699.20, compared with 728.85 for the reference. Both estimates later retained 67.41% of the 990 river-compatible holdings with 33.06% of exact incoming mass outside support. Incoming TV improved from 0.60064 to 0.57852 on that identical support. Under the production wager law, posterior TV improved from 0.66938 to 0.65543. Under the true wager law it moved from 0.59799 to 0.57793.

| Preflop category | Production mass | Calibrated mass | Exact mass | Contribution to TV, production → calibrated |
| --- | ---: | ---: | ---: | ---: |
| Premium | 11.29% | 17.68% | 21.88% | 0.1067 → 0.0913 |
| Strong | 16.13% | 17.21% | 17.30% | 0.1028 → 0.0934 |
| Playable | 36.08% | 27.09% | 24.67% | 0.1457 → 0.0987 |
| Speculative | 19.35% | 18.83% | 16.90% | 0.0698 → 0.0637 |
| Weak | 17.14% | 19.19% | 19.25% | 0.0626 → 0.0531 |

Under the modeled wager, high card / pair / two pair or better was 15.88 / 36.61 / 47.51% for production and 15.53 / 36.42 / 48.05% for calibration. The exact posterior had 6.23 / 34.15 / 59.62%. With the true wager law, calibrated two-pair-plus mass rose to 59.66%. These are hand-strength proxies for value and bluff composition. Betting intent is unspecified by the synthetic law.

| Stratum | Rows | Final preflop TV, production → calibrated | A ΔEV, bb |
| --- | ---: | ---: | ---: |
| Villain BB | 48 | 0.420 → 0.374 | +0.203 |
| Villain SB | 48 | 0.556 → 0.426 | +0.231 |
| 9 bb | 32 | 0.518 → 0.449 | −0.203 |
| 15 bb | 32 | 0.484 → 0.387 | +0.123 |
| 30 bb | 32 | 0.461 → 0.365 | +0.731 |
| BB calls open | 24 | 0.287 → 0.213 | +0.00008 |
| SB limps, then calls | 24 | 0.412 → 0.264 | +0.383 |
| BB three-bets | 24 | 0.552 → 0.535 | +0.405 |
| SB opens, then calls three-bet | 24 | 0.699 → 0.589 | +0.080 |
| 3-hand profile / 4 calibration draws per cell | 32 | 0.631 → 0.602 | −0.175 |
| 30 hands / 32 draws | 32 | 0.430 → 0.332 | +0.286 |
| 100 hands / 128 draws | 32 | 0.402 → 0.267 | +0.540 |
| Stream 111 | 48 | 0.479 → 0.398 | +0.036 |
| Stream 112 | 48 | 0.497 → 0.403 | +0.398 |

The SB first-action prefix TV fell from 0.385 to 0.314 across opening and limping prefixes. The chart probe switched depth at 21.213, 42.426, 77.460 and 141.421 bb. Unlocked BB-call distributions on either side of those boundaries differed by 0.1700, 0.1004, 0.0583 and 0.0250 TV. Production locked the chart on 4/32 sparse rows and on all 64 denser-profile rows. Changes across profile prefixes include different replayed rows and a joint change in the amount of calibration evidence and production history. TV gains repeated in both streams, with greater variability in EV than in calibration.

## Exact river EV and error isolation

All values are bb per decision. Regret uses the best common action and exact reference payoffs. A uses both production models, B replaces the wager likelihood, C replaces the response, and D replaces both.

| Config. | Production EV / regret | Calibrated EV / regret | Calibrated ΔEV [95% interval] | Exact incoming EV / regret |
| --- | ---: | ---: | ---: | ---: |
| A | 2.7213 / 1.9341 | 2.9383 / 1.7171 | **+0.2170 [−0.5069, +1.0350]** | 3.2548 / 1.4006 |
| B | 3.7601 / 0.8953 | 3.8400 / 0.8154 | +0.0799 [−0.2658, +0.4677] | 4.3390 / 0.3164 |
| C | 2.6701 / 1.9853 | 2.8676 / 1.7878 | +0.1975 [−0.4151, +0.8722] | 3.4339 / 1.2215 |
| D | 3.8795 / 0.7759 | 3.9720 / 0.6834 | +0.0924 [−0.2863, +0.4969] | 4.6553 / 0.00010 |

| Incoming weights | True wager effect, B − A / D − C | True response effect, C − A / D − B | Interaction, D − C − B + A |
| --- | ---: | ---: | ---: |
| Production | +1.039 / +1.209 | −0.051 / +0.119 | +0.171 |
| Calibrated | +0.902 / +1.104 | −0.071 / +0.132 | +0.203 |
| Exact incoming | +1.084 / +1.221 | +0.179 / +0.316 | +0.137 |

The wager likelihood had the largest effect on absolute EV for every incoming estimate. Replacing it reduced the candidate's relative gain under production replies from +0.217 to +0.080 bb as the baseline improved more. The response oracle alone decreased average EV for the two estimated ranges and improved it for the exact incoming prior. The response oracle helped all three when the true wager law was already in use. The positive interactions quantify how errors in the wager likelihood and the replies can obscure each other's effects. The full oracle's near-zero regret checks the common menu and selector against these synthetic payoffs.

The 52 closing-shove decisions accounted for most of the wager-likelihood effect. B − A was +1.594 bb for production and +1.237 bb for the candidate on closing shoves, and +0.383 and +0.505 bb on the 44 half-pot decisions. With both production models, the candidate gained +0.593 bb on closing shoves and lost 0.227 bb on half-pot decisions. The response substitution has no branch to change on a closing shove. On half-pot decisions it moved the calibrated policy by −0.154 bb with the modeled wager likelihood and +0.288 bb with the true likelihood.

| Config. | Modal changes | Losses > 0.000001 bb / > 0.01 bb | Total harmful cost | Worst loss |
| --- | ---: | ---: | ---: | ---: |
| A | 12 | 19 / 7 | 38.638 | 10.410 |
| B | 6 | 16 / 4 | 12.936 | 4.443 |
| C | 10 | 18 / 6 | 34.156 | 10.410 |
| D | 8 | 15 / 4 | 17.836 | 5.126 |

In A, calibration moved average fold frequency from 35.42% to 40.63%, call from 8.33% to 7.29% and all-in from 56.25% to 52.08%. Non-all-in raises remained below 0.01%. The mean A improvement came from loose-passive (+1.695 bb). Tight-passive (−0.483), tight-aggressive (−0.176) and loose-aggressive (−0.169) each regressed. Two loose-passive decisions alone gained 23.435 and 20.169 bb. All interval estimates use 12 board blocks, keeping both streams and all styles within each resampled block. They condition on the sampled profiles and deal design.

[Holdout rows and distributions](benchmark-results/phase-4p-2026-11-18/holdout-13.json) · [Deterministic replay](benchmark-results/phase-4p-2026-11-18/holdout-31.json) · [Subgroup and replay diagnostics](benchmark-results/phase-4p-2026-11-18/holdout-diagnostics.txt)

## New severe losses

| Deal / stream / opponent | Change in recommendation | Worst relevant ΔEV, bb | Diagnosis |
| --- | --- | ---: | --- |
| 5 / 111 / tight-passive | Call → fold | −3.571 A | At 500 into 1,000, modeled equity fell from 25.69% to 22.91%, below the 25% call threshold. The true wager law restored the call. |
| 5 / 111 / tight-aggressive | Call → fold | −8.360 A | Same geometry, candidate equity 24.46%. The likelihood oracle restored the call. Exact action EV favored shoving at +15.082 bb versus +8.361 bb for calling. |
| 6 / 111 / tight-passive | Cover → fold | −3.583 A | At 550 into 700, both estimates folded using the true likelihood. Exact range plus true likelihood valued the cover at +3.583 bb. The estimated priors had too little equity. |
| 6 / 111 / loose-passive | Cover → fold | −4.443 A–D | With the true likelihood, candidate equity was 29.94% versus a 30.56% threshold. The true cover gained +4.443 bb. No further response was possible. |
| 6 / 112 / tight-passive | Shove → call | −4.426 A, B and D | With production likelihood, the true response raised the candidate's modeled shove above its call. With both oracles, the candidate's remaining range error still valued the call more. True shove and call were +12.441 and +8.015 bb. |
| 0 / 112 / tight-aggressive | Fold → cover | −3.841 A–D | At 2,500 into 1,000, candidate equity was 44.51% with the modeled likelihood and 49.99% with the true likelihood, both above 41.67%. True cover EV was −3.842 bb. |
| 5 / 112 / loose-aggressive | Cover → fold | **−10.410 A and C** | Kh 6c on 2h As Ah 2s 9d, 15 bb, 1,000 into 1,000 after a BB three-bet. The calibrated posterior gave 31.35% equity with the modeled likelihood versus 41.95% for production. The threshold was 33.33%. True likelihood moved the candidate to 40.67% and restored the cover. |
| 2 / 112 / tight-aggressive | Shove → fold | −5.126 D | Under both oracles, baseline valued shove at +0.057 bb and candidate at −1.908 bb. The exact shove value was +5.127 bb. B's overly optimistic fold forecast made both ranges shove. The two oracle substitutions expose the remaining incoming-range error. |

The fresh exact-incoming oracle repeated the historical failure on deal 2, stream 111 against tight-passive. With 8c 3d on 8s Ad Tc Ks 2s, it assigned 60.04% equity against a 2,500-chip shove into 1,000 with the production wager law, and 6.18% with the true law. Covering lost 21.291 bb. The response was irrelevant to a closing action. A separate response failure on deal 1, stream 111 used 5s 3d against tight-aggressive with a 200-chip wager into 400. Given the true posterior, production expected 71.11% folds to the shove and priced it at +1.160 bb. The true fold rate was 34.80%, shove EV was −3.396 bb, and the full oracle recovered fold. These cases identify separate failure mechanisms under exact incoming weights.

[Full severe candidate distributions and policies](benchmark-results/phase-4p-2026-11-18/holdout-13.json) · [Per-case factors and values](benchmark-results/phase-4p-2026-11-18/loss-and-interaction-diagnostics.txt)

## Promotion decision and Phase 4Q

**Reject the candidate at the exact-EV gate.** The primary mean exceeded +0.05 bb and the calibration, harm-rate and performance gates passed. The interval lower bound, 0.50 bb maximum-loss bound and per-opponent floor of −0.03 bb failed. Production keeps its current strategy. The paired gameplay gate did not open.

For Phase 4Q, isolate a research-only river wager-likelihood model calibrated by effective price and public history, with separate handling of closing shoves. Anchor the baseline range and response policies for the primary test, retain oracle controls, and pre-register the same downside and opponent gates. Include observer denominator fixes and tied-strength percentile correction as separate, measurable ablations. Use legal public evidence for training and validate the scope of any labeled synthetic result before applying it to production data. The strongest Phase 4P signal is the 0.90–1.22 bb improvement from the wager oracle across the tested priors and response settings. The response control and losses persisting under D establish residual errors to measure independently.

## Verification

- Full backend regression passed **949 tests** in 1,429.40 s, retaining all 945 existing tests and adding four Phase 4P tests. It reported eight existing dependency deprecation warnings. The initial run stalled on Windows asyncio loopback setup. A bounded socket-pair check reproduced the issue and the full rerun passed with local loopback available. [Backend regression](benchmark-results/phase-4p-2026-11-18/backend-tests-loopback.txt)

- Four deterministic Phase 4P tests cover hand-calculated sequential conditioning, legal reference probabilities, support-preserving shrinkage, blocker masks and reproducible sample prefixes. The focused set passed 15 tests and the full research regression passed 128 tests. Both had seven existing eval7 deprecation warnings. [Focused tests](benchmark-results/phase-4p-2026-11-18/focused-tests.txt) · [Research tests](benchmark-results/phase-4p-2026-11-18/research-tests.txt)
- Each holdout repeated all 96 decision rows and every non-performance field across Python hash seeds 13 and 31. All 15 frozen SHA-256 hashes matched. Recorded policies were normalized and used legal concrete targets. The runner found zero blocked holdings and zero unexpected solver fallbacks, checked chip conservation on replays and verified reference payoffs independently. The maximum discrepancy with unrounded production EV was 0.000647 chips.
- The incremental median update took 0.638 ms on seed 13 and 0.679 ms on seed 31. Both peaked at 218.0 KiB of traced incremental allocation. These measurements use captured production arrays. Common live replay medians were 2.832 and 2.813 s. The complete runs took 287.66 and 288.21 s under concurrent regression load and peaked at 277.82 and 278.26 MiB process resident memory. [Replay and performance evidence](benchmark-results/phase-4p-2026-11-18/holdout-diagnostics.txt)
- Dependency check, frontend production build and the Coach strategy render test passed. Reference generation, calibration and evaluation use the existing local dependencies. [Dependency check](benchmark-results/phase-4p-2026-11-18/pip-check.txt) · [Frontend build](benchmark-results/phase-4p-2026-11-18/frontend-build.txt) · [Coach render test](benchmark-results/phase-4p-2026-11-18/frontend-coach-test.txt)
- Git is on `main` at `3e89367`, 19 commits ahead of local `origin/main`. The four Git-visible Phase 4P additions are the runner, tests, protocol and this report. Pre-existing working-tree changes and earlier research evidence were preserved. Whitespace checks passed with LF/CRLF conversion advisories. [Starting status](benchmark-results/phase-4p-2026-11-18/initial-status.txt) · [Final status](benchmark-results/phase-4p-2026-11-18/final-status.txt)

### Reproduction

Start in the project root. Use a fresh evidence directory and existing backend virtual environment. Each process below has an external time bound. Local loopback is required for the API tests.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phase4pPython = '.\.venv\Scripts\python.exe'
$phase4pOutput = '../benchmark-results/phase-4p-reproduction'
New-Item -Path $phase4pOutput -ItemType Directory -ErrorAction Stop | Out-Null
$phase4pBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:], timeout=int(sys.argv[1])).returncode)'
& $phase4pPython -c $phase4pBound 120 $phase4pPython -m research.holdem.phase_4p historical "$phase4pOutput/historical.json"
& $phase4pPython -c $phase4pBound 480 $phase4pPython -m research.holdem.phase_4p development "$phase4pOutput/development.json"
& $phase4pPython -c $phase4pBound 1200 $phase4pPython -m research.holdem.phase_4p holdout "$phase4pOutput/holdout-13.json"
$env:PYTHONHASHSEED = '31'
& $phase4pPython -c $phase4pBound 1200 $phase4pPython -m research.holdem.phase_4p holdout "$phase4pOutput/holdout-31.json"
& $phase4pPython ../benchmark-results/phase-4p-2026-11-18/inspect_evidence.py "$phase4pOutput/holdout-13.json" "$phase4pOutput/holdout-31.json"
$env:PYTHONHASHSEED = '13'
& $phase4pPython -c $phase4pBound 3600 $phase4pPython -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
```
