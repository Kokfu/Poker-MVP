# Poker Analyzer MVP

Poker Analyzer MVP is a local, educational, offline-first Texas Hold'em analyzer and heads-up simulator. It accepts manually entered poker states, performs mathematical analysis, and runs deterministic bot-versus-bot experiments on the local machine. It does not play poker for the user.

## Status (2026-11-25)

Phase 5 is COMPLETE under the owner's revised criterion. The original pool-score criterion remains open. Opponent-model proposals A (`solver_adaptive_gated`) and B (`solver_adaptive_sized`, bet-size-conditioned reads) failed their pre-registered tests and remain opt-in. See [ROADMAP.md](ROADMAP.md) and [DEVELOPMENT.md](DEVELOPMENT.md).

## Phase 5 at a glance

- **`solver` bot** — preflop charts solved offline plus a real-time range solve of every postflop street (discounted CFR over both players' public ranges). Select it anywhere a bot is chosen.
- **`solver_adaptive` bot** — the same solver, adjusting to confident reads of its opponent's public tendencies (node locking), learned hand by hand.
- **Coach tab** — enter heads-up hands by clicking cards in a four-colour deck or using the keyboard. The solver recommends a play with action frequencies, postflop EV, and an estimated opponent range. Logging finished hands under an opponent's name builds their profile. **Review** shows your results and possible leaks. **Saved data** shows the database path and controls for deleting logged hands. With **Opponents 2–8**, the default advice compares random-hand equity with pot odds. The optional action model is described below.
- **Duplicate-deal evaluation** — every deal is replayed with seats swapped to cancel card luck; learning sessions measure opponent adaptation; a Slumbot bridge benchmarks against a strong outside bot.

### Fast entry in the Coach

Every step of a hand can be entered from the keyboard (on a phone, the same steps are one tap each):

| Step | Keys |
| --- | --- |
| Cards (yours, board, their shown cards) | rank then suit, e.g. `a` `s` = A♠, `t` `d` or `1` `0` `d` = 10♦; `Backspace` removes the last card |
| Start the hand / add a street | automatic once the cards are in (turn off under **Speed**) |
| You followed the advice | `Enter` |
| Fold / check or call / bet or raise / all-in | `F` / `C` / `B` / `A` |
| A bet or raise of a given total | type the number, then `Enter` (or click a size chip: one click records it) |
| Undo (steps back through cards too) | `Z` |
| Next hand | `N`; the finished hand is saved to the opponent's profile and stacks carry over |
| Flip position before the hand | `P` |

Blinds, stacks, opponent name and the Speed options are remembered in the browser between visits.

On the opponent's turn, **Recent** records a legal bet or raise from their saved hands in one click. The total is scaled to the current big blind.

The Coach is manual entry for study, review, and practice. Using real-time assistance while playing on a poker site breaks most sites' rules; this project does not automate or assist play on any site.

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

The original baseline bots are `RandomBot`, `TightBot`, `AggressiveBot`, and `EquityBot`; later phases add `expert`, `adaptive`, `range_expert`, `solver`, and `solver_adaptive` (plus two experimental variants that are off by default: `solver_adaptive_gated`, not adopted, and `solver_adaptive_sized`, bet-size-conditioned reads, tested and not adopted; see ROADMAP). All are research strategies, not claims of optimal play.

Chip amounts are integer internal units:

```text
1 BB = 100 internal chip units
net_chips = final_stack - starting_stack
net_bb = net_chips / big_blind_units
bb_per_100 = net_bb / hands_played * 100
```

Each hand begins from a fresh configured stack, normally 100 BB. Results are not a persistent bankroll.

Phase 3 adds a separate persistent match mode: settled stacks carry between hands, positions alternate, and the match stops on elimination or a configured hand limit. Independent simulation mode still resets both stacks every hand. Open the **Match** tab in the local frontend to configure and run this mode.

## One-click start (you and friends on the same Wi-Fi)

Double-click **`Start Poker Coach.cmd`** in this folder.

- The first run sets everything up (Python 3.11 and Node.js must be installed; it creates `backend/.venv` and installs the web packages).
- It starts the Coach engine on this computer only and the web page on your home network, opens the page, and prints the address for friends, e.g. `http://192.168.1.20:5173`. Friends open that address in a phone or laptop browser on the same Wi-Fi.
- Press **Enter** in the window to stop. If you closed the window instead, double-click **`Stop Poker Coach.cmd`** (the next start also cleans up).
- The page is shared only when Windows marks the network **Private**. On a Public network (cafe, hotspot) it stays on this computer.
- Everyone shares one saved-hands file, and anyone who can open the page can delete hands, so share the address only on a network you trust.
- Different ports: set `POKER_API_PORT` / `POKER_WEB_PORT` before starting. Logs are in `.run/`.

## Timed practice table

From the repository root in PowerShell, the following starts Coach with a disposable saved-hands database:

```powershell
$env:COACH_DB_PATH = Join-Path $env:TEMP ('poker-practice-' + [guid]::NewGuid() + '.sqlite')
& '.\Start Poker Coach.cmd'
```

1. Open **Practice table**, enter a name for the opponent labelled **BOT**, and click **Start practice table**.
2. The clock starts at 20 seconds on each turn. Set **Seconds per action** before starting to choose a different limit, from 1 to 120 seconds. At expiry, the table checks if possible and otherwise folds. Sized actions use the total committed on the current street.
3. After each hand, Coach shows what it would have played and saves the hand under the opponent's name. **Review last session** lists differences and the estimated chip cost where the solver provides comparable EVs. Postflop custom sizes can show cost unavailable.
4. Use **New table** to open a second table. Refresh in the same browser tab to reconnect to the selected seat while the server is running. Each table's clock continues while the other table is selected.

To test on a second device, follow the [LAN checklist](docs/practice-table-lan-checklist.md).

To enable optional **Opponent actions** in multiway Coach, set the flag before starting:

```powershell
$env:POKER_COACH_MULTIWAY_RANGES = '1'
& '.\Start Poker Coach.cmd'
```

Choose two or more opponents, enter cards and the pot, then record each active opponent's visible actions in street order. The model uses those actions to reweight each opponent's range.

## Offline agent CLI

From the repository root in PowerShell, run a paired session diagnostic. Each hand is replayed with the agent in the other seat. To continue an interrupted run, repeat the same command and include `--resume`.

```powershell
Set-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m simulation.agent_cli --run practice-demo --opponent tight --sessions 3 --session-hands 4 --seed-offset 27000
.\.venv\Scripts\python.exe -m simulation.agent_cli --run practice-demo --opponent tight --sessions 3 --session-hands 4 --seed-offset 27000 --resume
```

The ledger and summary are under `benchmark-results/agent/`. The summary includes bb/100, a bootstrap interval, per-session results, illegal actions, engine and solver fallbacks, and deal mismatches. For a local learning experiment, use the same `--profile-dir` and opponent across runs. Give each run a unique name and a fresh, non-overlapping seed offset.

```powershell
# From backend
.\.venv\Scripts\python.exe -m simulation.agent_cli --run learning-1 --opponent tight --sessions 3 --session-hands 4 --seed-offset 61000 --profile-dir ..\benchmark-results\agent\profiles
.\.venv\Scripts\python.exe -m simulation.agent_cli --run learning-2 --opponent tight --sessions 3 --session-hands 4 --seed-offset 62000 --profile-dir ..\benchmark-results\agent\profiles
```

Learning reports include early and late bb/100 and the numbers of hands in each profile. Sessions share learning state, so their results are descriptive. [Agent architecture and replay contract](AUTONOMOUS_AGENT.md)

## Requirements

- Python 3.11; the accepted Windows environment uses Python 3.11.9.
- Node.js 20 or newer and npm for local frontend development.
- Docker Desktop with Docker Compose for the containerized workflow.

## Local development

Replace `path\to\poker-analyzer-mvp` below with the folder of your own clone. First-time setup, tested from a fresh `git clone`:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider   # full suite, takes several minutes
cd ..\frontend
npm.cmd ci
npm.cmd run build
```

Backend:

```powershell
cd path\to\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Frontend:

```powershell
cd path\to\poker-analyzer-mvp\frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. The backend listens on `http://127.0.0.1:8000`. When running the frontend outside Docker, point Vite at the local backend with `$env:API_PROXY = "http://127.0.0.1:8000"` before `npm.cmd run dev`. The tabs are Coach (default), Practice table, Equity calculator, Bot simulator, Bot match, and Replay.

## Docker

```powershell
cd path\to\poker-analyzer-mvp
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail 200
docker compose down
```

The configured ports bind to localhost. The frontend proxies `/api` requests to the backend service.

## API

- `GET /api/health`
- `POST /api/analyze` — equity and pot-odds check; `opponents` is 1-8 (1 = the original heads-up calculation, exact on the river; 2-8 = Monte Carlo against that many random hands, ties split)
- `POST /api/simulations/run`
- `POST /api/matches/simulate`
- `POST /api/histories/hand`
- `POST /api/histories/match`
- `POST /api/coach/advise` — replay a manually entered spot; returns advice, the villain's legal actions, or the next board cards needed
- `POST /api/coach/hands` — log a completed hand under an opponent name
- `GET /api/coach/review[?opponent=name]` — stats (VPIP, PFR, 3-bet, fold-to-raise, fold-to-bet, showdown results), net result, and heuristic leak flags over your logged hands
- `GET /api/coach/opponents`, `GET /api/coach/opponents/{name}` — logged opponents and their profiles
- `GET /api/coach/opponents/{name}/hands` — that opponent's logged hands, newest first, each with its `id` and `created_at`
- `DELETE /api/coach/hands/{id}` — delete one logged hand (404 if the id does not exist)
- `DELETE /api/coach/opponents/{name}` — delete every logged hand for that opponent
- `GET /api/coach/storage` — database file path, size, hand and opponent counts
- `DELETE /api/coach/hands?confirm=delete-all` — delete every logged hand for every opponent (the file is compacted afterwards)
- `POST /api/coach/multiway` — equity vs 1-8 random hands plus pot-odds advice for `hero_cards`, `board`, `opponents`, `pot`, `to_call`

Every registered bot (`random`, `tight`, `aggressive`, `equity`, `expert`, `adaptive`, `range_expert`, `solver`, `solver_adaptive`, `solver_adaptive_gated`, `solver_adaptive_sized`) is accepted wherever the API takes a bot name.

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
cd path\to\poker-analyzer-mvp\backend
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

- The solver Coach is heads-up only. Multiway pots (2-8 opponents) get a simpler equity-vs-random-hands and pot-odds estimate, which overstates equity against players who chose to stay in.
- The solver's flop and turn solves value the end of the street by equity over the remaining cards; future-street betting and position after that street are not modelled. Preflop charts value a seen flop by raw equity.
- Solver decisions take about 1-3 seconds each on a desktop CPU.
- No tournament structure, rake, antes, or ICM.
- No general side pots beyond heads-up matched-chip settlement and unmatched-excess return.
- No persistent bankroll across independent hands.
- No AI-training pipeline.
- No schema 1.0 migration, separate dataset manifest, or multiple simulation IDs per dataset file.
- EquityBot is computationally expensive, especially in long runs.
- Monte Carlo analysis is approximate and varies unless seeded.
- The frontend Analyzer has no loading or disabled submission state.
- Persistent matches have no dataset output, database persistence, or saved-match browser; results exist only in the current frontend session or API/CLI response.
- History JSON can be returned or written explicitly and replayed in the Replay tab, but there is no server-side history store, lookup endpoint, or cross-process resumption. The only stored data is the Coach hand log (local SQLite).
- Browser verification covers only the local application.
- No real-money integration, external poker-site automation, automatic clicking, OCR, screen scraping, screenshot card extraction, or hidden-card extraction.

See [SIMULATION.md](SIMULATION.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), [SECURITY.md](SECURITY.md), and [ROADMAP.md](ROADMAP.md) for further details.

### Single-hand Replay

The Replay tab has Single Hand and Persistent Match modes. Persistent Match calls `POST /api/histories/match`, provides the match form, overview and aggregate checks, completed-hand controls, a responsive stack-progression table, and the shared event replay panel. Histories are local to the current browser session: there is no storage, lookup, upload, or resumption. Folded cards remain hidden and board cards appear only at their reveal event.
