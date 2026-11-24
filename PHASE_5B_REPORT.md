# Phase 5B — Coach river shadow evaluator

**Decision A for the frozen integration gates.** Keep `POKER_COACH_RIVER_SHADOW` disabled by default. Across 20 distinct river decisions run under each of two hash seeds, the observer produced the same canonical Coach response and CFR inputs in every pair. All 40 traces completed. On identical working columns the two value calculations differed by at most **0.00000677 bb**, while the full-range shadow preference lost as much as **17.384 bb** against the actual CFR recommendation under the offline reference. [Protocol](PHASE_5B_PROTOCOL.md) · [Full experimental summary](benchmark-results/phase-5b-2026-11-19/summary.json)

## Coach path and observation boundary

| Step | Existing Coach path | Shadow input or action |
| --- | --- | --- |
| Public state | `coach.service._replay` applies typed actions through `HandEngine`. The advisor receives the current immutable `DecisionState`, with Hero cards, the five-card public board, commitments, stacks, blinds, legal action types, total-target bounds and public action history. | Hashes the decision's public fields and stores Hero cards only in the protected local trace. |
| Range | `SolverBot._decide` conditions chart reaches on observed preflop actions, applies board blockers and replays postflop actions through the street policies. The independent `POKER_COACH_PERSISTENT_RANGES` flag uses `ReplayBeliefs` and a separate projected working set. `profile_for` rebuilds public evidence from completed logged hands. | Copies the already estimated current-node opponent reach and normalizes it after applying Hero and board blockers. Records working-set sizes, effective and positive support, maximum holding weight and omitted compatible mass. |
| Menu and replies | `StreetTree` applies street total targets with half pot and pot at first wager depth, pot at first raise depth and effective all-in. Off-tree action sizes can trigger a current-state resolve. `_legalize` maps the tree choice to the engine action, including a closing short call represented as `all_in`. Profile locks can affect the final DCFR continuation. | Reuses the solved tree and conditional reply and Hero tail probabilities. Captures the concrete menu and abstract targets. Reports geometry or ambiguous mapping as unsupported. |
| CFR selection | `_postflop_advice` reads the Hero column of the final CFR mix, calls `_sample` and legalizes the actual selected action. `_pick` derives its private draw from the Coach seed and decision identifiers. The displayed mix and action EVs are rounded separately. | Copies the unrounded mix, selected index and available CFR EV. Calculates the mode from the full-precision mix using the first maximum in tree order. It performs no additional draw. |
| API and errors | `advise` concretizes labels and builds the Coach response. Solver replay and numeric errors follow the existing fallback path before shadow work starts. The Match and history services own their separate persistent range flag. | Runs after the Coach response is built. Shadow errors and timeouts are recorded locally and trace-write failure emits only an exception type. The Match and Replay callers never opt into capture. |

`RiverEvaluationInput` is a frozen data class with immutable tree nodes, read-only copied NumPy arrays and immutable policy mappings. The bounded traversal reuses Phase 5A's `holding_values`. Its full-range estimate extrapolates replies beyond CFR columns by averaging at the nearest showdown rank. The projected comparison prices only actual working columns. `DecisionState`, the native menu, the root selection and the frozen continuation are common inputs to the two comparisons. The shadow calculates net chips since the decision, including short-call refunds and tie settlement, then divides by the big blind. The offline ledger separately prices the same tree and fixed Hero continuation under explicit synthetic reference laws. A played hand outcome is a different quantity and this panel generated none. [Observer and input contract](backend/research/holdem/river_shadow.py) · [Solver handoff](backend/solver/bot.py) · [Coach boundary](backend/coach/service.py) · [Independent ledger](backend/research/holdem/action_ev_reference.py)

Start the local backend with `POKER_COACH_RIVER_SHADOW=1` for research traces. The per-user default is `PokerAnalyzer/research/river-shadow` under Local AppData on Windows and `~/.local/state` elsewhere. Override it with `POKER_COACH_RIVER_SHADOW_DIR` pointing to a private local directory. Each atomically published JSON file contains Hero cards and should be handled as local research data. Exact reference opponent cards and policies are confined to the offline harness. [Trace implementation](backend/research/holdem/river_shadow.py)

## Holdout and invariance

- All **40/40** enabled-versus-disabled pairs preserved the canonical response, raw strategy frequencies, sampled index and CFR input fingerprints. Both holdouts reproduced identical non-timing trace fields, including the state digest and diagnostics. All outcomes came from the incumbent postflop solve. Both fresh hash-seed runs had 20 complete traces and zero timeouts, errors, missing traces, unsupported states or production fallbacks. [Seed 13](benchmark-results/phase-5b-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-5b-2026-11-19/holdout-31.json) · [Canonical trace check](benchmark-results/phase-5b-2026-11-19/determinism.json)
- Each run contained 16 generated river decisions and four fresh accounting controls. The generated panel varied public position and action sequence, faced bets from one-quarter to 1.25 pot plus closing shoves, and used 15 and 30 bb starts. Controls added 25 bb starts and expanded sizing only inside the offline runner. Profile prefixes were 0, 3, 30 and 100, with legacy and 128- or 384-column persistent range paths. Per-style results are descriptive because each style shared one nested training stream and working-set settings were allocated by style. [Frozen cases and source hashes](benchmark-results/phase-5b-2026-11-19/frozen.json)
- A setup run was stopped after code review found that reconstructing action labels from targets would hide the native `all_in` reply bucket. The final implementation copies native labels. The final source and schedule were frozen before any reference metrics were inspected. [Manifest verification](benchmark-results/phase-5b-2026-11-19/final-manifest-and-whitespace.txt)
- Treys matched the snapshot's river outcome for all 990 compatible holdings per decision. The independent cash ledger matched all **67** bounded action values per hash seed within `1e-10` bb. The same-column CFR residual stayed below `1e-4` bb. Profitable pure-bluff quarter pot earned +3.000 bb in the specified reference and the unprofitable control returned −0.500 bb. The two closing all-in calls scored +17.500 and −12.500 bb. [Per-action ledger comparisons](benchmark-results/phase-5b-2026-11-19/holdout-13.json)

## Action values and disagreement

| Generated panel (16 decisions, 49 actions) | CFR | Bounded shadow |
| --- | ---: | ---: |
| EV MAE versus reference, bb | 4.205 | 4.259 |
| Correct materially separated reference pairs | 31/55 | 32/55 |
| Greedy mean regret, bb | 1.853 | 3.218 |
| Greedy maximum regret, bb | 9.854 | 17.384 |

CFR's actual seeded choices averaged 1.681 bb regret and its modes averaged 1.154 bb. CFR and shadow greedy preferences differed on **4/16** decisions. Two of those disagreements had ≥2 bb shadow regret, compared with five among the 12 agreements. Six agreements were wrong by more than 0.01 bb. Relative to the incumbent seeded choice, shadow greed produced one material improvement and four material losses. This comparison also includes cases where the greedy selectors agreed and the seeded advice used another action. Including the four controls, CFR and shadow ranked 45/99 and 46/99 pairs correctly, respectively. [Paired choices and reference deltas](benchmark-results/phase-5b-2026-11-19/summary.json)

| Opponent | CFR pairs | Shadow pairs | Harmful greedy agreements | Sensitivity flag among ≥2 bb regret cases |
| --- | ---: | ---: | ---: | ---: |
| Tight-passive | 9/13 | 9/13 | 2 | 2/2 |
| Loose-passive | 9/16 | 8/16 | 1 | 1/1 |
| Tight-aggressive | 6/15 | 8/15 | 1 | 2/2 |
| Loose-aggressive | 7/11 | 7/11 | 2 | 1/2 |

| Class | Finding |
| --- | --- |
| A · CFR approximation | No large same-column scoring residual. This experiment fixes the trained continuation and does not compare it with a converged strategy. |
| B · Action-EV calculation difference | No bounded-versus-ledger accounting discrepancy at the frozen tolerance. |
| C · Opponent-range error | Reference substitution of the incoming range reduced MAE from 4.259 to 2.322 bb at fixed estimated replies. |
| D · Future-reply forecast error | Reference substitution of replies reduced MAE from 4.259 to 3.912 bb at fixed estimated range. These interventions can interact. |
| E · Action abstraction | Shadow and CFR priced the same concrete actions on every row. Four greedy disagreements appeared when restoring omitted range mass with extrapolated replies. The full-versus-projected gap reached 4.714 bb. The panel did not establish optimal targets outside each supplied menu. |
| F · Unsupported betting-tree behavior | No scheduled tree was unsupported. The focused failure test exercised unsupported-state isolation. |
| G · Numerical precision or normalization | The worst projected residual was 0.00000677 bb and all full-precision mixes normalized. |

The worst prospective switch was a loose-passive overbet at 30 bb with a 30-hand profile and a 128-column cap. About 49.5% of compatible estimated mass fell outside the working set. CFR priced shoving at −3.007 bb, while full-range shadow repricing put it at +1.516 bb versus folding. The higher-continuation scenario put it at −15.398 bb and the offline reference at −17.384 bb. The incumbent sampled a fold. [Row 5 and attribution](benchmark-results/phase-5b-2026-11-19/holdout-13.json)

## Opponent-model visibility

The natural panel's average total variation from the reference range was **0.648**. Minimum effective support was **4.14** compatible holdings. At the 21 facing-wager nodes reached with at least 5% probability in both models, Coach overestimated fold probability by over 10 percentage points at **17**, underestimated call probability at **19**, and missed shove probability by over 10 points at **8**. The 15% range relaxation changed the preferred action on one of 16 decisions and moved an EV by up to 3.107 bb. The reply endpoint scenarios changed the preference on 11 decisions and moved an EV by up to 26.321 bb. [Range and conditional reply evidence](benchmark-results/phase-5b-2026-11-19/summary.json)

The frozen sensitivity flag caught **6/7** natural decisions with at least 2 bb of reference regret and raised five alerts among nine lower-risk cases. The disagreement-only flag caught **2/7** with two such alerts. Sensitivity had 55% precision and 86% recall on this panel, compared with 50% and 29% for disagreement. The synthetic laws and four shared profile clusters limit generalization. The observer surfaced potential errors during the live calculation. Their direction and actual magnitude required the offline references. [Per-style and decision-level evidence](benchmark-results/phase-5b-2026-11-19/summary.json)

## Isolated resource measurements

Fresh-process probes covered six cases and one cold-board and one warmed-board call per case for each arm. The nearest-rank p95 equals the maximum with six observations. The timed path includes the paired instrumentation. The holdout also timed every enabled and disabled call in isolation from the test suite.

| Arm | Cold median / p95 / max, s | Warm median / p95 / max, s | Peak working set |
| --- | ---: | ---: | ---: |
| CFR only | 0.879 / 3.169 / 3.169 | 0.333 / 2.244 / 2.244 | 157.20 MiB |
| CFR and shadow | 0.818 / 3.152 / 3.152 | 0.300 / 2.880 / 2.880 | 156.38 MiB |

The measured observer segment before the response returned, including trace write, was **8.94 / 26.23 / 26.23 ms** median/p95/max. Shadow compute alone was **5.00 / 19.82 / 19.82 ms** on those probes, with all 12 traces complete. The holdout's slowest Coach call was **8.899 s** across arms and seeds. The largest shadow working set held 1,081 columns on one seat, and the largest analyzed subtree had 95 nodes. Separate process and board timing variation affects cross-arm wall-clock and peak working-set differences. The observer's cooperative 150 ms deadline covers capture and pricing, with a 15-second total time reference. It can stop between bounded operations. Local I/O and OS scheduling can extend the wall time. [CFR resource probe](benchmark-results/phase-5b-2026-11-19/performance-cfr.json) · [Shadow resource probe](benchmark-results/phase-5b-2026-11-19/performance-shadow.json)

The frozen probes had both arms' modules loaded. A separate first-use probe from fresh Coach processes measured 2.022 s disabled and 2.173 s enabled, with the same action and a complete trace. In that enabled process, the segment after CFR included 452 ms for the first observer import, evaluation and trace write combined. Compute after import was 26 ms. The disabled process never loaded the observer. [Disabled first use](benchmark-results/phase-5b-2026-11-19/first-use-cfr.json) · [Enabled first use](benchmark-results/phase-5b-2026-11-19/first-use-shadow.json)

## Phase 5C objective

Use a new clustered panel to test calibration of the incoming posterior and the fold, call and shove forecast separately. Start with closing and overbet cases and quantify sensitivity-flag precision at matched recall across disjoint opponent profiles. Preserve incumbent advice while investigating whether substantially wrong forecasts can be detected more reliably from permitted data.

## Verification and Git status

- All **1,044 backend tests** passed across nine non-overlapping file groups in 342.54 seconds wall time. Collection retained all 1,036 Phase 5A node IDs and added eight. The full **223-test research regression** passed within those groups. The suites reported existing dependency deprecation warnings. [Collection](benchmark-results/phase-5b-2026-11-19/collected.txt) · [Full regression summary and per-group counts](benchmark-results/phase-5b-2026-11-19/backend-summary.json)
- Focused river and payoff tests passed under hash seeds 13 and 31. The seed-31 run passed 22 tests, including paired code-path invariance, private stored-profile evidence, RNG isolation, observer failure injection and real Match/history replay parity. The dependency check and frontend production build passed. [Focused tests](benchmark-results/phase-5b-2026-11-19/focused-31.txt) · [Dependencies](benchmark-results/phase-5b-2026-11-19/pip-check.txt) · [Frontend build](benchmark-results/phase-5b-2026-11-19/frontend-build.txt)
- The first backend and API attempts stalled on the sandboxed Windows socket pair. The repeated API smoke passed over local loopback for shadow unset, `0` and `1`, crossed with both persistent-range flag settings. Match and both Replay endpoints reproduced canonical results, validated histories and preserved chip conservation. The frontend smoke rendered Coach strategy, Match and both Replay forms and initial events using the local API histories. [API smoke](benchmark-results/phase-5b-2026-11-19/api-smoke.txt) · [Coach render](benchmark-results/phase-5b-2026-11-19/frontend-coach.txt) · [Match and Replay render](benchmark-results/phase-5b-2026-11-19/frontend-match-replay.txt)
- Branch `main` is at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. Phase 5B added the observer, frozen research runner, regression tests, protocol and report. It appended a Coach-only handoff to `SolverBot._postflop_advice` and a local observer boundary to `coach.service.advise`. The Phase 5A source and artifact manifest differs only on those two live files. `git diff --check` passed with the existing end-of-line advisory on `backend/test_poker.py`. [Final status](benchmark-results/phase-5b-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-5b-2026-11-19/status-delta.txt) · [Prior hashes](benchmark-results/phase-5b-2026-11-19/frozen-source-check.txt) · [Whitespace check](benchmark-results/phase-5b-2026-11-19/git-diff-check.txt)
