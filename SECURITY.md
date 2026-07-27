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

The history validator rejects hole-card disclosure outside showdown, disclosure in fold-ended histories, invalid board progression, duplicate public or revealed cards, and final-state inconsistencies. Full histories remain internal in Phase 3B1 and are not returned through existing APIs, CLI output, frontend responses, dataset schema 2.0, or an export endpoint.

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

- FastAPI/Pydantic validates card notation, card uniqueness, board length, opponent count, numeric bounds, bot names, stack bounds, and EquityBot iteration choices.
- The simulation API is capped at 10,000 hands per request.
- Engine-authoritative legal actions and targets prevent built-in bots from bypassing betting rules.
- A malformed custom-bot fallback uses Check when legal and Fold otherwise, preserving state safety while recording an illegal-action diagnostic.
- Settlement asserts total-chip conservation.
- Hand-history validation checks per-event chip conservation, non-negative stacks and pots, connected before/after snapshots, privacy, and final cleanup.
- Docker Compose binds backend and frontend ports to `127.0.0.1`.
- CORS permits only configured local frontend origins.

The application has no credential store or external-site secrets. Explicitly generated dataset and benchmark files remain on the user's local filesystem and should be handled according to the user's own privacy requirements.
