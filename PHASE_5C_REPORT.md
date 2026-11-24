# Phase 5C — Opponent-model reliability and decision-risk diagnostics

**Decision C.** The frozen Phase 5C rule caught 20 of 21 high-regret recommendations and all seven severe losses. It also flagged 33 of 75 lower-regret choices, for a 44.0% false-positive rate against a 25% ceiling. The evidence supports using sensitivity to select cases for offline research. It does not validate an individual warning for Coach users.

## Architecture and observation boundary

The Coach first builds and samples the incumbent CFR policy. River shadow capture then copies the concrete root menu, actual seeded action, full-precision mix, compatible opponent reach, solved working columns, and both players' conditional continuations. The diagnostic prices the captured decision in the existing observer. It adds two posterior dot products on closing wagers and scalar comparisons across the existing sensitivity values. It reads the tree and policy snapshot and uses public betting observations, profile counts and Hero's cards. A diagnostic failure is handled by the private observer after the response has been constructed. The Match and Replay paths have no call site for the diagnostic. [Observer](backend/research/holdem/river_shadow.py) · [Risk calculation](backend/research/holdem/river_risk.py)

The existing `POKER_COACH_RIVER_SHADOW=1` opt-in controls private JSON output. The new fields fit in the bounded per-decision trace. The default directory is the per-user Phase 5B research directory. Traces retain Hero cards and inherit the directory's permissions. The existing trace writer creates one file per run and has no automatic retention policy. The reference law and per-decision reference scores live in the offline runner and its private evidence files. [Frozen protocol](PHASE_5C_PROTOCOL.md) · [Offline runner](backend/research/holdem/phase_5c.py)

## Audit of the Phase 5B signals

Phase 5B sensitivity caught six of seven high-regret decisions on its 16 generated cases. Greedy CFR/shadow disagreement caught two. That comparison measured regret of the shadow greedy choice. Phase 5C measures regret of the seeded Coach action shown to the user. [Phase 5B report](PHASE_5B_REPORT.md)

| Signal | Information available at decision time | Interpretation |
| --- | --- | --- |
| Incoming opponent range | CFR reaches restricted to Hero- and board-compatible holdings, plus a 15% mixture toward uniform support | A fixed support stress. It is insensitive to some major changes in strength composition and to the causal effect of individual observed wagers. |
| Concentration | Positive holding count, inverse sum of squared holding probabilities, largest weight and mass omitted from the CFR columns | Effective support measures concentration. A narrow but correct posterior and a broad but incorrect posterior are both possible. |
| Reply forecast | Captured opponent strategy plus low and high continuation/aggression endpoint scenarios built from the same pooled river counts | Phase 4Y-derived 97.5% equal-tailed Beta endpoints use Beta(1,1) for continuation and Beta(1,7) for raises conditional on continuing. The forecast then applies a price tilt and fixed strength tiers. Joint perturbations mix these endpoints with the relaxed range. |
| Weak observations | Public fold and raise opportunity counts and the residual call count. Zero counts use the same priors. | Phase 5C also records preceding profile hands. Many logged hands can still produce few river reply opportunities. The pooled snapshot cannot directly establish the fold rate at a particular size. |
| Value and ranking sensitivity | Model EV by concrete action under nominal and perturbed assumptions. Capture also saves same-column repricing and greedy ranks. | Phase 5B alerted at a 2 bb swing in its preferred action's lead over Coach's draw, a 2 bb alternative lead under stress, or effective support below 50. The 15%, 2 bb and 50-holding quantities were fixed in the Phase 5B protocol as stress/materiality heuristics. That protocol does not record empirical calibration for those cutoffs. |
| Bluff and closing-call risk | Aggressive branches have modeled fold, call and raise continuations. Closing calls have exact pot geometry and a modeled showdown mixture. | Phase 5B had no dedicated break-even metric or win/loss tilt for closing calls. The realized correctness of a bluff, the value of a folded closing call, true range TV, reference fold overestimation and regret all require the offline law. |

Limited observations widen the count-based reply endpoints. The residual call count includes stack-closing all-ins that leave the highest commitment unchanged. Structural misspecification includes misread range strength, incomplete wager-size evidence, an incorrect strength tilt or changes in opponent behavior. These errors can persist with precise pooled counts. Same-column CFR residuals isolate numerical agreement under common assumptions. Working-column projection and finite sizing can shift estimated EV separately. [Phase 5B protocol](PHASE_5B_PROTOCOL.md) · [Reply forecasting](backend/research/holdem/reply_forecast.py) · [Phase 4Z audit](PHASE_4Z_REPORT.md)

## Phase 5C risk indicator

The margin is the selected action's net EV minus the highest-valued alternative in each model. The trace alerts when a stressed alternative leads by at least 2 bb and the selected margin deteriorates by at least 1 bb from nominal. The 2 bb floor inherits Phase 5B materiality. The 1 bb movement requirement makes the flag responsive to changes in assumptions. A stable nominal mistake can therefore escape the indicator. The separate nominal-gap baseline measures that failure mode. For closing calls, the extra alternatives multiply win-to-loss odds by two or one-half while holding tie weights fixed before normalization. These are symmetric stress scenarios. Their weights and the share of greedy-action changes have no statistical interpretation as the probability of recommending the wrong action. [Risk calculation](backend/research/holdem/river_risk.py) · [Frozen protocol](PHASE_5C_PROTOCOL.md)

The fold break-even figure solves for the immediate fold rate at which the selected wager equals the best modeled passive action. It holds conditional nonfold value fixed, including future Hero responses and any subsequent raises. The trace reports the margin between modeled folds and that threshold when a crossing exists. Its interpretation depends on the assumed nonfold response mix. The closing-call stress is separate because a call that ends betting creates no future opponent-reply branch. Both stress types share the same alert rule. [Observer](backend/research/holdem/river_shadow.py) · [Risk calculation](backend/research/holdem/river_risk.py)

## Reference design

The frozen panel crosses four synthetic opponent styles, six wager categories and four history sizes. Each row uses a unique board and, where applicable, a distinct training history. Profile lengths are 0, 3, 30 and 100 hands, with both same-style profiles and deliberately mismatched profiles among the trained rows. Public betting histories are scripted and starting stacks vary across 9, 15 and 30 bb. The independent reference weights all 990 compatible holdings by the stated public-path likelihood and prices each current action through a separate cash ledger with Treys ranks and fixed subsequent Hero policy. Its regret labels are exact for the specified laws, legal menu and continuation. Transfer to a live opponent population remains unmeasured. [Frozen protocol](PHASE_5C_PROTOCOL.md) · [Cash ledger](backend/research/holdem/action_ev_reference.py)

## Fresh holdout

All 96 scheduled decisions and 292 concrete actions were scored in the primary run. The independent ledger matched full and projected shadow values within 1e-10 bb. The maximum same-column residual against CFR was 0.00000725 bb. With opponent assumptions allowed to differ from reference, estimated action-EV MAE was 3.829 bb. Replacing only the posterior reduced it to 1.956 bb. Replacing only future replies reduced it to 3.452 bb. These are conditional substitutions and the effects can interact. Mean range TV was 0.729. Effective support ranged down to 2.65 holdings with a median of 132.38. At 117 facing-wager reply nodes reached at least 5% in both models, predicted fold, call and all-in frequencies averaged +24.74, −26.98 and +1.95 percentage points from reference. The median decision changed the shadow greedy action in 40% of its stress scenarios. Thirteen selections had a reportable fold break-even threshold. [Frozen source hashes and schedule](benchmark-results/phase-5c-2026-11-19/frozen.json) · [Primary holdout and per-action scores](benchmark-results/phase-5c-2026-11-19/holdout-13.json)

The panel contained 21 seeded recommendations with at least 2 bb regret and seven with at least 8 bb regret. The five classifiers below use those same decisions. Intervals are 95% Wilson score intervals in percentage points. The reverse-order hash-seed run reproduced all 96 canonical records. It contributes no additional independent cases. [Primary holdout](benchmark-results/phase-5c-2026-11-19/holdout-13.json) · [Reproducibility comparison](benchmark-results/phase-5c-2026-11-19/determinism.json)

| Indicator | TP / FP / FN / TN | Recall % | Precision % | False-positive rate % | False-negative rate % | Severe coverage % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CFR/shadow greedy disagreement | 1 / 1 / 20 / 74 | 4.8 [0.8, 22.7] | 50.0 [9.5, 90.5] | 1.3 [0.2, 7.2] | 95.2 [77.3, 99.2] | 0 [0, 35.4] |
| Phase 5B sensitivity | 18 / 40 / 3 / 35 | 85.7 [65.4, 95.0] | 31.0 [20.6, 43.8] | 53.3 [42.2, 64.2] | 14.3 [5.0, 34.6] | 100 [64.6, 100] |
| **Phase 5C** | **20 / 33 / 1 / 42** | **95.2 [77.3, 99.2]** | **37.7 [25.9, 51.2]** | **44.0 [33.3, 55.3]** | **4.8 [0.8, 22.7]** | **100 [64.6, 100]** |
| Nominal gap of at least 2 bb | 1 / 2 / 20 / 73 | 4.8 [0.8, 22.7] | 33.3 [6.1, 79.2] | 2.7 [0.7, 9.2] | 95.2 [77.3, 99.2] | 0 [0, 35.4] |
| Effective support below 50 | 8 / 24 / 13 / 51 | 38.1 [20.8, 59.1] | 25.0 [13.3, 42.1] | 32.0 [22.5, 43.2] | 61.9 [40.9, 79.2] | 42.9 [15.8, 75.0] |

Four severe losses occurred against overbets, two in the checked/unopened category and one against a three-quarter-pot bet. The largest was a 22.755 bb shove against a tight-passive overbet with a mismatched loose-aggressive profile. Nominal shadow favored the shove by 8.329 bb. The high-continuation stress put it 13.813 bb behind folding. The one missed high-regret choice was an A♦ Q♦ closing call against tight-passive with a mismatched 30-hand loose-aggressive profile and one usable river reply count. It cost 2.721 bb. The model valued the call at +5.372 bb and the strongest tested shift toward worse showdown outcomes still valued it at +2.456 bb. The model set missed the true value-heavy range. [Rows 21 and 46](benchmark-results/phase-5c-2026-11-19/holdout-13.json)

### Performance by wager, opponent and profile

| Slice | Phase 5C TP / FP / FN / TN | Recall | False-positive rate |
| --- | ---: | ---: | ---: |
| Checked or unopened | 5 / 6 / 0 / 5 | 5/5 | 6/11 |
| Quarter pot | 0 / 8 / 0 / 8 | — | 8/16 |
| Half pot | 3 / 5 / 0 / 8 | 3/3 | 5/13 |
| Three-quarter pot | 5 / 6 / 0 / 5 | 5/5 | 6/11 |
| Overbet | 4 / 5 / 0 / 7 | 4/4 | 5/12 |
| Closing shove | 3 / 3 / 1 / 9 | 3/4 | 3/12 |
| Tight-passive | 6 / 7 / 1 / 10 | 6/7 | 7/17 |
| Loose-passive | 5 / 9 / 0 / 10 | 5/5 | 9/19 |
| Tight-aggressive | 3 / 10 / 0 / 11 | 3/3 | 10/21 |
| Loose-aggressive | 6 / 7 / 0 / 11 | 6/6 | 7/18 |
| No profile | 6 / 12 / 0 / 6 | 6/6 | 12/18 |
| 3 hands | 6 / 9 / 0 / 9 | 6/6 | 9/18 |
| 30 hands | 7 / 6 / 1 / 10 | 7/8 | 6/16 |
| 100 hands | 1 / 6 / 0 / 17 | 1/1 | 6/23 |
| Same-style profile | 7 / 12 / 0 / 17 | 7/7 | 12/29 |
| Opposite-style profile | 7 / 9 / 1 / 19 | 7/8 | 9/28 |

The closing-wager stress improved detection from one to three of the four high-regret closing cases. There were zero severe closing outcomes. Nonclosing decisions produced all seven severe losses and a false-positive rate of 30/63. The quarter-pot class contained zero high-regret outcomes and eight alerts. The machine-readable results include per-slice intervals and all comparator counts, including starting-depth slices. The original Phase 5B target on this panel, regret of the shadow greedy action, produces 21 true alerts, 37 false alerts, three misses and 35 true negatives under its own flag. [Subgroup statistics](benchmark-results/phase-5c-2026-11-19/holdout-13.json)

### Profitable bluffs and calls

| Reference opportunity | Decisions offering it | Selected it | Phase 5C alerts when selected | Phase 5C alerts on other selections |
| --- | ---: | ---: | ---: | ---: |
| Profitable fold-dependent bluff | 12 | 4 | 1/4 | 6/8 |
| Unprofitable fold-dependent bluff | 49 | 16 | 8/16 | 28/33 |
| Profitable closing call | 7 | 5 | 0/5 | 2/2 |
| Unprofitable closing call | 9 | 3 | 2/3 | 2/6 |

The alert on a profitable bluff came on Q♣ 4♣ versus a loose-aggressive overbet. Shoving earned +7.416 bb in the reference, beating the +6.273 bb call. The modeled immediate fold forecast of 60.95% was close to its 60.97% threshold and the stronger continuation scenario put the shove 9.103 bb behind the best alternative. This was a false alert. All five selected profitable closing calls passed unflagged, with a Wilson 95% upper bound of 43.4% on the false alert rate for that group. The two alerts on folds surfaced missed calls worth +0.329 and +7.275 bb. The first falls below the preregistered high-regret threshold. [Bluff and call counts](benchmark-results/phase-5c-2026-11-19/holdout-13.json)

## Historical failures

The old-policy replay reproduced the archived loss or foregone call value on each witness. The separate Phase 5C probe rebuilt the public decision and eligible profile and priced the archived action with the observable shadow inputs. The probe used the 896-column persistent path for the Phase 4W bluff and Phase 4Z switch, and the legacy input path for the other witnesses. Several historical choices came from experimental policies. On those rows the archived choice is scored explicitly alongside the current draw. The diagnostics use no reference inputs. [Historical replay and candidate traces](benchmark-results/phase-5c-2026-11-19/historical.json)

| Archived case | Reproduced result | Flag | Observable explanation |
| --- | ---: | --- | --- |
| A♥ 9♣ harmful bluff | −17.690 bb mixed delta | Yes | Nominal shove margin was +0.362 bb. The 63.41% fold forecast was just above the 62.50% break-even rate. The higher-continuation scenario put the shove 15.024 bb behind folding. |
| Q♣ 2♦ action switch | −11.551 bb versus call | Yes | Shadow gave the shove +0.918 bb versus its best alternative. Higher continuation put it 12.371 bb behind. |
| Q♦ 8♥ seeded shove | −9.639 bb versus the original draw | Yes | On the legacy inputs, the archived shove already trailed the best alternative by 5.356 bb. Higher continuation widened the gap to 24.407 bb. The current Coach draw was fold. |
| 7♣ 7♦ displayed recommendation | −8.204 bb versus call | No | On the legacy inputs every frozen scenario preferred the shove. Its narrowest lead was +1.499 bb. The current draw was call. The historical audit found that substituting the reference range reversed the shove advantage. |
| T♦ 3♥ accepted adjustment | −2.347 bb mixed delta | No | Higher continuation widened the candidate's deficit from 0.370 to 1.533 bb, below the stress cutoff. The pure shove itself was 3.136 bb behind folding under the reference. The current draw was call. |
| J♦ 4♥ profitable closing call folded by the conservative rule | +1.315 bb foregone | Yes | The current draw called. The hypothetical fold was 2.776 bb behind nominal and 5.763 bb behind in the higher-win scenario. Its true loss is below the 2 bb classifier threshold, so it would count as a false positive by that definition. |
| Q♣ 4♠ profitable closing call folded | +5.547 bb foregone | Yes | The current draw folded even though the nominal estimate valued cover at +10.970 bb. The higher-win scenario raised that to +14.569 bb and triggered the flag. |

The current Coach choices on 7♣ 7♦, Q♦ 8♥ and T♦ 3♥ also raised alerts despite regrets of 0.745, 0.350 and 1.432 bb. In each case the stress model gave an aggressive alternative a large advantage over the incumbent call or fold. The profitable current closing call on J♦ 4♥ was unflagged. [Historical replay and candidate traces](benchmark-results/phase-5c-2026-11-19/historical.json)

## Shadow invariance and runtime

All 192 enabled holdout traces completed with zero missing traces, errors, timeouts or production fallbacks. Both runs paired twelve scheduled decisions with disabled-shadow Coach calls. All 24 pairs preserved canonical Coach responses, CFR input fingerprints, unrounded action probabilities and selected indices. The maximum total Coach time across holdout calls was 8.076 s. The two enabled-run median/p95/max were 2.419/6.595/7.949 s and 2.502/6.356/8.076 s. [Seed 13](benchmark-results/phase-5c-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-5c-2026-11-19/holdout-31.json)

| Isolated process | Cold-board Coach median / p95 / max, s | Warm-board Coach median / p95 / max, s | Peak working set |
| --- | ---: | ---: | ---: |
| CFR only | 2.412 / 4.879 / 4.879 | 1.337 / 3.723 / 3.723 | 200.62 MiB |
| CFR and shadow | 2.252 / 6.942 / 6.942 | 1.099 / 4.346 / 4.346 | 205.01 MiB |

All 12 isolated shadow traces completed. The extra decision-risk work took 0.107 / 0.501 / 0.501 ms median/p95/max. Full shadow compute was 7.676 / 45.387 / 45.387 ms, and the observer segment including private trace write was 11.476 / 58.846 / 58.846 ms. The observed whole-process peak increase was 4.39 MiB. Whole-process timings include board-cache and operating system variation. The 15 s Coach, 150 ms shadow compute, 5 ms incremental diagnostic and 64 MiB memory budgets all passed these probes. [CFR probes](benchmark-results/phase-5c-2026-11-19/performance-cfr.json) · [Shadow probes](benchmark-results/phase-5c-2026-11-19/performance-shadow.json)

The separate fresh-interpreter check took 2.428 s disabled and 3.413 s enabled, returning the same 500-chip bet. Only the enabled process imported the observer. Its first observer segment took 690 ms including import, evaluation and output, of which 34 ms was shadow compute. The 150 ms cooperative timer starts after import. The 15 s end-to-end reference includes import and file output. [Disabled first use](benchmark-results/phase-5c-2026-11-19/first-use-cfr.json) · [Enabled first use](benchmark-results/phase-5c-2026-11-19/first-use-shadow.json)

## Architecture decision and Phase 5D

**PHASE 5C NOT COMPLETE under the diagnostic acceptance gates.** The 95% interval for precision lies below the frozen 55% target. The 21 high-regret cases, seven severe cases, four selected profitable bluffs and five selected profitable calls also fell short of the sample minima. Closing cases had too few losses to qualify for a partial result. Nonclosing cases exceeded the false-positive limit.

Phase 5D should test the opponent inputs directly. Build independent validation sets with new policy families and explicit variation in river wager selection, calling and reraising. Measure conditional holding composition after observed wagers and future fold/call/raise frequencies by price, stack and evidence count. Use range-only and reply-only substitutions to attribute the resulting EV errors, then re-evaluate diagnosis on a larger frozen panel with enough severe and profitable decisions. Test closing-call composition separately because future replies cannot explain those errors. Keep the existing traces useful for offline case selection and retain incumbent decision selection.

## Verification and Git status

- All **1,052 backend tests** passed across nine disjoint file groups in 533.05 s wall time. Collection preserved all 1,044 Phase 5B test IDs and added eight. The passing total includes all 231 research regressions. The groups reported dependency deprecation warnings for Pyparsing and Starlette's multipart import. [Backend summary and group coverage](benchmark-results/phase-5c-2026-11-19/backend-summary.json) · [Collected tests](benchmark-results/phase-5c-2026-11-19/collected.txt)
- The focused payoff and observer suites passed 30 tests under each of hash seeds 13 and 31. They verify immutable range reaches and CFR mixes, unchanged stored profile and database contents, Match and history parity, isolation from hidden opponent cards, and safe handling of diagnostic, capture, deadline and trace-write failures. The eight new regressions include profitable and unprofitable decision margins and the private closing-call trace. [Focused seed 31](benchmark-results/phase-5c-2026-11-19/focused-31.txt)
- The local API matrix passed all six combinations of the shadow flag unset, zero or one with the persistent Coach and Match flags either both off or both on. Advice, Match outcomes and both Replay payloads matched within each persistence setting. Histories passed chip-conservation validation. There were zero unexpected fallbacks, zero diagnostic fields in public advice and no changes to process Python or NumPy RNG state. The default and explicit-zero cases created zero traces. The sandboxed socket-pair probe timed out, so the local FastAPI checks ran with Windows loopback access. [API smoke](benchmark-results/phase-5c-2026-11-19/api-smoke.txt)
- The frontend production build passed. The Coach solver-frequency rendering regression passed. Coach, Match, single Replay and Match Replay rendered through Vite, including initial events from the current API histories. The backend dependency check found no broken requirements. [Frontend build](benchmark-results/phase-5c-2026-11-19/frontend-build.txt) · [Coach render regression](benchmark-results/phase-5c-2026-11-19/frontend-coach.txt) · [Replay smoke](benchmark-results/phase-5c-2026-11-19/frontend-match-replay.txt) · [Dependencies](benchmark-results/phase-5c-2026-11-19/pip-check.txt)
- The branch is `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. Unrelated changes from the Phase 5B working tree remain in place. The only changes to files hashed by its manifest are in the shadow evaluator and the Phase 5B comparator's handling of the new timing field. New files are the risk module, frozen runner, regressions, protocol and report. The Phase 5C manifest still matches the source tree and schedule. `git diff --check` passed with the pre-existing CRLF advisory on `backend/test_poker.py`. [Git status](benchmark-results/phase-5c-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-5c-2026-11-19/status-delta.txt) · [Manifest verification](benchmark-results/phase-5c-2026-11-19/final-manifest.txt) · [Whitespace check](benchmark-results/phase-5c-2026-11-19/git-diff-check.txt)
