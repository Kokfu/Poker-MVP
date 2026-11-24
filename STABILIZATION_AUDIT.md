# Poker Analyzer MVP stabilization and solver audit

The audit ran on 2026-11-17 in Asia/Kuala_Lumpur. The clean nested project started on `main` at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. The tags include `phase-4g-complete` and `phase-5-complete`, both on earlier revisions.

## Test-stall diagnosis

The initial backend collection finished with 873 tests in 5.33 s. The first `test_poker.py` request stalled inside Starlette's TestClient before the handler ran. A 12 s traceback showed AnyIO creating the Windows asyncio proactor and blocking in `socket.socketpair()` at `accept()`. A bare Python socket-pair probe reproduced this with a 4 s watchdog inside the sandbox and completed outside it. The hung pytest invocation was stopped. Run the standard regression from `backend` on a Windows host that allows local socket pairs. Subprocess-based tests also depend on that working directory.

A separate 180 s focused run outside the sandbox progressed through requests before its wall-clock deadline. A targeted trace in Coach's postflop explanation test showed computation in `solver/cfr.py::_terminal_values`, inside the dense matrix pass. A full-suite watchdog later sampled the 360-hand learning case rebuilding each opponent's profile during logging in `coach/service.py::profile_for`. Both are distinct from the TestClient stall. Replaying all prior hands on each POST makes repeated logging quadratic in the size of each opponent's history. Historical full runs took 787–1,497 s on this project, so a short quiet run can time out while doing substantial work.

## Verified backend checks

| Check | New result | Scope |
| --- | --- | --- |
| Analyzer | 52 passed in 49.54 s | Exact river, Monte Carlo card removal and reproducibility, draw regressions, pot odds and HTTP validation. |
| Coach, Match and History | 104 passed in 295.88 s | Solver advice and explanations, local hand logging and review, opponent profile use, Match and Replay HTTP responses. |
| HTTP, legality and privacy | 116 passed in 7.77 s | Match and Replay contracts, short-stack and all-in sequences, history privacy. This group overlaps the preceding API group. |
| Simulation regression | 590 passed in 135.16 s | All `test_simulation*.py` modules, including legality, replay, persistence and mock external-benchmark bridge checks. |
| Coach facing a shove | 4 passed in 2.89 s | Equal, deeper and shorter preflop stacks, plus a postflop all-in call with an independently certain winning hand. |
| Exact Kuhn controls | 26 passed in 60.40 s | Tree, best response, exact CFR/CFR+ and deterministic CLI behavior. |
| Phase 4G controls | 12 passed in 358.56 s | Reduced-root coverage fix, chance/removal, zero-sum and privacy, full reachable coverage and matched 4F/4G scaling accounting. |
| Other research controls | 51 passed in 370.04 s | Hold'em abstraction, the bounded exact subgame, turn chance, generic external sampling and the later-street oracle. |
| Solver reference and benchmark | 2 exact transcript tests and 4 fast benchmark tests passed | Shared bounded subprocesses fix the BLAS thread layout. All eight fixed benchmark hands had zero solver fallbacks. |
| Package consistency | `pip check` passed | No broken installed requirements. |
| Frontend | Production build and render regression passed | The Coach keeps fallback advice usable when frequency options are empty. |
| Chromium browser | All five tabs passed the representative workflow | Exact Analyzer river calculation, Coach strategy and fallback with logging and Review, 100-hand Simulator, Match conservation, and event/hand navigation in both Replay modes. The browser reported zero uncaught runtime exceptions. |
| Docker Compose | Fresh image build, no-pull startup and restart persistence passed | Live frontend proxy served Analyzer, Simulator, Match, Replay and Coach. A test hand and its profile survived the backend restart. Initial image build resolved its package dependencies. |

The eight warnings in the focused API suites came from Starlette and eval7 dependencies. No test fixture or timeout changes were needed for the Windows socket issue.

The earlier 40-hand learning transcript records 98 decisions and 21 solver-to-Expert fallbacks. The corrected replay produced 100 decisions with zero such fallbacks and different outcomes in seven hands. The first changed advice source is a legal preflop shove response. The prior transcript stays available. The versioned post-fix regression compares all decisions, actions, numeric vectors and outcomes exactly under a fixed one-thread BLAS configuration. A comparison on unchanged early decisions demonstrated raw probability differences up to 1.33e-7 between thread configurations.

The old fast solver benchmark also depends on BLAS thread layout. Under one thread, reports produced from the original HEAD and the corrected source agree for all six spot identities and strategies and all eight fixed-hand actions and outcomes. Both differ from the historical reference at two probability vectors and the settlement of seed 9,300,006. A targeted default-thread run reproduced the historical river bet of 250 and net +500 chips. One thread selected check and returned +250 chips. The versioned one-thread reference preserves strict key, strategy and outcome comparisons under a known configuration. The historical reference is still available.

The monolithic run reached the Phase 4G conditional-chance regression after passing Analyzer, evaluator equivalence and Coach, including the three slow learning and persistence cases. It exited with a Windows access violation while the 180 s pytest traceback watchdog was dumping a stack. A fresh run of that single case without the watchdog passed in 123.36 s on the prior research code. The first research-only run reached its 720 s subprocess cap before completion. Verification continued in bounded suites without the periodic traceback watchdog.

All 884 collected backend tests have passing results from the split runs. This tally counts 126 Coach, Analyzer, evaluator and range-cache cases, 590 simulation cases, 89 research cases and 79 solver cases once each. The repeated focused totals overlap this count. A single-process run after all changes still has no clean summary.

## Defects

| Severity | Confirmed defect | Disposition |
| --- | --- | --- |
| High, verification environment | The Windows sandbox blocked the Python event loop's internal loopback socket pair. API tests waited for a blocking portal. | Reproduced with an application-independent probe and verified outside the sandbox. |
| High, Coach and solver bots | Replaying a voluntary shove inferred the all-in from provisional trillion-chip stacks instead of respecting its recorded total. A legal Coach spot could return `fallback` with a replay mismatch. The solver's abstract call could also project to a fold when the engine offered only `fold` and `all_in`. | Fixed in `backend/solver/bot.py` with regression coverage in `backend/test_solver_bot.py`. |
| High, Coach frontend | The fallback response contains a source and reason without frequency arrays. A valid sequence with five raises exceeds the preflop chart's decision depth and produces this fallback. The UI then attempts `labels.map`. | `frontend/src/Coach.tsx` renders the structured options when present and shows the fallback recommendation and reason. The render regression checks empty options and a populated mix. |
| Medium, Analyzer | A hole card duplicating a public rank could make a board-only straight draw appear personal. Two rank outs from different four-card runs were labeled open-ended. | Fixed in `backend/poker_analyzer.py`. Tests cover both cases and independently counted exact river equity in `backend/test_poker.py`. |
| Medium, exploit calibration | At the unopened button/SB node, `node_lock` recognizes an open decision and `tree_locks` still chooses facing-raise hand-strength correlation because of the forced big blind. | Retained for the isolated Phase 4H experiment below. |
| Medium, evaluation observability | `simulation/duplicate_evaluation.py` counts engine substitutions in `fallback_actions`. Solver-to-Expert fallbacks occur earlier and require the bot-level counter. Direct deal checks compare both hole cards and the common revealed-board prefix. | Preserve report-schema semantics and report both counters in baseline evidence. Remaining unseen cards follow the deterministic seeded deck. |
| Medium, regression coverage | `solver/benchmark.py::compare` compared only overlapping spot and hand keys, so omissions could pass as equivalent. | Comparison now flags missing and unexpected keys. Two focused comparator regressions passed. |
| Medium, research coverage and runtime | A Phase 4G trainer built with a reduced private-root fixture still reported the full reachable universe. The small conditional-chance test therefore computed the full tree before checking finite values. | The adapter now enumerates reachable information sets from explicitly supplied roots. Default full-fixture coverage still uses the full tree. The regression compares reduced coverage with exact diagnostics. |
| Medium, research and bot input | `simulation/decision_state.py` has independent legacy draw flags that also report duplicate-board-rank outs and treat two-rank draws as open-ended. `research/holdem/abstraction.py` duplicates the personal-draw predicate. | The Analyzer fix is isolated. Changing these inputs changes established bot policies and research information sets. Verify and version each policy comparison separately. |
| Low, research metadata | Fresh turn and river fixture states can expose the entire prior action sequence as `current_street_actions` because `[-0:]` returns the full list. Phase 4C keys use `hand_actions` independently. | Treat as a fixture metadata issue. Pin fresh-street action lists before changing it. |

The Analyzer river reference fixture has 990 possible opponent holdings. Exactly 44 contain the only card that beats Hero's flush, so Hero equity is 946/990. When the board is a royal flush, every holding ties and equity is 0.5. The existing suite verifies seeded Monte Carlo normalization and card removal, and pot odds of 40/(100+40).

## Solver architecture

| Area | Phase 4G research | Live Coach and solver bots |
| --- | --- | --- |
| Coverage | Fixed `As Kd 7c` flop, seven-card research deck, public turn and river chance, bounded betting. Early called all-ins score the fixture's current public board. | Offline 169-class preflop charts at 15, 30, 60, 100 and 200 bb. Postflop vectorized discounted CFR (DCFR) solves one street, then moves public ranges forward from observed actions. |
| Information and actions | Visible-card buckets, position, quantized geometry, limited public action history and legal-action labels. Bounded bet sizes and betting depth. | Combo-weighted public ranges, card-removal masks, pot-based opens and raises, all-in, and projection of real targets onto abstract sizes. |
| Chance and updates | Dedicated seeded RNG, true private/public chance and sampled opponent policy, enumerated traverser actions. Alternating frozen traversals. Regret increments use sampled action-value minus policy-weighted value. Strategy averaging cancels sampled opponent reach while retaining true chance weighting. Small sampled reach increases estimator variance, and zero-support paths get no samples through that route. | Equity at leaves integrates sampled flop runouts (30 by default) or exact turn/river runouts. Later-street betting is outside the leaf model. Fixed postflop budgets are 60/70/80 iterations. Optional opponent locks fit observed action-group frequencies. |
| Quality measures | Exact Kuhn best response and reduced Hold'em EV controls check mechanics. The two-million-node Phase 4G guard, visitation and table estimates measure coverage and cost. No full-game best-response or exploitability bound was established. | Coach uses chart or postflop solver with optional confidence-gated opponent reads. It can return Expert policy on a solver fallback. Reported preflop exploitability is scoped to the chart abstraction. Live advice has no full-game exploitability estimate. |
| Scaling | More public chance and betting states grow reachable infosets and coverage requirements. | Dense pairwise equity and compatibility matrices grow with both range sizes, and matrix passes recur at each iteration. Caching and range pruning reduce repeated work. |

The production weakness with direct evidence is action/model integration and abstraction. The audit found a concrete shove-path defect and an inconsistent open-node lock. A retained Stage 0 study reports mean regret of approximately 0.32 bb per turn spot against its oracle despite a larger abstract best-response gap. It missed its pre-registered practical-effect thresholds. There is no controlled evidence that more training or another street in the production tree would deliver a meaningful pool gain.

Historical opponent-model tests used paired, seat-swapped learning sessions. Proposal A's pooled delta was -12.5 bb/100 [−30.1, +4.8] and failed its no-harm gate. Proposal B's pooled delta was -92.4 [−123.4, −62.1] and failed all gates. The earlier holdout pool difference between solver_adaptive and equity was +46 [−37, +120]. Positive head-to-head results and a pool-average lead are distinct claims. Intervals in the archived multi-opponent tables are per matchup, and Expert and Adaptive results are correlated by construction. Treat the archived policy as a historical comparison after the current all-in correction.

## New performance baseline

The four-seed duplicate smoke completed 80 hands across all ten opponents. Each comparison used seat swaps, 100 bb stacks, 2,000 paired bootstrap resamples and eight total hands. All histories and zero-sum checks passed. There were zero illegal actions, engine substitutions, internal solver fallbacks and deal mismatches.

| Opponent | Net bb/100 | 95% paired interval | Pair wins/losses/ties |
| --- | ---: | --- | --- |
| equity | +806.25 | [−712.50, +3006.25] | 3/1/0 |
| expert | −280.38 | [−859.88, +43.75] | 1/2/1 |
| adaptive | −280.38 | [−859.88, +43.75] | 1/2/1 |
| range_expert | −280.38 | [−859.88, +43.75] | 1/2/1 |
| solver | +137.50 | [−37.50, +312.50] | 2/1/1 |

Per-matchup elapsed time was 4.07–95.56 s, process CPU time 2.34–23.98 s, and peak Windows working set 85.33–134.40 MiB. Four pairs per matchup give little information about playing strength and do not measure mature opponent adaptation. The stronger historical direct estimate against equity (+427.43 [+334.91, +517.27] over 48 sessions) measured the earlier base policy. The [benchmark record](benchmark-results/stabilization-2026-11-17/README.md) contains all ten comparisons, raw seed-level evidence, historical results, and commands for a full learning-session baseline and round robin.

A separate two-pair, 24-hand-per-seat learning smoke against Random hit its 240 s cap while the solver was iterating. It supplies no completed learning comparison. The retained benchmark directory is covered by the project's existing `benchmark-results/` Git ignore rule.

## Phase 4H proposal

Correct the preflop unopened-SB lock coefficient in isolation. The hypothesis is that selecting the opening-action coefficient removes artificial flat mixing of the opponent's raising range. It is a small production Coach correction with a deterministic oracle, low compute cost and clear scope. The new diagnostic reproduced the current 0.54 coefficient at all five chart depths with inputs 0.89/0.19, and 0.50 with inputs 0.20/0.80. The independently expected values are 0.89 and 0.20.

- Control is the stabilized `solver_adaptive`. Treatment changes only classification of the unopened button/SB lock in `tree_locks`. Keep chart data, solver budget, frequencies, sizing and other locks fixed.
- Freeze a fixture matrix covering both actor orientations, all five chart depths, an unopened SB and BB, facing a voluntary raise, and a cold profile. Use independently specified aggressive/call coefficient pairs of 0.89/0.19 and 0.20/0.80. Replay the fixed Step 17a tight-villain spot with exploitation on and off. Record coefficients, effective villain combinations, legal normalized advice, solver fallbacks and wall time.
- Primary metric is maximum absolute error between the applied coefficient and the expected rule in the targeted rows. Success requires error at most 1e-12 on every row, identical coefficients and chart policies for out-of-scope rows, legal normalized advice and no solver or engine fallbacks in the matrix. Stop at the end of the fixed matrix or on the first invariant failure. Retain the stabilized control if any criterion fails. A one-condition revert restores the old policy if a regression is later verified.
- Treat effective range size and latency as secondary diagnostics. A bb/100 claim requires a separate, powered, paired learning-session holdout. Use a disjoint development pilot to size it for a predeclared minimum effect, then freeze sample size, opponent pool and seeds before opening holdout results. Historical 48-session half-widths ranged from 17.5 to 30.6 bb/100, so a small one-node effect is unlikely to resolve in a 24-session run. The proposal requires no extended solver training or repeated holdout tuning.

## Acceptance still due

1. Run the regression as a single process in a Windows session with working local TCP sockets and without a periodic traceback watchdog. Accept on a clean pytest summary, with the checked-in deterministic reference settings for each solver fixture.
2. Freeze this code revision and run the full paired learning-session baseline. Accept a complete symmetric seed panel with legal actions, valid histories, zero-sum settlement and both fallback counters, plus separately scoped head-to-head and pool intervals. A pool lead over equity requires a paired lower bound above zero.
3. Run the Phase 4H correction matrix before considering a wider strategy change. Retain the existing policy if the coefficient or invariant gates fail.

The representative browser run used desktop Chromium. Simulator, Match and Replay menus offer eight bots. The local API and CLI also expose `solver_adaptive` and its two experimental variants. External benchmark transport is covered by offline fixtures. The live external benchmark remains unverified in this audit.

## Final Git state

`main` remains at `3e89367d88e32771f2789218640a0452443c21ed`, 19 commits ahead of local `origin/main`. All audit changes and new regression fixtures are local and uncommitted. `git diff --check` passed with a Windows line-ending advisory. The new benchmark files are present on disk under the existing ignore rule. Historical benchmark artifacts are retained.

