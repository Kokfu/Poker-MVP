# Phase 2 local simulator

The simulator is a deterministic, local-only, heads-up No-Limit Texas Hold'em research environment. It is educational software, not a real-money poker client.

## Hand model

- Exactly two players participate; multiway pots are not supported.
- Every hand independently resets both players to the configured starting stack, normally 100 BB.
- One big blind is 100 integer internal chip units; the default small blind is 50 units.
- The button posts the small blind and acts first preflop.
- The non-button posts the big blind and acts first on the flop, turn, and river.
- The button alternates between players across a simulation.
- There is no rake, ante, tournament structure, ICM, persistent bankroll, or general side-pot model.

The engine owns deck order, hole cards, community cards, stacks, commitments, the pot, legal actions, street progression, and settlement.

## Actions and target totals

The action vocabulary is:

- `Fold`: surrender the matched pot.
- `Check`: pass when the amount to call is zero.
- `Call`: reach the exact current highest commitment when the player can cover it.
- `Bet`: create the first wager on a street.
- `Raise`: increase an existing wager.
- `AllIn`: commit the player's complete remaining stack.

Bet and Raise amounts are total target commitments for the current betting round, not incremental chip additions. Call has an exact target equal to `current_highest_bet`; AllIn has an exact target equal to the player's current street commitment plus remaining stack.

The engine exposes `minimum_target_to`, `maximum_target_to`, and `all_in_target_to`. A normal Raise is legal only when:

```text
minimum_target_to <= maximum_target_to
```

## Full-raise calculation

For a full Raise:

```text
new_full_raise_size = new_target_to - prior_current_highest_bet
next_minimum_raise_to = current_highest_bet + last_full_raise_size
```

Verified target-total example:

```text
wager to 100
Raise to 300: increment 200, next minimum 500
Raise to 700: increment 400, next minimum 1100
```

## All-in classifications

- Short all-in Call: the all-in target remains below `current_highest_bet`.
- Exact all-in Call: the all-in target equals `current_highest_bet`.
- Short all-in Raise: the target exceeds `current_highest_bet` but the increment is smaller than `last_full_raise_size`.
- Full all-in Raise: the increment meets or exceeds `last_full_raise_size`.
- Opening all-in Bet: an all-in creates the first wager on a street.

An unmatched amount above the shorter player's matched commitment is returned before settlement.

## Reopening

A full Raise resets the full-raise baseline and reopens action. A short all-in Raise increases the wager but does not count as a full Raise and does not reopen raising rights for a player who has already acted. An increasing AllIn cannot bypass closed raising rights. Exact and short all-in Calls can remain legal even when further raising is closed.

These rules cover the engine's heads-up states. General cumulative multiway reopening rules are outside scope.

## Automatic runout and settlement

When one or both players are all-in and no decision remains, the engine automatically deals the remaining board. Each hand reaches exactly one fold ending or one showdown and exactly one settlement.

Settlement:

- returns unmatched excess;
- awards the matched pot;
- splits a tied pot in integer units, with a deterministic odd-chip rule;
- clears the pot;
- clears both current-street commitments;
- clears `pending_players`;
- marks the street complete;
- verifies total-chip conservation.

The two players' per-hand and aggregate net results sum to zero.

## Bot contract

Bots consume engine-authoritative `Observation` objects. An observation contains the acting bot's private cards, public board, visible stacks and commitments, legal actions, and exact target bounds. It never contains opponent hole cards, future board cards, deck order, remaining deck contents, or RNG state.

Built-in bots must return actions consistent with the observation:

- `RandomBot`
- `TightBot`
- `AggressiveBot`
- `EquityBot`

The engine validates every submitted action. A fallback exists only as a state-safety guard for malformed custom bots: Check is used when legal, otherwise Fold. Final built-in runtime evidence contains zero illegal actions and zero fallback diagnostics.

EquityBot estimates equity against a random unknown opponent. Its result is heuristic and its configurable Monte Carlo iterations trade runtime for precision.

## Statistics

For each player:

```text
net_chips = final_stack - starting_stack
net_bb = net_chips / big_blind_units
bb_per_100 = net_bb / hands_played * 100
```

Final stacks are not accumulated as profit. Each hand starts from a fresh stack baseline, while `net_chips` is accumulated across hands.

BB/100 can be numerically extreme because every hand resets to a fresh 100-BB stack and baseline bots may use high-variance all-in strategies. It is a mechanically correct rate for the sampled independent hands, not a claim of sustainable poker performance.

## Interfaces

CLI:

```powershell
cd backend
.\.venv\Scripts\python.exe -m simulation.cli list-bots
.\.venv\Scripts\python.exe -m simulation.cli run --bot-a random --bot-b aggressive --hands 1000 --seed 42
```

API:

```text
POST /api/simulations/run
```

The API accepts at most 10,000 hands per request. The React Simulator tab exposes bot, hand-count, seed, starting-stack, and EquityBot iteration controls.

## Dataset schema 2.0

Dataset generation is optional and writes one JSON decision record per line. Records include the acting bot's observation, chosen action and target, classification, terminal winner, net chips, reward in BB, and hand ending. The strict validator checks schema, types, target semantics, legal-action consistency, per-hand terminal consistency, privacy boundaries, and that a file contains only one simulation ID.

Schema 1.0 migration and a separate dataset manifest are not supported.

## Phase 3 persistent match mode

Persistent match mode is a separate orchestration mode. It does not change Phase 2 independent simulations.

`MatchConfig` supplies per-player starting stacks, small and big blinds, a maximum hand count, and a deterministic seed. For each hand, `PersistentMatchRunner`:

1. alternates the button, with the button posting the small blind;
2. creates a fresh `HandEngine` using the carried stacks;
3. lets the existing engine perform betting, all-in handling, automatic runout, and settlement;
4. requires exactly one settlement and clean terminal hand state;
5. records a per-hand summary;
6. carries the settled ending stacks into the next hand.

The match ends immediately when a player reaches zero chips. Otherwise it ends when `max_hands` is reached. The final winner is Bot A or Bot B according to final stacks; equal stacks at the hand limit produce `tied`. Total match chips remain constant and Bot A/B net results are exact opposites.

Blind posts are capped by available chips. A short-stacked big blind can leave the button with an exact call decision. A short or all-in blind that requires no response triggers unmatched-excess return where needed and automatic board runout. No negative stack or multiway side pot can be created.

The result contains the match ID, seed, bot names, starting and final stacks, hand count, winner, termination reason, net chips, showdown/fold totals, illegal/fallback counts, and per-hand summaries. Each summary records positions, starting/ending stacks, winner, nets, ending type, board, diagnostics, and settlement completion.

Phase 3A2 exposes the same orchestration through:

```text
POST /api/matches/simulate
```

and:

```powershell
.\.venv\Scripts\python.exe -m simulation.cli match --bot-a tight --bot-b aggressive --starting-stack 10000 --small-blind 50 --big-blind 100 --max-hands 100 --seed 42 --equity-iterations 500
```

Both interfaces use `run_builtin_match`; neither duplicates match rules. Defaults are random/random bots, a 10,000-unit stack per player, 50/100 blinds, 100 maximum hands, seed 0, and 1,000 equity iterations.

Public validation requires supported case-normalized bot names; positive integer stack and blinds; small blind no greater than big blind; 1–10,000 hands; integer seed; and 500, 1,000, or 2,000 equity iterations. Boolean values are not accepted as integers.

The public response omits private hole cards and returns flattened configuration, outcome, aggregate statistics, and per-hand settlement summaries.

Phase 3A3 adds a **Match** tab to the React frontend. Its form exposes both bots, starting stack, blinds, maximum hands, seed, and EquityBot iterations. The result view shows the winner and termination reason, final stacks, nets, showdown/fold totals, illegal/fallback counts, explicit chip-conservation and zero-sum indicators, and every public per-hand summary. The wide hand table scrolls inside its own container on narrow viewports.

The frontend does not change engine or API semantics. Match results are session-only: there is still no match dataset output, database persistence, saved-match browser, replay UI, or multiway support.

## Phase 3B1 action-level history foundation

Every completed `HandEngine` result now provides an internal `HandHistory` using history schema `1.0`. Persistent-match summaries retain the corresponding history internally while their public API representation remains unchanged.

The event stream records hand start, each blind post, every requested/applied action, street starts, incremental public-board reveals, unmatched-excess returns, automatic-runout start, showdown, pot award, and final settlement. Indexes start at zero and are contiguous. Every event carries connected before/after chip and betting snapshots.

Action amounts retain total-target semantics. For example, a raise to 1,200 is recorded as target 1,200 and the amount paid is separately recorded as the difference from the actor's prior street commitment. Short and exact all-in calls, short/full all-in raises, reopening state, legal target bounds, and fallback application are explicit.

Blind history stores both assigned and posted amounts, so a player with 30 chips assigned a 50-chip small blind records a 30-chip all-in post without implying a negative stack. During automatic runout, flop, turn, and river remain separate reveal events rather than appearing as an immediate five-card board.

At showdown, both legitimately revealed hole-card pairs may appear only on the showdown event. Fold-ended histories reveal no hole cards. No event contains future board cards, deck order, remaining-deck contents, or burn cards.

`validate_hand_history` is an internal replay-validation foundation. It checks continuity, conservation, board growth, action evidence, privacy, exactly-once settlement, cleanup, and agreement with the authoritative result. Phase 3B1 does not add a history API, CLI command, file export, persistence, or replay interface.
