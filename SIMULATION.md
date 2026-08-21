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

## Phase 3C1 decision intelligence foundation

At every bot decision, the engine can build an immutable `DecisionObservation` from authoritative state. Its `DecisionState` includes only the acting player's hole cards and the board revealed at that instant, public stacks/commitments/action context, button/blinds, position, legal actions, total-target bounds, and reopening state. Its `PokerFeatureSet` supplies finite deterministic values: pot odds and required equity are `call / (pot + call)` (zero when `call` is zero); SPR is `effective_stack / pot` (zero when pot is zero); and bet faced is `call / pot` (zero when pot is zero).

Feature categories include canonical made hands, flush/open-ended/gutshot draws, overcards and pair-plus-draw, plus paired/monotone/two-tone/rainbow/connected board texture. The builder neither consumes deck or bot RNG state nor performs equity calculation. An optional `EquityEstimate` can be attached by a future explicit estimator. New strategies can use `decide_decision(DecisionObservation)`; the four existing bots retain their legacy `Observation` contract and behavior. This internal layer does not change dataset schema 2.0, history schema 1.0, or API responses.

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

## Phase 3B2 history interfaces and export

Dedicated interfaces now expose validated histories without changing existing simulation or match responses:

```text
POST /api/histories/hand
POST /api/histories/match
```

The single-hand endpoint accepts built-in bots, independent starting stacks, blinds, button, seed, and EquityBot iterations. The match-history endpoint accepts the same configuration as the existing persistent-match endpoint and returns its public result summary plus one history per completed hand.

The CLI provides:

```text
history-hand
history-match
validate-history <path>
```

Both generation commands print deterministic JSON and optionally accept `--output` and `--overwrite`. `validate-history` accepts either a `hand_history` document or a `match_history` document, validates every typed history, and returns structured counts, errors, warnings, and schema versions. It exits nonzero for malformed or invalid documents.

Files are ordinary UTF-8 JSON:

- `hand_history`: schema identifier, one history, and its validation summary.
- `match_history`: schema identifier, unchanged match summary, ordered histories, counts, and aggregate validation.

History schema 1.0 remains distinct from dataset schema 2.0. This foundation can support future replay work, but it does not include event navigation, visualization, server storage, or match resumption.

## Single-hand Replay

## Phase 3C2 opponent-model foundation

Persistent matches retain public-action opponent models. Each future strategy-facing observation optionally includes the other player's snapshot before the current decision; both models update only from the completed hand afterward. The foundation tracks explicit denominators for general actions, public preflop and postflop opportunities, deterministic sizing buckets, Beta(1,1) smoothing, and conservative sample confidence. It uses no hidden cards, future board, deck, or RNG and does not change bot behavior, API output, or dataset schema 2.0.

`Replay` supports local single-hand and persistent-match histories. Persistent Match exposes aggregate validation, completed-hand selection, stack carry-forward checks, and the same event replay UI. Private folded cards and future board cards remain unavailable until legitimate event data reveals them.

## ExpertRuleBot v1

`expert` consumes the privacy-safe `DecisionObservation`: legal actions/bounds, position, stacks, pot odds, SPR, public action context, made-hand/draw/texture features, optional equity, and optional public-history profile. It groups preflop hands into premium, strong, medium playable, speculative, and weak categories; opens/isolates wider in position; tightens facing a 3-bet; and commits premium/strong hands more readily at 20 BB or less. Postflop it value-bets strong made hands, commits stronger pairs at SPR <= 3, continues strong draws at sensible prices, and makes only deterministic position/initiative/dry-board bluffs.

`adaptive` keeps this `expert` result as its control decision, then applies the separate, numeric `ExploitAdjustmentEngine` only when the pre-decision public profile has medium/high confidence. It uses bounded over-fold pressure, calling-station bluff suppression/value sizing, anti-aggression defense, passive initiative, and selective preflop fold-to-raise pressure. Isolated hands have no accumulated profile and retain baseline behavior; persistent matches update profiles only after settlement.

`simulation.adaptive_benchmark` includes long-horizon diagnostics and non-registered public-behavior archetypes for research tests. They use real engine actions and completed histories rather than injected snapshots. The bot retains an in-memory, non-serialized decision trace recording profile age, selected statistic, confidence, baseline/final action, and activation/rejection reason. This is diagnostic evidence only and does not alter API/history response shapes.

The passive diagnostic uses legal check/call behavior to mature the public `aggressive` statistic. A qualifying low-aggression profile may produce the bounded `passive_initiative` adjustment only from an in-position dry-board air check to a 33%-pot bet.

Sizing is target-total and clamped to engine bounds: 60% pot standard value/protection, 85% pot wet-board strong value, 60% pot draw semi-bluffs, and 33% pot selective bluffs. Supplied equity is compared to required equity with a 4% conservative margin; the bot does not force expensive equity computation. Profile adjustments require medium or high confidence: loose-passive reduces bluffs, loose-aggressive widens bluff-catching, tight-passive permits selective pressure, and tight-aggressive avoids marginal aggression. Low-confidence samples create a warning but no change. Internal explanations include action/target, categories, finite odds/SPR, optional equity, adjustment, rationale, reasons, and warnings. `python -m simulation.expert_benchmark` runs 1,000-hand deterministic diagnostic matchups; it is not a strength claim.

`run_mirrored` runs Expert in both seats for each seed and reports seat-specific plus combined accounting. These are seat-aware independent samples, not duplicate-deal pairs: seat swapping does not guarantee identical deck allocations. `run_legality_stress` covers 20 deterministic seeds against every built-in bot and records decisions, illegal/fallback counts, exceptions, and target incidents.

## Phase 3D1 statistical evaluation

The reproducible Expert-versus-Adaptive command is:

```powershell
cd C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend
.\.venv\Scripts\python.exe -m simulation.evaluation_cli compare --control expert --treatment adaptive --opponent tight --mode persistent_match --sample-count 100 --base-seed 10000 --max-hands 100 --bootstrap-resamples 2000 --statistics-seed 91001
```

Add `--output <path>` for explicit evaluation-schema 1.0 JSON. Existing files are refused unless `--overwrite` is supplied. Output includes the complete configuration and seed list, orientations, hand and unit counts, absolute metrics, confidence intervals, raw matched-unit deltas, warnings, and zero-sum status. A caller-sized unpooled matrix is also available:

```powershell
.\.venv\Scripts\python.exe -m simulation.evaluation_cli matrix --strategies expert adaptive --opponents random tight aggressive equity expert --sample-count 20 --equity-iterations 10
```

BB/100 is `100 * (total_net_chips / big_blind) / hands_played`; it is zero for no hands and is never calculated from match count. Mean, median, and descriptive per-hand values use hand results. Sample standard deviation and standard error use net BB at the evaluation-unit level: a reset hand in `independent`, a whole match in `persistent_match`. Average winning and losing sizes use that same unit.

Uncertainty uses a deterministic percentile bootstrap, defaulting to 2,000 resamples at 95% confidence with a separate statistics seed. Absolute BB/100 resamples whole units and recalculates the total-net-BB/total-hands ratio. Expert-versus-Adaptive deltas resample corresponding seed/orientation entries and recalculate each strategy's BB/100 before subtracting Expert from Adaptive. This is matched-schedule comparison, not duplicate-deal pairing; divergent actions can produce different trajectories and match lengths.

A delta interval entirely above zero is `positive_estimate_supported`; entirely below zero is `negative_estimate_supported`. An interval containing zero produces a directional uncertain label or `approximately_inconclusive` for a zero estimate. These are neutral finite-sample categories, not proof of superiority, GTO play, or a guaranteed winner. Fewer than 30 evaluation units sets machine-readable `sample_warning` without blocking smoke tests.

Adaptive conclusions should use `persistent_match`; independent mode is only a reset-hand sanity check because it provides no accumulated opponent history. Compare opponents separately. Matrix output deliberately supplies no pooled overall effect, avoiding implicit weighting choices.

