# Phase 4W — Live Coach persistent opponent beliefs

**Outcome A. Architecture validated. Strategy promotion declined.** The flagged live Coach recovered all 990 Hero-compatible holdings in the historical collapse. Repaired live Coach and the Phase 4V adapter produced identical posterior weights, CFR column mappings, concrete mixes and seeded actions on the matched postflop replays. The disabled Coach and Match reproduced the archived production outputs. On the fresh exact-EV panel, the repaired policy averaged **+0.299 bb** over incumbent with a 95% paired interval of **[−2.528, +2.885] bb**. Its worst adjustment cost **17.690 bb**. Both local flags default to off. [Frozen protocol](PHASE_4W_PROTOCOL.md) · [Architecture evidence](benchmark-results/phase-4w-2026-11-19/architecture-summary.json) · [Exact-EV evidence](benchmark-results/phase-4w-2026-11-19/holdout-13.json)

## Root cause and call graph

Coach’s advice service creates a new advisor, builds a public opponent profile from completed local histories when a name is supplied, and replays the manually entered prefix through `HandEngine`. `SolverBot._decide` owns the two incumbent per-hand reach arrays. It multiplies observed preflop actions by chart probabilities and applies a community-card mask at the start of each postflop street. With preflop locks, `_preflop_policy` supplies those probabilities from a 169-class solve expanded to every combo through `COMBO_CLASS`. The incumbent postflop path uses `_street_solve` or a current-state re-solve. `_solve` creates a computational subset from the board-legal arrays by retaining columns above 0.005 of the maximum weight and forcing the solving seat's own combo. It indexes the selected weights into scratch inputs and returns a `StreetSolve` with combo IDs, the strategy, value access and diagnostics. [Coach service](backend/coach/service.py) · [Solver replay](backend/solver/bot.py)

The destructive incumbent assignment is `ranges[step.player] = self._apply_strategy(ranges[step.player], solve, node, choice)`. This is the single live write that takes a postflop CFR result into replay reach. `_apply_strategy` creates a zero-filled full-size vector and writes `weight × observed-action probability` only for the selected IDs. The assignment runs after every mapped historical postflop action, including actions on the current street. Off-tree re-solves and subsequent streets consume those arrays. `np.where`, advanced indexing and the zero-filled result all allocate new arrays. The damage comes from replacing the replay owner's vector, even when there are no shared mutable references. `_HandMemory` retains street solutions within a hand. Match bots reconstruct reach per decision and reset that cache when the hand key changes. A new reconstruction can reproduce an earlier damaging assignment. [Writeback and solver result](backend/solver/bot.py) · [Phase 4V root-cause trace](PHASE_4V_REPORT.md)

In the profiled archive the turn check reduced 1,119 positive board-legal holdings to one. The selected holding represented about 65.986% of the incoming public weight. The next board card, `6s`, blocked the holding. The disabled path reproduced `ReplayError: empty range` and chose fold through the Expert fallback. The enabled path also chose fold on that river, using a normal solver result with effective opponent support of 466.794 and 990 positive compatible holdings. [Archived replay](benchmark-results/phase-4v-2026-11-19/final13/collapse-profiled.json) · [Flagged replay](benchmark-results/phase-4w-2026-11-19/architecture-verified-13.json)

## Range ownership and flags

- `ReplayBeliefs` is reconstructed per decision. Read-only board-public reaches apply chart probabilities preflop and the Phase 4V public action law postflop. The live opponent posterior conditions this public reach on Hero blockers at initialization, every observed opponent action, and each board reveal. Hero's actions can update Hero's own public reach. The actual opponent posterior stays fixed on a Hero action. Profile fitting uses public reach at the exact historical action state and public board prefix, so the fit has no private Hero or future-card information. The preflop chart and its existing adaptive lock use a fixed preflop abstraction independent of postflop projection choices. [Belief owner](backend/research/holdem/live_persistent.py) · [Shared likelihood](backend/research/holdem/decoupled_replay.py)
- An update is staged before publishing. A true zero-probability observation or a fully blocked distribution raises `RangeSupportError`, leaves the last valid snapshot intact, and yields the existing legal Expert fallback with a reason. Sparse tests cover a one-column working set, a Hero-only contradiction and blockers. Solver inputs have their own scratch arrays and read-only mappings. They record omitted board-public mass per seat and omitted Hero-compatible opponent mass. The existing compatibility matrix excludes colliding pairs throughout the subgame. That lets CFR represent counterfactual Hero holdings while the actual opponent posterior excludes all holdings that collide with the known Hero cards. [Range owner](backend/research/holdem/live_persistent.py) · [Regressions](backend/test_research_holdem_phase_4w.py)
- A flagged postflop decision enters the solver at a single reconstructed current root and uses the existing DCFR iterations, action legalization, explanation and chooser. Historical street solves and solver-frequency writeback are absent from this branch. The live experimental inference uses the Phase 4V adapter's public model, cutoff and selector. Gated and sized Match modes retain their optional unlocked pass at the same root. Current-root solving and the observed-action model can both change the strategy. [Solver integration](backend/solver/bot.py)
- Set `POKER_COACH_PERSISTENT_RANGES=1` for the local Coach advice service. Set `POKER_MATCH_PERSISTENT_RANGES=1` independently for built-in Match and history generation, including Single Hand and Persistent Match Replay. Only the literal `1` enables each flag. The environment flags apply when the respective service constructs an advisor or solver. Policy probes can directly opt in on their own bot instance. History and client schemas keep their existing contracts. [Coach flag](backend/coach/service.py) · [Match flag](backend/simulation/match_service.py) · [Replay construction](backend/simulation/history_service.py)

## Multi-street validation and live comparison

Six archived Coach hands gave 24 open decisions, including 18 postflop, plus six complete scripted settlements. All 24 disabled responses matched the Phase 4V records after timing fields were removed. Flagged and directly observed paths chose the same actions and sources. The enabled path made four different seeded recommendations relative to incumbent. Seventeen of the 24 concrete mixes changed, with maximum TV 0.984. All enabled policies were legal and normalized. The profiled incumbent river was the sole fallback in the archived panel. The short river call paid 500 chips, refunded 1,500 to Villain, and settled the contested 3,000-chip pot. [Coach runs](benchmark-results/phase-4w-2026-11-19/architecture-verified-13.json) · [Phase 4W regressions](backend/test_research_holdem_phase_4w.py)

A supplementary complete hand covered two legal Hero decisions on the same flop. Hero faced a check, bet 200, then faced a raise to 600. The outstanding price moved from zero to 400 and the effective opponent count moved from 681.35 to 482.12. Both results normalized, reconstructed identically when different unrevealed Villain cards were supplied, and matched across hash seeds. The test also completed and validated the turn and river settlement. [Supplemental replay](benchmark-results/phase-4w-2026-11-19/same-street-13.json) · [Fixture](benchmark-results/phase-4w-2026-11-19/same-street.py)

At every audited flagged update, direct reweighting of the previous Hero-compatible posterior by the likelihood or new blocker mask reproduced the actual posterior within 1e-15. No update resurrected zero weights. Across the 18 nominal postflop comparisons with the adapter, the maximum absolute weight difference and concrete policy TV were both zero. The projection matrix ran 72 solves for B and 72 for C across the two collapse lines, three streets and 12 configurations per prefix. Both arms kept bit-identical posterior weights across budgets and seeds. B matched C's global CFR column IDs and advice at every setting. Working-set changes moved concrete policy TV by up to 0.992 from nominal while the next replay's opponent weights held fixed. The profiled river used 380 Hero columns and 896 Villain columns at nominal, omitting 0.202% of Hero-compatible opponent probability from the solve. [Architecture run](benchmark-results/phase-4w-2026-11-19/architecture-verified-13.json) · [Paired summary](benchmark-results/phase-4w-2026-11-19/architecture-summary.json)

| Profiled river cap per seat | Hero-compatible mass omitted across ranked and seeded selection |
| ---: | ---: |
| 32 | 84.678%–94.993% |
| 128 | 61.215%–78.466% |
| 384 | 31.284%–41.967% |
| 896 | 0.202%–0.224% |

## Match and Replay

All four built-in solver variants share the incumbent assignment, so Match receives its own opt-in. The `range_expert` seat uses the engine's independent `PublicRangeTracker` and has no CFR writeback. Rule and equity-only seats use their existing local observation paths. Replay displays recorded events from the hand history services, which use the same configured solver construction when generating a history. Direct solver construction, including the separate Simulator route and benchmark callers, defaults to the incumbent path. [Match construction](backend/simulation/match_service.py) · [Match runner](backend/simulation/match.py) · [Range tracker](backend/simulation/range_intelligence.py) · [Replay](frontend/src/Replay.tsx)

Seven paired workflows produced 28 disabled and 26 enabled histories, plus a separate single-hand Replay control. The four solver fixtures exercised `solver`, `solver_adaptive`, `solver_adaptive_gated` and `solver_adaptive_sized`. Eighteen solver decisions in each arm were observed. Some flagged matches ended earlier when a stack was exhausted. Identical seeded reruns with the policy witness matched the untraced exported histories in each arm. The five original disabled fixtures matched their Phase 4V summaries and timelines, and all three non-solver fixtures agreed across flags. Public decoding, per-event chip conservation, legal target totals, settlements, alternating buttons and stack carry-forward passed. Engine and solver fallbacks were zero. These short gated and sized runs exercise construction and decision execution with thin profiles. Broader validation of those lock regimes remains outside the exact-EV result. [Match evidence](benchmark-results/phase-4w-2026-11-19/architecture-verified-13.json) · [API smoke](benchmark-results/phase-4w-2026-11-19/api-loopback-smoke.txt)

## Runtime and memory

Each triple is median / nearest-rank p95 / maximum in seconds. Coach advice workflows include profile reconstruction and all entered prefixes. The adapter workflow figure sums its postflop decision replays. A and B single decisions include preflop in the architecture panel. Both seeds used one BLAS thread and a warm matched holdout cache. The matrix timing covers individual B replays.

| Unit | Seed 13 | Seed 31 |
| --- | ---: | ---: |
| Coach decisions, A | 0.328 / 0.844 / 0.945 | 0.294 / 0.849 / 1.067 |
| Coach decisions, B | 0.073 / 0.281 / 0.329 | 0.074 / 0.287 / 0.312 |
| Offline postflop decisions, C | 0.101 / 0.294 / 0.294 | 0.105 / 0.287 / 0.287 |
| Coach workflows, A | 1.314 / 2.983 / 2.983 | 1.368 / 2.729 / 2.729 |
| Coach workflows, B | 0.376 / 0.998 / 0.998 | 0.348 / 1.138 / 1.138 |
| Summed postflop adapter, C | 0.320 / 0.680 / 0.680 | 0.384 / 0.657 / 0.657 |
| Match history workflows, A | 1.345 / 1.854 / 1.854 | 1.316 / 1.439 / 1.439 |
| Match history workflows, B | 0.414 / 1.151 / 1.151 | 0.507 / 1.743 / 1.743 |
| Working-set matrix, B | 0.032 / 0.122 / 0.168 | 0.031 / 0.129 / 0.184 |
| Fresh holdout, A | 0.662 / 1.644 / 2.186 | 0.636 / 1.862 / 2.822 |
| Fresh holdout, B | 0.059 / 0.784 / 1.104 | 0.078 / 0.879 / 1.330 |

The cold profiled river took A 0.832–0.855 s and B 0.088–0.094 s. Peak architecture process memory was 253.1/251.2 MiB for seeds 13/31. Corresponding holdout peaks were 268.7/265.9 MiB, including both arms, training, scoring and caches. B's belief-update median/p95/max was 1.67/3.07/3.07 ms and 1.46/3.49/3.49 ms in the nominal architecture panel. Holdout medians were 1.81 and 2.46 ms. B's column count per seat was median 728.5 and max 896 in the nominal architecture panel, and median 539 and max 896 in holdout. A's recorded architecture solves reached 1,176 columns. All timed replay and workflow units were inside 15 s. [Architecture timings](benchmark-results/phase-4w-2026-11-19/architecture-summary.json) · [Holdout timing and memory](benchmark-results/phase-4w-2026-11-19/determinism.json)

## Frozen exact-EV and safety result

The fresh 96-case panel covered 64 closing and 32 nonclosing river decisions with a separate synthetic posterior and fold/call reference. Scoring used full-precision legal mixes and a shared concrete menu per pair. All legal action values matched independent net-transfer accounting. The crossed 95% interval used 10,000 resamples over boards and training streams. All deterministic rows, summaries and numerical gate results matched across hash seeds 13 and 31. The manifest covered 185 files and all 96 scheduled cases. [Frozen inputs](benchmark-results/phase-4w-2026-11-19/frozen.json) · [Seed 13](benchmark-results/phase-4w-2026-11-19/holdout-13.json) · [Seed 31](benchmark-results/phase-4w-2026-11-19/holdout-31.json)

| Arm | Mean exact EV, bb | Mean / median / max decision regret, bb | Fallbacks |
| --- | ---: | ---: | ---: |
| A · incumbent | 2.413 | 2.062 / 0.3573 / 24.510 | 0 |
| B · flagged persistent replay | 2.712 | 1.762 / 0.00015 / 21.322 | 0 |

| Frozen gate | Observed result |
| --- | --- |
| Mean ≥ +0.05 bb and positive lower 95% bound | **Fail.** +0.299 bb, interval [−2.528, +2.885] bb |
| Worst adjustment within 0.50 bb | **Fail.** −17.690 bb |
| At most 10% of adjustments losing more than 0.01 bb | **Fail.** 18/96, 18.75% |
| Per-style mean ≥ −0.03 bb | Pass. Tight-passive +0.031, loose-passive +0.691, tight-aggressive +0.187, loose-aggressive +0.287 bb |
| Policy changes and profitable closing calls preserved | **Fail.** 69 mixes changed. Three profitable covers lost 0.0000069–0.0000074 in call probability each. Zero new seeded folds on profitable covers |
| Complete paired legal normalized coverage, exact scoring and no unexpected fallbacks | Pass. 96/96 pairs |
| Replay maximum ≤ 15 s, median ≤ 2× incumbent, peak ≤ 768 MiB | Pass in both runs |
| Frozen schedule and deterministic results | Pass in both runs |

Seeded actions changed on ten closing shoves. Across 30 profitable covers, seeded folds moved from three to zero and total fold mass moved from 1.6862 to 0.0003. Across 23 losing covers, seeded folds rose from 20 to 23 and total fold mass rose from 17.3652 to 22.9999. Eleven closing references were exactly break-even. The three small per-row profitable regressions still fail the frozen 1e-12 condition. [Closing decisions](benchmark-results/phase-4w-2026-11-19/holdout-13.json)

The worst case was tight-passive, board index 5, stream 311, three training hands, Hero Ah 9c on Tc 8s 5d Kh Jd. A folded with 99.83% probability and had exact EV −0.022 bb. B shoved with 98.94% probability and had exact EV −17.712 bb. The reference priced fold at zero, call at −4.773 bb and shove at −17.901 bb. B's live solve valued the shove at +0.362 bb with 990 positive persistent holdings and roughly 0.00124% of Hero-compatible mass omitted. The result demonstrates a gap between the modeled policy and reference even with dense support. Attribution among the posterior, reply policy and solver approximation remains open. [Worst row and model values](benchmark-results/phase-4w-2026-11-19/holdout-13.json)

## Phase 4X

Keep both flags opt-in. Diagnose the adverse nonclosing shove with crossed substitutions of the incoming prior, observed-wager likelihood and future reply law. Preserve the Phase 4W belief owner and compare any candidate decision rule on a new, frozen panel with strong sparse-profile shove coverage, the inherited 0.50 bb cap, and per-row profitable closing-call protection. A subsequent paired, seat-swapped gameplay experiment depends on passing those gates.

## Verification and Git status

- Both hash seeds passed the five Phase 4W regression tests. The separate seed-31 research regression passed **196 tests** in 250.93 s with seven existing dependency warnings. [Seed 13 focused](benchmark-results/phase-4w-2026-11-19/focused-13.txt) · [Seed 31 focused](benchmark-results/phase-4w-2026-11-19/focused-31.txt) · [Research regression](benchmark-results/phase-4w-2026-11-19/research-tests.txt)
- The full backend suite passed **1,017 tests** in 748.91 s, retaining all 1,012 existing tests and adding five. It reported eight existing dependency warnings. The initial sandbox run stalled at the local API test boundary. The completed run used Windows loopback access for the FastAPI test client. [Full backend log](benchmark-results/phase-4w-2026-11-19/backend-loopback-tests.txt)
- Frontend production build and Coach strategy rendering passed. Match and Replay forms rendered with both flag states, and the first event rendered from each real seeded history without future board cards. The API smoke exercised the Coach, Match and both Replay routes under both flags. `pip check` found no broken requirements. [Build](benchmark-results/phase-4w-2026-11-19/frontend-build.txt) · [Coach](benchmark-results/phase-4w-2026-11-19/frontend-coach.txt) · [Match and Replay](benchmark-results/phase-4w-2026-11-19/frontend-match-replay.txt) · [API smoke](benchmark-results/phase-4w-2026-11-19/api-loopback-smoke.txt) · [Dependencies](benchmark-results/phase-4w-2026-11-19/pip-check.txt)
- Git is on `main` at `3e89367`, 19 commits ahead of local `origin/main`. Existing local Phase 4V and prior work was preserved. Phase 4W appended changes to the already modified `backend/solver/bot.py`, edited the Coach, Match and history construction files, and added the owner, runner, regressions, protocol and report. Git and new-file whitespace checks passed with the existing `backend/test_poker.py` line-ending advisory. Earlier frozen manifests differed only on the intentionally edited shared live source. Historical research files and fixtures retained their recorded hashes. Evidence is under the existing ignored benchmark directory. [Git status](benchmark-results/phase-4w-2026-11-19/final-status.txt) · [Status delta](benchmark-results/phase-4w-2026-11-19/status-delta.txt) · [Frozen source checks](benchmark-results/phase-4w-2026-11-19/frozen-source-check.txt) · [Whitespace checks](benchmark-results/phase-4w-2026-11-19/git-diff-check.txt)

## Reproduction

Run from `backend` with the installed virtual environment, one BLAS thread, and a new output directory. The architecture script also reads the archived Phase 4V JSON under `benchmark-results/phase-4v-2026-11-19/final13`.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$phasePy = '.\.venv\Scripts\python.exe'
$phaseOut = '../benchmark-results/phase-4w-reproduction'
$phaseBound = 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[2:],timeout=int(sys.argv[1])).returncode)'
New-Item -ItemType Directory -Path $phaseOut -ErrorAction Stop | Out-Null
$env:PYTHONHASHSEED = '13'
& $phasePy -m research.holdem.phase_4w freeze "$phaseOut/frozen.json"
foreach ($phaseSeed in '13','31') {
    $env:PYTHONHASHSEED = $phaseSeed
    $phaseOrder = @()
    if ($phaseSeed -eq '31') { $phaseOrder = @('--reverse') }
    & $phasePy -c $phaseBound 1200 $phasePy -m research.holdem.phase_4w architecture "$phaseOut/architecture-$phaseSeed.json" @phaseOrder
    if ($LASTEXITCODE -ne 0) { throw "Phase 4W architecture failed" }
    & $phasePy -c $phaseBound 1200 $phasePy -m research.holdem.phase_4w holdout "$phaseOut/holdout-$phaseSeed.json" --manifest "$phaseOut/frozen.json" @phaseOrder
    if ($LASTEXITCODE -ne 0) { throw "Phase 4W holdout failed" }
}
```
