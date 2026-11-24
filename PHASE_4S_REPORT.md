# Phase 4S — Persistent range support and closing-river decisions

**PHASE 4S NOT COMPLETE — promotion gates failed.** The bounded research replay repaired the archived range collapse and passed the frozen replay time and memory gates. Architecture alone was EV-neutral within measurement error. The combined policy gained +0.817 bb per independent decision, with a 95% interval of [+0.128, +1.786] bb. Its 1.315 bb loss on a profitable closing call exceeded the 0.50 bb downside limit. Production remains on the incumbent.

## Range ownership and root cause

Coach validates and replays public actions, actual chip targets and the board prefix through the hand engine. The solver reconstructs the path, starts both public seat reaches at unit weight, and multiplies the acting seat's reach by chart likelihood at each preflop step. Stack-depth and raise-size abstraction affect those likelihoods. At each postflop street the board mask removes blocked columns from both public reaches. CFR also enforces pairwise card compatibility. Actual Hero cards condition the displayed opponent range and identify the decision column.

The incumbent `_solve` selects columns above 0.5% of the largest board-legal reach. For each observed action, `_apply_strategy` allocates a zero vector and writes updated reach only on those columns. This turns an unevaluated likelihood into zero posterior support. The vector is used for the next observation, street and any current-state re-solve after off-menu mapping. Production range normalization happens in the report and conditional EV calculation. Both operations preserve zeros introduced by pruning. When the next board blocks the final working column, a new solve can raise `ReplayError: empty range`. The expert fallback can still give legal advice. [Coach replay](backend/coach/service.py) · [Incumbent replay and solver interface](backend/solver/bot.py) · [CFR](backend/solver/cfr.py)

The research adapter keeps public reach in global combo order. Each solve receives a temporary projection with a maximum of 896 columns per seat, an explicit column mapping and a retained/omitted mass ledger. It uses the relative cutoff, stable ordering and mandatory actual Hero and compatible opponent coverage. Observations update evaluated holdings with their own likelihoods. Unevaluated holdings share the reach-weighted action likelihood among the evaluated holdings and retain their relative odds. Board-blocked holdings stay at zero. A contradictory observation with no positive donor likelihood or a genuinely unsupported range triggers the existing legal fallback with a research reason. The adapter is isolated in offline research. [Frozen protocol](PHASE_4S_PROTOCOL.md) · [Research adapter](backend/research/holdem/range_support.py)

The projection changes the numerical game that CFR solves. The pooled likelihood additionally changes inference in the omitted tail. A larger set of positive holdings therefore establishes support integrity, while its weights and action forecasts still require validation. The adapter carries unnormalized float64 reach and rescales very small common magnitudes. It inherits the incumbent's float32 CFR products and can still lose extreme relative weights below representable range. The scoped Coach adapter recomputes projected street solves when the spot is replayed or edited under the same hand ID. It continues to reuse the board equity cache.

## Archived collapse and severe calls

The original Phase 4Q turn solve reduced 1,119 positive public Villain holdings to 6s 7s. River 6s removed it and the incumbent fell back. B also used one Villain column at the turn, with **29.68%** of persistent public mass outside that working set. The persistent range carried 1,128 public combinations through the turn and 1,081 into the river solve after the reveal. All 990 Hero-compatible combinations had positive weight after the shove. B produced normalized advice and D removed its small remaining cover allocation. The legal 6s blocker still removed 6s 7s.

| Archive | Exact EV of cover (bb) | A EV | B EV | C EV | D EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase 4Q collapse, 3c 5c | −3.863 | 0 (fallback) | −0.001 | 0 (fallback) | 0 |
| Js 3c | −18.720 | −0.044 | −0.033 | 0 | 0 |
| Kc As | −24.716 | −7.897 | −6.611 | 0 | 0 |

The −18.720 and −24.715 bb losses in earlier phases came from different counterfactual model inputs. The table evaluates the four actual Phase 4S policies against the archived truth. It retains those distinctions. C/D remove residual cover mass on both severe fixtures, and both sensitivity envelopes miss the true cover EV on those two fixtures. The original 18.72 bb miss required an exact incoming prior combined with the incumbent likelihood. The 24.715 bb loss was an adjustment under the Phase 4Q likelihood, which made a harmful cover preferable on a fixed production prior. [Exact archive results](benchmark-results/phase-4s-2026-11-18/historical-final.json) · [Phase 4Q](PHASE_4Q_REPORT.md) · [Phase 4P](PHASE_4P_REPORT.md)

Applying the same envelope directly to the two archived bad counterfactual posteriors changes nominal cover EVs of +1.056 and +7.958 bb to lower bounds of −8.052 and −2.281 bb. The frozen rule would suppress both covers. Their true EVs remain below those bounds. This distinguishes useful action filtering from faithful uncertainty coverage.

## Closing-call policy

For a river fold/cover decision the cover pays minus its price if Hero loses, the matched pot less the price if Hero wins, and the seat's split share less the price on a tie. Refunded overhang is excluded. Both actions end the betting. Use exact river showdown ordering on the relevant nominal modeled posterior and allow every positive weight to vary by an odds multiplier between 1 and 2 before renormalization. The envelope is sharp over this set. Within the three showdown outcome groups, its endpoints are attained by putting the maximum multiplier on a contiguous lower or upper tail of outcomes. When lower-bound cover EV is nonpositive, restrict the mixed policy to folding. When the lower endpoint is positive, retain the parent policy, including its cover allocation. Apply the same seeded chooser and leave the parent fallback intact. Fixed odds sensitivity is descriptive. Coverage of the independent reference measures how often the particular set contains the true payoff. Sparse profiles and missing support can both produce large miscalibration even when the posterior is broad.

## Timing and allocation

On the final development board with a 100-hand prefix, cache-cold replay took 10.92 s for A and 9.88 s for B. Cache-warm replay took 7.38 s and 6.66 s. These are individual traces measured with other verification jobs running. Separate process resident peaks were 103.45 and 87.00 MiB. The warm profiler attributed 7.66/7.62 s to 210 CFR iterations and 1.28/1.05 s within those iterations to terminal values. Board filtering and working-set construction each took about 0.01 s in B. Reach application, copying and conditional normalization each took under 0.01 s. The replay reconstruction calls took under 0.01 s. Cold replay also pays for full board equity preparation before the bounded solves. Warm `_full_equity` calls took under 0.01 s in the profiler.

The projection reduces per-solve pair-matrix width and retains only the policy from earlier streets. The current street keeps the solver matrices for the EV report. The shared equity cache still materializes board-legal pair matrices and is bounded at 12 entries. At 896×896 four dense float32 solver matrices alone occupy about 12.3 MiB, before temporaries, policies and the cached full equity. Reworking per-action copying would yield little improvement at this scale. [A profile](benchmark-results/phase-4s-2026-11-18/profile-A.json) · [B profile](benchmark-results/phase-4s-2026-11-18/profile-B.json)

## Independent exact river EV

The 95-file hash manifest froze the implementation, executable inputs and protocol. The holdout crossed eight deal boards, three independent training streams and four fixed opponent styles. It used 96 decisions, 64 facing a closing shove. Starting depths were 9, 15 and 30 bb. Profiles used 0, 3, 30 and 100 prior public hands, with the closing subset covering 0, 30 and 100. Both full replays independently matched all 96 rows and statistical outputs across hash seeds 13 and 31. Both had zero unexpected fallbacks. The evaluator applies the same reference wagering and continuation laws to all arms, checks exact conditional weights against independent Bayesian enumeration and checks terminal values against a separate completed betting-tree traversal. Each replay verifies chip conservation, legal advice, unique concrete action targets, and finite normalized strategy and reach. [Frozen inputs and schedule](benchmark-results/phase-4s-2026-11-18/frozen-final.json) · [Seed 13](benchmark-results/phase-4s-2026-11-18/holdout-13.json) · [Seed 31](benchmark-results/phase-4s-2026-11-18/holdout-31.json) · [Reproducibility](benchmark-results/phase-4s-2026-11-18/determinism.json)

| Arm | Mean EV (bb) | Mean regret (bb) | Closing cover probability | Seeded covers |
| --- | ---: | ---: | ---: | ---: |
| A — incumbent | −1.539 | 2.199 | 31.33% | 15/64 |
| B — architecture | −1.539 | 2.198 | 31.23% | 15/64 |
| C — uncertainty | −0.723 | 1.382 | 12.42% | 7/64 |
| D — combined | −0.722 | 1.382 | 12.42% | 7/64 |

| Contrast | Mean (bb/decision) | Crossed 95% interval | Losses >0.01 bb | Sum of negative changes (bb) | Worst change (bb) |
| --- | ---: | --- | ---: | ---: | ---: |
| B − A | +0.0004 | [−0.0061, +0.0077] | 6/96 (6.25%) | −0.248 | −0.152 |
| C − A | +0.8162 | [+0.1282, +1.7857] | 1/96 (1.04%) | −1.315 | **−1.315** |
| D − A | +0.8170 | [+0.1283, +1.7865] | 1/96 (1.04%) | −1.316 | **−1.315** |
| D − B | +0.8166 | [+0.1288, +1.7862] | 1/96 (1.04%) | −1.315 | −1.315 |
| Interaction | +0.0004 | [−0.0076, +0.0065] | 2/96 (2.08%) | −0.213 | −0.184 |

The per-style mean changes against A all cleared the −0.03 bb floor.

| Opponent | B − A | C − A | D − A |
| --- | ---: | ---: | ---: |
| Tight-passive | +0.002 | +0.600 | +0.603 |
| Loose-passive | +0.007 | +1.164 | +1.164 |
| Tight-aggressive | −0.006 | +0.506 | +0.506 |
| Loose-aggressive | −0.001 | +0.994 | +0.994 |

The 16-decision development panel also showed a small architecture effect (+0.0006 bb) and a positive combined effect (+0.5809 bb). The independent B range contained 990 Hero-compatible holdings per decision, compared with 529.6 for A. Its effective size averaged 237.7, compared with 234.2 for A. B's solved subset averaged 505.7 positive holdings and omitted 49.68% of the reference posterior mass. A's solved subset omitted 45.19%. These are fractions under the independent truth, which can give large mass to holdings of low modeled reach. B's **public modeled** omitted mass per solve had medians of 0.75%, 0.73% and 1.07% on flop, turn and river, with median working widths of 596, 358 and 277. The architecture reliably preserved support while leaving the nominal EV of the incumbent policy close to its baseline. [Development evidence](benchmark-results/phase-4s-2026-11-18/development-final.json)

B's worst case increased cover probability from 1.99% to 3.66% for Tc 3h on 5s 5d 8s 6d Qh against tight-aggressive, 15 bb, stream 172, with exact cover EV of −9.109 bb. The increase cost 0.152 bb. Under C and D, the sensitivity rule restricted 55 closing decisions to fold, 53 with negative exact cover EV and two with positive exact cover EV. The largest benefit was +19.497 bb on Jd 4h against loose-passive at 30 bb. [Row-level cases and exact action values](benchmark-results/phase-4s-2026-11-18/holdout-13.json)

**Severe fresh failure.** Jd 4h on 2d 5h Kc Qd Js, 9 bb, loose-aggressive, stream 172, 30 public prior hands. A and B assigned more than 99.998% to covering, which was worth +1.3152 bb. C's interval was [−0.081, +5.780] bb. D's was [−0.556, +5.277] bb. Both covered the true EV and both caused a fold, costing 1.3152 bb. Maximizing the worst case can give up profitable calls even when the interval contains the truth.

Coverage was 15/64 for C and 19/64 for D. By prefix 0, 30 and 100, the counts were 2/24, 5/16 and 8/24 for C and 3/24, 8/16 and 8/24 for D. Closing coverage at the three-hand prefix was measured only on the archived collapse. The four styles are fixed synthetic references, with only eight independent boards and three independent profile streams. This experiment identifies conditional exact EV under those reference laws. [Full holdout rows](benchmark-results/phase-4s-2026-11-18/holdout-13.json)

A diagnostic on the first nonclosing geometry paired all four styles and substituted exact reply laws while holding the exact incoming posterior and Hero continuation fixed. Swapping those replies changed action EV by as much as 13.584 bb in either architecture, with a mean grouped reply excess Brier score of 0.593. This is a four-style diagnostic on one board. Closing calls have no equivalent response term. [Response diagnostic](benchmark-results/phase-4s-2026-11-18/response-profile.json)

## Frozen promotion gates

| Gate | B | C | D |
| --- | --- | --- | --- |
| Mean at least +0.05 bb and 95% lower bound above zero | Fail | Pass | Pass |
| Worst loss at most 0.50 bb | Pass | Fail | Fail |
| At most 10% harmful adjustments over 0.01 bb | Pass | Pass | Pass |
| Every opponent mean at least −0.03 bb | Pass | Pass | Pass |
| Zero unexpected fallbacks and valid exact-scoring checks | Pass | Pass | Pass |
| Warm replay median at most 2× A and max at most 15 s, both seeds | Pass | Pass | Pass |
| Runner peak resident memory at most 768 MiB, both seeds | Pass | Pass | Pass |

| Arm | Seed 13 median / max (s) | Seed 31 median / max (s) |
| --- | ---: | ---: |
| A | 1.889 / 9.934 | 1.877 / 10.327 |
| B | 1.900 / 14.744 | 1.814 / 14.666 |
| C | 1.890 / 9.934 | 1.878 / 10.327 |
| D | 1.901 / 14.745 | 1.814 / 14.666 |

Combined peak process memory was 290.0 and 290.2 MiB. Holdout wall times were 561 and 562 s within the 1,200 s process bound. On seed 13 the added decision pass took a median 0.50 ms for C and 0.36 ms for D. B and D passed the cap with limited headroom. Their slowest seed-13 decision was a 30 bb three-bet pot facing a nonclosing river wager against loose-aggressive. A separate spot check of that slow key measured 6.26 s cold and 3.21 s warm for B, and 6.41 s cold and 3.97 s warm for A. The frozen holdout measured warm board equity. The cold checks cover two cases. [Slow-key cold rerun](benchmark-results/phase-4s-2026-11-18/slow-key-cold.json)

Production Coach and Match retain the incumbent. Phase 4T should focus on architecture redesign. Give replay a separately validated likelihood interface that can update the full legal posterior without depending on which hands the decision solve evaluated. Test it against small full-support oracle cases and report errors in the hand-by-size likelihood and profitable closing calls. Then hold the posterior fixed while profiling selected-column terminal kernels and earlier-street policy-only solves, where Phase 4S spent most of its runtime. This would let inference calibration and compute budgets be evaluated independently. Gameplay validation and production integration remain gated by a candidate that clears both exact-EV and downside criteria.

## Verification and Git

- The focused Phase 4S suite passed 18 tests under each of hash seeds 13 and 31. It covers the exact collapse, board blockers, compatible donor reservation, pooled likelihoods for checks and aggressive actions, contradictory and narrow support, legal advice, edited and repeated replays, and exact incumbent parity on an unaffected preflop replay. [Seed 13 focused log](benchmark-results/phase-4s-2026-11-18/focused-4s.txt) · [Seed 31](benchmark-results/phase-4s-2026-11-18/focused-4s-31.txt)
- All 171 research regressions passed in 613.33 s. The 31 Coach API and explanation tests passed in 16.95 s with local loopback access. The frontend production build, Coach solver/fallback render test and backend dependency check passed. No external poker service was used. [Research regression](benchmark-results/phase-4s-2026-11-18/research-tests.txt) · [Coach API](benchmark-results/phase-4s-2026-11-18/coach-loopback.txt) · [Frontend build](benchmark-results/phase-4s-2026-11-18/frontend-build.txt) · [Coach frontend](benchmark-results/phase-4s-2026-11-18/frontend-coach.txt)
- The full backend suite passed all 992 tests in 1,738.58 s with eight existing dependency deprecation warnings. This retains all 974 prior tests and adds 18 focused cases. The default sandbox attempts stalled at the API boundary. The loopback-capable run completed successfully. [Full backend regression](benchmark-results/phase-4s-2026-11-18/backend-loopback.txt)
- The 28 Phase 4Q and 93 Phase 4R frozen input hashes match. Git is on `main`, at `3e89367`, 19 commits ahead of local `origin/main`. The only status additions are this report, the protocol, two research modules and a test file. Prior uncommitted work was preserved. `git diff --check` and new-file trailing-whitespace checks passed. Git reported its existing LF/CRLF conversion advisory for `backend/test_poker.py`. [Git status](benchmark-results/phase-4s-2026-11-18/final-status.txt)

## Reproduction

From `backend` with the local virtual environment and a new output directory:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$phase4sPython = '.\.venv\Scripts\python.exe'
$phase4sEvidence = '../benchmark-results/phase-4s-2026-11-18'
$phase4sOut = '../benchmark-results/phase-4s-reproduction'
$phase4sBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:], timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phase4sOut
foreach ($phase4sHash in '13', '31') {
    $env:PYTHONHASHSEED = $phase4sHash
    & $phase4sPython -c $phase4sBound 1200 $phase4sPython -m research.holdem.phase_4s holdout "$phase4sOut/holdout-$phase4sHash.json" --manifest "$phase4sEvidence/frozen-final.json"
}
& $phase4sPython -c $phase4sBound 300 $phase4sPython -m research.holdem.phase_4s development "$phase4sOut/development.json"
& $phase4sPython -c $phase4sBound 120 $phase4sPython -m research.holdem.phase_4s historical "$phase4sOut/historical.json" --archive '../benchmark-results/phase-4q-2026-11-18'
& $phase4sPython -m research.holdem.phase_4s profile-A "$phase4sOut/profile-A.json"
& $phase4sPython -m research.holdem.phase_4s profile-B "$phase4sOut/profile-B.json"
& $phase4sPython -m pytest -q -p no:cacheprovider
```

The backend API tests require loopback-capable execution. In the frontend directory, run `npm.cmd run build` and `node --test test/coach-strategy.test.mjs`.
