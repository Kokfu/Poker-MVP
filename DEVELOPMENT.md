# Development

## Backend

The accepted backend environment uses Python 3.11.9 at:

```text
C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend\.venv\Scripts\python.exe
```

Create or restore the environment and install dependencies:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use that interpreter for all backend commands:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

`-p no:cacheprovider` avoids the non-blocking Pytest cache permission warning that can occur under OneDrive.

## Frontend

## Kuhn CFR research CLI

Run from `backend`; this is not part of the simulator CLI:

```powershell
.\.venv\Scripts\python.exe -m research.kuhn.cli train --iterations 100000
.\.venv\Scripts\python.exe -m research.kuhn.cli train --iterations 100000 --output C:\Temp\kuhn-cfr.json
.\.venv\Scripts\python.exe -m research.kuhn.cli compare --iterations 100000 --output C:\Temp\kuhn-cfr-comparison.json
```

The JSON report is schema `kuhn_cfr` 1.0 and is canonical sorted JSON. It will not overwrite a file unless `--overwrite` is passed. It reports exact profile EV, information-set-constrained best responses, NashConv, and exploitability (`NashConv / 2`).

`compare` writes a separate `kuhn_cfr_convergence` 1.0 report with Vanilla CFR and CFR+ side by side at matched deterministic checkpoints (1, 10, 100, 1,000, 10,000, and 100,000 when in range). CFR+ is separate from Vanilla CFR: after each complete six-deal iteration it uses `R <- max(0, R + delta)`. Its average policy uses the standard linear weight `max(0, iteration - averaging_delay)`; `--averaging-delay` defaults to zero, so iterations 1, 2, ... have weights 1, 2, .... All EV, best-response, NashConv, and exploitability entries are exact enumerations, not Monte Carlo estimates.

## External-sampling MCCFR research

The Phase 4E control is library-only and remains outside the simulator CLI. From `backend`, produce deterministic research reports with:

```powershell
.\.venv\Scripts\python.exe -c "from research.kuhn.mccfr import convergence_report; from pprint import pprint; pprint(convergence_report())"
.\.venv\Scripts\python.exe -c "from research.holdem.mccfr import scaling_report; from pprint import pprint; pprint(scaling_report())"
```

`KuhnExternalSamplingMCCFRTrainer(seed)` owns its own RNG. A logical iteration contains two sequential, individually frozen traversals (Player 0 then Player 1): chance and opponent actions are sampled from their target distributions while traverser actions are enumerated. Diagnostics distinguish logical iterations from total traversals. The counterfactual estimator needs no extra importance division because chance/opponent sampling is the target reach; average-policy accumulation cancels sampled opponent reach but retains chance probability through expectation. It supplies exact Kuhn EV/BR metrics through `convergence_report`; sampled trajectories are reproducible for equal seed/configuration/iterations. `HoldemSubgameExternalSamplingMCCFRTrainer(seed)` applies the same core only to the fixed Phase 4D game. Its scaling report deliberately does not include full-subgame exploitability.

Use Node.js 20 or newer with npm. The Docker image uses Node 20; the accepted host build used Node 24.16.0 and npm 11.13.0.

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\frontend
npm.cmd install
npm.cmd run dev
npm.cmd run build
```

Use `npm.cmd` on Windows when PowerShell execution policy blocks `npm.ps1`.

The local frontend has three tabs:

- **Analyzer** submits manually entered hand states to `POST /api/analyze`.
- **Simulator** runs independent hands through `POST /api/simulations/run`; both stacks reset before each hand.
- **Match** runs stack-persistent matches through `POST /api/matches/simulate`; stacks carry forward until elimination or the configured hand limit.

The Match form validates whole-number inputs in the browser before submission. Its result view includes aggregate outcome data, invariant indicators, and every public per-hand settlement summary. Match results are not saved or replayable after the page is refreshed.

## Docker Compose

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail 200
docker compose restart
docker compose down
```

The backend health check is `GET http://127.0.0.1:8000/api/health`; the frontend is `http://127.0.0.1:5173`.

## Simulator CLI

List bots:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli list-bots
```

Run a deterministic simulation:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b aggressive --hands 1000 --seed 42 --starting-stack-bb 100
```

Generate and validate a schema 2.0 dataset:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b tight --hands 100 --seed 42 --dataset-output ..\benchmark-results\sample.jsonl --overwrite
.\.venv\Scripts\python.exe -m simulation.cli validate-dataset ..\benchmark-results\sample.jsonl
```

The dataset validator accepts one simulation ID per file. Schema 1.0 migration and a separate manifest are not supported.

## Required benchmark workloads

Run benchmarks separately so each command has its own timing and failure boundary:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b random --hands 1000 --seed 42
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b random --hands 10000 --seed 42
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a tight --bot-b aggressive --hands 10000 --seed 42
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a equity --bot-b aggressive --hands 1000 --seed 42 --equity-iterations 500
```

EquityBot at 500 iterations is intentionally slower than the rule-based bots. Long EquityBot workloads can exceed constrained command-runner time limits even when the process is healthy.

## Evidence invalidation rule

Regenerate stress, pairwise, and benchmark artifacts whenever engine, bot, settlement, statistics, or equity logic changes. Documentation-only and presentation-only changes do not invalidate deterministic runtime evidence.

## Phase 3 persistent match frontend, API, and CLI

Run a persistent match:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m simulation.cli match --bot-a tight --bot-b aggressive --starting-stack 10000 --small-blind 50 --big-blind 100 --max-hands 25 --seed 42 --equity-iterations 500
```

Run the focused foundation, API, and CLI suites directly:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_match.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_match_api.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_match_cli.py
```

Run the complete backend regression after any match or shared `HandEngine` change:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pip check
```

Persistent mode reuses the shared hand engine, so changes to blind posting, legal actions, runout, settlement, or the public adapter require the focused match suites and the full Phase 2-compatible regression suite. Do not overwrite retained Phase 2 benchmark artifacts during match development.

For a frontend smoke test, start both services, open `http://127.0.0.1:5173`, choose **Match**, and submit the defaults or the deterministic `tight` versus `aggressive`, seed 42 configuration shown above. Confirm the summary invariants pass and the hand table remains contained when the viewport is narrow.

## Phase 3B1 hand-history development

History schema `1.0` is implemented in `backend/simulation/history.py` and is intentionally unrelated to dataset schema 2.0. `HandEngine` emits typed events at the authoritative mutation points; do not reconstruct events from final statistics or duplicate poker rules in the validator.

Run the focused history suites:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_history.py test_simulation_history_validation.py test_simulation_history_privacy.py
```

Then run the complete backend regression and dependency check. Changes to history instrumentation must preserve the public Analyzer, independent-simulation, and persistent-match response shapes and dataset schema 2.0.

Completed histories are available internally as `result["history"]`. Persistent `MatchHandSummary` objects retain the history in an internal field. There is no history endpoint, validation CLI command, export file, persistence layer, or replay UI in Phase 3B1.

## Phase 3B2 history API and CLI

Run the history interface tests:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_history_service.py test_simulation_history_api.py test_simulation_history_cli.py
```

Generate and validate temporary history JSON:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli history-hand --seed 42 --output ..\history-output\hand.json
.\.venv\Scripts\python.exe -m simulation.cli history-match --seed 42 --max-hands 10 --output ..\history-output\match.json
.\.venv\Scripts\python.exe -m simulation.cli validate-history ..\history-output\hand.json
```

Generation refuses an existing path unless `--overwrite` is passed. Use project-local scratch or operating-system temporary directories, not retained benchmark directories.

The API routes are `POST /api/histories/hand` and `POST /api/histories/match`. They use the same service as the CLI. Existing `/api/matches/simulate` output intentionally omits histories and private cards.

## Phase 3C1 decision-state development

Keep `simulation.decision_state` a pure, read-only transformation of `HandEngine` state. It must not duplicate betting rules, inspect deck internals, consume RNG, or add fields to existing API/history/dataset serializers. Run the focused decision-state, poker-feature, and privacy suites before the complete backend regression. `DecisionObservation` is the future strategy boundary; legacy bots remain on `Observation` until deliberately migrated.

## Single-hand Replay

## Phase 3C2 opponent-model development

Keep `simulation.opponent_model` history-derived and deterministic: it must never read engine cards, deck, or RNG. Verify pre-decision profile delivery and post-settlement updates in match tests, then run the full backend regression. Public responses and dataset schema 2.0 remain unchanged.

`Replay` supports `/api/histories/hand` and `/api/histories/match`. Keep their shared event renderer responsible for event navigation, table state, timeline selection, and privacy filtering; match-only UI should remain limited to request controls, overview, hand selection, and stack progression.

## ExpertRuleBot benchmark

Run `\.venv\Scripts\python.exe -m simulation.expert_benchmark` from `backend` for deterministic independent 1,000-hand ExpertRuleBot matchups. It reports hands, net chips/net BB, BB/100, wins/losses/ties, illegal actions, and fallback diagnostics.

For adaptive work, retain `ExpertRuleBot` unchanged and put thresholds, confidence gates, and legal transition limits in `simulation.exploit_strategy`. Run `test_simulation_adaptive_bot.py` before the full backend suite. `simulation.adaptive_benchmark` provides persistent, seat-aware A/B diagnostics; seat swapping is not duplicate-deal pairing and finite results are not strength claims.

Use the long-stack archetype diagnostic when validating live activation. It deliberately uses legal, non-registered opponents to generate completed public histories; do not inject profiles into an end-to-end test or relax confidence thresholds because short eliminated matches do not mature samples.

## Phase 3D1 evaluation development

Keep statistical work in `simulation.evaluation`; bots and the authoritative poker engine must not know about bootstrap sampling or report formatting. The seed schedule is the consecutive range beginning at `base_seed`. Bot seeds are stable hashes of the evaluation seed and role, while the engine receives the schedule seed. Bootstrap calls must construct only their private statistics RNG.

Run the focused suite first:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_evaluation.py
```

Tests use small fixtures and tiny engine runs. Do not add large matrices to normal pytest execution. Diagnostic matrices are explicit CLI commands and should write only to caller-selected temporary/output locations. A performance regression record is metadata: include sample sizes, effect direction, and uncertainty overlap, but do not introduce a build failure from a small noisy BB/100 change.

When extending reports, preserve finite JSON values, deterministic sorted serialization, overwrite protection, evaluation schema 1.0, history schema 1.0, dataset schema 2.0, and existing API shapes. Any chip-conservation or history-validation failure must abort rather than enter an aggregate.

## Phase 3D1A legality development

`HandEngine.legal` is authoritative for normal actions and the distinct `all_in` action. For every exposed normal `bet` or `raise`, require an inclusive total-target interval with `minimum_target_to <= maximum_target_to`. Do not clamp an unaffordable normal minimum, and do not move this guard into bots. An under-minimum all-in may remain legal through `all_in` when stack, call, and reopening rules permit it.

## Phase 3D2 range intelligence development

Run `test_simulation_range_intelligence.py` before the complete backend suite. Range builders accept visible cards and public evidence only; do not pass a `HandEngine`, deck, actual unrevealed opponent cards, or future cards into this layer. Use `RangeEquityEstimator` only when explicitly requested, because flop/turn Monte Carlo is intentionally not part of normal bot decisions. Its seed is an isolated range-equity RNG input.

For an engine-backed diagnostic, feed `PublicRangeTracker.observe` each opponent `action_taken` event with that event's public board. Do not replay a final board into earlier actions. Showdown calibration accepts an actual combination only after a legitimate `showdown` event and must retain the captured pre-showdown `WeightedRange` unchanged.

Run the focused invariant and related suites with:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_short_stack_legality.py test_simulation_all_in.py test_simulation_decision_state.py test_simulation_fallback.py
```

Regression coverage must include zero-wager short stacks, exact minimum targets, ordinary bets/raises, short and full all-ins, reopening, short blinds, river state, DecisionObservation, all registered bots, and the evaluation seeds that originally produced invalid-target fallbacks. Preserve history/action total-target fields and keep evaluation warnings intact so future defects continue to surface naturally.

# Phase 3D3 notes

`expert`, `adaptive`, and `range_expert` are intentionally independent experimental controls.  Benchmark them with the existing evaluation framework using matched seed schedules and seat-swapped orientations; do not interpret a single seed as a performance claim.  Range equity is calculated once at the decision boundary and reused by the decision/explanation.

## Phase 5 workflows

All commands run from `backend` with the project interpreter.  `eval7` is a
required dependency (`pip install -r requirements.txt`); binary wheels exist
for Windows and Linux (Docker).

### Solver preflop charts

The charts in `solver/data` are committed runtime assets.  Rebuild them only
when the preflop tree or equity model changes (about 6 minutes):

```powershell
.\.venv\Scripts\python.exe -m solver.preflop build --boards 20000 --iterations 3000
```

`PreflopCharts` refuses to load a chart whose stored node labels no longer
match the current tree.

### Duplicate-deal evaluation

```powershell
# one strategy against one opponent, 500 duplicate pairs (1,000 hands)
.\.venv\Scripts\python.exe -m simulation.duplicate_cli pair --strategy solver --opponent equity --pairs 500
# round robin with pool standings, saved as JSON
.\.venv\Scripts\python.exe -m simulation.duplicate_cli tournament --bots equity expert solver --pairs 1000 --output ..\benchmark-results\phase-5\example.json
# learning sessions: the same bots play 60 hands in a row with growing opponent profiles
.\.venv\Scripts\python.exe -m simulation.duplicate_cli tournament --bots equity solver_adaptive --pairs 12 --session-hands 60
# the Phase 5 win-rate gate for a saved tournament
.\.venv\Scripts\python.exe -m simulation.duplicate_cli gate --report ..\benchmark-results\phase-5\example.json --candidate solver
```

`--workers` defaults to CPU count minus one; results are identical for any
worker count.  Use the default `development` seed set while building
strategies; `--seed-set holdout` is reserved for frozen final acceptance runs,
and only holdout reports are `acceptance_eligible`.

### Slumbot benchmark (network, opt-in)

```powershell
.\.venv\Scripts\python.exe -m simulation.slumbot_cli --bot solver --hands 200 --output ..\benchmark-results\phase-5\slumbot-solver.jsonl
```

Slumbot plays 200 bb deep at 50/100.  Each finished hand is appended to the
JSONL file immediately.  `baseline_adjusted_bb_per_100` subtracts Slumbot's
own reported baseline and has much lower variance than raw winnings.

### Coach locally

```powershell
# terminal 1 (backend)
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
# terminal 2 (frontend); API_PROXY points Vite at the local backend
cd ..\frontend
$env:API_PROXY = "http://127.0.0.1:8000"; npm.cmd run dev
```

Open `http://127.0.0.1:5173` and choose **Coach**.  Logged hands go to
`backend/data/coach.sqlite` (override with `COACH_DB_PATH`); Docker Compose
stores them in the `coach-data` volume.

Hero, board, and shown-villain cards can be typed or clicked from a 52-card
picker next to each field (used cards are disabled); bet/raise amounts have
1/3, 1/2, 3/4, pot, and all-in quick-size buttons that fill the total-target
amount box, clamped to the legal range.  `GET /api/coach/opponents/{name}/hands`
lists an opponent's logged hands newest-first for the history panel under
their profile; clicking one reloads it read-only.  `DELETE
/api/coach/hands/{id}` and `DELETE /api/coach/opponents/{name}` remove a hand
or every hand for an opponent; the frontend confirms before either call.
**New hand** clears the cards and board, alternates your seat between button
and big blind, and keeps blinds, stacks, and opponent; a finished hand can be
logged once.  Quick sizes use the acting player's own stack, so they are also
correct for villain actions when stacks differ.

### Solver performance

`solver/benchmark.py` is a reproducible, fixed-seed benchmark: ~30 solver
decision spots (every street, both a cached street solve and a re-solve
forced by an off-tree opponent size, with and without a confident opponent
profile) plus 200 full fixed-seed hands of `solver` vs `equity`.  It records
each spot's exact sampled strategy vector and every hand's chosen actions.

```powershell
.\.venv\Scripts\python.exe -m solver.benchmark --save solver/data/benchmark_baseline.json
.\.venv\Scripts\python.exe -m solver.benchmark --compare solver/data/benchmark_baseline.json
```

`test_solver_benchmark.py` runs a small fixed-size configuration against
`solver/data/benchmark_baseline_fast.json` as a fast regression guard; it is
not itself the equivalence evidence for a performance change (that needs the
full 30-spot/200-hand run compared against a baseline recorded before the
change).

A perf-solver pass (branch `perf-solver`, based on `b3be891`) profiled
`SolverBot`/`AdaptiveSolverBot` with `cProfile` and found the cost concentrated
in three places, in order: `cfr.py`'s per-node Python loop rebuilding a
`np.stack` from a list comprehension once per decision node per iteration
(about 55% of profiled time across `_terminal_values`/`iterate`), eval7 calls
and array construction in `equity.py`'s `rank_vector`/`equity_matrix`, and
`current()`/`average()` reallocating a fresh uniform-strategy array with
`np.full_like` on every call (tens of thousands of calls per hand).

Changes, in the profiled order:

- `cfr.py`: `_reaches`/`_terminal_values`/`iterate` now store reach
  probabilities and backward-induction values as one `(nodes, combos)` array
  per player instead of a `dict[int, ndarray]`, and gather a node's children
  with a single fancy-index (`values[self._children[node.index]]`) instead of
  `np.stack([values[c] for c in node.children])`.  `current()`/`average()`
  reuse a per-node uniform-strategy array computed once in `__init__` instead
  of calling `np.full_like` every call.  No iteration count, discounting
  parameter, or lock/exploit logic changed.
- `equity.py`: `rank_vector` gathers every combo's card pair once
  (vectorized) instead of fancy-indexing per combo, reuses one two-slot list
  for the eval7 call instead of concatenating a new list per combo, and skips
  blocked combos via a precomputed index instead of a per-combo membership
  check; eval7 has no batch entry point, so the evaluate() call itself is
  still one Python call per live combo.  `equity_matrix`'s per-board loop
  reuses three scratch buffers instead of allocating four temporaries
  (two gathers, a subtract, a sign) on every board.
- `bot.py`: `_EQUITY_CACHE` (memoized per-board equity matrices, shared for
  the life of the process) grew from 6 to 12 entries so a session touching
  many distinct boards recomputes fewer of them; worst case is roughly
  6&nbsp;MB/entry, so 12 entries stays under 75&nbsp;MB.

**Measured speedup.**  A `cProfile` run of 6 full hands (`solver` vs
`equity`, unaffected by the machine's other concurrent load because it counts
CPU time inside each function rather than wall clock) went from 18.38 s to
12.47 s, about **1.47x**.  `_terminal_values` dropped from 7.41 s to 4.63 s
tottime and no longer shows any `np.stack` calls; `equity_matrix` dropped
from 2.89 s to 1.70 s; `rank_vector` from 1.37 s to 0.86 s.  Wall-clock
benchmark runs were recorded while another long-running benchmark shared the
same machine (up to a dozen-plus competing processes), so their absolute
numbers are noisy and are not used as the primary evidence; the cProfile
figures above, measuring CPU time actually spent inside the code, are.  This
falls short of the 3-5x target; the remaining cost is real compute (BLAS
matmuls in `_terminal_values`, and eval7's per-combo Python call in
`rank_vector`, which has no batch API) rather than avoidable Python/numpy
overhead.  A JIT-compiled hand evaluator (`numba`, discussed with the user)
could remove the eval7 call overhead but was not attempted in this pass: it
would require an independently-verified hand-ranking implementation, which is
a larger, separately-scoped piece of work.

**Equivalence.**  All 30 spots' chosen actions and all 200 fixed hands'
action sequences were compared against a baseline recorded at `b3be891`
before any change.  28/30 spots and 197/200 hands matched exactly (mixed
strategies within 1e-5).  Two spots and three hands differed.  Investigation
(isolating `_reaches`, `_terminal_values`, and the backward-induction gather
against the original dict/`np.stack` implementation on identical real
tree/range/equity inputs) found `cfr.py`'s core functions individually
reproduce the original to within 1e-13-1e-16 &mdash; floating-point noise from
computing the same sums via `fancy-index` gathers instead of
`np.stack`-from-a-list, not a logic difference.  In one case that noise
landed on a regret value sitting almost exactly at zero for one combo at a
deeply nested decision node; DCFR's regret matching is a hard threshold
(`positive = max(regret, 0)`), so the two implementations picked the opposite
pure action for that one combo, and the discounted-regret iteration then
compounded that single flip over the remaining iterations.  This is the
"float tie at a sampling threshold" scenario documented as a possible outcome
of this kind of change: it is an inherent property of restructuring array
construction in an iterative regret-matching algorithm, not a defect, and is
not fixable without giving up the array-gather rewrite (the largest single
win).  The user reviewed this evidence and chose to accept it; the benchmark
baseline was then re-recorded from the optimized code, so it is now the
regression reference going forward.

No new dependency was added.  `pip check` passes, and the full backend suite
(776 tests before this branch, 778 with the two new tests above) passes.
