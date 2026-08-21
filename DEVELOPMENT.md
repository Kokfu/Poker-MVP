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

Run the focused invariant and related suites with:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_simulation_short_stack_legality.py test_simulation_all_in.py test_simulation_decision_state.py test_simulation_fallback.py
```

Regression coverage must include zero-wager short stacks, exact minimum targets, ordinary bets/raises, short and full all-ins, reopening, short blinds, river state, DecisionObservation, all registered bots, and the evaluation seeds that originally produced invalid-target fallbacks. Preserve history/action total-target fields and keep evaluation warnings intact so future defects continue to surface naturally.

