# Phase 5E — Opponent Profile V2

**Decision B — partially validated.** At 300 hands, V2 reduced held-out reply Brier from 0.557 to 0.434. River action-EV error increased from 0.326 to 0.404 bb per decision because the fallback for unsupported wagers was weaker than the incumbent's. Keep the model in research and test coverage-aware backoff in Phase 5F.

## Audit of the current data flow

| Stage | Data retained and used |
| --- | --- |
| Hand and wager log | The engine records action order and seat, the legal menu, amount to call, target/payment, pre/post pot and street commitments, stack, raise reopening, applied action, fallback and all-in classification. The history also records button, blinds, settlement and unmatched returns. Showdown reveals are selected by who reaches showdown. |
| Coach storage | SQLite stores original entered spots under a normalized, case-sensitive opponent name. The production learner replays complete records into the same Villain seat. Every replay uses the same internal `coach-hand` ID. A research importer therefore needs a stable database namespace and original row ID, or an externally preserved hand ID. The derived sizing cache stores optional postflop counts. |
| Match learning | Completed public histories feed the opponent models for the corresponding simulated seats within a match. Match identity should include a durable source plus match/hand key for deduplication. Seat and button may vary across histories. The application has no existing cross-source identity or synchronization layer for these profiles. |
| Pooled profile | The legacy model tracks VPIP and PFR at preflop decisions, plus limp, three-bet and fold-to-raise counts. It tracks broad aggression and postflop checks, bets and responses by street. The public profile lacks opponent position, exact wager faced, effective depth, SPR, closing status and their interactions. Its private size buckets pool postflop streets, combine regular raises and aggressive all-ins, and coarsen size without explicit closure or an effective-price cap. |
| Denominators | Legacy confidence is a threshold label on each statistic's opportunity count. The VPIP read is per decision and can count the same hand more than once. The legacy three-bet and three reply counts can use a broader exposure than the concrete legal opportunity. For example, a fold/call-only reply contributes to the street's raise-vs-bet denominator. |
| Ranges, forecasting and selection | The solver consumes learned counts through preflop charts and pooled postflop node locks. Replay likelihoods update incoming range weights. CFR estimates future replies and supplies the final Coach policy and advice. Phase 5D's research forecast also uses pooled response counts with explicit hand and price tilts. The optional river observer captures already-built advice inputs. |

The available event data can recover public opportunity geometry and observable replies. It cannot recover a counterfactual response to a wager that never occurred, the unseen holdings of opponents who folded, or whether different local aliases identify the same opponent. An opponent encounter mix can distort pooled comparisons. Under the closing-family laws, sampling the low-fold context 90% of the time gives a 25.8% pooled fold rate, versus 56.2% under the opposite sampling mix for the **same** policy. A 50/50 exposure mix gives 41% for both members despite their opposite conditional behavior. [Incumbent profile](backend/simulation/opponent_model.py) · [Hand schema](backend/simulation/history.py) · [Coach](backend/coach/service.py) · [Store](backend/coach/store.py) · [Match](backend/simulation/match_service.py) · [Forecast](backend/research/holdem/reply_forecast.py)

## Research-only V2

The versioned in-memory profile aggregates response vectors keyed by street, position, previous action, aggression depth, collectible price/pot, effective depth, SPR, closure and normalized legal action menu. Each extracted observation has the source event index and exact offered price, collectible price, matched pot, effective stack and big blind. The original wager target and payment are available on the backing history events. Each cell supplies exposure, observed-response and missing-response counts. Unknown eligibility is counted separately. For example, a shove of 1,250 chips into a 400-chip stack yields a 400-chip collectible price and 850-chip call refund. The reply is eligible for fold and call. The short all-in call feeds the call count.

Computing an observed-outcome frequency uses the cell's grounded replies. The known-opportunity count identifies coverage and bounds a complete-case estimate when some responses are missing. The Dirichlet prior contributes two pseudo-observations from the other cells on the same street and legal menu. A cell with zero usable responses backfills from that street/menu pool. Missing legal evidence never creates a reconstructed opportunity. A complete, valid history is required. A fallback with known eligibility creates a missing response, and a decision following an untrustworthy fallback prefix is excluded when the previous action lacks provenance. Repeated legal turns on a street have separate event indexes and exposure counts.

The caller supplies a stable, namespaced source ID and opponent seat for each hand. An equal retry is ignored, while conflicting evidence under the same ID is rejected before changing counts. Time is linear in replayed events. Counts grow with occupied cells and the deduplication index grows with hand count. This is a single-writer, offline read model. Deduplication across import aliases or after restarting requires replay from original stable IDs, and a legacy export without such IDs cannot guarantee cross-copy deduplication. Neither cards nor oracle laws are stored in the profile. Coach still uses the incumbent profile and Match still uses its existing learner. Phase 5E introduces no storage migration, production import, user-visible field or default flag change. [V2 aggregation](backend/research/holdem/opponent_profile_v2.py) · [Frozen protocol](PHASE_5E_PROTOCOL.md)

## Historical identifiability

The original 1,000-hand paired experiment reproduced exactly. The two incumbent serialized profiles were equal at every prefix below. Both ended with 409 folds and 591 calls. Each had 500 quarter-pot and 500 closing opportunities. V2 identified **21.6% versus 60.2% closing folds** using completed public histories.

| Hands per opponent | Closing opportunities per opponent | Low closing folds | High closing folds |
| ---: | ---: | ---: | ---: |
| 10 | 5 | 0/5 | 0/5 |
| 30 | 15 | 2/15 | 4/15 |
| 100 | 50 | 17/50 | 29/50 |
| 300 | 150 | 39/150 | 86/150 |
| 1,000 | 500 | 108/500 | 301/500 |

The private incumbent sizing read can distinguish these particular quarter/shove sizes. Its size buckets lack an explicit closure feature and do not isolate the same contrast when closing and nonclosing wagers occupy one bucket. The fresh legality-aware baseline below demonstrates how much closure information is already recoverable once the reply menu is preserved. [Historical evidence](benchmark-results/phase-5e-2026-11-19/historical.json) · [Phase 5D report](PHASE_5D_REPORT.md)

## Frozen fresh reply holdout

There were 24 independent profile clusters, 48 synthetic opponents and 3,072 held-out scored replies per prefix. Each cluster shared deals and draws within its opponent pair. The same held-out replies are scored at each nested training length. A adapts the incumbent's pooled counts to the legal menu, A* uses street/menu counts, B adds the V2 context, and C knows the synthetic law. A uses global action counts as the preflop proxy because the incumbent profile has no complete preflop reply vector. The comparison runs outside production CFR. At 300 hands B reduced realized multiclass Brier by **0.123** against A (95% paired cluster interval **−0.138 to −0.108**) and **0.104** against A* (**−0.117 to −0.091**). Both comparisons passed the frozen 0.02 materiality gate. Expected Brier at 300 hands was 0.557 / 0.538 / 0.430 / 0.427 for A / A* / B / C.

| Profile hands | Relevant replies per cell | Brier A / A* / B / C | Log loss A / A* / B / C |
| ---: | ---: | --- | --- |
| 10 | 5 | .598 / .586 / .528 / .429 | 1.000 / .981 / .863 / .669 |
| 30 | 15 | .575 / .557 / .466 / .429 | .912 / .877 / .732 / .669 |
| 100 | 50 | .557 / .538 / .435 / .429 | .866 / .824 / .680 / .669 |
| 300 | 150 | .557 / .538 / .434 / .429 | .858 / .813 / .676 / .669 |
| 1,000 | 500 | .555 / .536 / .432 / .429 | .852 / .807 / .673 / .669 |

Across the 300-hand panel, fold/call/raise/shove probability MAE against the known law was **16.1 / 22.8 / 8.7 / 2.6 percentage points** for A and **2.5 / 2.8 / 1.2 / 0.03 pp** for B. These averages count every scored reply and assign zero to unavailable actions. Small cells show sampling variation. For example, the historical profile supplied five legal closing replies per member at 10 hands and both happened to be calls. A live sample can have 300 hands and zero closing opportunities.

| Family and wager in chips | Equal incumbent profiles at 1,000 hands | Brier A / A* / B / C at 300 | Fold calibration A → B versus observed, by context |
| --- | ---: | --- | --- |
| Small 125 / 250 | 4/4 pairs | .493 / .493 / .401 / .397 | .451 → .454 vs .426 in both |
| Large 500 / 625 | 4/4 | .492 / .492 / .395 / .388 | .441 → .443 vs .418 in both |
| Closing 125 / shove | 4/4 | .483 / .406 / .406 / .406 | .415 → .415 vs .406 and .418 → .419 vs .406 |
| Preflop open / reraise | 0/4 | .724 / .724 / .514 / .503 | .127 → .187 vs .203 in both |
| River aggression 125 / 500 | 0/4 | .655 / .617 / .498 / .496 | .224 → .223 vs .211 in both |
| Position 250 / 250 | 4/4 | .493 / .493 / .390 / .385 | .428 → .431 vs .434 in both |

The paired laws deliberately swap propensities. Calibration averaged over both members can look similar even when the members' forecasts are wrong in opposite directions. The Brier and per-action MAE use individual predictions. For example, the matched legal-menu baseline already separated the closing masks, nearly accounting for the fresh closing-family gain on its own. The preflop and river-aggression scripts also change other legacy profile counts through downstream actions and wager amounts. The preflop and positional results identify the scripted contexts jointly. They cannot isolate the causal effect of a position change. No synthetic exposure mix establishes expected performance on naturally occurring histories. [Canonical summary](benchmark-results/phase-5e-2026-11-19/summary.json)

## Exact river action values

The bounded ledger priced 256 opponent/deal cases. Half are checked-to scenarios where future replies can matter. The other half are closing calls on a fixed, common incoming range. The same legal tree, Treys ranks, fixed Hero continuation, oracle and label-tied choice apply to all arms. Calls and bluffs are counted at their concrete opportunities. A bluff is defined by its value when folds are removed.

| Arm | Decision-weighted MAE (bb) | Action-weighted MAE (bb) | Material pairs correct | False aggression edges | Mean / worst choice regret (bb) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | .326 | .489 | 1,695/2,043 | 21 | .150 / 1.971 |
| A* | .495 | .742 | 1,481/2,043 | 22 | .144 / 1.971 |
| B | .404 | .606 | 1,594/2,043 | 16 | .062 / .856 |
| C | .000 | .000 | 2,043/2,043 | 0 | .000 / .000 |

B's decision-weighted MAE increased by **0.078 bb** versus A (95% interval **+0.043 to +0.112**) and decreased by 0.091 bb versus A* (−0.107 to −0.074). The frozen requirement was a reduction of at least 0.10 bb versus A. On wagers with a corresponding training price, B cut action MAE from 1.050 to 0.531 bb across 256 action instances. On the other 384 wager instances, its street/menu backoff raised MAE from 0.604 to 1.261 bb. Those unsupported wagers drove the aggregate reversal. The fixed menu, scripted law and fixed Hero continuation limit the decision results to this bounded panel.

B changed 26 greedy choices relative to A. No switch increased oracle regret, so mean material switch harm and worst switch harm were both zero. All arms took 80 of 80 profitable closing calls and declined all 48 unprofitable calls. Of 209 profitable and 175 unprofitable bluff opportunities, A selected 62 profitable and two unprofitable bluffs, B selected 67 and two, and C selected 74 and zero. Other selections could have greater oracle value than an available profitable bluff.

In the historical row 31, the incumbent called with estimated EV **+7.364 bb**. The true EV was **−20.920 bb**. Replacing the incoming range fixed that error. Replacing future replies alone left the estimate at +7.364 bb because the call closed betting. The fresh fixed-range controls give every model the same closing-call EV by construction. They do not show that V2 can correct the historical incoming-range failure. The historical row contributes to none of the fresh metrics. [Exact EV and archived diagnostic](benchmark-results/phase-5e-2026-11-19/summary.json)

## Decision B — Profile V2 partially validated

Wager-conditional counts materially improved independent reply forecasts and identified public behavior lost by legacy pooling. The V2 backoff at unsupported alternatives caused the model to miss the frozen exact-EV gate despite lower greedy regret on this panel. Keep V2 in research. In Phase 5F, test a coverage-aware fallback that preserves the incumbent reply forecast where the relevant cell has no evidence, then evaluate it on a fresh panel with variable and sparse exposure. Keep the incoming-range assessment separate for closing calls.

## Runtime and observer reliability

The isolated Coach probe used archived rows 78 and 31 and quarter-pot and pot controls. Each had three shadow-enabled runs and one disabled run. All 12 traces completed and all 16 calls produced legal CFR advice with zero fallbacks. Enabled and disabled public advice matched within each case. Each completed trace's CFR mix summed to 1 within floating-point precision. The probe uses prebuilt legacy snapshots for its archived rows, with a separate single-hand SQLite replay measurement. It does not include rebuilding a full stored profile on every decision.

| Segment | First | Median | p95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Cold study and Coach imports | 0.954 s | — | — | — |
| One stored-hand incumbent replay | 12.63 ms | 5.50 ms | 12.63 ms | 12.63 ms |
| Coach with observer, all enabled trials | 4.396 s | 1.867 s | 4.728 s | 4.728 s |
| Coach with observer, first trial per case | 4.396 s | 3.208 s | 4.728 s | 4.728 s |
| Coach with observer, repeat trials | 2.449 s | 1.372 s | 2.551 s | 2.551 s |
| CFR calls inside Coach | 3.309 s | 1.849 s | 3.480 s | 3.480 s |
| Observer snapshot | 5.53 ms | 3.49 ms | 7.59 ms | 7.59 ms |
| Observer exact pricing and diagnostics | 5.86 ms | 3.66 ms | 5.86 ms | 5.86 ms |
| Observer total before writing | 11.77 ms | 7.54 ms | 13.88 ms | 13.88 ms |
| Trace serialization and write | 2.96 ms | 4.20 ms | 7.81 ms | 7.81 ms |
| V2 aggregation per completed hand, seed 13 | 0.479 ms | 0.253 ms | 0.716 ms | 68.030 ms |
| Forecast all four arms per reply, seed 13 | 0.094 ms | 0.047 ms | 0.137 ms | 12.897 ms |
| Fresh exact study per deal, seed 13 | 50.66 ms | 34.89 ms | 134.79 ms | 346.05 ms |

The row 78 isolated timeout from Phase 5D did not recur. Its Coach calls took 2.449–4.396 s with shadow enabled, and its observer took 8.06–13.88 ms. The original evidence includes 27 deadlines missed during concurrent work and one 150.16 ms observer timeout in isolation. The observer's deadline is the earlier of its 150 ms compute budget and the 15 s Coach reference deadline. Time spent in CFR or waiting to run can therefore exhaust the remaining budget before the observer computes a result. The isolated measurements point to CFR and scheduling pressure as plausible contributors. They leave the cause of the one isolated outlier unconfirmed. No timeout was raised, and concurrent-load reliability remains unresolved.

Coach probe peak working set was 263.4 MiB and the two holdout workers peaked at 151.6 and 155.4 MiB. Across seeds the longest fresh exact evaluation was 0.346 s. In a separate 1,000-hand allocation probe excluding input histories, Python allocation peaked at 12.8 KiB for the incumbent and 470.0 KiB for V2. The V2 footprint includes the source-ID index. The synthetic profiles occupied six to nine cells each at 1,000 hands. The isolated Coach, observer, offline scoring and worker memory ceilings passed on the measured sample. The native observer still isolates failures from public advice, and the trace remains optional. [Coach timing](benchmark-results/phase-5e-2026-11-19/coach-timing.json) · [Seed 13 study timing](benchmark-results/phase-5e-2026-11-19/timing-13.json) · [Seed 31 study timing](benchmark-results/phase-5e-2026-11-19/timing-31.json) · [Profile memory](benchmark-results/phase-5e-2026-11-19/profile-memory.json)

## Reproduction

From the backend directory, use its virtual environment with one numerical thread. Use an empty output directory for `python -m research.holdem.phase_5e freeze OUT`, then `python -m research.holdem.phase_5e holdout OUT` with `PYTHONHASHSEED=13` and the same command with `--reverse` under seed 31. Use `diagnostic OUT` for the original paired experiment. Run `python -m research.holdem.phase_5e_timing OUT` in isolation. The saved summary driver can be run from backend with backend on `PYTHONPATH` and with its local Phase 5D archive alongside OUT. It checks exact byte parity before deriving tables. SHA-256 of both canonical holdouts is `cd3868df3026aa2ded9f0ca9ed0591c1ae4b8ab6539d19bb29059d686e943077`. [Frozen source hashes](benchmark-results/phase-5e-2026-11-19/frozen.json) · [Summary driver](benchmark-results/phase-5e-2026-11-19/summarize.py)

## Verification and Git status

- All **1,064 backend tests** passed in nine disjoint groups. Collection preserved all 1,056 Phase 5D test IDs. The 243 research tests passed, including eight new V2 regressions. The focused V2 cases passed under both hash seeds. They cover short-call refunds, legal opportunity counts, missing and invalid replies, repeat imports, incomplete and invalid histories, seat identity, multiple same-street actions and legacy snapshot compatibility. Windows loopback access enabled the existing FastAPI TestClient tests. The groups emitted existing Pyparsing and Starlette deprecation warnings. [Full regression summary](benchmark-results/phase-5e-2026-11-19/socket-backend-summary.json) · [V2 tests](backend/test_research_holdem_phase_5e.py)
- The frontend production build, Coach rendering regression and Vite server-side render of Coach, Match, single Replay and Match Replay passed. Both fresh API history sets rendered their initial Replay events. The offline API smoke passed all six combinations of shadow unset, off or on and both persistent flags off or on. The paired outputs matched within each persistence mode. The smoke also verified legal CFR advice, valid histories, chip conservation, zero unexpected fallbacks and disabled-by-default tracing. The backend dependency check found no broken requirements. [API smoke](benchmark-results/phase-5e-2026-11-19/api-smoke.txt) · [Frontend build](benchmark-results/phase-5e-2026-11-19/frontend-build.txt) · [Coach rendering](benchmark-results/phase-5e-2026-11-19/frontend-coach.txt) · [Dependencies](benchmark-results/phase-5e-2026-11-19/pip-check.txt)
- The checkout remains on `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. The tracked diff matches the entry snapshot. Git status adds six untracked Phase 5E files to the existing working tree. The ignored benchmark directory contains the frozen results and verification logs. `git diff --check` passed with the existing CRLF advisory. [Final Git status](benchmark-results/phase-5e-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-5e-2026-11-19/status-delta.txt)
