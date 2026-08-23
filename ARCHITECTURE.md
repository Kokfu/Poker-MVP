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

## Kuhn CFR research isolation

`backend/research/kuhn` is a deliberately separate, exact three-card Kuhn Poker laboratory. It has no imports from the Hold'em engine, no registered bot, API route, frontend dependency, or shared schema. It enumerates the six deals, uses visible-card-plus-public-history information sets, and keeps vanilla full-tree CFR as a control alongside a separate CFR+ implementation. CFR+ projects cumulative regrets to zero after each full iteration and uses documented linear average-policy weights. Its terminal convention is Player 0 utility: check/check is +/-1, bet/fold is +/-1, and bet/call is +/-2.

## Hold'em abstraction research isolation

`backend/research/holdem` is a Phase 4C research-only abstraction layer. It accepts immutable `DecisionState` snapshots and has no `HandEngine` dependency or engine-rule implementation. Its deterministic card abstraction reads only Hero hole cards and cards public on the current street; its information-set key omits opponent cards, future board, deck/deck order, RNG, and identity fields. Action representatives preserve the authoritative total-target contract and are rejected before conversion if their supplied legal interval is empty or their target is outside it; all-in remains distinct so short all-ins cannot be disguised as normal bets or raises. Diagnostics consume caller-supplied deterministic state sets and report compression, card and geometry bucket occupancy/pathology, and round-trip coverage. The package is not a CFR trainer, bot, API, schema, or frontend feature and does not alter Expert, Adaptive, or RangeExpert.

### Phase 4C card and information-set abstraction

The card abstraction is deterministic and uses no equity calculation or RNG. Preflop it sorts Hero's two ranks and assigns: `preflop_premium` to AA/KK or a non-pair score of at least 26; `preflop_strong` to QQ–TT or score at least 22; `preflop_medium` to 99–66 or score at least 18; `preflop_speculative` to lower pairs or score at least 15; and `preflop_weak` otherwise. The non-pair score is high rank plus half the low rank, plus 2 if suited and plus 1 if connected within two ranks.

On flop and turn, `postflop_draw` denotes a Hero-involved four-flush or incomplete straight with at least one completion; `postflop_pair_draw` combines that with one pair. Made-hand categories are `postflop_air`, `postflop_pair`, `postflop_two_pair`, `postflop_trips`, `postflop_straight_plus` (straight or flush), and `postflop_full_house_plus` (full house, quads, straight flush, or royal flush). River has no draw bucket: it uses the applicable made-hand bucket.

The key deliberately abstracts exact min/max target, last-full-raise size, and board texture beyond Hero's made-hand/draw category. Exact bounds are represented operationally by bounded abstract legal actions and are rechecked on every concretization; action labels, pot/SPR/call/commitment bands, public betting history, and reopening state retain the relevant action context. Board texture is intentionally deferred from this small foundation: its direct Hero draw/made-hand effect is retained in the card bucket, while a future strategically richer abstraction may add a separately justified texture bucket. These are intentional aliases, not hidden information reads; tests record matching aliases and contrasting visible states that must remain distinct. Diagnostics report every absent card bucket and report an encountered card bucket as overloaded only for samples of at least 10 states when it contains more than 70% of those states; this is a warning, never a threshold to tune away.

## Analyzer

FastAPI validates card notation, uniqueness, board length, opponent count, and numeric constraints before calling the analysis layer. `TreysAdapter` confines Treys hand evaluation to `poker_analyzer.py`. NumPy-backed Monte Carlo uses only unseen cards for preflop, flop, and turn calculations. River equity enumerates exactly 990 possible two-card opponent combinations.

## Simulation components

- `simulation.engine.HandEngine` owns cards, stacks, betting state, legal-action validation, street progression, runout, and settlement.
- `simulation.match.PersistentMatchRunner` is the Phase 3A1 orchestration layer. It creates one clean `HandEngine` per hand and carries only settled stacks into the next hand.
- `simulation.bots` contains `RandomBot`, `TightBot`, `AggressiveBot`, and `EquityBot`.
- `Observation` is the bot-facing information boundary. It exposes the acting player's cards, public board, stacks, commitments, legal actions, and target bounds, but not hidden opponent cards, future board cards, deck order, or RNG state.
- `simulation.decision_state` provides the Phase 3C1 strategy-facing boundary. `DecisionState` is a typed, immutable snapshot of one legitimate player decision; `PokerFeatureSet` is its deterministic derived feature layer; and `DecisionObservation` combines both with optional `EquityEstimate` data. `HandEngine` builds it immediately before each bot decision. Existing bots continue through the legacy `Observation` adapter, while future strategies may implement `decide_decision(DecisionObservation)` without direct engine access.
- `simulation.statistics` aggregates wins, ties, losses, net chips, net BB, BB/100, showdowns, folds, action counts, and illegal actions.
- `simulation.dataset` writes and validates JSONL schema 2.0 records.
- `simulation.cli` lists bots, runs simulations, generates datasets, and validates datasets.

Bots choose among engine-authoritative legal actions. They do not independently reconstruct betting legality. A malformed custom bot can trigger a safety fallback, but accepted built-in workloads produce no fallback diagnostics.

## Decision intelligence foundation

`DecisionState` derives identity, button/blind context, in/out-of-position status, only hero hole cards plus the currently public board, visible stacks/pot/effective stack, authoritative total-target bounds and legal actions, raise-reopening state, and ordered public action context. It never reads opponent cards, undealt cards, deck contents, burn cards, or RNG state.

`PokerFeatureSet` is deterministic and JSON-safe. It provides pot odds and required equity (`call / (pot + call)`, or zero for a free action), SPR (`effective_stack / pot`, or zero for a zero pot), bet faced as a pot fraction, position flags, made-hand/draw flags, and deterministic board texture. It emits finite values only. Optional `EquityEstimate` is deliberately not computed as part of observation construction, so no solver or RNG work is mandatory. This is an internal foundation: it does not alter public API responses, history schema 1.0, or dataset schema 2.0.

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

## Phase 3C2 opponent-model foundation

`simulation.opponent_model` consumes only completed public `HandHistory` action events. Persistent matches maintain one model per player; the opposing snapshot is attached to `DecisionObservation` before an action and histories are incorporated only after settlement. The model records explicit opportunities and occurrences, raw and Beta(1,1)-smoothed frequencies, and 0–4/5–19/20–49/50+ very-low/low/medium/high confidence. VPIP excludes blinds; a limp is an unopened voluntary preflop call; a 3-bet follows one prior preflop raise. Bet sizing is public wager increment divided by pre-action pot: small <= .40, medium <= .75, large <= 1.25, overbet above. Labels require 20 hands and VPIP opportunities and do not alter strategy. Snapshots are finite JSON-safe and contain no cards, deck, RNG, timestamps, or API/dataset additions.

`Replay` has Single Hand and Persistent Match modes. Both use one event renderer for table state, timeline, navigation, and privacy filtering. Persistent Match uses `/api/histories/match` and adds match overview, hand selection, and stack progression without changing existing public match responses.

## Phase 3C3 ExpertRuleBot

`simulation.expert_bot.ExpertRuleBot`, registered as `expert`, is a deterministic heads-up rule-based baseline. It consumes only `DecisionObservation`, uses engine-authoritative action bounds, and retains internal explanation metadata. It is neither GTO nor a learning system.

## Phase 3C4 adaptive exploit layer

`expert` remains the stable Phase 3C3 control. `adaptive` is the separate `ExpertAdaptiveBot`: it first asks an embedded `ExpertRuleBot` for its baseline decision and explanation, then passes only that result plus the current `DecisionObservation.opponent_profile` into `ExploitAdjustmentEngine`. The engine never queries `HandEngine`, histories, cards, deck, or RNG.

Numeric public estimates, rather than profile labels, drive adjustments. The initial research thresholds are centralized in `exploit_strategy.py`: fold-to-bet >= .62, call-vs-bet >= .62 or fold-to-bet <= .28, aggression >= .42 or <= .18, and preflop fold-to-raise >= .58. Signal strength is bounded deviation from the relevant reference rate multiplied by a confidence weight (very-low 0, low .15, medium .55, high 1). It is explanatory rather than a statistical claim.

Very-low and low confidence retain the baseline. Medium allows controlled changes and high permits stronger, still-bounded sizing. Allowed transitions are only suitable check-to-bet pressure, fold-to-call defense with showdown value, removal of an existing pure bluff against a calling station, and adjustment of existing strong-value sizing. Targets retain engine total-target semantics and are clamped to supplied legal bounds.

The passive-player initiative path uses the same low-aggression threshold (smoothed aggression <= .18) and confidence gate. It may turn only an in-position, dry-board air baseline check into a 33%-pot bet. It does not require the control bot already to hold initiative, because that would exclude the check-back spots the adjustment is intended to address.

For auditability, `ExpertAdaptiveBot` keeps an internal in-memory decision trace. It is derived after the strategy decision from the same observation and explanation and records profile hand count, numeric signal metadata, activation outcome, and rejection rationale. It is not part of histories, datasets, or public API serialization.

## Statistical strategy evaluation

Phase 3D1 adds `simulation.evaluation` as a dedicated research layer above the existing hand and match runners. An immutable `EvaluationConfig` produces a deterministic integer seed schedule, each seed is run in the configured seat orientation(s), raw hand or match units are validated, and aggregation produces evaluation-schema `1.0` JSON. No statistical code is located in a bot, poker engine, public API serializer, history serializer, or dataset writer.

`independent` mode creates a fresh bot pair and reset-stack `HandEngine` for each seed/orientation; its statistical unit is one independently reset hand. `persistent_match` mode creates a fresh `PersistentMatchRunner` for each seed/orientation and preserves stacks, alternating blinds/button, completed-hand opponent profiles, elimination, and the hand limit inside that match; its statistical unit is the whole match. Persistent-match hands are descriptive observations only and are not treated as independent for standard errors or confidence intervals.

Seat swapping runs the strategy as A against the opponent as B and, when enabled, the opponent as A against the strategy as B. Both orientations use a matched seed schedule and are reported separately and combined. This is seat-swapped, orientation-paired evaluation, not claimed duplicate-deal poker: strategy actions can change random trajectories, match lengths, and decisions even when schedules correspond.

Poker seeds and bot decision seeds are deterministic and role-derived. Schedule generation does not instantiate or consume an engine RNG. Percentile bootstrap work uses a separate local `random.Random(statistics_seed)` instance. Report formatting, aggregation, and JSON export use no poker RNG, so confidence analysis cannot change cards, decisions, profiles, or outcomes.

Every evaluated history is validated and every hand and match must satisfy exact heads-up zero-sum chip conservation. Corruption raises `EvaluationAccountingError`; it is never converted into a performance observation. Existing history schema 1.0, dataset schema 2.0, and public API response shapes remain unchanged.

## Short-stack legal-action invariant

Phase 3D1A corrects an authoritative `HandEngine.legal` defect found by evaluation: in a zero-wager street state, a positive stack previously received normal `bet` unconditionally even when its total all-in target was below the one-big-blind minimum. A normal target-based `bet` or `raise` is now advertised only when at least one total target satisfies `minimum_target <= maximum_target`. The engine does not clamp an empty interval into a synthetic target.

The distinct `all_in` action remains available when poker state and reopening rights permit it. Thus a player with 50 chips facing no wager and a 100-chip big blind receives `check` and `all_in`, but not normal `bet`; the all-in target remains the accepted total commitment of 50. Existing short all-in call/raise classification, non-reopening behavior, full-raise reopening, and total-target action semantics are unchanged. Legacy `Observation` and `DecisionObservation` obtain the corrected legal-action tuple directly from the engine.

## Phase 3D2 range and equity intelligence

`simulation.range_intelligence` is optional, privacy-safe inference infrastructure. `HoleCardCombo` is an immutable canonical physical-card pair; legal ranges enumerate only combinations left after Hero cards and the currently public board are removed. `WeightedRange` is finite, nonnegative, deterministically ordered, and normalized. Uniform is the safe default; the compact preflop hand-quality prior is heuristic, not solver-derived.

`RangeUpdater` converts public actions and sizing evidence into floored likelihood weights. Public numeric opponent statistics can influence it only conservatively after medium/high confidence. `RangeEquityEstimator` is exact on the river and uses an isolated seeded RNG for earlier-street Monte Carlo, removing Hero, candidate, and public board cards from each runout. Optional range fields on `DecisionObservation` are unused by Expert and Adaptive.

`PublicRangeTracker` is the explicit history integration boundary. A caller supplies each opponent public action together with the board visible at that action; it has no `HandEngine`, deck, or actual-card input. Summary concentration uses normalized Shannon entropy `-sum(p log p) / log(n)` and effective combinations `1 / sum(p²)`. Equity uses `P(win) + 0.5 P(tie)`.

# Range-aware expert strategy (Phase 3D3)

`RangeAwareExpertBot` (`range_expert`) is separate from the immutable `ExpertRuleBot` and `ExpertAdaptiveBot`.  At each decision the engine supplies only the acting player's cards, public board/actions so far, a `PublicRangeTracker` summary, and (postflop) one range-equity estimate.  The bot applies `RangeStrategyAdjustmentEngine` after the Expert baseline.  It permits only bounded fold/call and modest check/bet value transitions; all targets remain engine-authoritative.

The range represents current-hand public-action hypotheses.  Opponent profiles represent completed-hand behavioural evidence; the range-aware layer does not additionally apply profile signals, avoiding double counting.
