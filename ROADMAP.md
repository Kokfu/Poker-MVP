# Roadmap

## Phase 1: Analyzer — complete

Phase 1 delivered manual card entry, strict state validation, Treys hand evaluation, preflop/flop/turn Monte Carlo equity, exact river enumeration, hero-specific draw detection, pot odds, and an educational recommendation.

## Phase 2: Local heads-up simulator — complete

Phase 2 is accepted. It delivered:

- a deterministic heads-up No-Limit Texas Hold'em engine;
- `RandomBot`, `TightBot`, `AggressiveBot`, and `EquityBot`;
- an engine-authoritative legal-action and target-bounds contract;
- target-total Bet, Raise, Call, and AllIn semantics;
- deterministic scripted preflop and postflop betting matrices;
- short/full all-in classification and heads-up reopening behavior;
- automatic board runout;
- fold and showdown settlement with unmatched-excess return;
- exactly-once settlement and zero-sum per-hand accounting;
- independent stack resets and audited per-hand statistics;
- JSONL dataset schema 2.0 and strict positive/negative validation;
- hidden-information isolation through the bot observation boundary;
- CLI and API simulation;
- a React Simulator frontend;
- retained stress, ordered-pairwise, benchmark, browser, and Docker acceptance evidence.

### Final acceptance evidence

- Backend suite: 275 passing tests.
- Dataset-targeted suite: 98 passing tests.
- Scripted-targeted suite: 56 passing tests.
- Five-seed stress: 5 entries and 5,000 hands.
- Ordered pairwise matrix: 16 ordered matchups and 4,000 hands.
- Required benchmark matrix: 4 workloads and 22,000 hands.
- Final built-in runtime evidence: zero illegal actions, zero fallback diagnostics, and zero-sum results.
- Valid retained dataset: schema 2.0, 202 decision records across 100 hands, zero invalid records, and zero forbidden hidden-information fields.
- Frontend production build, Analyzer browser flow, Simulator browser flow, responsive/basic accessibility checks, Docker runtime, restart, and cleanup all accepted.

Retained artifacts:

- `benchmark-results/dataset-valid-seed42.jsonl`
- `benchmark-results/post-dataset-runtime/five-seed-stress.json`
- `benchmark-results/post-dataset-runtime/pairwise-results.json`
- `benchmark-results/post-dataset-runtime/benchmark-results.json`

### Accepted checklist

- [x] Phase 1 Analyzer
- [x] Deterministic heads-up engine
- [x] Betting and target-total Raise semantics
- [x] Short/full all-in behavior
- [x] Reopening behavior for heads-up scope
- [x] Automatic runout
- [x] Fold and showdown settlement
- [x] Built-in bot legality
- [x] Malformed custom-bot fallback
- [x] Hidden-information isolation
- [x] Dataset schema 2.0
- [x] Dataset negative validation
- [x] Five-seed stress
- [x] Ordered pairwise matrix
- [x] Four required benchmarks
- [x] Frontend production build
- [x] Analyzer browser flow
- [x] Simulator browser flow
- [x] Docker runtime, restart, and cleanup
- [x] Final documentation and lightweight checks

## Known limitations

Phase 2 remains heads-up only. It has no multiway pots, tournament structure, general side-pot model, or persistent bankroll. Dataset schema 1.0 migration and separate manifests are unsupported, and each dataset file accepts one simulation ID. EquityBot and Monte Carlo calculations can be expensive and remain approximate. The built-in bots are research baselines, not optimal poker strategies. The Analyzer frontend has no loading/disabled submission state. Browser verification is local only. There is no real-money integration, external poker-site automation, OCR, screen scraping, hidden-card extraction, or AI-training pipeline.

## Phase 3 — in progress

### Phase 3A1: Persistent match engine foundation

The backend foundation now includes:

- persistent per-player stacks across hands;
- configurable starting stacks and blinds;
- deterministic hand seeds;
- alternating button and blind positions;
- elimination and hand-limit termination;
- short/all-in blind handling;
- chip-conserving per-hand summaries and aggregate match results;
- strict separation from Phase 2 independent-hand simulations.

### Phase 3A2: Persistent match API and CLI

The backend now exposes the same match orchestration through:

- validated `POST /api/matches/simulate`;
- `python -m simulation.cli match`;
- shared public response serialization and invariant checks;
- deterministic API/CLI equivalence;
- focused positive, negative, compatibility, and Docker acceptance coverage.

Phase 3 as a whole is not complete. There is no persistent-match frontend, dataset output, database persistence, replay UI, AI training, multiway poker, tournament model, or external integration. Any subsequent Phase 3 work requires a separate scope and explicit authorization.
