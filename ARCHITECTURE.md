# Architecture

## System overview

The application is local and stateless:

```text
React/Vite frontend
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

## Phase 3 persistent match boundary

Persistent match mode is Phase 3 work in progress and remains separate from `SimulationRunner`:

- `SimulationRunner` retains Phase 2 independent-hand semantics and starts every hand with fresh equal stacks.
- `PersistentMatchRunner` accepts per-player starting stacks, small and big blinds, a deterministic seed, and a maximum hand count.
- The match alternates the button each hand, passes settled stacks into a new `HandEngine`, and stops on elimination or the hand limit.
- The hand engine still owns betting, legal actions, all-ins, runout, unmatched-excess return, and settlement; the match layer does not duplicate poker rules.
- A capped blind post never exceeds the player's available stack. If a blind is all-in, only a live opponent who owes chips receives a decision; otherwise unmatched excess is returned and the board runs out.
- Every hand must finish with exactly one settlement, zero pot, zero current commitments, and no pending players before its stacks are accepted by the match.

Phase 3A2 exposes this orchestration through `simulation.match_service.run_builtin_match`. That adapter normalizes and validates public parameters, constructs seeded built-in bots, invokes `run_match`, flattens the internal dataclasses into the public snake_case response, and checks aggregate invariants. Both `POST /api/matches/simulate` and `simulation.cli match` call this same adapter.

The match API/CLI layer has no poker-rule implementation. There is still no match frontend, dataset integration, or database persistence. Dataset schema 2.0 and retained Phase 2 evidence remain unchanged.

## Deployment

Docker Compose provides the reproducible local deployment. The frontend uses its `/api` proxy to reach `http://backend:8000` inside the Compose network. Host access remains on `http://127.0.0.1:5173` and `http://127.0.0.1:8000`.
