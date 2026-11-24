# Phase 4X — Why persistent river beliefs can still produce harmful decisions

**PHASE 4X NOT COMPLETE — strategy promotion failed.** The diagnosis and independent evaluation reproduced across two hash seeds. The targeted candidate reduced the worst fresh mixed-policy loss from 8.299 bb to 0.411 bb, with zero profitable closing-call regressions. Its +0.021 bb mean improvement fell short of the +0.05 bb gate and the paired interval crossed zero. The live strategy remains the incumbent. [Frozen protocol](PHASE_4X_PROTOCOL.md) · [Fresh exact-EV results](benchmark-results/phase-4x-2026-11-19/holdout-13.json)

## The −17.690 bb decision

The repaired solver treated a 25 bb raise as a profitable bluff. On the same modeled range, substituting the reference opponent's future replies moved the shove from **+0.362 bb to −11.789 bb** and made folding preferable. The solver predicted **63.41% folds** on its projected range, just above the 62.5% breakeven rate for risking 25 bb to win 15 bb if Hero always loses when called. The reference law gave **30.15% folds on that same range** and **17.54% on its own posterior**. The three-hand profile contained zero river facing-wager opportunities. Correcting either the incoming prior or the wager likelihood also reversed the ranking in this case. The four opponent styles on this geometry shared the reply failure. [Per-holding weights, replies and replay](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

Hero held **Ah 9c** on **Tc 8s 5d Kh Jd**, in the big blind, with 30 bb starting stacks and 50/100 blinds. Villain limped, Hero raised to 250 and Villain called. Hero checked the flop, Villain bet 250 and Hero called. Both checked the turn. Hero checked the river and Villain bet 500 into 1,000. At the decision the pot was 1,500 chips, Hero had 2,500 behind, and Villain had 2,000 behind and 500 committed. The engine allowed fold, call, raise to 1,000–2,500 total, and all-in. Both policy menus offered fold, call and all-in. The reference's legal-size endpoint search also selected fold. [Case, concrete menu and replay](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

| Action | Incumbent displayed EV, bb | Repaired CFR EV, bb | Exact reference EV, bb | Incumbent mass | Repaired mass |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fold | 0.000 | ≈0 | 0.000 | 99.8269% | 1.0526% |
| Call | −4.890 | −1.808 | −4.773 | 0.0704% | 0.0097% |
| All-in | −1.125 | +0.362 | −17.901 | 0.1027% | 98.9378% |

The net-transfer check starts from the moment Hero can fold. A call pays 500 and contests 2,000, so its win, tie and loss transfers are +1,500, +500 and −500 chips. A shove wins +1,500 on a fold. When called, it contests 5,500 and transfers +3,000, +250 or −2,500. The exact evaluator, independent transfer loop and **3,960 completed engine histories** agree on all three EVs. The engine check replays four terminal paths for each compatible holding and verifies event-level accounting. The seeded recommendations were fold for A and shove for B. Their exact mixed-policy EVs were −0.021748 and −17.711701 bb, with equal-magnitude regret against fold. The chosen shove's conditional regret was 17.901394 bb. [Exact scorer](backend/research/holdem/river_ev.py) · [Engine settlement cross-check](benchmark-results/phase-4x-2026-11-19/engine-settlement.txt) · [Reproduction data](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

| Opponent distribution | Positive compatible holdings | Effective holdings | Total variation from reference |
| --- | ---: | ---: | ---: |
| Incumbent replay | 221 | 57.63 | 0.736 |
| Repaired posterior | 990 | 473.05 | 0.508 |
| Reference posterior | 990 | 345.82 | 0 |

The repaired solve used 631 Villain and 324 Hero columns. It omitted 0.00124% of its compatible probability, while those omitted columns contained 32.69% under the reference. On B's modeled weights, restoring omitted mass with rank-matched replies moved the shove by only 0.000049 bb. The projected transfer calculation and full-precision CFR action values agree within the numerical tolerance. The modeled range gave Hero 15.96% showdown equity, versus 1.14% in the reference. The reference prior alone reduced posterior TV to 0.032, while the reference wager likelihood alone reduced it to 0.492. [Selected IDs, omitted mass and full weighting factors](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

## Decision pipeline

Coach replays the public history to an engine-authoritative state. The chart initializes reaches. The Phase 4W owner applies public action likelihoods and board blockers, then conditions Villain's posterior on Hero's cards. Direct reweighting reproduced every audited update. The last observed wager likelihood comes from a hand-tier action law with optional profile locks. A complete positive support and correct Bayes multiplication establish internal consistency. The prior weights and the likelihood still require calibration. [Coach replay](backend/coach/service.py) · [Persistent owner](backend/research/holdem/live_persistent.py) · [Action likelihood](backend/research/holdem/decoupled_replay.py)

The working set copies selected board-public reaches into scratch arrays. DCFR solves a bounded current-root tree on their compatible pair matrix. It generates Villain's future replies as part of the same modeled game, using confidence-weighted locks when available. The final policy supplies Hero's full-precision action frequencies. The displayed EV uses this same modeled policy and rounds in chips. Coach samples the mix deterministically and legalizes the action. Nearly all repaired mass landed on a shove with a modeled edge of 0.362 bb. The 18.264 bb shove pricing error overwhelms that edge. Increasing the iteration budget kept the wrong preference. The nominal sizing abstraction admitted the exact optimal action, fold. [Solver pipeline](backend/solver/bot.py) · [DCFR values](backend/solver/cfr.py) · [Sizing abstraction](backend/solver/tree.py)

## Controlled substitutions

All comparisons use the same state, concrete menu and exact scoring opponent. The digits below indicate substitution of the incoming prior, last-wager likelihood and future replies, in that order. **000** uses B's components on full modeled support, extending its replies on omitted columns by nearest showdown rank. The response comparison on the worst row also measures fold rates strictly within the actual projection. Each diagnostic cell uses the same greedy action selector. A and B use the actual Coach mixtures. [All eight cells and policy distributions](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

| Arm or substitution | Worst-row call EV, bb | Worst-row shove EV, bb | Worst-row preference or chosen action | Mean regret on 18 harmed rows, bb |
| --- | ---: | ---: | --- | ---: |
| A · incumbent replay | −4.890 | −1.125 | Fold | 1.646 |
| B · repaired replay | −1.808 | +0.362 | Shove | 6.071 |
| 000 · modeled inputs | −1.808 | +0.362 | Shove | 5.873 |
| 001 · replies | −1.808 | −11.789 | Fold | 1.611 |
| 010 · wager likelihood | −3.523 | −1.616 | Fold | 2.014 |
| 011 · wager likelihood and replies | −3.523 | −14.923 | Fold | 0.095 |
| 100 · prior | −4.459 | −0.640 | Fold | 4.493 |
| 101 · prior and replies | −4.459 | −17.097 | Fold | 1.182 |
| 110 · prior and wager likelihood | −4.773 | −1.784 | Fold | 2.435 |
| 111 · full reference, diagnostic only | −4.773 | −17.901 | Fold | 0.000 |

Reply substitution alone repaired the four largest nonclosing shove preferences and recovered the 1,000-chip value raise on all four board-1 nonclosing cases. Reply substitution had zero effect on the three losing closing calls. The last-wager likelihood alone reversed two of those calls, including the largest, and the incoming prior alone reversed the third. The model gave the largest closing call +6.027 bb against an exact −21.273 bb. B increased cover from 50% to 99.999%. This is a wrong ranking under the modeled posterior with the same settlement arithmetic. Correcting replies alone also made the greedy policy worse by 5.792 bb on the selected positive nonclosing control, where the dual prior and likelihood correction was needed to recover fold. Component effects depend on the other inputs. [Closing and beneficial controls](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

## The 18 harmful decisions

| Board / stream | Opponent | Prior hands | B−A, bb | Classification |
| --- | --- | ---: | ---: | --- |
| 5 / 311 | Tight-passive | 3 | −17.690 | Unsupported bluff shove. Reply, prior or wager correction flips to fold. |
| 5 / 311 | Loose-passive | 3 | −15.636 | Same shove. Reply, prior or wager correction flips to fold. |
| 5 / 311 | Tight-aggressive | 3 | −11.143 | Same shove. Full reference weights with modeled replies still prefer it. |
| 1 / 313 | Loose-passive | 100 | −10.636 | Losing closing call. Wager-likelihood substitution flips to fold. |
| 5 / 311 | Loose-aggressive | 3 | −10.524 | Same shove. Reply substitution flips to fold on B's modeled range. |
| 1 / 311 | Tight-aggressive | 3 | −2.411 | Call displaces a better value raise. Either reply or wager correction restores the raise. |
| 1 / 311 | Loose-aggressive | 3 | −2.190 | Call displaces a better value raise. Either reply or wager correction restores the raise. |
| 3 / 313 | Tight-passive | 3 | −1.762 | Bluff-shove mass rises on a ≈0.04 bb modeled advantage. Reply correction flips to fold. |
| 3 / 313 | Loose-passive | 3 | −1.758 | Same thin-margin shove. Reply correction flips to fold. |
| 1 / 311 | Loose-passive | 3 | −1.536 | Call displaces a better value raise. Reply correction restores the raise. |
| 1 / 311 | Tight-passive | 3 | −1.238 | Call displaces a better value raise. Reply correction restores the raise. |
| 5 / 313 | Loose-aggressive | 100 | −0.851 | Losing closing call. Prior substitution flips to fold. |
| 0 / 312 | Loose-aggressive | 3 | −0.751 | Call mass replaces a better shove. Correct nominal ranking, with only about 0.014 bb between shove and call. |
| 0 / 312 | Tight-aggressive | 3 | −0.722 | Same near-indifferent mix. Exact shove advantage over call is 9.279 bb. |
| 0 / 312 | Tight-passive | 3 | −0.607 | Same near-indifferent mix. Exact shove advantage over call is 7.792 bb. |
| 7 / 311 | Loose-passive | 100 | −0.102 | Losing closing call. Either prior or wager substitution flips to fold. |
| 3 / 313 | Tight-aggressive | 3 | −0.053 | Same thin-margin shove as the passive rows, with smaller exact loss. |
| 3 / 313 | Loose-aggressive | 3 | −0.032 | Same thin-margin shove as the passive rows, with smaller exact loss. |

On the full historical denominator, 15 of 32 nonclosing decisions and 3 of 64 closing decisions lost more than 0.01 bb. The nonclosing losses all followed a half-pot wager on the limp/call path with a three-hand profile, including 14 cases with zero observed river replies and one with a single call. The closing losses all followed three-bet pots with 100-hand profiles. This schedule ties wager size, history and profile coverage together, so the counts do not independently identify the effect of any one of them. By depth the losses were 1/32 at 9 bb, 9/32 at 15 bb, and 8/32 at 30 bb. They were distributed across all four styles at 4–5 per style out of 24. Concentration in nominal working-set omissions was weak for the large bluffs. The closing example that lost 0.851 bb omitted 9.83% modeled mass, while the 10.636 bb closing loss omitted only 0.23%. [Full historical denominator](benchmark-results/phase-4w-2026-11-19/holdout-13.json) · [Classified rows and profile counts](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

## Solver sensitivity and calibration

Four decision extremes were stressed. Each unchanged-state projection and root-weight perturbation kept B's persistent posterior bit-identical and used the original exact payoffs. The root-weight probe multiplied solver scratch weights on holdings beating Hero by ½ or 2. That deliberately uses a private-card-dependent perturbation as an offline diagnostic. The depth and preflop-size variants changed the engine state, so each received its own independently checked exact payoffs. [Stress runs and full mixes](benchmark-results/phase-4x-2026-11-19/sensitivity-final-13.json)

| Control | Maximum projection mix TV | Exact EV across 12 projection settings, bb | Harmful settings vs A across 16 same-state stresses |
| --- | ---: | ---: | ---: |
| Worst nonclosing | 0.986 | −17.714 to −0.061 | 16/16 |
| Worst closing | 1.000 | −21.273 to −0.00024 | 6/16 |
| Best nonclosing | 0.999 | −6.410 to −0.624 | 0/16 |
| Best closing | 0.000 | −0.00027 at every cap | 0/16 |

In the worst nonclosing case the greedy recommendation still shoved with 2.5% reference continuation mixed into the model, and folded at 5%. River iterations of 40, 80 and 320 gave modeled shove EVs of +0.348, +0.362 and +0.237 bb and exact policy EVs of −16.464, −17.712 and −17.898 bb. Halving or doubling the scratch odds on losing holdings still cost more than 17 bb. The −3 and +3 bb depth changes returned −15.252 and −9.001 bb exact policy EV respectively, and increasing the earlier raise target by 50 chips returned −16.191 bb. In the worst closing case doubling losing odds flipped the modeled call from +6.027 to −4.015 bb and nearly eliminated the call. Its fourfold iteration run still called. All four chooser seeds selected the same nominal action per control. [Iteration, range, response, seed and geometry records](benchmark-results/phase-4x-2026-11-19/sensitivity-final-13.json)

Each hash seed ran 76 stress replays. Median per-replay time was 0.049/0.045 s and maximum was 0.777/0.807 s for seeds 13/31. Peak resident memory was 167.71/167.67 MiB. Policy mixes, projection diagnostics and payoff results matched across hash seeds. [Seed 31 stress record](benchmark-results/phase-4x-2026-11-19/sensitivity-final-31.json) · [Determinism](benchmark-results/phase-4x-2026-11-19/sensitivity-determinism.json)

Under B's modeled values, 15 of the 18 historical harms appeared to be improvements over A. The worst appeared to gain +0.359 bb and actually lost 17.690 bb. The 10.636 bb closing loss appeared to gain +3.032 bb. The three small board-0 regressions had a modeled policy change of −0.0011 bb. The two selected positive controls had modeled increments of +2.661 and +16.441 bb and exact increments of +5.785 and +24.510 bb. This calibration check measures the selected harms and controls. Larger budgets may reduce some mix instability. They leave the measured prior and reply biases intact. [Modeled contrasts and exact changes](benchmark-results/phase-4x-2026-11-19/diagnosis-13.json)

## Targeted candidate

The offline candidate bounds the policy change against A for nonclosing river decisions. It computes the lower incremental payoff over loss, tie and win with each aggression allowed any fold/call response, then mixes in as much of B as fits the frozen 0.50 bb budget. Closing decisions use A's mix and seeded action because their failure comes from the wagering posterior and there is no future reply to bound. The targeted rule requires no probability fit. The worst historical adjustment drops to **−0.358 bb** with about **2.02%** of B mixed in. The two selected positive historical changes shrink from +5.785 to +0.097 bb and from +24.510 to zero. The bound covers expected EV under fold/call continuation. A sampled recommendation and a live tree containing further raises need separate safety evidence. [Frozen protocol](PHASE_4X_PROTOCOL.md) · [Bound implementation](backend/research/holdem/river_adjustment.py)

## Independent holdout and gates

The 144 fresh decisions crossed 12 new boards, three independent profile streams, and four fixed opponent styles. There were 100 closing and 44 nonclosing decisions. Of the nonclosing decisions, 20 used a three-hand profile and four used no profile. All 144 rows reproduced across hash seeds 13 and 31 with the A/B timing order reversed. Both runs verified all 189 frozen source and protocol hashes and the exact case schedule before evaluation. Every concrete action payoff passed independent chip-transfer accounting, and all mixes were legal and normalized. [Manifest](benchmark-results/phase-4x-2026-11-19/frozen.json) · [Seed 13](benchmark-results/phase-4x-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-4x-2026-11-19/holdout-31.json) · [Determinism](benchmark-results/phase-4x-2026-11-19/holdout-determinism.json)

| Policy | Mean EV, bb | Worst absolute EV, bb | Mean / median / max regret, bb | Unexpected fallbacks |
| --- | ---: | ---: | ---: | ---: |
| A · incumbent | −0.615 | −23.491 | 2.436 / 0.573 / 23.491 | 0 |
| B · Phase 4W | +0.936 | −23.491 | 0.884 / 0.00018 / 23.491 | 0 |
| C · bounded change | −0.594 | −23.491 | 2.415 / 0.611 / 23.491 | 0 |

| Contrast | Mean, bb | Crossed paired 95% interval, bb | Losses over 0.01 bb | Worst change, bb |
| --- | ---: | ---: | ---: | ---: |
| B−A | +1.551 | [+0.273, +3.422] | 20/144 (13.89%) | −8.299 |
| **C−A** | **+0.021** | **[−0.012, +0.068]** | **9/144 (6.25%)** | **−0.411** |
| C−B | −1.530 | [−3.400, −0.264] | 72/144 (50.00%) | −22.989 |

| Opponent | B−A, bb | C−A, bb |
| --- | ---: | ---: |
| Tight-passive | +1.759 | −0.004 |
| Loose-passive | +1.403 | −0.003 |
| Tight-aggressive | +1.271 | +0.047 |
| Loose-aggressive | +1.772 | +0.046 |

The worst B and C adjustments occurred on the same fresh tight-passive case, with no profile, 30 bb, and Hero Ac Jd on Th Qs 9c 7h 7d. Fold was worth zero, call −3.834 bb and shove −21.331 bb. C brought the loss inside the budget and selected fold on this row. Across open rows, C mixed in a median of 21.58% of the proposed B adjustment. C changed 42 mixes and 22 seeded recommendations. It preserved A on 23 profitable closing calls and all other closing decisions. B regressed on eight profitable closing calls. B also averaged +2.046 bb on the closing subset, while C left that potential benefit unexploited. On the nonclosing subset B and C gained +0.428 and +0.070 bb, respectively. The frozen endpoint includes both subsets. [Row-level results](benchmark-results/phase-4x-2026-11-19/holdout-13.json)

The fixed-seed action comparison is descriptive. The worst C recommendation change was from fold to all-in and lost **9.639 bb** under the reference. Twelve seeded C choices lost more than 0.01 bb versus A, and their mean paired change was −0.051 bb over the full sample. The 0.50 bb bound applies to averaging the mixed policy. A rare action under that mix can still have a large adverse payoff. This matters for a Coach interface that presents a single sampled recommendation. [Full-precision policies and recorded recommendations](benchmark-results/phase-4x-2026-11-19/holdout-13.json)

| Gate | B versus A | C versus A |
| --- | --- | --- |
| Mean ≥ +0.05 bb and strictly positive 95% lower bound | Pass | **Fail** |
| Worst mixed-policy loss ≤ 0.50 bb | **Fail** | Pass |
| Harm rate ≤ 10% | **Fail** | Pass |
| Every style mean ≥ −0.03 bb | Pass | Pass |
| Profitable closing-call preservation | **Fail** | Pass |
| Complete legal policies, independent payoff checks, deterministic parity and zero unexpected fallbacks | Pass | Pass |
| Runtime, memory and working-set limits | Pass | Pass |

Each entry below is median / nearest-rank p95 / maximum replay seconds. C includes the A and B replays it requires, plus its own measured overhead, and uses only A for closing decisions. The process peaks were 280.27 and 289.11 MiB. Whole-panel wall times were 277.41 and 275.09 s. Both runs met the 15 s maximum, 2× incumbent median and 768 MiB ceiling. [Resource records](benchmark-results/phase-4x-2026-11-19/holdout-13.json) · [Second run](benchmark-results/phase-4x-2026-11-19/holdout-31.json)

| Policy | Hash seed 13 | Hash seed 31 |
| --- | ---: | ---: |
| A | 0.958 / 3.526 / 7.179 | 0.905 / 3.922 / 6.815 |
| B | 0.094 / 1.421 / 1.801 | 0.103 / 1.191 / 2.102 |
| C | 0.970 / 3.829 / 7.179 | 0.971 / 4.206 / 6.815 |

## Architecture and gameplay readiness

Keep the Phase 4W range owner available behind both opt-in flags. The strongest next investment is **response forecasting and its interface to solver decisions**. The nonclosing ablations show enough recoverable decision quality to justify that work. Sparse, pooled reply statistics could not identify fold rates by holding and price. Increasing the projection or iteration budget does little to address that gap. A separate prior and wager-likelihood error explains the worst closing call. That error needs its own calibration evidence before any closing-call change.

For **Phase 4Y**, first freeze an offline decision benchmark that independently varies response coverage, offered price, preflop history and observed wager. Include a prospective held-out reference with legal re-raises and test reply prediction and paired action-advantage calibration at fixed posteriors. Require measurable recovery of profitable value bets and explicit downside checks for the seeded Coach recommendation before another policy candidate. If available public data cannot identify a useful price-conditioned response law at sparse coverage, stop tuning and retain the incumbent. Passing a future exact-EV and safety protocol would justify planning a separate paired gameplay benchmark against production, adaptation disabled and the equity baseline, using duplicate deals, seat swaps, independent seeds and fixed training profiles. Phase 4X provides no gameplay-readiness approval.

## Verification and Git

- The two focused runs passed 17 tests each, with seven existing dependency deprecation warnings each. The four new cases pin the sparse-profile shove mispricing, independently enumerate downside endpoints with a refund and odd chip, and cover both closing stack configurations. Existing tests check the persistent owner, archived collapse, flag parity, deterministic advice, explicit zero-support fallback, and short all-in accounting. [Seed 13](benchmark-results/phase-4x-2026-11-19/focused-all-13.txt) · [Seed 31](benchmark-results/phase-4x-2026-11-19/focused-all-31.txt)
- The final combined backend suite passed all **1,021 tests** in 1,293.43 s with eight existing dependency warnings. This retains the 1,017 existing passes and includes four Phase 4X cases. The separate research suite passed all **200 tests** in 461.16 s with seven existing warnings. The first sandboxed full run stalled when FastAPI attempted to open its local Windows socket pair. The completed full runs used Windows loopback access. [Final backend regression](benchmark-results/phase-4x-2026-11-19/backend-final.txt) · [Original suite](benchmark-results/phase-4x-2026-11-19/backend-loopback.txt) · [Research regression](benchmark-results/phase-4x-2026-11-19/research-tests.txt) · [Sandbox trace](benchmark-results/phase-4x-2026-11-19/backend-default.txt)
- All 20 historical decisions, including the 18 harms, reproduced archived A/B mixes, recommendations and displayed values. Both hash seeds reproduced the weighting, projections and payoff diagnostics. All 185 Phase 4W frozen files retained their recorded hashes. [Historical determinism](benchmark-results/phase-4x-2026-11-19/historical-determinism.json) · [Source hashes](benchmark-results/phase-4x-2026-11-19/frozen-source-check.txt)
- Local API smoke passed Coach advice, Match, Single Hand Replay and Persistent Match Replay with both flags off and with both enabled. Existing focused tests exercise independent flag construction and replayed chip conservation. The frontend production build, Coach strategy render, and Match and Replay render smoke passed. Both replay controls rendered the first event from real histories with only the public cards available at that event. The dependency check passed. [API smoke](benchmark-results/phase-4x-2026-11-19/api-smoke.txt) · [Frontend build](benchmark-results/phase-4x-2026-11-19/frontend-build.txt) · [Coach render](benchmark-results/phase-4x-2026-11-19/frontend-coach.txt) · [Match and Replay](benchmark-results/phase-4x-2026-11-19/frontend-match-replay.txt) · [Dependencies](benchmark-results/phase-4x-2026-11-19/pip-check.txt)
- Git stayed on main at 3e89367, 19 commits ahead of local origin/main. The only additions are this report, the protocol, the two offline research modules and one regression test file. All prior working-tree changes were preserved. Git whitespace and new-file checks passed, with the existing LF/CRLF advisory for the pre-existing test_poker.py edit. Evidence is in the repository's ignored benchmark-results directory. No commits, pushes or deployments were made. [Full status](benchmark-results/phase-4x-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-4x-2026-11-19/status-delta.txt) · [Whitespace check](benchmark-results/phase-4x-2026-11-19/new-file-check.txt)

## Reproduction

From the backend directory, use the installed virtual environment and a new output directory. The historical and sensitivity runners read the Phase 4W archive. The fresh runner uses the frozen Phase 4X manifest.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$phase4xPython = '.\.venv\Scripts\python.exe'
$phase4xFrozen = '../benchmark-results/phase-4x-2026-11-19/frozen.json'
$phase4xOut = '../benchmark-results/phase-4x-reproduction'
$phase4xBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:], timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phase4xOut
foreach ($phase4xHash in '13', '31') {
    $env:PYTHONHASHSEED = $phase4xHash
    $phase4xOrder = if ($phase4xHash -eq '31') { @('--reverse') } else { @() }
    foreach ($phase4xMode in 'historical', 'sensitivity') {
        & $phase4xPython -c $phase4xBound 1200 $phase4xPython -m research.holdem.phase_4x $phase4xMode "$phase4xOut/$phase4xMode-$phase4xHash.json"
        if ($LASTEXITCODE -ne 0) { throw "$phase4xMode failed" }
    }
    & $phase4xPython -c $phase4xBound 1200 $phase4xPython -m research.holdem.phase_4x holdout "$phase4xOut/holdout-$phase4xHash.json" --manifest $phase4xFrozen @phase4xOrder
    if ($LASTEXITCODE -ne 0) { throw "Holdout failed at hash seed $phase4xHash" }
}
foreach ($phase4xMode in 'historical', 'sensitivity', 'holdout') {
    & $phase4xPython -m research.holdem.phase_4x compare "$phase4xOut/$phase4xMode-determinism.json" --runs "$phase4xOut/$phase4xMode-13.json" "$phase4xOut/$phase4xMode-31.json"
    if ($LASTEXITCODE -ne 0) { throw "Determinism check failed for $phase4xMode" }
}
```

Run backend pytest from the backend directory with Windows loopback available to the FastAPI test client. Use the frontend directory for npm.cmd run build and node --test test/coach-strategy.test.mjs.
