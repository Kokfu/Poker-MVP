# Phase 4L — Solver oracle decomposition and decision EV

## Solver input audit

| Stage | Live Coach implementation | Implication for the river decision |
| --- | --- | --- |
| Observation | Coach replays the spot through `HandEngine` with the entered public board and Hero cards. It stops at the first open Hero decision. For a named opponent with completed records, adaptive Coach rebuilds action and opportunity counts from SQLite and uses legitimately revealed showdowns for hand-strength evidence. | The profile's type label is display metadata. The solve consumes opportunity-level statistics and the current hand's public line. Oracle inputs are confined to the offline runner. |
| Estimated reach | The solver starts both public ranges uniform, chooses the nearest effective-stack preflop chart and walks the chart using the likelihood of each observed action. It masks board cards street by street, solves each street and multiplies the actor's weights by the chosen per-combo strategy. Postflop it prunes combos at 0.5% of the largest reach and retains the actual Hero combo. Off-menu actions use the nearest abstract action to update reach before a re-solve at the actual public state. | An observed amount can produce exact pot geometry but an approximate likelihood. The display range is captured before the final re-solve's pruning on off-menu lines. This experiment uses conditioned reach from the final solver, masking Hero's blockers, and records the display difference separately. |
| Betting inputs | Public commitments, stacks, last full raise and acted flags reconstruct the pot and legal targets. The solver combines the call price with remaining stacks and the mapped action tree. Pot odds enter via incremental payoffs and possible showdown receipts. | In the checked-to historical case the pot is 500 chips and both players have 1,250 behind. Facing an ordinary wager, the closing call breaks even at call divided by pot plus call under an exact showdown split. |
| Concrete sizes | The default postflop tree offers half-pot and pot bets at first aggression, a pot-sized raise after one aggressive action, and an effective all-in. Targets are rounded up, bumped to a legal minimum and merged into the shove at 85% of the cap. The bot concretizes the sampled abstract action against engine legality. | Legal integer sizes can be absent. With equal stacks in this panel, the tree shove and concrete all-in have the same target. Actual supported and unrestricted legal regret are measured separately. |
| Opponent response | Unlocked postflop responses come from discounted CFR. Adaptive Coach partially blends an opponent strategy toward smoothed, confidence-weighted, pooled action groups. Fitting preserves an estimated ordering by hand, with a flat component informed by revealed showdowns. Facing-bet groups cover fold, call and aggression. Default Coach does not enable the size-conditioned lock experiment. | The live probabilities can vary with size through the game tree, while the observations used to anchor them pool prices. Even a never-raising reference can receive a large modeled raising probability on a particular branch. Pooled counts and selective showdown observations do not identify a per-hand response curve for each candidate action. |
| Values and recommendation | River leaf ranks are exact in the production equity matrix. `RangeSolver.action_values` prices each action using the final policy, divides by compatible incoming villain mass, and adds back Hero's contribution to measure net chips from the decision. Coach displays rounded values. The bot independently samples the actual Hero combo's average strategy using a stable hash-derived seed. | The value display is read-only. The strategy is an average from coupled regret updates over both public ranges, so its modal action need not maximize EV under the final average continuation. The decision path counts calculation fallbacks. |

Source paths are [Coach replay](backend/coach/service.py#L139), [decision-state construction](backend/simulation/decision_state.py#L175), [live solver](backend/solver/bot.py#L279), [betting tree](backend/solver/tree.py#L128), [opponent locks](backend/solver/exploit.py#L106) and [value traversal](backend/solver/cfr.py#L298).

To audit the arithmetic, the runner independently enumerates Treys ranks and propagates the frozen policies to stack receipts, then compares each value in chips to the live solver's unrounded traversal. On the fixed reference branch it independently uses the Phase 4J terminal evaluator. Engine settlement tests separately validate the price boundary, all-in, total targets and conservation. Incorrect true action rankings reproduced in the tested states even when modeled payoffs matched the model's own inputs. The audit covers the recorded equal-starting-stack, heads-up river trees. It leaves off-menu hand inference, unsupported bet sizes and the convergence of the coupled solve as model and policy limitations to measure.

## Experiment specification

Development uses the four Phase 4K boards at 15 bb, 50/100 blinds, stream 0 at 30 training hands. The 96-row holdout crosses four fresh scripted boards, four reference styles, independent profile streams 9 and 10, and 15, 9 and 30 bb starting stacks. The 15 bb holdout is the primary comparison. The 9 and 30 bb panels reuse the same frozen 15 bb profiles to measure depth sensitivity. All rows script Hero's preflop open, Villain's call, check-through flop and turn, then Villain's river check or 500-chip bet. The new open targets are 250, 300 and 350 chips, producing pots from 500 to 1,200 chips at decision. The estimand is exact conditional decision EV against a finite set of synthetic opponents. Repeated boards and profiles induce dependence. [Frozen protocol](PHASE_4L_PROTOCOL.md)

The reference range starts uniformly across the 990 holdings compatible with Hero and the public river. Each weight is multiplied by the known likelihood of preflop participation and declining to raise, checking the flop and turn, and the observed river action. The reference continuation depends on Villain's own holding rank and the effective call price relative to the pot. The small-price band applies when twice that price is at most the pot before the call. Both passive and aggressive styles have zero postflop raise probability, with different opening and calling rates. The evaluator integrates over hidden holdings. No strategy is fed an actual opponent deal or future information.

| Arm | Decision-time range | Response model |
| --- | --- | --- |
| A — Controlled baseline | Estimated | Final estimated Coach continuation |
| B — Range oracle | True | Same frozen estimated Coach continuation |
| C — Response oracle | Estimated | True per-holding response at each legal menu action |
| D — Full oracle | True | True per-holding response at each legal menu action |

All four arms use 80 discounted regret-matching steps at the Hero decision under fixed action values. This keeps the root converter and estimated continuation constant across substitutions. The estimated response stays fixed when the range changes. The live adaptive policy is retained as a separate control using its exact replay, action mix and seeded recommendation. A's modeled values are audited against live; the difference in their realized reference EV measures the effect of replacing its root mix under the same modeled payoffs. The full oracle tests conversion in this controlled fixed-response problem. Convergence of the coupled live solve is a separate question.

For A and B, if the model's Villain raises, the audit follows the frozen modeled Hero continuation. When a combo was pruned, B uses the average modeled response of the nearest retained Treys rank, pooling all equally near donor holdings. A assigns those holdings zero reach. This extension is an explicit modeling choice and its role depends on how much true probability lies outside retained support. C and D need no modeled re-raise continuation. The same exact reference scores every policy mix. Fold is zero relative to the open decision. Showdown receipts are based on matched contributions after refunding excess. For the best legal action, the runner checks the endpoints of both price regions, the effective cap and the closing passive actions. Payoff is affine in integer wager size within each price region for these equal-commitment paths. A shallow regression compares the endpoint result with exhaustive enumeration.

## Largest Phase 4K loss

Hero held Kd Td on Kh 7d 4s Qc 3h, checked to on the river against loose-aggressive after training for 30 hands on stream 0. The pot was **5 bb**, both remaining stacks were **12.5 bb**, the legal actions were check, bet 100–1,250, or all-in. The tree offered check, bet 250, bet 500 and all-in to 1,250 chips. The Phase 4K off mix earned **7.074373 bb** and the live matched mix earned **5.895088 bb**, reproducing a loss of **1.179285 bb**. The live recommendation was bet 250. [Phase 4K exact evidence](benchmark-results/phase-4k-2026-11-18/exact.json) · [Phase 4L reconstruction and 990 combo weights](benchmark-results/phase-4l-2026-11-18/development-final.json)

| Range | Equity vs Villain | Combo TV from true |
| --- | ---: | ---: |
| Disabled live estimate | 97.76% | 37.27% |
| Adaptive live estimate, A/C | 91.45% | 34.49% |
| Reference posterior, B/D | 98.62% | 0% |

Adaptation improved the combo TV by 2.78 percentage points and worsened the equity error from 0.86 to 7.17 points. All true mass was inside the retained river support in this spot.

| Action | Live and A EV | B EV | C EV | D and true EV |
| --- | ---: | ---: | ---: | ---: |
| Check | 4.572 | 4.931 | 4.572 | 4.931 |
| Bet 250 | 9.037 | 9.693 | 5.563 | 5.895 |
| Bet 500 | 7.928 | 8.523 | 6.548 | 6.847 |
| All-in | 8.712 | 7.838 | 7.436 | 7.610 |

| Arm | Bet 250 F/C/R | Bet 500 F/C/R | All-in F/C/R |
| --- | ---: | ---: | ---: |
| Live and A | 33.04/26.91/40.04% | 38.07/28.30/33.63% | 51.58/48.42/0% |
| B | 38.10/27.79/34.11% | 46.69/26.07/27.24% | 74.26/25.74/0% |
| C | 43.73/56.27/0% | 43.73/56.27/0% | 61.14/38.86/0% |
| D and true | 59.62/40.38/0% | 59.62/40.38/0% | 76.87/23.13/0% |

A check closes the river. F/C/R gives fold, call and all raising mass conditional on the candidate and the arm's range. The per-holding oracle applies the small-price rule for both nonshove sizes here. The 250-chip bet under the live continuation was valued 3.474 bb higher than under the true continuation with the estimated range held fixed. The corresponding shove overvaluation was 1.276 bb. The modeled raises after a small bet and the way calls and folds are distributed across hands allowed the small bet to outrank the shove. Replacing the range alone made the wrong ranking stronger. Replacing the response alone made the shove optimal by 0.888 bb over the next-best modeled size. The true shove is best in both the supported and unrestricted legal sets.

The modeled raise after bet 250 was a shove, worth 13.926 bb conditional on that branch. Its 40.04% probability contributed 5.576 bb of modeled EV. In a one-spot sensitivity check, zeroing modeled raises and renormalizing each hand's existing fold and call weights reduced bet-250 EV to 5.741 bb and bet-500 EV to 6.697 bb. Shove stayed at 8.712 bb. That single perturbation restored the ranking and isolates the modeled reraise opportunity as the main mechanism for the historical sizing error. [Historical branch decomposition](benchmark-results/phase-4l-2026-11-18/historical-response-branches.json)

| Policy | Check | Bet 250 | Bet 500 | All-in | True EV | Supported regret |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Disabled live | 0.0017% | 5.5347% | 57.7371% | 36.7265% | 7.07437 | 0.53533 |
| Adaptive live | 0.0006% | 99.9850% | 0.0018% | 0.0126% | 5.89509 | 1.71461 |
| A | 0.0006% | 99.9864% | 0.0012% | 0.0118% | 5.89507 | 1.71463 |
| B | 0.0006% | 99.9968% | 0.0019% | 0.0007% | 5.89488 | 1.71481 |
| C | 0.0006% | 0.0006% | 0.0019% | 99.9970% | 7.60966 | 0.00004 |
| D | 0.0006% | 0.0006% | 0.0020% | 99.9969% | 7.60966 | 0.00004 |

A separate Phase 4K middle-pair control shows selection can matter. Against the same profile, live called 82.65% while its estimated shove EV was 5.667 bb versus 4.879 bb for calling. Independent true EVs were 3.968 and 3.482 bb respectively. The root EV selector gained 0.402 bb there. This contrast with the top-pair case motivated testing the selector on the fresh panel.

## Holdout results

EV and regret are in bb per decision. Regret is relative to the best action on the existing concrete menu. Harm counts EV below A by more than 0.000001 bb. The raw artifact includes the full legal action interval, per-action estimated and true EVs, conditional first-reply probabilities, policy mixes, and both ranges for each row. [96-row holdout evidence](benchmark-results/phase-4l-2026-11-18/holdout.json)

| Policy | 15 bb mean EV | 15 bb median | 15 bb worst EV | 15 bb harm | 15 bb mean regret | 15 bb action EV MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Live adaptive | 7.109 | 6.470 | 0.421 | 18/32 | 0.374 | 1.695 |
| A — Estimated/estimated | 7.184 | 6.472 | −0.921 | 0/32 | 0.299 | 1.695 |
| B — True range | 7.422 | 6.472 | 2.233 | 16/32 | 0.061 | 0.718 |
| C — True response | 7.327 | 6.472 | 0.767 | 19/32 | 0.155 | 1.673 |
| D — Both true | 7.482 | 6.472 | 2.233 | 18/32 | 0.00015 | 0 |

| Policy | All-depth mean EV | Median EV | Worst EV | Harm vs A | Worst delta vs A | Mean / max regret | Action EV MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Live adaptive | 7.215 | 6.368 | −0.861 | 53/96 | −8.634 | 0.611 / 8.635 | 1.928 |
| A | 7.220 | 6.468 | −5.851 | 0/96 | 0 | 0.606 / 8.084 | 1.928 |
| B | 7.493 | 5.951 | 1.766 | 38/96 | −3.822 | 0.333 / 3.822 | 0.883 |
| C | 7.529 | 6.468 | −5.851 | 43/96 | −2.959 | 0.297 / 8.084 | 1.884 |
| D | 7.826 | 6.629 | 2.233 | 34/96 | −0.00127 | 0.00012 / 0.00130 | 0 |

At a descriptive 0.01 bb loss threshold, B, C and D harmed 6, 10 and 0 of 96 rows respectively. At 15 bb the counts were 0, 6 and 0. The full oracle's negative deltas at the protocol threshold arise from finite mixing on nearly or exactly the same best action as A. Selecting the highest D value deterministically has zero supported regret. The independent modeled-payoff audit matched live across the holdout within 0.00081 chips per action.

### Range and response interaction

| Stack | Live | A | B | C | D | B−A | D−C | C−A | D−B | Interaction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 bb | 7.109 | 7.184 | 7.422 | 7.327 | 7.482 | +0.238 | +0.155 | +0.144 | +0.061 | −0.083 |
| 9 bb | 6.385 | 6.379 | 6.450 | 6.467 | 6.559 | +0.071 | +0.092 | +0.088 | +0.108 | +0.020 |
| 30 bb | 8.151 | 8.096 | 8.608 | 8.793 | 9.437 | +0.512 | +0.644 | +0.697 | +0.829 | +0.132 |
| Equal weight across depths | 7.215 | 7.220 | 7.493 | 7.529 | 7.826 | +0.274 | +0.297 | +0.309 | +0.333 | +0.023 |

Each depth has 32 rows. B−A and D−C measure the range effect under estimated and true response. C−A and D−B measure the response effect under estimated and true range. The interaction is D−C−B+A. The primary 15 bb panel shows overlap in gains from the two substitutions. Deeper stacks give greater value to the response model and a positive interaction. Full-oracle EV exceeds live by **0.374 bb** at 15 bb and **0.611 bb** pooled. Root conversion alone gives **+0.075 bb** at 15 bb and **+0.005 bb** pooled.

| Opponent | Stack | A | B | C | D |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tight-passive | 15 | 3.349 | 4.213 | 3.759 | 4.213 |
| Loose-passive | 15 | 5.868 | 5.956 | 6.165 | 6.198 |
| Tight-aggressive | 15 | 8.922 | 8.922 | 8.789 | 8.922 |
| Loose-aggressive | 15 | 10.597 | 10.597 | 10.597 | 10.597 |
| Tight-passive | 9 | 3.678 | 4.044 | 3.711 | 4.078 |
| Loose-passive | 9 | 5.512 | 5.430 | 5.628 | 5.628 |
| Tight-aggressive | 9 | 7.499 | 7.499 | 7.595 | 7.595 |
| Loose-aggressive | 9 | 8.828 | 8.828 | 8.934 | 8.934 |
| Tight-passive | 30 | 1.455 | 4.150 | 2.873 | 4.681 |
| Loose-passive | 30 | 5.960 | 6.551 | 6.943 | 7.309 |
| Tight-aggressive | 30 | 10.981 | 9.741 | 11.320 | 11.320 |
| Loose-aggressive | 30 | 13.988 | 13.988 | 14.035 | 14.437 |

The tight-passive missed draw drove much of the range benefit. With As Ts on Ks 8d 5s 3h 3c at 30 bb, shoving earned −5.851 bb and the check earned 2.233 bb. B and D shifted to check in both profiles and gained 8.084 bb over A. Against the tight-aggressive reference at the same depth and board, B instead lost 3.822 bb in each stream. B's improvement in average action EV calibration coexists with wrong sizing rankings when the continuation still misprices the response. Across depths, D gained more than 0.01 bb on 37 rows. Excluding all six tight-passive missed-draw rows leaves a gain of 0.364 bb per decision. C gained above 0.01 bb on 32 rows, while B did so on 14. The D mean was identical across the two streams because it uses the same known inputs at each board, depth and opponent. Stream interactions varied from −0.077 to +0.123 bb.

The estimated range differed from the true range by an average 48.69% combo TV. True mass missing from the retained modeled support averaged 7.46% and reached 64.39%. On the 53 rows below 1% omitted mass, B, C and D gained 0.299, 0.377 and 0.527 bb respectively over A. On the other 43 rows the gains were 0.242, 0.226 and 0.704 bb. B depends on the stated nearest-rank response extension. These strata are descriptive. On the 16 off-menu rows where the displayed and solved weights diverged, their TV reached 1.43%. The initial holdout attempt stopped at this difference. The runner was corrected to take the actual final solve reach for both estimated-range arms, with the frozen inputs, holdout rows and gates retained.

### Action frequencies and missing sizes

| Policy | All-in | Smaller bet | Non-all-in raise | Check | Call |
| --- | ---: | ---: | ---: | ---: | ---: |
| Live adaptive | 87.78% | 6.38% | 1.97% | 3.86% | 0.01% |
| A | 99.04% | 0.93% | 0.02% | <0.01% | 0.01% |
| B | 80.20% | 2.09% | 2.08% | 11.46% | 4.17% |
| C | 57.87% | 26.03% | 16.10% | <0.01% | 0.01% |
| D | 61.67% | 12.50% | 12.50% | 6.25% | 7.08% |

Folds were below 0.01% throughout. Correcting the range chiefly recovered check and call options, while correcting responses moved substantial mass from shoves to smaller aggressive sizes. At 15 bb the shove share was 83.70% in live, 99.99% in A, 84.37% in B, 68.79% in C and 78.75% in D.

Four holdout rows had an omitted best legal action, all on second pair facing 500 against loose-passive. At 15 bb the tree offered fold, call and shove. At 30 bb it also offered raise to 2,200. The minimum raise to 1,000 was best at both depths and absent from both menus, costing 0.115 and 0.118 bb, respectively, versus the best supported action. Across all 96 rows the mean abstraction cost was 0.00487 bb. The largest historical loss had the correct size available. Across this holdout, model input error accounts for more supported regret than the available size menu.

## Controlled research candidate

The candidate takes the argmax of the live solver's full-precision final action values and concretizes that action through the existing legalizer. Development cleared the predeclared eligibility conditions. Mean true EV increased 0.008 bb, the model-valued improvement was 0.132 bb, and three of four opponent means rose. The historical middle-pair case gained 0.402 bb, while the historical top-pair case still chose bet 250.

The holdout candidate **failed**. Its 15 bb gain was **+0.075 bb** against the +0.10 bb gate. The 9 bb and 30 bb deltas were −0.007 and −0.056 bb. Tight-passive and loose-passive means declined by 0.609 and 0.033 bb. It lost EV on 31/96 rows and lost 5.180 bb on the worst 30 bb missed-draw row. On that row the live policy checked 63.99%, while the candidate shoved because the live model saw 4.882 bb for shoving and 4.091 bb for checking. The true values were −5.851 and +2.233 bb. The full oracle gained 0.607 bb per decision over the candidate pooled. At 15 bb the candidate shoved in every holdout row. A more decisive selector amplified risk from the misranked values.

A separate 16-decision timing workload used the same 15 bb holdout spots and stream 9 in two processes. The greedy arm retained only the river solver for its value pass. The pass averaged **7.38 ms** and action selection plus legalization averaged **0.030 ms**. Process peaks were **157.48 MiB** for the live solve without the EV pass and **164.14 MiB** for greedy. The observed end-to-end means were 1.855 and 2.559 s under unequal concurrent verification load, so the timed pass is the direct estimate of incremental compute. Coach already requests a read-only action EV pass. [Live timing](benchmark-results/phase-4l-2026-11-18/time-live.json) · [Greedy timing](benchmark-results/phase-4l-2026-11-18/time-greedy.json)

## Phase 4M recommendation

The results support **D, interacting limitations**. At 15 bb the range substitution moved mean EV and calibration the most. The historical loss and the larger 30 bb response gain identify an independent response-model problem. The full oracle nearly eliminated supported regret through the common selector. The live action EV arithmetic passed the independent payoff audit, and greedy selection with the estimated inputs failed.

Build a research-only river continuation interface that holds the incoming posterior fixed and prices each existing candidate through a separate fold/call/raise model conditioned on effective price and public state. Start by fitting and validating the price-specific outcome frequencies against fresh, legally observed decisions, with pooled shrinkage for sparse contexts. Integrate any estimated holding dependence over the available posterior. Showdown data are selected by the observed line, so measure calibration and support before trusting hand-dependent extrapolation. The previously tested sized locks still blend estimates into a coupled solver. The proposed interface exposes per-action continuation and its resulting ranking for an independent test. Keep the menu fixed in that test, and ablate range support repair separately because the 15 bb panel showed a material range contribution. Evaluate prediction and exact EV across opponents and depths before a paired gameplay trial. Phase 4L uses an isolated river runner.

## Verification and Git status

- Focused verification passed **18 tests** in 14.96 s, with seven existing eval7 dependency deprecation warnings. Six Phase 4L cases cover deterministic tie-preserving conversion, three actual-engine response and settlement controls, exhaustive validation of the size optimum, and parity of modeled and independent oracle values.
- The research suite passed **107 tests** in 300.47 s with the same seven warnings, including the retained Kuhn, exact CFR and MCCFR controls.
- Development replay matched exactly across Python hash seeds 13 and 31 after excluding timing and memory. Development took 44.53 s and 223.88 MiB, with 35.19 s and 223.63 MiB on replay. All 96 holdout rows and summaries also repeated exactly under hash seed 31. The holdout took 195.11 s and 322.82 MiB, with 119.12 s and 323.10 MiB on replay. [Development replay](benchmark-results/phase-4l-2026-11-18/development-final-replay.json) · [Holdout replay](benchmark-results/phase-4l-2026-11-18/holdout-replay.json)
- Each development run checked 20 live decisions, each holdout run checked 96, and the separately timed policies checked 32 combined. The runner required zero unexpected fallbacks, legal target totals, normalized policies and chip conservation. Training used the Phase 4K completed-history validator. Independent tests settled the bet-500, bet-501 and all-in fold and call branches in the engine.
- `pip check`, the frontend production build and the existing Coach solver/fallback render test passed.

- The full backend regression passed **928 tests** in 632.54 s, preserving all 922 baseline tests and adding six Phase 4L cases. It reported eight existing dependency deprecation warnings. The first sandboxed attempt stalled while Windows asyncio created its local socket pair for the first API test. A bounded diagnostic confirmed the stall, and the full rerun completed with local loopback available.
- Git remains on `main` at `3e89367`, 19 commits ahead of local `origin/main`. Phase 4L adds this report, the protocol, the isolated research runner and its test module. Prior working-tree changes, historical fixtures and benchmark artifacts were retained. New evidence is in the existing ignored `benchmark-results/` directory. The work is local and uncommitted. `git diff --check` and new-file whitespace checks passed with an existing LF/CRLF advisory on `backend/test_poker.py`.

## Reproduction

Use the backend virtual environment and a new output directory. The runner creates each output exclusively. The PowerShell example bounds each process externally and runs offline.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONHASHSEED = '13'
$py = '.\.venv\Scripts\python.exe'
$out = '../benchmark-results/phase-4l-reproduction'
New-Item -Path $out -ItemType Directory | Out-Null
$run = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:], timeout=int(sys.argv[1])).returncode)'
& $py -c $run 240 $py -m research.holdem.phase_4l development "$out/development.json"
& $py -c $run 900 $py -m research.holdem.phase_4l holdout "$out/holdout.json"
& $py -c $run 240 $py -m research.holdem.phase_4l time-live "$out/time-live.json"
& $py -c $run 240 $py -m research.holdem.phase_4l time-greedy "$out/time-greedy.json"
```
