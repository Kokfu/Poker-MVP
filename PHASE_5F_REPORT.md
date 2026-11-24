# Phase 5F — Evidence-aware Profile V2 forecasting

**Decision B — partially validated.** The hybrid recovered the EV accuracy lost by pure V2 and improved fresh per-decision MAE from 0.588 to 0.529 bb. The 0.059 bb improvement fell short of the frozen 0.10 bb requirement. The largest increase in oracle recommendation regret was 0.047 bb. Keep the hybrid in offline research. [Frozen protocol](PHASE_5F_PROTOCOL.md)

## Fallback diagnosis

The importer validates a settled public history and extracts an opportunity only when the preceding wager and legal menu are known. It aggregates observed legal replies, eligible opportunities and missing replies by situation. The Phase 5E forecast sends the cell's reply counts through a two-count Dirichlet prior based on the remaining river counts for the same legal menu. If the cell has zero usable replies, the prior supplies the entire forecast. An empty street/menu pool gives equal probability to every legal class. The river evaluator then weights fold, showdown and raise branches by the forecast, compares action values and chooses the highest EV. Legal probability alone can still put substantial mass on a response the opponent seldom takes.

| Decision-time evidence | Pure V2 behavior | Hybrid behavior |
| --- | --- | --- |
| Wager cell absent, or zero valid replies | Uses the same-street, same-menu prior or a uniform empty-pool distribution | Returns incumbent forecast exactly |
| 1–19 valid replies | Applies the same two-count prior to the few responses | Sparse, returns incumbent forecast |
| Many total hands but few relevant replies | Total hands confer no cell support, though other cells affect the prior | Uses the matching valid-reply count |
| Never faced a closing shove | Closing is a distinct key, but the backoff can borrow other fold/call contexts or use a uniform law | Returns incumbent when the closing situation has zero exact evidence |
| Unseen wager size | A different size bucket has no cell, and a size inside the same bucket can reuse the bucket counts | Requires the same reduced collectible-price-to-matched-pot ratio |
| Different stack depth or SPR | A bucket boundary changes the cell. Depth edges are 10, 30 and 100 bb, and SPR edges are 1, 3 and 8 | Falls back across boundaries and shares support within the existing buckets |
| Conditional reply currently illegal | Exact legal menu is part of the cell and prior keys. Only legal classes enter the normalization | Preserves the same legal menu, including fold/call-only closing states |
| Legacy pooled profile with absent V2 | A separately created empty V2 would yield uniform legal mass. The Phase 5E forecast expects a V2 object | Accepts absent evidence and calls the existing incumbent provider |

The new offline adapter indexes matching opportunities and valid replies alongside the original V2 profile. It reuses V2's settled-history validation and stable hand IDs before touching its index. Eligible replies exclude fallbacks and missing or invalid responses. A pre-existing bucket-only profile needs its original histories to populate the exact-ratio index. At 20 matching replies the hybrid delegates to the original V2 cell estimate. It reuses the bucket estimate when multiple supported ratios coexist within a bucket. The exact-ratio check affects selection only. The incumbent callable supplies its original distribution unchanged on fallback. Short calls use the collectible price and leave excess chips to the existing settlement and independent cash ledger. The adapter operates on public replay evidence and runs offline. [Adapter](backend/research/holdem/profile_v2_hybrid.py) · [Aggregation](backend/research/holdem/opponent_profile_v2.py) · [Independent ledger](backend/research/holdem/action_ev_reference.py)

## Phase 5E reconstruction

The archive rerun reproduced all 256 decisions and all A, B and oracle concrete action values within 1e-12 bb and their selected actions exactly. The historical decision-weighted MAE was **0.326 / 0.404 / 0.197 / 0.000 bb** for A / B / C / D. B increased error by 0.078 bb. C reduced error by 0.129 bb versus A (paired 95% interval −0.147 to −0.111). The archive was excluded from the fresh gate.

| Archived pricing slice | Actions | MAE A / B / C / D, bb |
| --- | ---: | --- |
| Prices present in the training schedule | 256 | 1.050 / 0.531 / 0.274 / 0 |
| Other prices | 384 | 0.604 / 1.261 / 0.604 / 0 |
| Full evidence-key match | 224 | 1.034 / 0.147 / 0.147 / 0 |
| No full evidence-key match | 416 | 0.647 / 1.411 / 0.647 / 0 |
| No future reply | 384 | 0 / 0 / 0 / 0 |

The 32-action difference between the scheduled-price and exact-support splits came from legal-menu mismatch. At 625 chips the bounded tree had fold, call and shove, while public replay at that price also allowed an ordinary raise. The V2 bucket itself carries the legal menu. The schedule's price match therefore overstated support. The exact-supported B and C estimates are identical. Changing only the unsupported forecast restores the incumbent EV, which isolates the degradation to unsupported probability assignment. Valid replay counts, legal normalization, range and the payoff-to-choice code stayed common. Smoothing contributes a small prior to supported estimates and can dominate sparse cells. The larger archival loss came from substituting an entire street/menu or uniform distribution at zero support.

The largest archived error increase was a 625-chip overbet with 7♦ K♥ on 9♥ 7♥ A♥ J♥ 5♠. The checked-to river had a 500-chip pot and 1,250/2,250 chips behind. Small-family cluster 0, member 0 had 32 folds and 118 calls at 125, and 98 folds and 52 calls at 250. The 625 overbet had zero relevant opportunities. Its responder could fold, call or shove. A and C assigned 43.23% / 56.44% / 0.33% to those classes, B assigned one third each, and the oracle assigned 40% / 60% / 0%. The resulting EV was **+8.480 / +3.327 / +8.480 / +8.739 bb**. The hybrid used the incumbent and all four arms chose the all-in. The 5.153 bb added valuation error recurred for the paired member with the swapped 125/250 counts. The archive retains the ranked witnesses with public states, counts, probabilities, values and choices.

The separate Phase 5D row 31 closing-call witness remains an incoming-range error. The estimate was +7.364 bb and the oracle value was −20.920 bb. The call ends betting, leaving no future opponent reply to substitute. [Archived reconstruction](benchmark-results/phase-5f-2026-11-20/archive.json) · [Phase 5E report](PHASE_5E_REPORT.md)

## Fresh holdout

The fresh sample comprised 24 training clusters, 48 synthetic opponent profiles with 300 hands each, and 576 evaluation decisions. The forecasts were A (incumbent pooled), B (pure V2), C (hybrid), and D (oracle). There were 1,152 scripted reply scores and 1,920 counterfactual wager-menu reply scores. The two panels can share geometries and deals. Both hash seeds produced byte-identical canonical results, including the reversed cluster order in seed 31. SHA-256 for each result is `bf42cfecfbccffc2d68a2dc859132e3de8722a0446288bf9d07fc2fcb31ddd02`. [Frozen sources](benchmark-results/phase-5f-2026-11-20/frozen.json) · [Summary and paired intervals](benchmark-results/phase-5f-2026-11-20/summary.json)

### Reply forecasts

| Slice | Scored | C uses V2 | Brier A / B / C / D | Log loss A / B / C / D |
| --- | ---: | ---: | --- | --- |
| All replies | 3,072 | 1,216 | .575 / .541 / .545 / .437 | .863 / .827 / .813 / .652 |
| Supported | 1,216 | 1,216 | .497 / .421 / .421 / .424 | .781 / .654 / .654 / .656 |
| Sparse | 304 | 0 | .809 / .585 / .809 / .418 | 1.207 / .881 / 1.207 / .643 |
| Unsupported | 1,552 | 0 | .591 / .627 / .591 / .452 | .859 / .951 / .859 / .651 |
| Closing shove | 528 | 160 | .521 / .469 / .498 / .451 | .719 / .660 / .695 / .643 |

C used the incumbent on **1,856/3,072** replies. It reduced realized Brier by 0.030 (paired 95% CI −0.037 to −0.023) and log loss by 0.050 (−0.058 to −0.042) versus A. B reduced Brier by 0.034 (−0.048 to −0.021) and log loss by 0.036 (−0.066 to −0.007). Expected Brier A/B/C/D was .580/.544/.556/.450 and expected log loss was .865/.829/.823/.668. Finite realized samples account for the small supported-slice reversal relative to oracle scores.

| Oracle probability MAE, percentage points | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| Fold | 16.77 | 10.57 | 13.87 | 0 |
| Call | 19.66 | 14.48 | 15.89 | 0 |
| Raise | 3.89 | 3.28 | 2.31 | 0 |
| Shove | 3.73 | 5.09 | 2.22 | 0 |
| Closing shove fold | 17.03 | 9.25 | 14.62 | 0 |

Modal closing reply accuracy was 55.7% / 48.5% / 61.7% / 66.3%. For calibration by collectible wager, the price is relative to a 500-chip matched pot. Mean fold rates can cancel errors across the swapped opponent pair. The individual probability scores above measure those errors directly.

| Wager, chips | Scored | C uses V2 | Observed fold | Forecast fold A / B / C / D |
| --- | ---: | ---: | ---: | --- |
| 125 | 816 | 480 | 36.0% | 37.5% / 37.8% / 37.6% / 36.6% |
| 250 | 528 | 160 | 37.5% | 39.5% / 38.9% / 39.6% / 40.9% |
| 500 | 672 | 320 | 36.6% | 37.5% / 38.7% / 37.6% / 36.6% |
| 625 | 528 | 96 | 42.6% | 41.4% / 37.5% / 41.5% / 43.4% |
| 1,250 | 528 | 160 | 41.7% | 42.7% / 48.7% / 42.6% / 41.6% |

The sparse slice had five replies in the relevant cell and 295 at the other scripted context. B scored better there, and C inherited the often inaccurate incumbent in this deliberately imbalanced exposure mix. The data establish a cost of the frozen conservative selection under these laws. Threshold and smoothing remained frozen. [Reply rows, per-price and coverage metrics](benchmark-results/phase-5f-2026-11-20/summary.json)

### Action values and recommendation harm

All arms saw the same blocker-compatible uniform range, pot, legal targets, board, exact terminal cash ledger and Hero continuation. The oracle changed only future opponent replies. Every model evaluated all 2,688 concrete actions. The 192 closing-call controls have identical estimates because the call closes betting.

| Metric | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| Decision-weighted MAE, bb | .588 | .675 | .529 | 0 |
| Action-weighted MAE, bb | .756 | .868 | .680 | 0 |
| Mean signed error, bb per decision | −.122 | −.384 | −.120 | 0 |
| Material action pairs ranked correctly, of 5,936 | 4,877 | 4,426 | 5,024 | 5,936 |
| False positive aggressive advantages | 146 | 61 | 130 | 0 |
| Mean regret, bb | .250 | .164 | .197 | 0 |
| Worst absolute regret, bb | 2.819 | 2.819 | 2.819 | 0 |
| Profitable bluffs selected, of 227 decisions offering one | 173 | 179 | 178 | 216 |
| Unprofitable bluffs selected | 19 | 13 | 14 | 0 |
| Profitable closing calls taken, of 120 | 120 | 120 | 120 | 120 |
| Unprofitable closing calls declined, of 72 | 72 | 72 | 72 | 72 |
| Unprofitable shoves detected, of 183 | 154 | 165 | 153 | 183 |

C minus A in per-decision MAE was **−0.059 bb** (paired 95% CI **−0.062 to −0.056**). B minus A was **+0.087 bb** (**+0.037 to +0.137**). On the 384 checked-to decisions C lowered MAE from .882 to .794 bb, a descriptive 0.088 bb improvement. C reduced mean regret by .053 bb (95% CI −.060 to −.046), while B reduced it by .085 bb (−.103 to −.067). The arms can rank the top action differently even when a model's value errors are smaller across the full menu.

| Wager action stratum | Actions | MAE A / B / C / D, bb |
| --- | ---: | --- |
| Supported | 448 | .573 / .119 / .119 / 0 |
| Sparse | 112 | 2.096 / .901 / 2.096 / 0 |
| Unsupported | 1,360 | 1.133 / 1.601 / 1.133 / 0 |
| No future reply | 768 | 0 / 0 / 0 / 0 |

C used V2 on 448/1,920 future-reply wagers and the incumbent on 1,472. Every sparse and unsupported forecast and its associated root wager EV matched A exactly. Across the closing, large, river-aggression and small families the hybrid lowered decision-weighted MAE by .061, .041, .070 and .064 bb respectively. The supported gain was diluted by the frequency of fallback and closing controls. The evidence applies to the four synthetic response families, whose laws depend only on public context.

C changed 35 recommendations versus A. One change was harmful. Holding 2♦ 3♣ on 4♥ 7♦ 7♥ J♦ 5♣ with a 500-chip pot and 1,250/2,250 behind, A chose 125, B and D chose 125, and C chose 250. The 125 cell had 41 folds and 109 calls in 150 opportunities, leading C to use V2 for that bet. It estimated +0.481 bb versus A's +1.606 and D's +0.276. The 250 cell had zero opportunities, so C retained A's +0.929 bb forecast versus B's −0.422 and D's +0.229. Improved pricing of the supported bet exposed a small overestimate in the unsupported alternative. The switch gave up 0.047 bb. The sole failed numerical gate was the 0.10 bb primary materiality threshold. [Exact holdout rows](benchmark-results/phase-5f-2026-11-20/holdout-13.json) · [Action slices and downside witnesses](benchmark-results/phase-5f-2026-11-20/summary.json)

## Observer reliability

The existing observer ran on archived Coach rows 78 and 31 plus quarter-pot and pot controls. Each worker ran three enabled calls and one disabled call per case with a private store and trace directory. The isolated process completed 12/12 enabled traces and the four simultaneous processes completed 48/48. All 80 Coach calls returned legal CFR advice, with zero unexpected fallbacks and identical paired public advice. All normalized CFR mixes were within 1e-12 of one. No observer errors or timeouts occurred. Both measured workloads passed the frozen 15 s Coach and 150 ms observer limits.

| Segment | Isolated first / median / p95 / max | Four workers first / median / p95 / max |
| --- | --- | --- |
| Enabled Coach calls, s | 3.903 / 1.699 / 5.235 / 5.235 | 4.079 / 2.319 / 4.079 / 4.324 |
| First call per case, s | 3.903 / 2.733 / 5.235 / 5.235 | 4.079 / 2.700 / 4.174 / 4.174 |
| Repeat calls, s | 2.127 / 1.444 / 2.149 / 2.149 | 2.459 / 1.790 / 3.717 / 4.324 |
| CFR, s | 2.864 / 1.684 / 4.249 / 4.249 | 3.406 / 2.224 / 3.491 / 4.247 |
| Observer capture, ms | 9.10 / 2.45 / 9.63 / 9.63 | 4.10 / 3.69 / 7.20 / 18.05 |
| Shadow pricing and diagnostics, ms | 6.27 / 1.86 / 6.27 / 6.27 | 5.57 / 3.60 / 10.80 / 41.16 |
| Observer before trace write, ms | 16.37 / 4.97 / 16.37 / 16.37 | 10.01 / 7.90 / 29.44 / 52.15 |
| Trace write, ms | 6.27 / 3.05 / 6.27 / 6.27 | 4.74 / 5.26 / 15.82 / 37.85 |

Cold worker imports took 0.573 s isolated and 0.798–0.843 s with four workers. A separate one-hand SQLite incumbent replay took 3.39 ms median isolated, with 2.52–5.26 ms worker medians under concurrency. The archived probes used prebuilt profile snapshots. Peak worker working set was 262.8 MiB over both runs. Four simultaneous workers increased median observer and trace-write time, with the widest tail in pricing and output. CFR remained the largest part of end-to-end advice.

The deadline is the earlier of 150 ms after observer entry and 15 s after Coach advice starts. CFR and scheduler contention can consume that headroom. Trace I/O occurs after the compute checks, and the deadline checks are cooperative. Forced error, timeout and trace-write tests exercise failure isolation. The measured four-worker workload passed. Saturated contention of the kind that produced 27 Phase 5D deadlines remains unverified, and the cooperative observer offers no hard elapsed-time guarantee during scheduler or filesystem stalls. [Isolated observer](benchmark-results/phase-5f-2026-11-20/observer-isolated/results.json) · [Four-worker observer](benchmark-results/phase-5f-2026-11-20/observer-concurrent/results.json)

In a separate 300-hand Python allocation probe, peak allocations above the prepared histories were 12.1 KiB for the incumbent, 200.7 KiB for V2 and 228.1 KiB for indexed V2. The exact support index added a measured 27.4 KiB in this fixture, which uses only two live wager ratios. The source-ID index grows with hands, and the coverage index grows with distinct observed keys. Supported hybrid lookup took 19.3 µs median, 46.2 µs p95 and 11.08 ms max versus 5.9 µs, 16.2 µs and 5.76 ms for its incumbent comparison. Unsupported hybrid lookup including its incumbent call took 10.5 µs median, 15.0 µs p95 and 0.98 ms max. Interpreter scheduling affects the microbenchmark maxima. [Allocation and lookup probe](benchmark-results/phase-5f-2026-11-20/profile-memory.json)

## Phase 5G direction

Run one targeted research repair focused on observation coverage. Collect legally observed replies at underrepresented wager ratios and matched public situations, then test the same selector and threshold on an independent time- or opponent-separated panel with realistic missingness. Compare the original and expanded coverage at fixed holdout states. Require at least 0.10 bb lower decision-weighted MAE than the incumbent with the paired 95% upper endpoint below zero, exact fallback, a mean regret increase of at most 0.05 bb, no switch adding 8 bb or more, and both measured reliability gates. Keep the frozen candidate offline until a later study clears those gates.

## Reproduction

From the backend directory, use the project virtual environment and set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1. Choose an empty output directory beside the Phase 5E archive. Run the study and observer as follows.

```text
python -m research.holdem.phase_5f development OUT
python -m research.holdem.phase_5f archive OUT
python -m research.holdem.phase_5f freeze OUT
python -m research.holdem.phase_5f holdout OUT
python -m research.holdem.phase_5f holdout OUT --reverse
python -m research.holdem.phase_5f_observer OUT
python -m research.holdem.phase_5f memory OUT
python -m research.holdem.phase_5f_summary OUT
```

Set `PYTHONHASHSEED=13` for the first holdout and 31 for the reverse run. Run the observer batches without concurrent verification jobs. The summary checks the freeze manifest, exact hash parity and the archived EV comparison before reporting the gates.

| Offline holdout segment | Seed 13 first / median / p95 / max | Seed 31 first / median / p95 / max |
| --- | --- | --- |
| Public training replay, ms per hand | 1.52 / 3.52 / 11.55 / 259.62 | 3.62 / 5.09 / 32.46 / 928.61 |
| Indexed V2 aggregation, ms per hand | .96 / .79 / 2.83 / 246.44 | .53 / .67 / 9.14 / 863.73 |
| Four forecasts, µs per evaluator node | 162 / 56 / 283 / 12,326 | 129 / 53 / 268 / 197,856 |
| Bounded action-EV evaluation, s per deal | .116 / .087 / .181 / 1.572 | .045 / .144 / 2.066 / 6.649 |

The study workers ran alongside verification jobs. Their timing tails reflect shared machine load. Peak working set was 76.9 MiB for seed 13 and 77.5 MiB for seed 31. Both workers met the 15 s exact-evaluation and 768 MiB limits. [Seed 13 timing](benchmark-results/phase-5f-2026-11-20/holdout-13-timing.json) · [Seed 31 timing](benchmark-results/phase-5f-2026-11-20/holdout-31-timing.json)

## Verification and Git status

- The full backend regression passed **1,077/1,077 tests** in nine disjoint groups, including all 256 research tests. Collection kept all 1,064 Phase 5E test IDs. The passing run took 1,079.5 s wall time. Windows loopback enabled existing FastAPI TestClient calls after the restricted socket path stalled. The groups reported existing Pyparsing and Starlette deprecation warnings. [Full regression results](benchmark-results/phase-5f-2026-11-20/verified/socket-backend-summary.json) · [Collected test IDs](benchmark-results/phase-5f-2026-11-20/verified/collected.txt)
- The 13 new regression cases cover supported and unseen closing shoves, unseen small bets and overbets inside occupied buckets, 1/19/20 matching replies, legacy profiles, eligible responses missing from history, legal action masks, position/depth/SPR shifts, short-call refunds, repeated imports and hidden holdings. The focused runs passed 21 tests under hash seed 13 and 29 under hash seed 31. The latter includes forced observer failures and unchanged advice. [Seed 13](benchmark-results/phase-5f-2026-11-20/focused-13.txt) · [Seed 31](benchmark-results/phase-5f-2026-11-20/focused-31.txt)
- The offline API smoke verified Coach, Match, single Replay and Match Replay across six combinations of shadow unset/off/on and the persistent flags off/on. Public outputs agreed within each persistence mode. The smoke verified legal advice, conserved chips, zero unexpected fallbacks, default-disabled tracing and unchanged Python and NumPy RNG state. The frontend production build, Coach strategy rendering test and Vite rendering of all four screens and Replay events passed. The dependency check found no broken requirements. [API smoke](benchmark-results/phase-5f-2026-11-20/api-smoke-loopback.txt) · [Frontend build](benchmark-results/phase-5f-2026-11-20/frontend-build.txt) · [Coach rendering test](benchmark-results/phase-5f-2026-11-20/frontend-coach.txt) · [Frontend Replay smoke](benchmark-results/phase-5f-2026-11-20/frontend-match-replay.txt) · [Dependencies](benchmark-results/phase-5f-2026-11-20/pip-check.txt)
- Work remained on `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. The tracked diff matched entry byte for byte. The status delta consists of the protocol, report, adapter, three offline study modules and focused regressions. Production Coach and Match code, research defaults and the historical fixtures stayed as found. Git's whitespace check passed with the existing CRLF advisory for `backend/test_poker.py`. The freeze manifest still matches the working sources. [Final Git status](benchmark-results/phase-5f-2026-11-20/final-status.txt) · [Status delta](benchmark-results/phase-5f-2026-11-20/status-delta.txt) · [Whitespace check](benchmark-results/phase-5f-2026-11-20/git-diff-check.txt) · [Final manifest check](benchmark-results/phase-5f-2026-11-20/final-manifest.txt)
