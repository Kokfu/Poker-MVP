# Architecture

## System overview

The application is local and stateless:

```text
React/Vite frontend
        +-- Analyzer tab
        +-- independent Simulator tab
        +-- persistent Match tab
        |
        | JSON over localhost /api
        v
FastAPI backend
        |
        +-- Analyzer: validation, Treys, NumPy/Monte Carlo
        |
        +-- Simulator API and CLI
                |
                +-- deterministic heads-up engine
                +-- bot strategy layer
                +-- observation boundary
                +-- statistics
                +-- JSONL dataset writer/validator
```

Docker Compose runs the FastAPI backend and React/Vite frontend as separate services. Ports 8000 and 5173 are bound to `127.0.0.1`. There is no database and no application persistence beyond explicitly requested dataset or result files.

## Analyzer

FastAPI validates card notation, uniqueness, board length, opponent count, and numeric constraints before calling the analysis layer. `TreysAdapter` confines Treys hand evaluation to `poker_analyzer.py`. NumPy-backed Monte Carlo uses only unseen cards for preflop, flop, and turn calculations. River equity enumerates exactly 990 possible two-card opponent combinations.

## Simulation components

- `simulation.engine.HandEngine` owns cards, stacks, betting state, legal-action validation, street progression, runout, and settlement.
- `simulation.match.PersistentMatchRunner` is the Phase 3A1 orchestration layer. It creates one clean `HandEngine` per hand and carries only settled stacks into the next hand.
- `simulation.bots` contains `RandomBot`, `TightBot`, `AggressiveBot`, and `EquityBot`.
- `Observation` is the bot-facing information boundary. It exposes the acting player's cards, public board, stacks, commitments, legal actions, and target bounds, but not hidden opponent cards, future board cards, deck order, or RNG state.
- `simulation.statistics` aggregates wins, ties, losses, net chips, net BB, BB/100, showdowns, folds, action counts, and illegal actions.
- `simulation.dataset` writes and validates JSONL schema 2.0 records.
- `simulation.cli` lists bots, runs simulations, generates datasets, and validates datasets.

Bots choose among engine-authoritative legal actions. They do not independently reconstruct betting legality. A malformed custom bot can trigger a safety fallback, but accepted built-in workloads produce no fallback diagnostics.

## Betting state

The engine tracks:

- `current_highest_bet`: the largest current-street commitment.
- `last_full_raise_size`: the increment made by the most recent full bet or raise; it determines the next minimum.
- `pending_players`: players still required to respond before the street can close.
- `acted_since_full_raise`: whether each player has acted since the last full raise.
- `raising_reopened`: whether each player's raising rights are open.
- `acting_player`: the player whose decision is currently requested.

At a new postflop street, current commitments and `current_highest_bet` reset to zero, `last_full_raise_size` resets to one big blind, both players become pending, and the non-button acts first.

## Target-total action semantics

Action amounts are total target commitments for the current street:

- Bet: target the player's total street commitment.
- Raise: target the player's total street commitment after raising.
- Call: commit to the exact `current_highest_bet` when affordable.
- AllIn: target the exact current commitment plus the player's remaining stack.

A normal Raise is exposed only when it is affordable:

```text
minimum_target_to <= maximum_target_to
```

The engine also exposes the exact `all_in_target_to`. Bots must use the supplied bounds and exact targets.

## All-in and reopening behavior

- A short all-in Call cannot reach `current_highest_bet`; unmatched opponent excess is returned.
- An exact all-in Call reaches `current_highest_bet` exactly.
- A short all-in Raise increases the wager but does not meet `last_full_raise_size`; it does not count as a full raise.
- A full all-in Raise meets or exceeds the full-raise increment and reopens action.
- An increasing AllIn cannot bypass closed raising rights.
- When raising rights are closed, an exact or short all-in Call may remain legal.

General cumulative multiway reopening rules are outside this heads-up engine's scope.

## Runout and settlement

When no further betting is possible, the engine automatically deals the remaining community cards. A hand has exactly one fold settlement or one showdown and exactly one settlement. Settlement returns unmatched excess, awards the matched pot, clears the pot and street commitments, clears `pending_players`, marks the hand complete, and asserts chip conservation. Aggregate results remain zero-sum.

## Internal hand-history boundary

Phase 3B1 adds `simulation.history` as a typed observation layer around the authoritative `HandEngine`. The engine appends events while each transition occurs; the history module does not calculate legal actions, betting, cards, winners, or settlement independently.

History schema `1.0` is separate from dataset schema 2.0. A `HandHistory` records deterministic hand identity/configuration, blinds, initial and final stacks, public board, result, diagnostics, and a contiguous event stream. Its event types are:

- `hand_started`
- `blind_posted`
- `action_taken`
- `street_started`
- `board_revealed`
- `unmatched_excess_returned`
- `automatic_runout_started`
- `showdown`
- `pot_awarded`
- `hand_settled`

Every event carries before/after pot, stack, street-commitment, and current-highest-bet evidence. Action events preserve requested and applied actions, engine fallback details, exact amount paid, total target, legal bounds, reopening state, last-full-raise state, pending players, and all-in classification. Thus a raise to 1,200 is stored as target 1,200, consistent with the engine contract.

Blind events distinguish assigned and actually posted amounts, including capped short-stack all-ins. Street and board events reveal the flop, turn, and river separately. Automatic runout records its start and still produces each intermediate public reveal. Settlement is split into showdown when applicable, pot award, and exactly one final cleanup event.

`validate_hand_history` verifies schema support, indexes, event cardinality, state continuity, chip conservation, non-negative values, board progression, card uniqueness, action targets, cleanup, final-result agreement, and privacy. It returns a structured list of useful errors.

Phase 3B2 adds `simulation.history_service` as the only public serialization boundary. It converts typed histories to ordinary JSON-safe dictionaries only after validation, scans forbidden internal keys, constructs deterministic single-hand and persistent-match documents, parses exported documents back into typed models, and coordinates UTF-8 file output with explicit overwrite protection.

`POST /api/histories/hand`, `POST /api/histories/match`, and the `history-hand`, `history-match`, and `validate-history` CLI commands all call this service. The existing match summary endpoint still calls its original serializer and does not gain history fields. Dataset schema 2.0 remains a separate decision-record system.

History JSON is request/command output, not server-side persistence. There is no history database, lookup ID endpoint, process-resumption mechanism, or replay frontend.

## Phase 3 persistent match boundary

Persistent match mode is Phase 3 work in progress and remains separate from `SimulationRunner`:

- `SimulationRunner` retains Phase 2 independent-hand semantics and starts every hand with fresh equal stacks.
- `PersistentMatchRunner` accepts per-player starting stacks, small and big blinds, a deterministic seed, and a maximum hand count.
- The match alternates the button each hand, passes settled stacks into a new `HandEngine`, and stops on elimination or the hand limit.
- The hand engine still owns betting, legal actions, all-ins, runout, unmatched-excess return, and settlement; the match layer does not duplicate poker rules.
- A capped blind post never exceeds the player's available stack. If a blind is all-in, only a live opponent who owes chips receives a decision; otherwise unmatched excess is returned and the board runs out.
- Every hand must finish with exactly one settlement, zero pot, zero current commitments, and no pending players before its stacks are accepted by the match.

Phase 3A2 exposes this orchestration through `simulation.match_service.run_builtin_match`. That adapter normalizes and validates public parameters, constructs seeded built-in bots, invokes `run_match`, flattens the internal dataclasses into the public snake_case response, and checks aggregate invariants. Both `POST /api/matches/simulate` and `simulation.cli match` call this same adapter.

The match API/CLI layer has no poker-rule implementation. Phase 3A3 adds a presentation-only React Match tab that calls the existing endpoint, performs strict client input checks, and renders aggregate and per-hand public output. It does not calculate poker state, persist matches, or alter the independent Simulator. There is still no match dataset integration, database persistence, saved-match browser, or replay system. Dataset schema 2.0 and retained Phase 2 evidence remain unchanged.

## Deployment

Docker Compose provides the reproducible local deployment. The frontend uses its `/api` proxy to reach `http://backend:8000` inside the Compose network. Host access remains on `http://127.0.0.1:5173` and `http://127.0.0.1:8000`.

## Single-hand Replay

`Replay` is a single-hand-only frontend for deterministic local histories: generate through `/api/histories/hand`, navigate events, inspect the selected snapshot and timeline, and observe validation/conservation indicators. Persistent-match replay remains future work.

