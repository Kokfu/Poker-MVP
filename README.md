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

Phase 3 adds a separate persistent match mode: settled stacks carry between hands, positions alternate, and the match stops on elimination or a configured hand limit. Independent simulation mode still resets both stacks every hand. Open the **Match** tab in the local frontend to configure and run this mode.

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
- `POST /api/matches/simulate`
- `POST /api/histories/hand`
- `POST /api/histories/match`

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

Persistent match request:

```powershell
$match = @{
  bot_a = "tight"
  bot_b = "aggressive"
  starting_stack = 10000
  small_blind = 50
  big_blind = 100
  max_hands = 100
  seed = 42
  equity_iterations = 500
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/matches/simulate -Method Post -ContentType application/json -Body $match
```

Match defaults are `random` versus `random`, 10,000-unit stacks, 50/100 blinds, 100 hands, seed 0, and 1,000 EquityBot iterations. Stack and blinds must be positive integers, the small blind cannot exceed the big blind, `max_hands` is 1–10,000, and EquityBot iterations are 500, 1,000, or 2,000. Bot names are case-normalized.

The response contains match configuration, final stacks, winner, termination reason, net chips, showdown/fold totals, diagnostics, and settled per-hand summaries without private hole cards. The Match tab renders these aggregate results, explicit chip-conservation and zero-sum checks, and every returned hand summary in a horizontally scrollable table.

The equivalent CLI command is:

```powershell
cd backend
.\.venv\Scripts\python.exe -m simulation.cli match --bot-a tight --bot-b aggressive --starting-stack 10000 --small-blind 50 --big-blind 100 --max-hands 100 --seed 42 --equity-iterations 500
```

## Action-level history JSON

History schema `1.0` is separate from dataset schema 2.0. Dedicated history interfaces validate the engine-generated event stream before returning or writing it; existing Analyzer, Simulator, and Match response shapes remain unchanged.

Run or export one deterministic hand:

```powershell
cd backend
.\.venv\Scripts\python.exe -m simulation.cli history-hand --bot-a tight --bot-b aggressive --seed 42 --equity-iterations 500
.\.venv\Scripts\python.exe -m simulation.cli history-hand --seed 42 --output ..\history-output\hand-seed42.json --overwrite
```

Run or export a persistent match with every completed hand history:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli history-match --bot-a tight --bot-b aggressive --max-hands 25 --seed 42 --equity-iterations 500 --output ..\history-output\match-seed42.json
```

Validate either JSON document type:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli validate-history ..\history-output\hand-seed42.json
```

Exports use UTF-8 JSON. An existing output is refused unless `--overwrite` is supplied. `hand_history` documents contain one validated history; `match_history` documents contain the unchanged public match summary plus one validated history per completed hand and aggregate validation evidence.

Fold histories contain no private cards. Showdown events may contain only legitimately revealed hole cards. Histories never contain future board cards, deck order, remaining-deck contents, or burn cards.

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
- Persistent matches have no dataset output, database persistence, saved-match browser, or replay controls; results exist only in the current frontend session or API/CLI response.
- History JSON can be returned or written explicitly, but there is no server-side history store, lookup endpoint, cross-process resumption, or replay frontend.
- Browser verification covers only the local application.
- No real-money integration, external poker-site automation, automatic clicking, OCR, screen scraping, screenshot card extraction, or hidden-card extraction.

See [SIMULATION.md](SIMULATION.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), [SECURITY.md](SECURITY.md), and [ROADMAP.md](ROADMAP.md) for further details.

### Single-hand Replay

The Replay tab generates one deterministic local hand through `POST /api/histories/hand`. Use the form, event controls, table-state panel, and selectable timeline to inspect incremental board reveals. Validation and chip-conservation indicators are shown client-side. Folded cards and future board cards remain private; persistent-match replay is future work.
