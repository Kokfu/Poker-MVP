# Phase 4J — Exact river EV and opponent adaptation

Existing adaptation improved exact EV by **0.280 bb per holdout decision** on the frozen panel. It improved the mean against both fixed reference opponents and lost EV in **10 of 40 comparisons**, at a summed cost of **5.367 bb** on those rows. The confidence-limited candidate cut the cost to **3.002 bb** and the mean gain to **0.194 bb**. It missed the promotion gate. The production change is limited to the confirmed fallback isolation defect.

## Root causes

### Confirmed defect

Turning off **Adjust to this opponent** selected `SolverBot` and made the regular solver ignore the profile. The error handler still sent the original decision observation to `ExpertRuleBot`. Expert read `opponent_profile` and could change advice while Coach reported `exploiting=false`. The profile on the observation came from the same reconstruction used to populate the visible profile card. Phase 4J clears that field on a copy of the observation at the disabled fallback boundary. Enabled fallback, Expert's own strategy, the public state and the visible profile retain their existing behavior.

### Strategy and measurement

1. Coach replays completed observations into `OpponentModel` for action and opportunity counts and, on the adaptive path, into `ShowdownModel` for revealed hand-strength evidence. The current hand's public action path conditions the estimated ranges. The classification and VPIP shown in Coach do not select a policy.
2. Confidence is assigned per statistic. Its four bands start at 0, 5, 20 and 50 opportunities and yield lock blend weights of 0, 0.30, 0.55 and 0.75. Default postflop pooling shrinks the local rate toward all-street evidence using 10 pseudo-observations and uses the pooled denominator for confidence. Locks fit grouped frequencies, round targets and retain a hand-ordering component estimated from showdown evidence. A low lock weight controls a single opponent update. It places no bound on Hero's response to a changed action ranking.
3. Preflop locks can re-solve the chart. Every chart and street action then multiplies the acting player's reach by its inferred per-combo likelihood. The current river policy depends on these accumulated weights, river hand strength and the modeled continuation. Off-tree sizes condition reach using a nearby abstract action and then trigger a solve from the actual pot and stacks. This can bias the inferred range even when chip geometry is accurate. Pooling across streets and sizes, rounded groups and selective showdown reveals create strategic model error. An unusual aggregate frequency can be measured precisely while remaining a poor predictor at a particular node.
4. `RangeSolver.action_values` propagates the final policy through the modeled tree, normalizes by the opponent reach compatible with Hero's hand at the current node and adds back sunk Hero contributions to express EV relative to giving up now. In the independent reach control, a 3-weight losing-to-Hero hand bets half the time, a 1-weight winning hand always bets and a blocked hand has weight 100. The compatible betting weights are 1.5 and 1. Call EV is `0.6 × 1,200 − 300 = 420` chips and fold is 0, matching production and the reference within 1e-10 chips. This verifies the weighted call path through an observed action. Coach shows a separate reach-based equity estimate. The solve can prune that reach again at an off-tree re-solve, so the displayed estimate and the modeled decision need not use identical support. Each arm's displayed action EV uses its own estimated range and continuation. Those EVs cannot establish common-opponent gains. [Weighted reach control](benchmark-results/phase-4j-2026-11-17/solver-ev-control.json)

## Exact river evaluator

`research.holdem.river_ev` enumerates all 990 two-card holdings left by the known five-card board and Hero's two cards, including any holding assigned zero weight. It uses the Treys hand-rank path, separate from the production solver's eval7 equity matrix and CFR traversal. Each compatible holding receives a finite, nonnegative likelihood weight divided by total compatible mass. An empty posterior fails validation. There is no sampling or dependence on the advisor's own estimate.

EV is the change in Hero's stack from the decision onward. Earlier contributions are sunk and fold is zero. For a showdown, the settled pot is the already contributed pot outside the river commitments plus twice the matched river commitment. Hero receives the full pot on a win, zero on a loss, and the engine's integer split on a tie, then subtracts chips paid from the decision onward. Excess chips above the effective stack are refunded. A Villain fold pays Hero the pot present at the decision after returning Hero's added wager. The evaluator takes the call probability conditional on Villain's cards and the proposed effective wager, and integrates the call and fold payoffs for every compatible pair.

Supported lines include a check that closes the river, fold or call facing a wager, and each legal explicit bet or raise or implicit all-in target with a specified fold/call reply. Non-closing checks and Villain reraises require additional continuation policies. The panel covers heads-up, rake-free river decisions with one Hero action, a limited menu of concrete targets and no future cards.

### Independent validation

| Control | Expected result | Result |
| --- | --- | --- |
| 9s 3c on As Ks Qs Js 2d | Exactly 44 of 990 holdings contain Ts and win. Hero equity 946/990. With Ts in Hero's hand, equity 1. | Matched |
| Board royal | All 990 holdings tie. At the specified 500-chip starting pot, closing check, matched bet/call and either direction of a short all-in are +250 chips from the decision. Villain folding to a shove pays +500. | All five lines matched actual engine settlement |
| Weighted raise | One losing holding of mass 1/4 calls every time. One winning holding of mass 3/4 calls half the time. A raise to 400 pays `¼ × (−300) + ⅜ × 1,000 + ⅜ × 800 = 600` chips. A called shove capped at 550 total pays `¾ × 1,150 + ¼ × (−450) = 750`. | Matched |
| Invalid inputs | Reject duplicate cards, invalid or zero compatible mass, illegal targets, missing or malformed responses and a check requiring an unspecified continuation. | Matched |

Decimals in the reference are evaluated with floating-point arithmetic. The settlement tests use an absolute tolerance of 1e-10 chips.

## Experimental design

The [frozen protocol](PHASE_4J_PROTOCOL.md) specifies six distinct Coach spots, the reference action probabilities, sensitivity ladder and decision gates. Calibration and holdout share one board with different Hero holdings. Each size uses a nested prefix of the same completed Aggressive histories from Phase 4I. Loose Aggressive and Selective are synthetic conditional river opponents with explicit hand-strength likelihoods and size-conditioned calls. The histories used to build the profile are independent of these reference policies. The experiment tests transfer from the same observed profile to two fixed river contexts, including possible context mismatch. The cases are equally weighted diagnostic spots.

All three policies face the same reference posterior and response for a given case. Off and On use the current live Coach solve and seeded recommendation. The research candidate mixes their concrete action probabilities with an adaptive share of `n / (n + k)`. Calibration chooses `k` before the holdout is evaluated. All metrics are from the full-precision policy mix. The regret baseline is the highest-EV action in the union of the Coach menus, and harmful adjustment means losing more than 1e-6 bb compared with Off on the same case.

## Exact EV results

Mean EV, differences and regret are in bb per decision. Harm cost sums the EV losses on affected rows. Each reference has 20 holdout rows across four spots and five profile sizes.

| Panel | Rows | Off EV | On EV | Candidate EV | Off / On / candidate regret | On / candidate harm cost and count |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Calibration | 20 | 3.079 | 3.427 | 3.296 | 0.656 / 0.309 / 0.440 | 4.240 / 2.932 bb, 4 each |
| Holdout | 40 | 5.976 | 6.256 | 6.171 | 0.597 / 0.317 / 0.402 | 5.367 / 3.002 bb, 10 each |
| Holdout, Loose Aggressive | 20 | 6.621 | 7.055 | 6.945 | 0.771 / 0.338 / 0.448 | 4.013 / 2.016 bb, 3 each |
| Holdout, Selective | 20 | 5.332 | 5.458 | 5.397 | 0.422 / 0.296 / 0.357 | 1.354 / 0.986 bb, 7 each |
| Holdout, 3–30 hands | 24 | 5.976 | 6.248 | 6.114 | 0.597 / 0.325 / 0.459 | 4.771 / 2.438 bb, 6 each |
| Holdout, 100–500 hands | 16 | 5.976 | 6.268 | 6.255 | 0.597 / 0.305 / 0.318 | 0.596 / 0.563 bb, 4 each |

### Fixed action values

Each entry gives exact net bb for Loose Aggressive / Selective. Bet and raise sizes are street totals in chips. The facing-bet spots use the Coach's fold/call/shove menu at this stack depth. The evaluator's explicit raise support is exercised by the independent weighted control.

| Spot | Fold | Call | Check | Bet 250 | Bet 500 | Shove |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibration J-high facing 250 | 0 / 0 | −0.923 / −2.164 | | | | −3.673 / −5.452 |
| Calibration AQ checked to | | | 4.830 / 4.869 | 6.026 / 5.442 | 7.207 / 5.980 | 8.703 / 6.240 |
| Holdout set facing 500 | 0 / 0 | 9.884 / 9.612 | | | | 14.143 / 13.629 |
| Holdout sevens facing 500 | 0 / 0 | 4.308 / 0.120 | | | | 5.088 / −0.186 |
| Holdout ace-high checked to | | | 1.953 / 2.024 | 2.088 / 3.227 | 1.313 / 2.670 | 0.254 / 2.614 |
| Holdout QT checked to | | | 4.693 / 4.735 | 5.821 / 5.321 | 6.899 / 5.799 | 8.251 / 6.038 |

- **The same recommendation can gain or lose.** With 12 hands and sevens facing 500, Off called 91.86% and shoved 0.04%. On shoved 99.97%. That gained 1.128 bb against Loose Aggressive and lost 0.297 bb against Selective. Shoving had negative EV against Selective at every evidence size because the reference's action-conditioned range and calling mix were fixed. At 500 hands the solver still estimated shove at +7.281 bb in its own model. More observations from a different context can reinforce the mistake.
- **Sparse bluffing was the main holdout loss.** With ace-high checked to, Off checked 99.81%. On shoved 97.33% at three hands and 99.91% at 30. The same adjustment lost 1.652 and 1.696 bb respectively against Loose Aggressive and gained 0.574 and 0.588 against Selective. At 12 hands On bet 500 with 96.43% probability and lost 0.665 bb against Loose Aggressive. With 100 and 500 hands it returned to essentially pure check. Taken together the three sparse ace-high rows cost 4.013 bb against Loose Aggressive.
- **Thin reads can also add value.** With QT checked to at 12 hands, On shoved 98.95%, up from 8.23%. It gained 1.805 bb against Loose Aggressive and 0.474 bb against Selective. With the set, both arms already shoved over 99.99% and gained around 0.0001 bb from the adjustment.
- **A closer range can still produce worse advice.** Estimated conditional combo TV improved in 39 of 40 holdout rows and in nine of the 10 harmful rows. Absolute showdown-equity error improved in 20 rows, including four harmful rows. At 30 hands in the ace-high case against Loose Aggressive, range TV and absolute equity error fell by 37.72 and 12.64 percentage points while EV fell 1.696 bb. Posterior TV, equity accuracy and the response to a wager measure different parts of the decision.

The raw evidence contains full action mixes, seeded recommendations, modeled and reference EVs, range distances, and row-level regret and deltas. Seven Selective holdout losses include five sevens rows and two roughly 0.0015 bb ace-high adjustments. The table counts rows of this panel, which share cases and prefixes. [Raw decision evidence](benchmark-results/phase-4j-2026-11-17/verified-1.json)

## Sparse-data sensitivity

### The original 99.41% call

Phase 4I's exact input is Jc 9d on Qh 7s 2d, facing a bet of 200 in a pot of 500 before the bet. The 12-hand profile was still classified as unknown. Its preflop raise statistic had 31 opportunities and the limp statistic had nine. The weaker of the two confidence bands gave the opening lock a 0.30 weight. Postflop pooling turned seven local flop bet opportunities into 12 across streets and five local facing-bet opportunities into 12, also enough for 0.30 weights. The near-binary response arose from repeated reach conditioning and changed local incentives.

| Enabled locks | Call mix | Displayed equity | Modeled call EV (chips) | Seeded advice |
| --- | ---: | ---: | ---: | --- |
| None | 27.14% | 20.63% | −14.3 | Fold |
| Preflop only | 90.89% | 26.52% | +38.7 | Call |
| Postflop only | 44.78% | 21.88% | −3.1 | Fold |
| Both | **99.41%** | 28.93% | +60.4 | Call |

Preflop propagation accounts for most of this shift. The joint effect is nonlinear. The 200 wager conditions the flop reach using the nearest 250-chip action before the solver re-solves at the real wager. The `adjusted` flag reports local locks and was false for the preflop-only run. The flop continues through two more streets, outside the evaluator's exact coverage.

### River evidence ladder

Bet/facing counts are actual river opportunities and pooled flop/turn/river opportunities. On action TV and estimated range TV are averages across the holdout spots. The range TV baseline is 69.60 points at every size.

| Hands | River bet/facing | Pooled bet/facing | On action TV vs Off | On range TV vs reference | On ΔEV | Candidate ΔEV | On / candidate harm cost |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 3 | 2 / 1 | 6 / 5 | 61.49 pp | 50.67 pp | +0.231 | +0.053 | 1.817 / 0.419 bb |
| 12 | 2 / 1 | 12 / 12 | 72.45 pp | 35.36 pp | +0.386 | +0.210 | 0.961 / 0.524 bb |
| 30 | 5 / 8 | 30 / 45 | 66.32 pp | 43.51 pp | +0.200 | +0.150 | 1.993 / 1.495 bb |
| 100 | 23 / 28 | 105 / 140 | 40.50 pp | 22.83 pp | +0.192 | +0.175 | 0.298 / 0.271 bb |
| 500 | 141 / 134 | 592 / 772 | 47.98 pp | 17.11 pp | +0.391 | +0.383 | 0.298 / 0.292 bb |

At 30 hands the calibration J-high spot called 99.78% with adaptation and lost 0.899 bb against Loose Aggressive and 2.127 bb against Selective. The adaptive call mix was 39.84% at 12 hands and effectively zero at 100 and 500. Neither EV nor action sensitivity moves monotonically with sample size.

## Research candidate and production decision

The calibration means at 10, 30 and 100 pseudo-hands were 3.296, 3.255 and 3.216 bb. The selected 10-hand prior retained 23.08%, 54.55%, 75.00%, 90.91% and 98.04% of the adaptive policy at the five evidence sizes. This shrank the cost of harmful holdout adjustments by about 44% across the same 10 rows. It also attenuated profitable decisions and lost 0.086 bb per holdout decision compared with On, so it missed the predeclared promotion gate. Keep the mixture as a research comparator. Computing both policies for a live mixture would also add the unlocked solve cost. Keep the production locks and sizing unchanged.

The positive development signal for existing adaptation met the mean-EV gate on both fixed opponents and in both size groups. The harms indicate that a strategy change needs context-specific evidence for how a profile predicts this river action and how the same opponent responds to each size. The current solver result remains a model estimate. Where the UI exposes this value, describe it as EV under the solver's estimated opponent policy.

## Proposed Phase 4K

1. Hold solver budgets and action menus fixed. Independently substitute the exact reference posterior, then the exact per-combo response policy, then both, to measure the regret attributable to inference and continuation. Preregister a new split with more boards and both seat orientations where exact continuation is specified. Include several independent profile histories for each defined reference. Generate evidence from the same reference where the model specifies the historical contexts, and retain mismatch cases as a separate stress test. Evaluate size and street conditioning by predictive accuracy and exact decision EV.
2. Freeze an out-of-sample EV and harm gate before tuning another candidate. Compare Off, On, the Phase 4J mixture and the candidate under common conditional reference policies. Include action-value and deterministic legal-advice checks and require material benefit across opponent families with an explicit tolerance for tail harm.
3. Separately measure existing On versus Off in paired play against existing local opponents. Use a small development pilot to estimate variance and freeze a practical bb/100 threshold and sample size. Duplicate each deal in both seat orientations for both arms, warm both from identical completed histories from the evaluated opponent, and start the fixed-read test from the same stacks and seeds. Record session-level paired differences, opportunity counts, runtime, both fallback counters, legality and deal concordance. Use fresh seeds for the measured holdout and test learning sessions separately. This checks whether the conditional river gains translate into actual game performance.

## Fallback isolation

The Phase 4I forced `ReplayError` spot is Jc 9d on Qh 7s 2d after Hero limps and Villain checks both preflop and flop. Before the fix, adaptation-disabled advice was check without a profile and bet 100 with the 150-hand Tight profile. The new regression reproduces that failure before the edit. After the edit all three arms still report a fallback with the same reason. Disabled advice is check with or without the profile, enabled advice with the Tight profile is bet 100, and the disabled profiled response repeats exactly.

## Verification and Git status

- Focused verification passed all **9 tests** in 9.39 s. It includes both evaluator reference arithmetic and the forced Expert fallback, legality and replay checks. The standalone research suite passed **97 tests** in 273.24 s, including the earlier exact and MCCFR research controls.
- The single-process full backend regression passed **918 tests** in 878.01 s within the 2,400 s cap, with eight dependency deprecation warnings from eval7 and Starlette. The run allowed local loopback for the HTTP tests and used one BLAS thread.
- Two final matrix runs with distinct Python hash seeds matched exactly after omitting wall times. Each completed within its 420 s cap. Both runs recorded 64 legal, normalized Coach decisions with zero solver fallbacks, four of them for the original flop reproduction. The 30 research mixtures used only the legal action menus and summed to one. The slowest river advice call in the two final runs took 5.82 s. An initial comparison found changes below 3e-16 in action TV due to the order of floating-point summation. The runner now sums labels deterministically and the EV measurements match the initial runs exactly. [Deterministic recheck](benchmark-results/phase-4j-2026-11-17/verified-2.json)
- Dependency checks found no broken Python requirements. The frontend production build and the existing Coach solver/fallback smoke test passed. The tests and experiments use local fixtures and scratch SQLite.
- `git diff --check` passed with the existing LF/CRLF advisory. The branch is `main` at `3e89367`, 19 commits ahead of local `origin/main`. The existing uncommitted work and historical fixtures are retained. Phase 4J adds this report, the protocol, the evaluator, the experiment runner and two test files. Its production diff adds two lines to the SolverBot fallback handler. The evidence is under the existing ignored `benchmark-results/` path. The work is local and uncommitted.

To reproduce from `backend` with a fresh output directory, use the retained Windows timeout wrapper. The experiment refuses to overwrite existing evidence.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$py = '.\.venv\Scripts\python.exe'
$out = '../benchmark-results/phase-4j-reproduction'
New-Item -ItemType Directory -Path $out | Out-Null
$env:PYTHONHASHSEED = '1'
& $py ../benchmark-results/phase-4h-2026-11-17/run_bounded.py 420 $py -m research.holdem.phase_4j "$out/decisions.json"
$env:PYTHONHASHSEED = '2'
& $py ../benchmark-results/phase-4h-2026-11-17/run_bounded.py 420 $py -m research.holdem.phase_4j "$out/decisions-recheck.json"
& $py -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0 test_research_holdem_river_ev.py test_solver_fallback_isolation.py
```
