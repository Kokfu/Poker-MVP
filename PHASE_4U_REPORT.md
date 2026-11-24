# Phase 4U — Independent reply forecasting and robust strategy adjustment

**PHASE 4U NOT COMPLETE — promotion rejected.** Across 96 fresh paired river decisions, independent forecasting with the incremental-EV gate gained **+0.733 bb per decision** versus the incumbent. The crossed 95% interval was **[+0.025, +1.843] bb**. The worst accepted adjustment lost **2.347 bb**, exceeding the frozen **0.50 bb** limit. The gate preserved profitable closing-call mass and rejected the largest losses proposed by the ungated model. Three harmful adjustments still passed it. Coach and Match continue to use the existing strategy. [Frozen protocol](PHASE_4U_PROTOCOL.md) · [Holdout rows and gates](benchmark-results/phase-4u-2026-11-18/holdout-13.json)

## Pipeline audit

1. **Observed action.** Coach validates the public action line, cards, stacks and total targets with the hand engine. Incumbent replay starts both ranges from the preflop chart. It maps each observed postflop action to a street solve and uses the actor's solved action probability as the likelihood for that holding. Phase 4T instead applies a hand-dependent likelihood at the actual public state and street prefix to board-legal posterior weights in global combo order. Board blockers and Hero card compatibility condition the decision. The resulting persistent range is computed before projection into CFR columns. [Coach](backend/coach/service.py) · [Solver replay](backend/solver/bot.py) · [Persistent inference](backend/research/holdem/decoupled_replay.py)
2. **Hypothetical reply.** At each proposed Hero bet, raise or shove, incumbent and Phase 4T read the opposing strategy at the resulting tree node from the final locked DCFR policy. Regret matching trains responses on selected seat holdings, with compatibility, geometry and terminal payoffs. Each applicable lock fits observed public fold/call/raise frequencies against reach at that node, blends by confidence and can flatten assignment across hands using observed showdown correlation. The default street reads pool across size and the adaptive bot partially pools across streets. Size affects the betting tree, affordable targets and payoffs. The optional sized-lock variant is outside the default Coach path. The baseline’s hypothetical fold rate can therefore change when the working set or upstream policy changes. Its responses on omitted combos are undefined in the solver. The nearest-rank fill used in the calibration exercise is a research diagnostic. [Lock construction](backend/solver/exploit.py) · [DCFR responses and action EV](backend/solver/cfr.py) · [Research reply extension](backend/research/holdem/phase_4l.py)
3. **Payoff and choice.** The solver integrates downstream action probabilities and counterfactual reach over the compatible solve columns, then reports action EV. The chooser samples the iteration-averaged, locked strategy with a stable decision seed. Action EV and allocation can disagree because the reported EV uses final policies, while the mix summarizes training. Closing checks and calls end the hand and need only showdown and chip receipts. A short call pays the available stack and the excess outstanding amount is refunded. An effective closing shove has only fold and call replies. The same candidate menu is concretized through engine legality. [Street tree](backend/solver/tree.py) · [Chooser and legalizer](backend/solver/bot.py) · [Exact river evaluator](backend/research/holdem/river_ev.py)
4. **Independent scoring.** A frozen synthetic action path defines a reference posterior over all 990 Hero-compatible holdings. A separate reference law supplies each holding's future fold/call probabilities at the same effective price. The exact enumerator prices the same legal actions for all arms and agrees with a separate betting-tree payoff calculation. Reference weights and reply probabilities enter calibration, scoring and oracle substitutions only. [Bayesian reference](backend/research/holdem/river_bayes_reference.py) · [Common scoring](backend/research/holdem/phase_4r.py) · [Comparison runner](backend/research/holdem/phase_4u.py)

**Confirmed failures.** The original turn projection wrote omitted hands to zero and river 6s removed its final supported hand. Phase 4T's independent replay repairs the collapse and carries through to this phase. The archived −9.059 bb adjustment is a measured reply forecast error against the independent reference. Restoring the omitted holdings moved each modeled action by under 0.001 bb in that case. Substituting only the true replies restored the shove ranking on the same modeled range. The historical closing losses have no future reply branch. They expose distinct prior/likelihood and policy sensitivity. The equal-stack fresh panel passed legality and exact payoff parity. Short all-in refunds and legal raises were tested independently. [Phase 4T diagnosis](PHASE_4T_REPORT.md) · [Deterministic tests](backend/test_research_holdem_phase_4u.py)

**Model limitations.** Node locks estimate action frequencies with sparse public evidence and inherit equilibrium assumptions and finite CFR convergence. Aggregate rates do not identify which hands generate folds, calls and raises, how replies change by size, or how a different action gets selected on the observed path. On paired boards, many hand hypotheses share a made-hand tier but have very different showdown values. The independent candidate still assumes the effect of that tier and uses pooled river response intercepts. Its unmodeled reply-shape and joint range errors can dominate EV, even when the average forecast score improves.

## Candidate and independent validation

The new forecast evaluates every compatible holding with a price-dependent continuation probability and a conditional raise probability. It uses the collectible price after removing overhang, restricts aggression to legal children and assigns remaining continuing probability to call. It takes only public river counts, board-derived holding tiers and candidate action geometry. Changing the CFR working set changes the incumbent mix and may change the fixed Hero continuation. The new Villain reply matrices stay bit-identical for identical observables, including after changing engine-hidden Villain cards. Persistent ranges and observed-action likelihoods also stay identical in the 896-column default and 32-column checks with seeds 17 and 29. [Forecast and paired gate](backend/research/holdem/reply_forecast.py) · [Working-set and privacy test](backend/test_research_holdem_phase_4u.py)

The deterministic controls independently calculate continuation probabilities for a half-pot bet, pot bet and closing shove. At half pot their expected high-card/pair/strong values are 25%, 50% and 75%. At pot size they are 18.18%, 40% and 66.67%. A separate fixed law with 25%, 75% and 50% call probabilities gives net bluff EVs of +250, −200 and −550 chips for the toy bets and shove. A legal raise-to-target/call branch agrees with the manually counted pot receipt. An offered 600-chip shove into a 400-chip base pot against a 300-chip stack returns 300, yields a 1,000-chip contested pot, and gives net payoff −300, +200 or +700 chips for loss, tie or win. The independent exact river enumerator gives +200 chips at 50% equity and −200 chips at 10%. Sparse and 100-reply count fixtures validate posterior means and narrower beta intervals with evidence. [Control fixtures](backend/test_research_holdem_phase_4u.py)

For each proposal, both mixes are valued under the same model and fixed Hero continuation. The gate takes the smallest of those paired differences and accepts only a strictly positive minimum after numerical tolerance. The reply model set varies beta intercept endpoints, the strength gradient and allocation among legal raises. The range model set omits one public evidence source at a time while holding the other fitted likelihood factors fixed. The matrix contains 5–6 models on terminal historical spots and 85 on the archived nonclosing loss. Its min/max are sharp over the specified scenarios and their convex hull. The beta credible mass describes only the assumed intercept marginals. The scenario interval is a sensitivity calculation with limited scope. Unlike the inherited cover rule, the same calculation applies to every change in the initial action mix. [Frozen assumptions](PHASE_4U_PROTOCOL.md)

## Historical replays

Pot is before Villain's observed river wager. Variant A is the incumbent and C is the actual proposal. A percentage in a closing row is the all-in cover probability. Modeled and reference incoming ranges have all 990 compatible holdings positive in these diagnostics. The effective holding count is the reciprocal of the sum of squared holding probabilities. The evidence files include the full aligned vectors, modeled observation probabilities, exact posterior, stack geometry, and scenario action EVs. The synthetic reference integrates over Villain hypotheses.

| Hero and reference | Board | Pot / wager, chips | Incoming effective count, model / reference | A → C mix | Predicted Δ (bb) | True Δ (bb) | Model interval (bb) | Gate |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| Js Kh, loose-aggressive, 15 bb, prefix 3 | Qh 5d Qc 5s Jd | 400 / 200 | 322.6 / 792.4 | 94.18% shove, 5.82% raise, trace call/fold → 100% shove | +0.072 | +0.136 | [+0.0005, +0.141] | Accept |
| Jd 4h, loose-aggressive, 9 bb, prefix 30 | 2d 5h Kc Qd Js | 700 / 550 | 590.4 / 347.1 | 99.9989% → 99.9989% | 0 | 0 | [0, 0] | Retain |
| Kc As, tight-passive, 30 bb, prefix 0 | Th 8s 4h Qs 7s | 1,000 / 2,500 | 710.7 / 491.1 | 31.9522% → 0.0011% | +4.711 | +7.897 | [+2.211, +5.553] | Accept |
| Js 3c, loose-aggressive, 30 bb, prefix 30 | 2d Ah Jh 2h Kh | 1,200 / 2,400 | 441.5 / 912.2 | 0.2332% → 0.0011% | +0.0397 | +0.0434 | [+0.0111, +0.0398] | Accept |
| 3c 5c, tight-aggressive, 15 bb, prefix 3 | Qc 3s Ks 8h 6s | 1,000 / 1,000 | 661.0 / 496.8 | 0% fallback → 0.0011% | −0.000028 | −0.000043 | [−0.000044, +0.000005] | Retain |

For Js Kh, B and D called with 94.23% and lost 9.059 bb versus A. The reference priced call at +5.681, raise to 1,000 at +12.972 and shove at +15.313 bb. Here are the first replies with a common exact posterior. The independent model predicts calls much more often than B. It still understates calling and gives legal aggression positive mass in the smaller branch.

| Hero action | Forecast source | Fold | Call | Raise or shove |
| --- | --- | ---: | ---: | ---: |
| Raise to 1,000 | B | 89.90% | 7.05% | 3.05% |
| Raise to 1,000 | Independent | 33.33% | 53.41% | 13.25% |
| Raise to 1,000 | Reference | 1.00% | 99.00% | 0% |
| Shove | B | 92.69% | 7.31% | 0% |
| Shove | Independent | 36.67% | 63.33% | 0% |
| Shove | Reference | 5.00% | 95.00% | 0% |

The independent model priced the shove at +11.196 bb under its own posterior. Replacing only CFR replies with true replies moved the shove from +4.987 to +13.794 bb. Replacing only CFR's input posterior with the true range left the shove at +5.860 bb. The reply error was enough to change the ranking. [Historical vectors, replies and crossed substitutes](benchmark-results/phase-4u-2026-11-18/historical-final.json)

On Jd 4h the +1.315 bb call survived intact. D's inherited rule folded it, and Phase 4T separately demonstrated that the inherited rule folds it even with the reference posterior. The Kc As −24.715 bb archive reflects an earlier likelihood experiment's switch to an almost pure cover on the same production prior. Its exact cover was −24.716 bb. The Js 3c −18.720 bb archive reflects the incumbent wager likelihood paired with the exact incoming prior. The actual incumbent mostly folded. The 4U table evaluates the actual mixes, and the original runners reproduced both counterfactual losses to within 1e-9 bb of the recorded differences. All four closing cases have an empty future reply set. On 3c 5c, A reproduced the expected empty-range fallback. B produced legal advice, retained 990 positive compatible holdings, and assigned 6s 7s zero mass. [Original Phase 4Q evidence](PHASE_4Q_REPORT.md) · [Historical replays](benchmark-results/phase-4u-2026-11-18/historical-final.json) · [Counterfactual replays](benchmark-results/phase-4u-2026-11-18/archived-counterfactual-controls.json)

## Frozen development and holdout

Development comprised 16 decisions on a disjoint seed and profile stream. E−A was +0.492 bb with 6 accepted adjustments. Fresh holdout crossed eight boards, three independent training streams and four fixed styles for 96 decisions, including 64 closing and 32 nonclosing. Each interval resamples boards and training streams, keeping the styles together within each board-stream cell. The scores estimate conditional river decision EV under this prescribed synthetic panel. [102-file freeze and all case keys](benchmark-results/phase-4u-2026-11-18/frozen.json) · [Development run](benchmark-results/phase-4u-2026-11-18/development-final.json)

| Arm | Mean EV (bb) | Median / max regret (bb) | Paired gain vs A (bb) | Crossed 95% CI (bb) | Losses >0.01 bb | Worst Δ (bb) |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| A · incumbent | 5.322 | 0.2032 / 10.818 | — | — | — | — |
| B · decoupled | 6.104 | 0.0002 / 10.818 | +0.782 | [+0.095, +1.712] | 10 | −5.070 |
| C · independent replies | 5.715 | 0.0001 / 22.362 | +0.393 | [−1.676, +1.843] | 15 | −17.036 |
| D · inherited Phase 4S rule | 6.318 | 0.0002 / 8.395 | +0.996 | [+0.071, +2.051] | 11 | −6.895 |
| E · independent replies and gate | 6.055 | 0.0002 / 10.818 | +0.733 | [+0.025, +1.843] | 3 | −2.347 |

E gained +0.341 bb over C with a 95% interval [−0.520, +2.523], and changed −0.263 bb relative to D [−1.262, +0.453]. Across tight-passive, loose-passive, tight-aggressive and loose-aggressive, E−A was +0.939, +0.939, +0.449 and +0.607 bb. E accepted 34/67 distinct proposals (50.7%), including 16 closing and 18 nonclosing, and 34/96 decisions overall. Accepted proposals averaged +2.071 bb. The 33 rejected proposals averaged −0.991 bb under exact scoring, including 12 beneficial and 12 harmful proposals larger than 0.01 bb in absolute value. There were 29 effectively unchanged proposals. [Paired contrasts and coverage](benchmark-results/phase-4u-2026-11-18/holdout-13.json)

| Arm | Seeded folds of 30 profitable covers | Seeded folds of 34 losing covers | Profitable fold mass | Losing fold mass |
| --- | ---: | ---: | ---: | ---: |
| A | 11 | 26 | 7.924 | 22.883 |
| B | 2 | 22 | 2.000 | 22.000 |
| C | 2 | 22 | 2.000 | 22.000 |
| D | 8 | 31 | 8.000 | 31.000 |
| E | 5 | 24 | 4.916 | 22.908 |

E introduced zero per-row profitable-cover mass regressions. D's worst loss came from folding a +6.895 bb cover on 7h 3s. E preserved the incumbent cover there. E reduced seeded profitable folds by six and seeded losing folds by two. Summed probabilities give a separate expectation over the mixed strategies. [Closing results](benchmark-results/phase-4u-2026-11-18/holdout-13.json)

The independent law improved mean first-reply marginal excess Brier from 0.383 for A and 0.352 for B to **0.115** over 40 legal Hero-target branches. Mean holding-weighted Brier moved from 0.748 and 0.783 to **0.385**. Independent marginal error was 0.122, 0.109, 0.140 and 0.088 across the four styles in the stated order. In the nonclosing stratum, the matched same-choice-rule control held the full range and Hero continuation fixed. Replacing CFR replies with independent replies **reduced** exact EV by **1.334 bb per nonclosing decision** in that control. The 3- and 30-hand prefixes are the observed nonclosing strata. The 0- and 100-hand prefixes are represented in closing decisions, which have no reply calibration score. Sparse and well-supported forecast intervals were tested in the toy controls. [Style and prefix calibration](benchmark-results/phase-4u-2026-11-18/holdout-13.json)

## Downside analysis

The E gate rejected C's worst fresh proposal, a −17.036 bb shove on 4d Jd with a modeled interval [−7.344, +12.735] bb. It rejected B's largest closing loss of −5.070 bb on 7h 3s. Every accepted loss over 0.01 bb came from the same Td 3h / 9s 7s 3s 2h 7h board, across two training streams and both passive opponents.

| Profile and geometry | Predicted Δ (bb) | Scenario interval (bb) | True Δ (bb) | Range TV from reference |
| --- | ---: | ---: | ---: | ---: |
| Loose-passive, 3 hands, stream 213, jam over a 600-chip wager | +3.440 | [+1.187, +15.332] | −2.347 | 0.650 |
| Tight-passive, 100 hands, stream 211, closing cover for 550 | +1.218 | [+0.715, +3.601] | −1.490 | 0.794 |
| Loose-passive, 100 hands, stream 211, closing cover for 550 | +1.586 | [+0.715, +3.601] | −0.684 | 0.695 |

On stream 213, A folded 45.41%, called 54.15%, and shoved 0.44%. E chose a pure shove. The exact call and shove values were −1.432 and −3.136 bb. The independent law predicted an 83.44% shove call rate under its own range. The same law predicted 88.60% on the true range, versus the reference's 97.04%. Holding the modeled range fixed and giving it true replies still ranked the proposal +2.232 bb ahead. Giving the model the true range with its own replies reversed the sign to −0.423 bb. True range and replies together gave −2.347 bb. On the two closing covers, substituting the true posterior alone reproduced the exact negative increment. The one-source omissions failed to span the relevant prior and action-selection misspecification. These substitutions use privileged evaluation inputs and were calculated after the frozen run. [Loss decomposition with full vectors](benchmark-results/phase-4u-2026-11-18/holdout-harm-diagnostics.json)

## Runtime, reliability and promotion

| Arm | Seed 13 median / p95 / max (s) | Seed 31 median / p95 / max (s) |
| --- | ---: | ---: |
| A | 1.063 / 2.947 / 3.868 | 0.862 / 2.305 / 2.975 |
| B | 0.127 / 1.519 / 2.320 | 0.096 / 1.218 / 1.585 |
| C | 0.128 / 1.529 / 2.322 | 0.097 / 1.220 / 1.587 |
| D | 0.127 / 1.519 / 2.320 | 0.096 / 1.218 / 1.585 |
| E | 1.280 / 3.957 / 4.867 | 1.074 / 3.059 / 3.670 |

E includes both A and B replays. Under seed 13, median forecast and gate work took 1.91 ms and 0.58 ms, and their respective maxima were 12.94 ms and 36.57 ms. Whole-run peak resident memory was 299.0 MiB and 294.4 MiB. Excluding time, memory and their associated fields, all 96 paired rows and their summaries were bit-identical across hash seeds. Both runs had zero unexpected fallbacks. B performed one decision solve per row with at most 896 columns per seat. Its persistent Hero-compatible range had 990 positive holdings on every row. Mean exact reference mass outside B's solver columns was 29.85%. The forecast scorer and gate had access to every compatible holding. The holdout used warmed board caches. In a separate diagnostic, the three slowest warm keys for A, B and E were replayed with board caches cleared before each pair. E took 3.618–4.429 s on those keys. This is a small cold-cache probe with shared cache reuse within each A/B pair. [Seed 13](benchmark-results/phase-4u-2026-11-18/holdout-13.json) · [Seed 31](benchmark-results/phase-4u-2026-11-18/holdout-31.json) · [Determinism check](benchmark-results/phase-4u-2026-11-18/determinism.json) · [Cold-cache probes](benchmark-results/phase-4u-2026-11-18/cold-replay-probes.json)

| Frozen E gate | Outcome on both seeds |
| --- | --- |
| Mean ≥ +0.05 bb and paired lower bound above zero | Pass |
| Maximum harmful adjustment ≤ 0.50 bb | **Fail** |
| At most 10% of rows losing more than 0.01 bb | Pass, 3.125% |
| Per-style mean ≥ −0.03 bb | Pass |
| Positive adjustment coverage and profitable covers preserved | Pass |
| Legal normalized advice, matched scoring, zero unexpected fallbacks | Pass |
| 15 s max, median ≤ 2× A, peak ≤ 768 MiB | Pass |
| Deterministic results and frozen inputs | Pass |

**Architecture no-go for live adaptive strategy selection.** Public river counts identify pooled action rates under the old behavior and visited states. Sparse or even well-supported pooled profiles leave hand-by-size response probabilities and selection into the current range underidentified. CFR's sample and iteration budget introduce another approximation. The close 4T 8s Qh call illustrates numerical decision sensitivity, with +0.012 bb from the working set and −0.002 bb on the full modeled posterior. The archived Js Kh case illustrates a much larger response-law effect that increasing CFR's budget alone would leave unresolved. Phase 4U's gate had useful coverage and positive pooled EV on this panel. Its defining weakness is shared bias across scenarios. On the worst accepted adjustment every scenario favored the wrong sign. Widening the same assumptions could reject more profitable adjustments and still leave important correlated range errors outside the model set.

**One next direction.** Run a trace-only multi-street integration of the persistent range and projection boundary using archived Coach and Match public histories. Compare actual-replay support, blocker and omitted-mass ledgers, fallback behavior, and latency at each street while the existing solver and chooser continue to drive advice. Phase 4T and 4U establish that support can be preserved in current-decision replay. The live street-root solve reuses a solved descendant when action and geometry match, and can re-solve from the actual state after an off-tree action. Phase 4U reconstructs past observations without street solves, then B solves from the current river root once. That can materially change the policy, as B's holdout losses and gains show, and a live multi-street parity test is still needed. The proposed trace work targets the confirmed range-integrity problem. The promotion failure rules out a paired gameplay validation of the Phase 4U strategy candidate.

## Verification and Git status

- The full backend suite passed **1,007 tests** in 1,053.87 s, retaining all 998 existing tests and adding nine. It reported eight existing dependency deprecation warnings. Coach API tests ran with local loopback access because the default sandbox denied local socket connections. [Full backend log](benchmark-results/phase-4u-2026-11-18/backend-tests.txt)
- Nine focused deterministic controls passed under each of Python hash seeds 13 and 31. All 186 research tests passed in 314.75 s under seed 31 with seven existing dependency deprecation warnings. [Focused seed 13](benchmark-results/phase-4u-2026-11-18/focused-13.txt) · [Focused seed 31](benchmark-results/phase-4u-2026-11-18/focused-31.txt) · [Research test log](benchmark-results/phase-4u-2026-11-18/research-tests.txt)
- The frontend production build and Coach strategy/fallback rendering smoke check passed. The backend dependency check found no broken requirements. Benchmarks and verification used installed dependencies and offline research inputs. [Frontend build](benchmark-results/phase-4u-2026-11-18/frontend-build.txt) · [Coach rendering](benchmark-results/phase-4u-2026-11-18/frontend-coach.txt) · [Dependency check](benchmark-results/phase-4u-2026-11-18/pip-check.txt)
- Frozen manifests for Phases 4Q, 4R, 4S, 4T and 4U matched all recorded inputs. Git is on `main` at `3e89367`, 19 commits ahead of local `origin/main`. The worktree matches the Phase 4T handoff plus five local untracked Phase 4U files, and the evidence lives in the existing ignored benchmark directory. Git and new-file whitespace checks passed with the existing `backend/test_poker.py` line-ending advisory. [Manifest checks](benchmark-results/phase-4u-2026-11-18/frozen-source-check.txt) · [Git status](benchmark-results/phase-4u-2026-11-18/final-status.txt) · [Status delta](benchmark-results/phase-4u-2026-11-18/status-delta.txt)

## Reproduction

From the repository root use the installed backend environment. Choose a new evidence directory for every run. The frozen manifest verifies the 102 source files and both case schedules before the holdout replay.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$phasePy = '.\.venv\Scripts\python.exe'
$phaseOut = '../benchmark-results/phase-4u-reproduction'
$phaseFreeze = '../benchmark-results/phase-4u-2026-11-18/frozen.json'
$phaseBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:],timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phaseOut -ErrorAction Stop | Out-Null
foreach ($phaseMode in 'development', 'historical') {
    & $phasePy -c $phaseBound 480 $phasePy -m research.holdem.phase_4u $phaseMode "$phaseOut/$phaseMode.json"
    if ($LASTEXITCODE -ne 0) { throw "Phase 4U $phaseMode failed" }
}
foreach ($phaseSeed in '13', '31') {
    $env:PYTHONHASHSEED = $phaseSeed
    & $phasePy -c $phaseBound 1200 $phasePy -m research.holdem.phase_4u holdout "$phaseOut/holdout-$phaseSeed.json" --manifest $phaseFreeze
    if ($LASTEXITCODE -ne 0) { throw "Phase 4U holdout $phaseSeed failed" }
}
& $phasePy -m research.holdem.phase_4u compare "$phaseOut/determinism.json" --runs "$phaseOut/holdout-13.json" "$phaseOut/holdout-31.json"
```
