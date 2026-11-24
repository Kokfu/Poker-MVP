# Phase 4K — Matched opponent profiles and paired gameplay

## Policy and data audit

| Path | Evidence and policy |
| --- | --- |
| Live Coach | `HandStore` keeps manually entered hands in local SQLite. `coach.service.profile_for` replays each completed hand through `HandEngine` and rebuilds `OpponentModel`. It also feeds revealed-showdown observations to the adaptive solver. `advise` makes a fresh `AdaptiveSolverBot` for a named opponent with a completed-hand profile, or a `SolverBot` when adaptation is off or the profile is absent. The current hand's public actions condition the ranges. Coach has a read-only EV explanation pass. |
| Solver and Expert fallback | `SolverBot.decide_decision` replays the same betting history for both arms. Adaptive mode adds confidence-weighted preflop and pooled postflop locks and uses the fixed showdown model for hand ordering. The solver samples using its own seeded stream. A replay or calculation error invokes `ExpertRuleBot` and increments `fallback_count`. Phase 4J already removed the profile from the disabled fallback. |
| Simulator and Match | Both use `HandEngine`'s typed decision dispatch, including the same solver classes when those bots are selected. Independent simulation supplies no opponent profile. Persistent Match carries stacks and forwards each side's completed-hand public snapshot and showdown evidence to later decisions. Its normal fallback diagnostics cover engine action failures. A legal Expert fallback needs a separate solver counter. |
| Learning sessions | Duplicate session mode resets stacks but persists bots. It updates each arm's model after its own hands, so policies may train on different later action histories. Single-hand duplicate mode has no evidence stream. The Slumbot fingerprint is a separate, evolving-profile integration regression against a local fake referee. |
| Fixed solver benchmark | `solver.benchmark` records action mixes and timing under its own profile-collection setup. Its fast comparison checks fixture equivalence. Phase 4K measures a paired effect with the same profile input in both arms. |

The research harness supplies a frozen snapshot and a copy of the trained showdown model at the existing engine decision boundary. Its probe observes full-precision probabilities and delegates action selection to the production implementation. The exact panel uses Coach's replay and EV pass. Gameplay uses the same solve and action sampler with distinct deterministic IDs for each deal, shared across arms and orientations. It retains the live Match solver's within-hand cache and omits the read-only EV pass. The parity test rebuilds the same training corpus through SQLite and compares the snapshot, showdown evidence, concrete policy and seeded recommendation with live Coach. The comparison measures the effect of switching solver policy for a fixed trained opponent at these starting conditions.

## Training and holdout design

The [preregistered protocol](PHASE_4K_PROTOCOL.md) defines the synthetic tight-passive, loose-passive, tight-aggressive and loose-aggressive policies. Selectivity governs facing a preflop price. Aggression governs preflop raises and postflop opening bets. After a postflop wager the opponents fold or call according to hand strength and the effective cost. The pilot also includes the registered equity, expert and solver bots.

Training plays real hands against AggressiveBot, resetting 15 bb stacks and alternating the button at 50/100 blinds. Profile sizes are nested within each training stream. The engine history validator checks every event for continuity, settlement, cards, privacy and chip conservation. The model reads completed public actions, and the showdown model reads opponent cards only when legitimately revealed. No holdout hand reaches either model. Preset opponent names describe the generating policy. The profile's classification, empirical frequencies and confidence bands are measured from its own opportunities and can differ from those names. Mismatch supplies the same-size, same-stream evidence from the opposite style on both axes.

For the exact panel, two independent training streams supply 3, 30 and 100 completed hands. The four held-out Coach spots are new scripted boards and Hero holdings. The Phase 4J evaluator enumerates each of the 990 compatible holdings using Treys ranks, weights it by the probability of the full observed Villain line, and prices every action against the same conditional fold/call response. Hero's actions are scripted. EV measures changes in Hero's stack from the open decision and uses the exact engine settlement convention. The candidate mixes the matched and disabled policies with the frozen Phase 4J prior of 10 pseudo-hands. Off, matched, mismatched and candidate share the reference posterior and continuation within each row.

For gameplay, each block uses two seeded deals, each played from both seats under both arms. The full seed-derived deck stays fixed across replays, and the engine's hole cards and reached board must match it. New strategy instances share each role's seed across replays. Divergent lines can reach different random draws and different public streets. Both arms receive the same 30-hand snapshot and solve settings. An off-arm solver ignores that snapshot. Baseline opponents receive no profile. Stacks reset every hand, so match outcomes below refer to the sign of net chips summed over a block.

The exact EV table is a finite comparison. Training prefixes and repeated spots are dependent. Gameplay intervals resample whole independent profile blocks within opponent and retain both deal/seat pairings. The pooled interval weights the four synthetic opponents equally. With six blocks per opponent, individual intervals are descriptive and can be wide. The pilot has one block per opponent and supplies no interval. Findings apply to the specified opponent policies, 15 bb stacks and one training partner. Ordinary-size matches, other population mixes, live opponents, and later learning require new validation.

## Exact river EV

All figures are bb from the decision. The three rightmost columns are differences from Off. Each opponent contributes 24 rows. [Full action mixes, posteriors and EV evidence](benchmark-results/phase-4k-2026-11-18/exact.json)

| Opponent | Off EV | Matched Δ | Mismatched Δ | Candidate Δ |
| --- | ---: | ---: | ---: | ---: |
| Tight-passive | 3.176 | +0.037 | −0.032 | +0.031 |
| Loose-passive | 4.251 | +0.464 | −0.056 | +0.385 |
| Tight-aggressive | 5.276 | +0.217 | +0.174 | +0.187 |
| Loose-aggressive | 6.637 | −0.023 | +0.061 | −0.016 |
| **Pooled** | **4.835** | **+0.174** | **+0.036** | **+0.147** |

| Training prefix | Matched Δ | Mismatched Δ | Candidate Δ | Matched policy TV vs Off | Matched harmful rows and sum |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 hands | −0.009 | −0.002 | −0.002 | 1.21% | 2/32, 0.294 bb |
| 30 hands | +0.249 | +0.097 | +0.186 | 37.48% | 9/32, 1.683 bb |
| 100 hands | +0.281 | +0.015 | +0.256 | 32.55% | 10/32, 0.356 bb |

Matched EV improved by 0.154 and 0.193 bb/decision in streams 0 and 1. The largest case-level mean gain was 0.432 bb on the middle-pair spot, pooled across all opponents and profiles. The set spot barely changed. The matched advantage over mismatch averaged 0.137 bb. The predeclared exact gate still failed because matched mean EV fell against loose-aggressive.

At three hands all displayed classifications were unknown and most stats were very-low confidence. At 30 hands the preflop raise denominators were 31–45, with medium confidence, while river bet denominators ranged from 3–12 with very-low or low confidence. At 100 hands the preflop raise denominator was high confidence for all eight profiles and local river bet and fold evidence ranged from very-low to medium. The adaptive solver can gain lock confidence through pooling earlier streets. Both tight-aggressive samples were classified tight-passive at 30 and 100 hands because aggregate action counts weight frequent preflop folds. The profile classification is display metadata. Locks use opportunity-level rates.

| Policy | EV per decision | Harm count | Total harm | Mean per harmful row | Shove / smaller bet / call / check |
| --- | ---: | ---: | ---: | ---: | ---: |
| Off | 4.835 | 0/96 | 0 bb | — | 59.01% / 15.88% / 0.18% / 24.94% |
| Matched | 5.009 | 21/96 | 2.332 bb | 0.111 bb | 65.11% / 11.35% / 5.88% / 17.65% |
| Mismatched | 4.871 | 29/96 | 8.435 bb | 0.291 bb | 65.11% / 11.35% / 5.88% / 17.65% |
| Candidate | 4.982 | 21/96 | 1.653 bb | 0.079 bb | 64.54% / 11.80% / 4.77% / 18.89% |

Fold mass was below 0.01% in every arm. The balanced mismatch permutation reuses the same policy vectors against different opponents, giving the same aggregate action mix and TV as Matched. Harm counts adjustments losing more than 1e-6 bb. The candidate cut the sum of harmful losses by 29% and gave back 0.027 bb/decision relative to Matched, missing its promotion criterion. The river run took 218.75 s and peaked at 397.24 MiB resident memory.

## Why some adjustments lost EV

Mean combo-level posterior TV fell from 0.679 to 0.530 with matched profiles. Mean absolute equity error fell from 29.54 to 20.93 percentage points. TV improved on 20 of 21 harmful rows, including 16 with lower equity error. To distinguish range error from the solver's use of the range, the analysis maximized exact EV in the same legal action union under the inferred posterior and then under the true posterior. Both rankings use the true response. In 12 harmful rows the inferred-posterior optimum still incurred positive regret under the true posterior. In 17 harmful rows the inferred-posterior optimum earned more true EV than the solver mix. These counts overlap. The latter gap can combine errors in response probabilities, reach pruning and the solver's use of a mixed policy.

- **Response ranking on top pair.** On Kd Td against loose-aggressive, stream 0 at 30 hands, Matched bet 250 with 99.99% probability and lost 1.179 bb relative to Off. The solver valued the bet at +9.037 bb and the shove at +8.712 bb. With the measured opponent response and the solver's inferred range, the shove ranks first at +7.436 bb versus +5.563 bb for the bet. The true range also ranks the shove first at +7.610 bb. A closer range did not protect this sizing decision.
- **Policy mix on middle pair.** Against the same stream and opponent, Matched called 82.65% instead of 0.71%, losing 0.399 bb. Both posteriors favor the shove under the true response. Even the solver's own values favored the shove by 0.788 bb. This points to a gap between the mixed policy and action values within the existing tree. Those reported values do not establish the cause or quantify convergence.
- **Both effects against tight-passive.** On 6d 5d facing 500, stream 0 at 100 hands, the true all-in and call EVs were −6.056 and −2.618 bb, with fold at zero. The adapted range retained a 42.08-point equity error. Substituting the actual response while retaining that range still preferred a call. The live policy shoved 99.99%. The small −0.024 bb delta over Off masks large regret in both arms.

The two largest harmful rows account for 68% of matched harm. The swing between streams on loose-aggressive, thin late-street opportunities at 30 hands, and strong losses from mismatched profiles make calibration relevant. A sample-size adjustment alone would also attenuate gains when the profile fits.

## Paired gameplay

The seven-opponent pilot played 56 hands, 28 per arm, in 47.81 s with 155.73 MiB peak resident memory. Synthetic pilot blocks took 16.65 s including training, projecting about 100 s for the larger synthetic workload under pilot conditions. This cleared the time gate. The strategy output, profiles and analytic results repeated exactly on a separate run with a different Python hash seed, excluding timing and memory. [Pilot evidence](benchmark-results/phase-4k-2026-11-18/pilot.json) · [Pilot replay](benchmark-results/phase-4k-2026-11-18/pilot-recheck.json)

| Opponent | Off bb/100 | Matched bb/100 | Matched − Off |
| --- | ---: | ---: | ---: |
| Tight-passive | +75.0 | +75.0 | 0.0 |
| Loose-passive | +350.0 | +350.0 | 0.0 |
| Tight-aggressive | −37.5 | +37.5 | +75.0 |
| Loose-aggressive | −237.5 | −312.5 | −75.0 |
| Equity | +400.0 | +400.0 | 0.0 |
| Expert | +75.0 | +75.0 | 0.0 |
| Solver | +137.5 | −37.5 | −175.0 |
| **Pooled pilot** | **+108.9** | **+83.9** | **−25.0** |

The preregistered larger run played 192 hands, 96 per arm, in 24 independently trained profile blocks. Its primary result was **−85.94 bb/100 [−191.15, +1.04]**. The bootstrap interval includes zero and the lower bound is far below the advancement gate. The wide intervals and small opponent-specific samples limit estimates of the effect. [Larger benchmark evidence](benchmark-results/phase-4k-2026-11-18/larger.json)

| Opponent | Off bb/100 | Matched bb/100 | Matched − Off | Paired 95% interval | Block W–L, Off → Matched |
| --- | ---: | ---: | ---: | ---: | --- |
| Tight-passive | +118.75 | +58.33 | −60.42 | [−168.75, +29.17] | 5–1 → 3–3 |
| Loose-passive | −77.08 | −106.25 | −29.17 | [−208.39, +141.67] | 4–2 → 3–3 |
| Tight-aggressive | +177.08 | +85.42 | −91.67 | [−229.17, +29.17] | 4–2 → 5–1 |
| Loose-aggressive | +143.75 | −18.75 | −162.50 | [−487.50, 0.00] | 5–1 → 4–2 |
| **Pooled** | **+90.63** | **+4.69** | **−85.94** | **[−191.15, +1.04]** | **18–6 → 15–9** |

On the larger panel, Off won 67 and lost 29 hands, while Matched won 65 and lost 31. There were no ties. The paired block delta was positive in six blocks, zero in seven and negative in 11. All 248 pilot and larger gameplay hands passed history, seeded deal, and chip conservation checks. There were zero illegal actions, invalid hero probability mixes or unexpected solver fallbacks in either arm, including against the registered solver pilot opponent. The larger run took 289.13 s with 158.67 MiB peak process resident memory and 2.67 s of profile training. Summed hand runtimes were 107.51 s Off and 175.89 s Matched, with 177 and 144 Hero decisions and 148 and 101 solves respectively. The arms reached different game paths. These are observed end-to-end costs on a machine also running verification.

The first strategy action diverged on 35 of 96 same-seat comparisons. Realized net changes from these replays sum to −2,550 chips for 17 comparisons first differing preflop, −3,700 chips for 12 first differing on the flop, and −2,000 chips for six first differing on the turn. Every first divergence was a Hero decision. One loose-aggressive block accounted for −3,900 of the total −8,250 chips across all blocks, and the other five blocks against that opponent were tied between arms. For example, on seed 43303000 from seat B, Off first checked the flop and lost 200 chips. Matched bet 200 and lost 1,500. These are realized path differences with a single shared deal per orientation. Estimating the EV of those earlier decisions requires a continuation model beyond the closing-river evaluator. The river panel's positive mean cannot establish a gain across full hands.

## Phase 4L recommendation

**Keep the current production strategy and take option C into Phase 4L.** The exact gain cleared the pooled effect size and repeated across two training streams. The negative loose-aggressive mean failed the per-opponent gate. Gameplay favored Off in the observed sample and failed the practical and statistical gates. The confidence-limited mix also missed its exact-EV comparator gate.

First isolate where the current solver loses the value of a better range. Keep the existing tree and budgets. Use a fresh terminal panel with known opponent action likelihoods and responses, substitute the true incoming reach and true response policy one at a time and together, then compare the sampled mix, the reported EV ranking, and the exact payoff ranking. Inspect numerical convergence in the current tree when the solver's reported values and action mix diverge. Option B can help when late-street opportunities are scarce, but shrinkage left the response and action-ranking errors in place here. Option D should follow evidence that the current tree or the solve budget remains the limiting factor after correcting the inputs. Extend subsequent paired tests to preflop and flop exposure because those streets account for most observed gameplay losses. The evidence does not call for expanding MCCFR.

## Verification and Git status

- Focused regression passed 13 tests in 15.20 s with eight dependency deprecation warnings. The four new checks cover SQLite Coach parity, the full-path synthetic posterior and response sizing, deterministic duplicate play with a frozen profile, and whole-block intervals. The focused run also covered the independently validated Phase 4J evaluator and disabled fallback isolation.
- The research regression passed 101 tests in 393.53 s with seven eval7 dependency deprecation warnings. This included the retained exact, CFR and MCCFR controls.
- The full backend regression passed **922 tests**, preserving the 918-test baseline and adding four deterministic checks. It took 1,292.66 s with eight existing dependency deprecation warnings. The run used one BLAS thread and local loopback for the HTTP integration tests.
- Each exact run completed 100 solver decisions with legal normalized mixes and zero fallbacks. The second run reproduced all 96 four-policy score rows and summaries exactly after excluding runtime and peak memory. It took 225.98 s and peaked at 396.90 MiB. The pilot replay also matched after excluding timing and memory. Both replays used Python hash seed 31. [Exact replay](benchmark-results/phase-4k-2026-11-18/exact-recheck.json)
- `pip check` found no broken requirements. The frontend production build and the Coach solver/fallback render test passed.
- `git diff --check` and whitespace checks on the new files passed. Git reported an existing Windows LF/CRLF advisory. The branch is `main` at `3e89367`, 19 commits ahead of local `origin/main`. Phase 4K added four untracked files. The working tree still contains the prior milestone changes. The raw evidence is under the existing ignored `benchmark-results/` directory. No commit, push, or deployment was made.

| Phase 4K file | Purpose |
| --- | --- |
| `PHASE_4K_PROTOCOL.md` | Frozen experiment design and advancement criteria |
| `PHASE_4K_REPORT.md` | Audit, outcome and recommendation |
| `backend/research/holdem/phase_4k.py` | Offline profile training, exact scoring and paired gameplay runner |
| `backend/test_research_holdem_phase_4k.py` | Deterministic regression checks |

## Reproduction

Run from `backend` with a new output directory and the local virtual environment. The research CLI refuses to overwrite evidence. The protocol gives the external time cap and the condition for launching the larger run.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$py = '.\.venv\Scripts\python.exe'
$out = '../benchmark-results/phase-4k-reproduction'
New-Item -Path $out -ItemType Directory | Out-Null
& $py -m research.holdem.phase_4k pilot "$out/pilot.json"
& $py -m research.holdem.phase_4k exact "$out/exact.json"
& $py -m research.holdem.phase_4k larger "$out/larger.json"
```
