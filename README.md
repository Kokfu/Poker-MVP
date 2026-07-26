# Poker Analyzer MVP

Poker Analyzer MVP is a local, educational, offline-first Texas Hold'em analyzer and heads-up simulator. It accepts manually entered poker states, performs mathematical analysis, and runs deterministic bot-versus-bot experiments on the local machine. It does not play poker for the user.

## Analyzer

The Analyzer supports:

- two manually entered hero cards;
- valid Hold'em board states of 0, 3, 4, or 5 cards;
- duplicate-card and input validation;
- one random unknown opponent;
- Treys made-hand evaluation after the flop;
- Monte Carlo equity on preflop, flop, and turn;
- exact enumeration of all 990 opponent hands on the river;
- win, tie, loss, equity, pot-odds, and basic recommendation output;
- hero-specific flush and straight-draw labels.

The recommendation is an educational heuristic. It does not model opponent ranges, rake, tournament ICM, player tendencies, or future-street strategy.

## Simulator

Phase 2 adds a deterministic, local-only, heads-up No-Limit Texas Hold'em simulator with:

- independent starting-stack reset for every hand;
- button and blind rotation;
- preflop and postflop betting;
- engine-authoritative legal actions and target bounds;
- all-in classification, automatic runout, fold settlement, and showdown settlement;
- per-hand and aggregate zero-sum statistics;
- JSONL dataset schema 2.0 generation and strict validation;
- CLI, API, and React Simulator interfaces.

Built-in bots are `RandomBot`, `TightBot`, `AggressiveBot`, and `EquityBot`. They are baseline research strategies, not claims of optimal or game-theoretic play.

Chip amounts are integer internal units:

```text
1 BB = 100 internal chip units
net_chips = final_stack - starting_stack
net_bb = net_chips / big_blind_units
bb_per_100 = net_bb / hands_played * 100
```

Each hand begins from a fresh configured stack, normally 100 BB. Results are not a persistent bankroll.

## Requirements

- Python 3.11; the accepted Windows environment uses Python 3.11.9.
- Node.js 20 or newer and npm for local frontend development.
- Docker Desktop with Docker Compose for the containerized workflow.

## Local development

Backend:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Frontend:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. The backend listens on `http://127.0.0.1:8000`.

## Docker

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail 200
docker compose down
```

The configured ports bind to localhost. The frontend proxies `/api` requests to the backend service.

## API

- `GET /api/health`
- `POST /api/analyze`
- `POST /api/simulations/run`

The simulation API accepts 1 through 10,000 hands per request. Representative Analyzer request:

```powershell
$body = @{
  hero_cards = @("As", "Qs")
  board_cards = @("Js", "8s", "3d")
  opponents = 1
  pot = 100
  amount_to_call = 40
  hero_stack = 850
  iterations = 10000
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/analyze -Method Post -ContentType application/json -Body $body
```

## Dataset schema 2.0

Generate and validate a dataset:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b tight --hands 100 --seed 42 --dataset-output ..\benchmark-results\sample.jsonl --overwrite
.\.venv\Scripts\python.exe -m simulation.cli validate-dataset ..\benchmark-results\sample.jsonl
```

Schema 2.0 stores only the acting bot's observation and final reward. The validator rejects malformed records, unsupported schema versions, multiple simulation IDs in one file, and privacy-leaking fields. Schema 1.0 migration is not supported, and there is no separate dataset manifest.

## Retained acceptance evidence

- Valid dataset: `benchmark-results/dataset-valid-seed42.jsonl`
- Five-seed stress: `benchmark-results/post-dataset-runtime/five-seed-stress.json`
- Ordered pairwise matrix: `benchmark-results/post-dataset-runtime/pairwise-results.json`
- Required benchmarks: `benchmark-results/post-dataset-runtime/benchmark-results.json`

The final Phase 2 backend suite contains 275 passing tests. Retained runtime evidence covers 5,000 stress hands, 4,000 ordered-pairwise hands, and 22,000 benchmark hands with zero illegal actions, zero built-in fallback diagnostics, and zero-sum results.

## Limitations

- Heads-up only; no multiway pots.
- No tournament structure, rake, antes, or ICM.
- No general side pots beyond heads-up matched-chip settlement and unmatched-excess return.
- No persistent bankroll across independent hands.
- No AI-training pipeline in Phase 2.
- No schema 1.0 migration, separate dataset manifest, or multiple simulation IDs per dataset file.
- EquityBot is computationally expensive, especially in long runs.
- Monte Carlo analysis is approximate and varies unless seeded.
- The frontend Analyzer has no loading or disabled submission state.
- Browser verification covers only the local application.
- No real-money integration, external poker-site automation, automatic clicking, OCR, screen scraping, screenshot card extraction, or hidden-card extraction.

See [SIMULATION.md](SIMULATION.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), [SECURITY.md](SECURITY.md), and [ROADMAP.md](ROADMAP.md) for further details.
