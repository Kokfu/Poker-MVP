# Phase 5G — Wager observation coverage and hybrid validation

**Decision B — partially validated.** Expanded observations reduced independent river action-EV error from **0.597 to 0.071 bb/decision**, an improvement of **0.525 bb/decision** (paired 95% interval [0.493, 0.560]). They also improved on the original hybrid by **0.472 bb/decision** [0.440, 0.505]. The numerical and downside gates passed. The eight-worker Coach reliability gate failed with nine calls over 15 seconds and nine observer timeouts. Keep Profile V2 in offline research. [Frozen protocol](PHASE_5G_PROTOCOL.md) · [Holdout summary](benchmark-results/phase-5g-2026-11-20/summary.json)

## Wager coverage audit

The local Coach store contained zero logged hands at audit time. Phase 5F's public exports provided one single-hand fixture and two persistent-match fixture hands. The single-hand solver and tight exports had zero valid wager-response opportunities for either seat. In the persistent match, one hand contributed three live opportunities across both seats. These are simulator examples and cannot establish population frequencies or the rarity of unobserved wagers.

| Audited dimension | Fixture opportunities and responses | Exact evidence reading |
| --- | --- | --- |
| Preflop | 0 live / 0 observed | A logged limp or response to a forced blind does not establish a voluntary-wager opportunity. |
| Flop | 1 / 1 | Tight, big blind, facing a bet, called. |
| Turn | 0 / 0 | The available turn actions were checks. |
| River | 2 / 2 | Solver, button, raised against a bet. Tight, big blind, called a raise. |
| Wager size | Small 0, half-pot band 2, pot band 1, overbet 0 | All three observed replies came from exact sparse cells. |
| Closing shove and short all-in call | 0 / 0 in each | Both are unsupported in these exports. A deterministic short-call fixture verifies closing status and refund handling independently. |
| Effective depth | All 3 at >10–30 bb | 0 at ≤10, >30–100 or >100 bb. |
| Effective SPR | 1 at >1–3 and 2 at >3–8 | 0 at ≤1 or >8. |
| Style, position and previous action | Solver 1 / 1 on the button, Tight 2 / 2 in the big blind. Two followed a bet and one a raise. | All observed exact cells select the incumbent. Effective reply count is 1 per matched cell. |

The three fixture cells each have zero observed folds and a descriptive 95% Wilson interval of [0, 0.793]. Missing cells have effective sample size zero and no empirical forecast interval. No independent action-EV labels are available for the public exports. The [machine-readable audit](benchmark-results/phase-5g-2026-11-20/coverage-audit.json) gives logged and contributing hand counts, legal opportunity/reply counts, coverage and forecast source by exact key and marginal dimension. Its Phase 5F section records the original per-opponent river query coverage and links each comparable exact context to historical action-MAE samples and observed forecast error against the reference. The Phase 5F panel lacks raw sample fold counts for every exact key, so it reports reference error in place of a sampling interval.

| Archived Phase 5F root action slice | Actions | Incumbent MAE (bb/action) | Original hybrid MAE (bb/action) |
| --- | ---: | ---: | ---: |
| Supported | 448 | 0.573 | 0.119 |
| Sparse | 112 | 2.096 | 2.096 |
| Unsupported | 1,360 | 1.133 | 1.133 |
| No future reply | 768 | 0.000 | 0.000 |

The sparse and unsupported slices accounted for 1,472 of the 1,920 live-wager actions in the archived whole-menu panel. Their errors identify where additional evidence could affect the primary endpoint. Equal errors in the two forecast columns reflect the frozen fallback. [Phase 5F coverage and EV evidence](benchmark-results/phase-5f-2026-11-20/summary.json)

## Why coverage was missing

- **Training selection.** The original synthetic stream scheduled only two wager prices per opponent family. Some original clusters deliberately offered one of them five times or zero times. The original play script reaches the river after a preflop raise/call and checks on flop and turn. No learned reply to a flop or turn wager follows from those histories. Sparse and unsupported river actions can have large errors even when the hand count reaches 300.
- **Exact reply geometry.** The normal 625-chip public observation has both a full raise and shove available. The bounded root after the same 625-chip bet exposes fold, call and shove. The full legal mask is part of the frozen evidence key. The engine and bounded tree agree on the other four root keys. The short-stack 625-chip variant independently reproduces the bounded reply mask within the existing depth and SPR buckets. This is a training compatibility gap, with no confirmed corrupted observations.
- **Opportunity denominators.** A training hand contributes two live wager opportunities, one to a preflop raise and one to a river wager, plus unrelated public actions. The preflop denominator adds no evidence for river queries. A known opportunity with an invalid or fallback reply contributes zero valid responses. An unverified action prefix does not certify the next opportunity. Tests exercise all of these boundaries.
- **Stacks and closure.** The complete public event format has the commitment and stack geometry needed for collectible price, depth, SPR and closing status. The independent 1,250-offered/400-collectible fixture returns 850 chips, and the short all-in response counts as a call. No closing-shove classification defect was reproduced. A closing call when Hero acts ends betting and therefore has no future opponent reply to learn.
- **Imports and identity.** Completed fixture histories passed validation. Repeat source IDs are ignored, conflicting repeats are rejected, and database spot copies are counted separately when present. The local store was empty, so missing fields, incomplete real imports and cross-alias duplicates could not be estimated. An action summary without certified history geometry cannot be used to infer a denominator.
- **Coarse sizes.** V2 shares conditional estimates inside the existing size buckets, while the hybrid requires an exact reduced collectible-price ratio before using them. An extra 1-chip wager in the same bucket remains unsupported in regression. The 625-chip finding shows that a price match alone is likewise insufficient.

No stored observations were edited. The initial holdout schedule was stopped after a geometry regression failed, before opening any score files. The study added the alternate 625-chip training stratum, passed the engine/tree and denominator regressions, and froze a new independent holdout schedule. The selector, original engine histories, harness action menu and scoring rules were preserved. [Frozen protocol](PHASE_5G_PROTOCOL.md)

## Training and evaluation

The study evaluated 24 independent training clusters, two paired synthetic reference members per cluster and 12 held-out deals per member. Each profile preserved its original 300-hand Phase 5F allocation and added 1,200 engine-replayed histories, 240 at each of 125, 250, 500, 625 and 1,250 chips into a 500-chip matched pot. At 625 chips, 120 were replayed at each of the two legal geometries. Stable source IDs identify the opponent, stream and sequence index. The supplemental generator uses independent seeds and checks for repeated deals within each supplemental profile. Synthetic cards are used for engine settlement and the existing bounded evaluator. The forecast reads only public histories.

The training mix was stratified to cover query contexts. The fixed primary population gave each family, paired member and replicate equal weight, with 384 full-menu decisions and 192 closing-call controls. The independent 990-holding cash-ledger scorer reused the same range, legal menu, continuation and reference law across arms. The development comparison reproduced Phase 5F's exact action values and selected actions for the incumbent, original hybrid and diagnostic reference. The additional scripted reply panel is reported separately from the menu and has no EV weight. Results apply to these public synthetic laws at the measured geometry.

## Coverage and learning curve

Each budget evaluates the same holdout. Counts sum across 48 profiles. The all-wager count includes the preflop raise response, and the query count deduplicates exact river keys within each profile. Both counts equal their respective observed replies. Coverage proportions and forecast selection refer to the 3,072 scored reply queries. V2 selection equals the supported share, and the other queries use the incumbent.

| Hands per profile | All wager opportunities | Exact query opportunities | Supported / sparse / unsupported | Brier | Log loss | Closing fold MAE | EV MAE (bb/decision) | Incorrect action pairs |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 30 | 2,880 | 1,440 | 19.8% / 29.7% / 50.5% | 0.578 | 0.859 | 0.183 | 0.615 | 1,162 |
| 100 | 9,600 | 4,800 | 39.6% / 9.9% / 50.5% | 0.561 | 0.828 | 0.152 | 0.553 | 1,007 |
| 300 | 28,800 | 14,400 | 39.6% / 9.9% / 50.5% | 0.559 | 0.825 | 0.149 | 0.543 | 977 |
| 500 | 48,000 | 23,280 | 100% / 0% / 0% | 0.457 | 0.680 | 0.059 | 0.177 | 405 |
| 1,000 | 96,000 | 45,480 | 100% / 0% / 0% | 0.453 | 0.672 | 0.031 | 0.095 | 194 |
| 1,500 | 144,000 | 67,680 | 100% / 0% / 0% | 0.453 | 0.672 | 0.027 | 0.071 | 158 |

The largest EV improvement came between 300 and 500 hands when the supplemental schedule first covered the whole menu. The 500-to-1,000 and 1,000-to-1,500 increments continued to improve EV with coverage already at 100%, with diminishing returns. Realized Brier worsened slightly from 0.4525 to 0.4531 over the final increment, while expected Brier against the reference improved from 0.4527 to 0.4516. At 30 hands the hybrid's 0.615 bb MAE exceeded the incumbent's 0.597 bb. That comparison uses the fixed 300-hand incumbent, and the early hybrid had only 30 hands. The 100% coverage applies to the bounded query population. Exact-ratio, position, stack, SPR and legal-mask shifts still fall back when evidence is absent.

| Hands per profile | Cumulative train median / p95 (s) | Forecast panel median / p95 (ms) | Instrumented allocation peak (MiB) |
| ---: | ---: | ---: | ---: |
| 30 | 0.114 / 0.207 | 0.300 / 0.579 | 0.86 |
| 100 | 0.359 / 0.550 | 0.303 / 0.399 | 1.03 |
| 300 | 1.091 / 1.532 | 0.350 / 0.496 | 1.64 |
| 500 | 1.817 / 2.359 | 0.425 / 0.643 | 2.19 |
| 1,000 | 3.612 / 4.495 | 0.444 / 0.530 | 3.80 |
| 1,500 | 5.365 / 6.777 | 0.601 / 0.819 | 4.57 |

Timing is from hash seed 13 during concurrent holdout and regression work. Panel timing covers the unique forecast queries once per profile and budget. Instrumented allocation uses a separate development run. Exact scoring median/p95/max was 0.066/0.113/0.440 s per deal for seed 13 and 0.066/0.112/0.334 s for seed 31. Peak worker resident memory was 102.68 and 102.78 MiB. The canonical outputs were byte-identical. [Seed 13 timings](benchmark-results/phase-5g-2026-11-20/holdout-13-timing.json) · [Seed 31 timings](benchmark-results/phase-5g-2026-11-20/holdout-31-timing.json) · [Per-budget allocation](benchmark-results/phase-5g-2026-11-20/profile-memory.json)

## Controlled reply forecasts

A is the incumbent, B is pure V2 at 1,500 hands, C is the original 300-hand hybrid, D is the expanded hybrid, and E is the diagnostic reference. B and D agreed on all scored queries because each had crossed the support threshold. E's realized scoring noise can occasionally give B or D a lower score on a single price. The expected scores remain lowest for E. The combined reply table uses the fixed panel mix. The menu-only Brier moved from 0.561 with C to 0.464 with D, while the scripted panel moved from 0.556 to 0.436.

| Wager price and geometry | Replies | C supported replies | Brier A / C / D / E | Log loss A / C / D / E | Menu action MAE A / C / D (bb/action) |
| --- | ---: | ---: | --- | --- | --- |
| 125, quarter pot | 816 | 480 | 0.599 / 0.568 / 0.455 / 0.455 | 0.926 / 0.862 / 0.696 / 0.696 | 0.641 / 0.491 / 0.061 |
| 250, half pot | 528 | 160 | 0.554 / 0.535 / 0.431 / 0.428 | 0.807 / 0.783 / 0.617 / 0.614 | 0.935 / 0.866 / 0.086 |
| 500, pot | 672 | 320 | 0.611 / 0.581 / 0.472 / 0.473 | 0.969 / 0.898 / 0.728 / 0.729 | 1.004 / 0.831 / 0.104 |
| 625, 1.25 pot | 528 | 96 | 0.570 / 0.562 / 0.436 / 0.434 | 0.812 / 0.803 / 0.631 / 0.625 | 1.476 / 1.476 / 0.179 |
| 1,250, closing shove | 528 | 160 | 0.545 / 0.538 / 0.465 / 0.459 | 0.745 / 0.739 / 0.658 / 0.651 | 1.313 / 1.225 / 0.212 |

D supported all 3,072 replies, including all 384 bounded 625-chip menu queries. C's 96 supported 625-chip replies were confined to the scripted panel with the other legal mask. Closing-shove fold MAE fell from 17.52 percentage points for A and 14.86 for C to 2.67 for D. Combined expected Brier and log loss were 0.5810/0.8676 for A, 0.5576/0.8252 for C, 0.4516/0.6713 for D, and 0.4497/0.6684 for E. [Forecast panels and style-specific scores](benchmark-results/phase-5g-2026-11-20/summary.json)

## Independent river decision quality

The primary holdout scored 576 decisions across 2,688 concrete actions. Per-decision MAE gives each full-menu or closing-control decision equal weight. Intervals resample whole training/evaluation clusters within family and exposure strata, keeping both reference members paired.

| Arm | EV MAE (bb/decision) | Gain over A, paired 95% interval | Correct material pairs / 5,935 | False positive advantages | Mean / worst regret (bb) | Profitable calls / bluffs chosen | Harmful shoves chosen |
| --- | ---: | --- | ---: | ---: | --- | --- | ---: |
| A · Incumbent | 0.597 | — | 4,807 | 145 | 0.2280 / 2.6263 | 112 / 173 | 1 |
| B · Pure V2, expanded | 0.071 | 0.525 [0.493, 0.560] | 5,777 | 24 | 0.0014 / 0.1443 | 112 / 204 | 0 |
| C · Original hybrid | 0.543 | 0.053 [0.050, 0.057] | 4,958 | 129 | 0.1767 / 2.6263 | 112 / 178 | 1 |
| D · Expanded hybrid | 0.071 | 0.525 [0.493, 0.560] | 5,777 | 24 | 0.0014 / 0.1443 | 112 / 204 | 0 |
| E · Reference | 0.000 | 0.597 [0.562, 0.632] | 5,935 | 0 | 0.0000 / 0.0000 | 112 / 204 | 0 |

The new C-versus-A comparison gives 0.053 bb improvement on independent deals, close to Phase 5F's historical 0.059 bb. D's additional 0.472 bb improvement [0.440, 0.505] over C clears the incremental gate. In the 112 action instances that moved from sparse to supported, C-to-D MAE fell from 2.042 to 0.131 bb/action. For 1,360 instances that moved from unsupported to supported, it fell from 1.172 to 0.145. For 448 already supported instances, it fell from 0.123 to 0.076. The 768 no-future-reply actions had zero prediction error in every arm. Every sparse or unsupported forecast and corresponding root EV at every measured budget exactly reproduced A. D preserved all 112 profitable closing calls and chose a profitable fold-dependent bluff on every one of the 204 decisions where the oracle did. D also removed the incumbent's single harmful shove.

| Synthetic opponent | EV MAE A / C / D (bb/decision) | Brier A / C / D | D correct pairs | D mean regret (bb) |
| --- | --- | --- | --- | ---: |
| Small 0 | 0.489 / 0.430 / 0.051 | 0.570 / 0.544 / 0.383 | 719 / 741 | 0.0000 |
| Small 1 | 0.476 / 0.420 / 0.049 | 0.501 / 0.474 / 0.402 | 716 / 741 | 0.0000 |
| Large 0 | 0.534 / 0.507 / 0.067 | 0.633 / 0.620 / 0.442 | 733 / 743 | 0.0000 |
| Large 1 | 0.526 / 0.489 / 0.082 | 0.518 / 0.499 / 0.441 | 733 / 744 | 0.0000 |
| Closing 0 | 0.491 / 0.435 / 0.085 | 0.626 / 0.617 / 0.463 | 688 / 738 | 0.0041 |
| Closing 1 | 0.461 / 0.404 / 0.073 | 0.491 / 0.482 / 0.465 | 725 / 741 | 0.0000 |
| River aggression 0 | 0.830 / 0.764 / 0.076 | 0.653 / 0.622 / 0.503 | 733 / 743 | 0.0056 |
| River aggression 1 | 0.966 / 0.897 / 0.087 | 0.646 / 0.614 / 0.525 | 730 / 744 | 0.0017 |

Both regret gates passed. Mean regret decreased by 0.227 bb and the largest additional loss on a switch was 0.030 bb. All three decisions harmed relative to A were close choices for closing-family member 0 on checked-to rivers. D chose half pot over quarter pot, costing 0.02985, 0.02419 and 0.01854 bb at the reference values. In the worst switch, with 6♣ 5♦ on J♦ 2♣ J♥ 3♥ K♠, quarter pot earned 0.4141 bb and half pot earned 0.3842 bb under the reference. D's absolute worst regret of 0.1443 bb came from choosing the same profitable quarter-pot bluff as A when half pot was better. [Decision-level values and harmful cases](benchmark-results/phase-5g-2026-11-20/summary.json)

## Eight-worker Coach reliability

Eight fresh processes returned 128/128 legal Coach responses, with zero changed recommendations or unexpected production fallbacks. All 96 enabled calls wrote parseable traces. Of those, 87 completed and nine recorded the observer's deadline status. The same nine Coach calls exceeded 15 seconds. The deadline had already expired when the observer entered on those calls, so its measured work was near zero. Eight timeouts came from archived row 31 and one from row 78. This was an end-to-end latency failure even though production CFR finished and the advice matched the disabled pairs. The worker peak was 177.67 MiB against a 768 MiB limit.

| Measurement | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Coach end to end, all calls (s) | 6.482 | 18.635 | 22.823 |
| CFR, all calls (s) | 6.320 | 15.504 | 17.395 |
| Coach first enabled call per spot (s) | 11.260 | 22.706 | 22.823 |
| Coach repeat enabled call (s) | 6.634 | 8.232 | 8.455 |
| Shadow work excluding trace write (ms) | 13.745 | 74.655 | 126.807 |
| Trace file write (ms) | 9.780 | 88.329 | 126.494 |

Worker import time ranged from 2.09 to 5.31 s, outside the per-call measurements. Median one-hand store replay per worker ranged from 3.59 to 6.61 ms, with a 54.50 ms maximum. The measured first-call and CFR tails place the largest delay in cold production work under contention. The probe did not isolate scheduler, memory-bandwidth or cache contributions. Eight threads also replayed 500 hands each into worker-owned profiles with identical counts, and wrote 96/96 unique complete records into one shared directory with zero orphan temporary files. The existing accumulator has a single-writer contract. The shared-directory probe tests concurrent publication independently of Coach timing. [Coach timing and normalized traces](benchmark-results/phase-5g-2026-11-20/observer-concurrent/summary.json) · [Contention diagnostics](benchmark-results/phase-5g-2026-11-20/contention.json)

## Frozen acceptance and Phase 5H

| Gate | Outcome |
| --- | --- |
| At least 0.10 bb/decision improvement over A with positive lower 95% bound | Pass. Gain 0.525, lower bound 0.493. |
| Positive lower 95% bound against C | Pass. Lower bound 0.440. |
| Historical support slices, expanded menu coverage and exact fallback | Pass. 112 sparse and 1,360 unsupported initial menu actions. All 1,920 menu wagers supported after expansion. Fallback reproduced A exactly throughout. |
| Mean regret increase at most 0.05 bb, worst new harm below 8 bb and all profitable calls preserved | Pass. Mean regret decreased 0.227 bb. Worst new harm 0.030 bb. All 112 profitable calls preserved. |
| Bounded evaluator time, memory and hash reproducibility | Pass. Both workers stayed below 15 s per deal and 768 MiB. Canonical SHA-256 was `2e863ee5a8c1a68396c2543d02e6c6077b4a67281dcff5f8928ac30a872c4c6e` in both orders. |
| Eight-worker Coach and observer reliability | **Fail.** 87/96 successful observations and nine Coach calls over the 15 s reference. |

Phase 5H should target cold CFR latency under eight simultaneous Coach workers, starting with the row 31 workload that accounted for eight of nine misses. Measure CPU time versus elapsed time through cold setup and CFR, then test a bounded cold-start workload or cache-preparation change against the exact same 128-call probe. The expected benefit is more calls reaching the observer before its deadline, without increasing its budget or the 15 s Coach ceiling. Require legal paired advice, 96/96 completed traces and zero unexpected fallbacks before a separate gameplay-validation phase. The synthetic result establishes that matched coverage can improve these conditional forecasts and river EVs. Transfer to real opponents remains unmeasured because the audit found no local player histories.

## Reproduction

From `backend` in the project's virtual environment, set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1. Use a fresh output directory alongside the Phase 5F evidence folder. Run the audit, development and freeze first. Run the eight-worker Coach probe separately from the holdout and backend regression.

```text
python -m research.holdem.phase_5g_audit audit OUT
python -m research.holdem.phase_5g development OUT
python -m research.holdem.phase_5g freeze OUT
python -m research.holdem.phase_5g_observer coach OUT
python -m research.holdem.phase_5g_observer diagnostics OUT
python -m research.holdem.phase_5g holdout OUT
python -m research.holdem.phase_5g holdout OUT --reverse
python -m research.holdem.phase_5g_audit memory OUT
python -m research.holdem.phase_5g_summary OUT
```

Use `PYTHONHASHSEED=13` for the first holdout and 31 for the reverse holdout. The entry-point verifies the frozen sources each time. The summary verifies the manifest again and compares canonical file bytes. Seeds, training allocations, query counts, probability vectors and action values are recorded in the holdout files. [Source manifest](benchmark-results/phase-5g-2026-11-20/frozen.json) · [Primary raw results](benchmark-results/phase-5g-2026-11-20/holdout-13.json) · [Reverse raw results](benchmark-results/phase-5g-2026-11-20/holdout-31.json)

## Regression evidence and Git status

- **1,084/1,084 backend tests passed** across nine disjoint groups, including all 1,077 retained Phase 5F test IDs and seven new Phase 5G cases. The 263 research tests passed. The local-loopback run resolved the restricted Windows TestClient stalls and finished in 323.5 s wall time, reusing the successfully completed benchmark and solver groups from the first launch. The logs show existing Pyparsing and Starlette deprecation warnings. [Backend results](benchmark-results/phase-5g-2026-11-20/verified/socket-backend-summary.json) · [Collected test IDs](benchmark-results/phase-5g-2026-11-20/verified/collected.txt)
- **Focused verification passed** with 28 tests under hash seed 13 and 36 under hash seed 31. The added cases reconcile engine and bounded menus, exercise the distinct preflop and river denominators, check independent allocations, reject duplicate imports and preserve exact fallback on an unseen price. The seed-31 run includes existing forced observer timeout, computation-error and trace-output isolation cases. [Seed 13](benchmark-results/phase-5g-2026-11-20/focused-13.txt) · [Seed 31](benchmark-results/phase-5g-2026-11-20/focused-31.txt)
- **Production checks passed.** The frontend production build, Coach rendering test and offline Coach, Match, Replay and Match Replay checks passed. Six API smoke combinations exercised shadow unset, disabled and enabled with both persistence settings. Within each persistence setting, public outputs agreed, advice was legal, histories conserved chips, no unexpected match fallback occurred, and Python and NumPy RNG states were unchanged. The unset setting produced no shadow trace. Vite rendered all four screens and replay events from the API histories. `pip check` found no broken requirements. [API smoke](benchmark-results/phase-5g-2026-11-20/api-smoke-loopback.txt) · [Frontend build](benchmark-results/phase-5g-2026-11-20/frontend-build.txt) · [Coach component](benchmark-results/phase-5g-2026-11-20/frontend-coach.txt) · [Replay rendering](benchmark-results/phase-5g-2026-11-20/frontend-match-replay.txt) · [Dependency check](benchmark-results/phase-5g-2026-11-20/pip-check.txt)
- **Git remains on `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`.** The tracked diff matched entry byte for byte. The seven new untracked files are the protocol, report, four offline research modules and regression file. The historical Phase 5F manifest and final Phase 5G manifest both verified. `git diff --check` passed with the existing LF/CRLF advisory for `backend/test_poker.py`. [Git status](benchmark-results/phase-5g-2026-11-20/final-status.txt) · [Status delta](benchmark-results/phase-5g-2026-11-20/status-delta.txt) · [Whitespace check](benchmark-results/phase-5g-2026-11-20/git-diff-check.txt) · [Manifest check](benchmark-results/phase-5g-2026-11-20/final-manifest.txt)
