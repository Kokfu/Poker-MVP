# Security and privacy boundaries

Poker Analyzer MVP is local educational software. These controls define its scope; they are not a claim that the project is production-grade security software.

## Explicit exclusions

The application does not:

- place or assist with real-money actions;
- integrate with external poker sites;
- automate a browser against a poker platform;
- click poker controls automatically;
- use OCR, screen scraping, or screenshot card extraction;
- access opponent hidden cards;
- expose future board cards;
- expose deck order, remaining deck contents, burn cards, or RNG state;
- provide an AI-training pipeline in Phase 2.

Browser verification is limited to the local application.

## Information boundary

The simulation engine owns hole cards, future cards, deck order, and RNG state. A bot receives only its engine-authoritative `Observation`: its own cards, the public board, visible stacks and commitments, legal actions, and target bounds.

Internal hand-history schema 1.0 follows the same boundary. Action, blind, street, board, runout, and settlement events contain only the public board available at that event. They never contain opponent hole cards, future board cards, deck order, remaining-deck contents, burn cards, or RNG state. At a normal showdown only, the showdown event may contain both legitimately revealed hole-card pairs. A fold-ended history reveals neither player's private cards.

The history validator rejects hole-card disclosure outside showdown, disclosure in fold-ended histories, invalid board progression, duplicate public or revealed cards, and final-state inconsistencies.

Phase 3C1 `DecisionObservation` has the same stricter per-decision boundary: `DecisionState` serializes only hero hole cards and cards public at that decision. It contains no opponent-hole-card, future-board, deck, deck-order, remaining-deck, burn-card, or RNG fields. Its builder is deterministic and read-only; tests recursively inspect serialized observations and verify construction does not change deck order or later deterministic play.

Phase 3B2 exposes histories only through dedicated history API routes and CLI commands. The public serializer validates each typed history before serialization and recursively rejects deck, future-card, remaining-deck, and burn-card keys. Existing Analyzer, Simulator, Match, frontend, and dataset responses do not gain histories or hole cards.

History exports are explicit local UTF-8 JSON files. Existing files require `--overwrite`; there is no automatic export, server-side history database, history lookup endpoint, upload, or external transmission.

Dataset schema 2.0 rejects privacy-leaking keys anywhere in a record, including:

- `opponent_cards`
- `opponent_hole_cards`
- `villain_cards`
- `future_cards`
- `deck`
- `deck_order`
- `remaining_deck`
- `burn_cards`

The validator also rejects unknown fields, malformed values, unsupported schema versions, cross-record terminal inconsistencies, and more than one simulation ID in a file.

## Input and runtime safeguards

Phase 3C2 opponent profiles use only public completed-history actions, stacks, commitments, pot, and street. The persistent match supplies a snapshot before the current action and updates after settlement, so no current/future action, hidden card, future board, deck, or RNG can leak into it. Profile serialization contains only finite aggregate statistics.

Phase 3C4 `adaptive` receives that same immutable pre-decision snapshot only. Its exploit engine receives `DecisionObservation`, the Expert baseline action/explanation, and no engine reference. Therefore decision N cannot incorporate its own action, later actions in its hand, future hands, board cards not yet public, unrevealed hole cards, or deck state. Its explanation serializes only public statistic aggregates and action metadata.

- FastAPI/Pydantic validates card notation, card uniqueness, board length, opponent count, numeric bounds, bot names, stack bounds, and EquityBot iteration choices.
- The simulation API is capped at 10,000 hands per request.
- Engine-authoritative legal actions and targets prevent built-in bots from bypassing betting rules.
- A malformed custom-bot fallback uses Check when legal and Fold otherwise, preserving state safety while recording an illegal-action diagnostic.
- Settlement asserts total-chip conservation.
- Hand-history validation checks per-event chip conservation, non-negative stacks and pots, connected before/after snapshots, privacy, and final cleanup.
- Docker Compose binds backend and frontend ports to `127.0.0.1`.
- CORS permits only configured local frontend origins.

The application has no credential store or external-site secrets. Explicitly generated dataset and benchmark files remain on the user's local filesystem and should be handled according to the user's own privacy requirements.

## Single-hand Replay

`Replay` renders locally generated single-hand and persistent-match histories. The shared event renderer uses only the selected event's public board and fields, so changing hands or moving earlier cannot retain future board cards. Folded hole cards remain hidden; showdown cards may appear only in the legitimate showdown event.

## Phase 3C3 strategy boundary

ExpertRuleBot consumes only the existing `DecisionObservation` privacy boundary. Its profile adjustment uses only optional public completed-hand aggregates, is disabled for very-low/low confidence samples, and never predicts hidden cards. Its decision path consumes neither deck nor bot RNG.

## Evaluation boundary

Phase 3D1 evaluation consumes settled results but does not expand a bot's information boundary. It validates the existing privacy-safe history for every evaluated hand and exports performance values, configuration, seeds, orientations, and adaptive aggregate diagnostics—not deck order, RNG state, future cards, or folded private cards. Evaluation report schema 1.0 is independent of history schema 1.0 and dataset schema 2.0.

Schedule generation, aggregation, confidence intervals, interpretation, and JSON formatting never receive the poker engine's RNG. Bootstrap resampling uses a separately seeded local statistics RNG. JSON files are created only at caller-supplied paths, are UTF-8, and refuse overwrite by default. There is no evaluation API, database, automatic repository artifact, external transmission, or live-poker integration.

