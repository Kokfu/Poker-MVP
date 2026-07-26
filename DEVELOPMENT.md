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

## Phase 3 persistent match API and CLI

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
