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

## Phase 4A — Kuhn Poker vanilla CFR foundation

Phase 4A adds an isolated canonical Kuhn Poker research package: immutable game state, private-information-safe information sets, exact chance traversal, vanilla CFR, average strategies, exact EV, information-set-constrained best response, and NashConv/exploitability diagnostics. It intentionally excludes Hold'em CFR, abstraction, sampling variants, CFR+, neural methods, persistence, APIs, and UI work. Kuhn is a mathematical validation step, not a claim that Hold'em strategy is solved.

## Phase 4B — CFR+ and convergence tooling

Phase 4B retains the accepted Vanilla CFR implementation as an independent control and adds a separate exact-chance CFR+ trainer. CFR+ truncates cumulative regrets after each frozen-profile six-deal iteration; it does not replace Vanilla CFR. The reusable convergence reporter evaluates both algorithms at deterministic matched checkpoints using exact EV, information-set-constrained best responses, NashConv, and exploitability. CFR+ average policies use documented linear weights with an explicit optional delay. This remains isolated Kuhn research: no Hold'em engine, bot, schema, API, or frontend integration is introduced.

## Phase 4C — Heads-Up Hold'em abstraction foundation

Phase 4C adds a research-only deterministic abstraction package that consumes the immutable player-visible `DecisionState` boundary. It buckets Hero's preflop holding or current public-board hand strength/draw state, maps authoritative legal Hold'em actions into fold/check/call/all-in plus 50%, 75%, and 125%-pot sizing representatives, and returns only bounded total-target actions. Information-set keys include street, position, public betting context, legal abstract actions, and bucketed pot/stack geometry, while excluding opponent cards, future board, deck order, IDs, and RNG. Deterministic diagnostics report concrete-to-abstract compression, card-bucket occupancy/pathologies, and action mapping coverage/errors. This deliberately does not add Hold'em CFR training, a bot, API/schema/UI change, or any production-strategy change.

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

### Phase 3A3: Persistent match frontend

The frontend now includes:

- a distinct Match tab backed by `POST /api/matches/simulate`;
- strict whole-number client validation and duplicate-submission protection;
- persistent-match defaults for bots, stacks, blinds, hand limit, seed, and equity iterations;
- aggregate winner, termination, stack, net, showdown/fold, illegal-action, and fallback output;
- visible chip-conservation and zero-sum invariant indicators;
- all returned hand summaries, including positions, stack transitions, outcomes, board, diagnostics, and settlement status;
- responsive form, summary, and contained horizontally scrollable table layouts.

### Phase 3B1: Action-level hand-history foundation

The backend foundation now includes:

- typed internal history schema 1.0, separate from dataset schema 2.0;
- deterministic zero-based event streams emitted by `HandEngine`;
- blind, action, street, incremental board-reveal, automatic-runout, unmatched-return, showdown, pot-award, and settlement events;
- total-target and exact-payment action evidence;
- short-stack blind and all-in classification evidence;
- connected pot, stack, commitment, reopening, and pending-player snapshots;
- showdown-only hole-card disclosure with fold and future-card privacy;
- an internal validator for continuity, chip conservation, cards, action evidence, cleanup, privacy, and authoritative-result agreement;
- internal history retention on persistent-match hand summaries without public response changes.

### Phase 3B2: History API, CLI, and JSON export

The history foundation now has:

- validated `POST /api/histories/hand` and `POST /api/histories/match` interfaces;
- `history-hand` and `history-match` CLI generation commands;
- optional UTF-8 JSON output with explicit overwrite protection;
- `hand_history` and `match_history` document types using history schema 1.0;
- a `validate-history` CLI command for both document types;
- structured validation counts, errors, warnings, and discovered schema versions;
- recursive privacy enforcement and existing-response compatibility tests;
- no changes to dataset schema 2.0 or existing Analyzer, Simulator, and Match response shapes.

Phase 3B as a whole is not complete. There is no database persistence, stored-history lookup, cross-process match resumption, saved-history browser, action replay UI, replay navigation, dataset integration, AI training, multiway poker, tournament model, or external integration. Any subsequent Phase 3 work requires a separate scope and explicit authorization.

### Phase 3C1: Decision intelligence foundation

The backend now has a typed, deterministic internal `DecisionState`, `PokerFeatureSet`, optional `EquityEstimate`, and normalized `DecisionObservation` boundary for future strategies. It exposes only legitimate player-visible state, authoritative betting bounds and public action context, deterministic hand/draw/board features, and finite pot/stack features. Existing bots and public response shapes remain unchanged. This does not provide opponent modeling, player classification, ExpertRuleBot, CFR, neural policy, reinforcement learning, GTO solving, training, persistence, or a Decision Intelligence UI. Phase 3C2 may add explicitly scoped opponent modeling; a future phase may add an `ExpertRuleBot` on this boundary.

## Single-hand Replay

### Phase 3C2: Opponent modeling foundation

The backend now has deterministic public-history opponent profiles with explicit opportunity denominators, finite smoothed estimates, confidence categories, sizing buckets, and descriptive player-type labels. Persistent matches provide the opposing pre-decision profile but no bot adapts to it. Phase 3C remains incomplete: a future 3C3 may add a scoped ExpertRuleBot; there is no solver, training, persistence, or frontend profile.

### Phase 3C3: ExpertRuleBot v1

Phase 3C3 adds the `expert` deterministic rule-based heads-up baseline: compact preflop categories, position/stack-aware play, made-hand/draw/texture rules, pot odds and SPR thresholds, legal total-target sizing, conservative confidence-gated public-history adjustments, and internal explanations. It is a heuristic educational baseline, not GTO, CFR, reinforcement learning, or an expert-human claim. Phase 3C4 may add a carefully evaluated exploit layer while retaining these safeguards.

### Phase 3C4: Opponent-aware exploit strategy

`adaptive` is a separate, confidence-gated layer over the unchanged `expert` control. It uses public numeric profile estimates only, bounded legal adjustments, and persistent-match diagnostics. Phase 3D remains the place for stronger statistical evaluation; Phase 3C4 does not claim superiority from finite samples.

### Phase 3B3B: Persistent-Match Replay Frontend

The Replay tab now supports locally generated persistent-match documents through `/api/histories/match`, with form validation, match overview, aggregate invariants, completed-hand selection, stack progression, and the shared privacy-safe event replay UI. Phase 3B remains incomplete: there is still no stored-history lookup, database persistence, cross-process resumption, match editing, dataset integration, AI training, multiway poker, tournaments, or external integration.

### Phase 3D1: Statistical strategy evaluation framework

The backend now has a deterministic evaluation layer with independent-hand and persistent-match modes, whole-match inference for adaptive experiments, matched seed schedules, seat-swapped orientation reporting, exact zero-sum/history validation, centralized BB/100, unit-level variance and standard error, deterministic percentile-bootstrap confidence intervals, neutral interval interpretation, small-sample warnings, adaptive activation aggregates, Expert-versus-Adaptive delta reports, unpooled strategy matrices, metadata-only regression comparisons, evaluation schema 1.0 JSON export, and an internal CLI.

Phase 3D is not complete. Phase 3D1 does not tune either strategy, claim duplicate-deal pairing, prove superiority, provide a CI performance gate, add a frontend, persist reports in a database, or add solvers/training. Larger benchmark evidence and any later acceptance thresholds remain separately scoped work.

### Phase 3D1A: Short-stack legal-action invariant

The authoritative engine now withholds normal `bet` or `raise` whenever no inclusive total target is affordable, while preserving the distinct legal under-minimum `all_in`, short all-in call/raise behavior, reopening rules, and total-target semantics. Focused invariant tests cover short blinds, river states, DecisionObservation, built-in bots, and the exact evaluation seeds that exposed the defect. The 400-match Phase 3D1 regression rerun records zero illegal actions, fallbacks, exceptions, or conservation failures.

This milestone is an engine correctness correction, not Expert/Adaptive tuning or a new evaluation method. Phase 3D remains in progress.

### Phase 3D2: Range & equity intelligence foundation

Phase 3D2 adds privacy-safe canonical opponent-card hypotheses, legal visible-card range construction, deterministic weighted priors and public-action updates, compact heuristic descriptors, range summaries, exact river weighted equity, and isolated seeded earlier-street Monte Carlo. It is not a solver, training system, card predictor, strategy retune, persistence feature, or frontend dashboard. Expert and Adaptive remain unchanged controls; showdown calibration is post-hand diagnostics only.

The completed foundation also has an explicit public-history tracker for diagnostics and deterministic engine-backed range evolution. It does not automatically execute in a bot decision or reinterpret history with later board information.

# Phase 3D3 — range-aware expert strategy

Implemented a bounded public-range/range-equity layer over `ExpertRuleBot`.  It is not a solver, CFR variant, neural strategy, self-play system, or exact opponent-card predictor.  Current limitations include heuristic ranges, conservative preflop use (summary only), and no exact EV/fold-equity solver.

## Phase 4D — Abstract Hold'em CFR subgame prototype

Phase 4D adds a deliberately bounded research subgame driven by Phase 4C: exact collision-free private-card enumeration on a fixed flop, no future board cards, legal Phase 4C abstract transitions, zero-sum terminal utilities, and deterministic Vanilla CFR/CFR+ training. It measures the complete tree and writes research-only information-set strategy tables. This is not a full Hold'em solver, full-game exploitability report, or production bot integration.

## Phase 4E — External-Sampling MCCFR scaling foundation

Phase 4E adds an independent, seeded External-Sampling MCCFR research core. It samples correct chance outcomes and current-strategy opponent actions while fully enumerating traverser actions; regret and average-policy estimators document their sampling/importance convention. Kuhn runs are evaluated exactly at increasing checkpoints and several seeds. The accepted Phase 4D fixed-flop game also has a sampled adapter and operational comparison with exact traversal, including tree-visit, stability, runtime, memory estimate, and sampling diagnostics. This does not integrate a strategy into the production registry or assert full Hold'em exploitability, GTO play, or a solved game.

## Phase 4F — Turn-Chance Hold'em MCCFR expansion

Phase 4F extends the isolated fixed-flop research fixture with one real conditional public turn chance node and bounded turn betting. It preserves Phase 4C abstraction, protects hidden and future-card information sets, validates street-local target totals and pot/stack carry-forward, and reuses the accepted external-sampling MCCFR core. A reduced exact two-street control supplies deterministic tree counts and constrained best-response metrics, while direct future-chance estimator, frozen-policy, seeded RNG, card-removal, and sampling-coverage fixtures validate the stochastic path. The seven-card configuration is explicitly capped by a 150,000-node exact-tree guardrail. This is not a river expansion, full heads-up no-limit model, production strategy, or full-game exploitability result.

## Phase 4G — River-Chance Multi-Street MCCFR expansion

Phase 4G adds a real conditional river chance node after completed non-all-in turn betting, bounded river betting, and five-public-card showdown to the same isolated research fixture. River candidates exclude the fixed flop, both private hands, and the selected turn; flop keys hide turn and river and turn keys hide river. The accepted external-sampling core remains the sole MCCFR implementation and records the public chance stage. Direct frozen-policy fixtures independently weight root/private, turn, river, and opponent-action probabilities. A representative-root tree measurement scales to the full bounded private-root count under a two-million-node guardrail. The smallest exact three-street control exhaustively validates tree/EV invariants but labels constrained BR enumeration intractable, so it makes no Phase 4G exploitability claim. This is not a full Hold'em solver, GTO strategy, production bot, API, frontend, or schema change.

The reduced control delegates its read-only physical state to the same Phase 4G transitions, so its exhaustive diagnostics derive node, decision, turn/river chance, terminal, depth, action-branching, utility, card-removal, and chance-order evidence without a second poker implementation. The larger bounded game deterministically derives and caches its full reachable information-set universe (flop/turn/river) outside MCCFR, so reports distinguish visited from zero-visit sets and publish coverage by street. `scaling_4g.py` compares the accepted Phase 4F and Phase 4G adapters under a common one-logical-iteration/two-traversal convention; it is operational cost evidence only, never strategy-strength evidence.

## Phase 5 — solver bot, opponent learning, and Coach

Branch `phase-5`.  Implemented and tested:

- **5A evaluation** — duplicate-deal and learning-session evaluation with disjoint development/holdout seed sets, a win-rate gate, and a Slumbot benchmark bridge.
- **5B speed** — eval7 evaluator with Treys-identical ranks (verified on all 7,462 hand classes, 60,000 random hands, and duplicate-card probes); memoized Range Intelligence features.
- **5C/5D `solver`** — offline 169-class preflop charts (15/30/60/100/200 bb, exploitability under 0.04 mbb/hand inside the chart model) and real-time discounted-CFR range solves of each postflop street; all bots exposed in the API and UI.
- **5E `solver_adaptive`** — confidence-gated node locking from public `OpponentModel` reads.
- **5F Coach** — manual-entry advice tab and API with local SQLite opponent profiles.

### Evidence

Baseline (development, independent duplicate hands, 84,000 hands): `equity` led the existing bots at +469 bb/100 pool.

**Holdout acceptance** (`benchmark-results/phase-5/session-tournament-holdout.json`): 9 bots, 16 learning sessions of 60 hands per pairing, seats swapped on identical cards — 69,120 hands, 0 illegal actions, 0 fallbacks, 0 deal mismatches.

| Pool rank | Bot | Pool bb/100 | 95% CI |
|---|---|---|---|
| 1 | equity | +299 | [+222, +372] |
| 2 | solver_adaptive | +249 | [+197, +300] |
| 3 | solver | +161 | [+112, +211] |
| 4 | range_expert | +98 | [+49, +146] |
| 5-7 | tight / adaptive / expert | +68 to +70 | |

`solver_adaptive` head-to-head (bb/100, 95% CI): aggressive +843 [+695, +995], random +395 [+242, +560], equity +333 [+139, +499], expert +100 [+12, +181], adaptive +100 [+11, +180], solver +103 [+15, +189], range_expert +74 [-12, +164] (inconclusive), tight +43 [-5, +94] (inconclusive).

`solver` head-to-head: beats random, aggressive, equity (+133 [+40, +222]), expert, adaptive, and range_expert with intervals above zero; tight +11 [-37, +60] is inconclusive.

Slumbot (300 hands each, 200 bb): baseline-adjusted `solver` +131 bb/100 [-18, +321], `expert` -137 [-394, +80]; both inconclusive; 0 desyncs, all settlements verified.

Regression: 770 backend tests pass, `pip check` clean, frontend production build passes, Docker Compose build/run verified (Coach and solver answer inside the container; Coach data persists in the `coach-data` volume).

### Verdict

**PHASE 5 NOT COMPLETE.**  The gate requires every head-to-head interval above zero *and* a pool score above the best other bot.  `solver_adaptive` beats every bot on point estimate and six of eight with intervals above zero, but its pool score (+249) trails `equity` (+299; difference interval [-148, +57], inconclusive), and the `tight` and `range_expert` intervals include zero.  `equity`'s pool lead comes from its larger margin against the two degenerate bots (`aggressive`, `random`).

Smallest missing evidence: a pool-score win over `equity` and positive intervals against `tight` and `range_expert`, measured on fresh holdout seeds.

### 5H showdown learning (merged into `phase-5`)

Learns from showdown-revealed cards how strongly an opponent's bets and calls follow hand strength, so node locks treat maniacs' aggression as random rather than strength-ordered.  Development sessions on the same seeds: aggressive +744 (was +612), random +435 (+412), equity +439 (+515), expert +48 (+80) bb/100 — every difference inside noise.  Not merged because it is not shown to avoid losses against sensible opponents; next step is a larger paired evaluation on a fresh holdout range.

Pre-registered fresh-holdout test (holdout seeds offset by 1,000,000, 16 sessions x 60 hands, 53,760 hands, 0 illegal actions/fallbacks/deal mismatches; `benchmark-results/phase-5/session-tournament-holdout2-5h.json`), rule: merge only if the full gate passes.  5H `solver_adaptive` beats **all seven** existing bots with intervals above zero — aggressive +843 [+713, +985], equity +409 [+289, +514], random +381 [+198, +561], expert +110 [+17, +206], adaptive +110 [+16, +205], range_expert +100 [+11, +191], tight +73 [+32, +119] — but its pool score (+289) still trails equity (+316; difference [-108, +51], inconclusive).  Gate not passed.  By decision of the project owner, 5H was merged into `phase-5` as the stronger `solver_adaptive` (774 backend tests pass after the merge); the gate is unchanged, so Phase 5 remains NOT COMPLETE until the pool criterion is met.

### Known limitations

Heads-up only; flop/turn solves value the end of the street by equity over remaining cards (no later-street betting); preflop charts value a seen flop by raw equity; solver decisions take about 1-3 s on a desktop CPU; the Coach is manual entry for study and review only.

### 5I pooled opponent reads (merged)

Diagnosis (development sessions, identical cards): against `aggressive` and `random`, `solver_adaptive` folded far more often than `equity` and bet reckless opponents off hands they would call with, because after 60 hands its postflop reads stood on only 3-11 opportunities per street (weight 0.3).  5I partially pools postflop reads across flop/turn/river: each street's rate is shrunk toward the all-streets rate (10 pseudo-observations) and weighted by the pooled evidence.

Paired A/B on unused development seeds (8 sessions x 60 hands per opponent), change versus the previous `solver_adaptive` in bb/100 [95% CI]: aggressive +358 [-50, +783], random +26 [-159, +213], equity +114 [+21, +221], expert +143 [+60, +226], tight -29 [-66, +22].  Adopted as the `solver_adaptive` default.  A sample-size lock-weight variant gained more against aggressive but lost significantly against tight (-46 [-76, -14]) and was rejected (kept as an off-by-default option).

**Pre-registered final test (fixed before running):** learning-session tournament of the seven existing bots plus `solver_adaptive` on unused holdout seeds (holdout set, seed offset 2,000,000; 16 sessions x 60 hands per pairing).  Phase 5 is COMPLETE if and only if `win_rate_gate(report, "solver_adaptive")` passes: every head-to-head interval above zero, pool score above the best other bot with the paired interval of the difference above zero, and zero illegal actions and deal mismatches.

**Result of the pre-registered 5I test** (`benchmark-results/phase-5/session-tournament-holdout3-5i.json`; 53,760 hands, 0 illegal actions, 0 fallbacks, 0 deal mismatches): gate **not passed**.  Pool: equity +400 [+330, +477], `solver_adaptive` +344 [+287, +398] (difference [-157, +36], inconclusive), range_expert +114.  `solver_adaptive` head-to-head: aggressive +1,167 [+919, +1,404], random +612 [+483, +740], equity +436 [+345, +520], tight +57 [+16, +105] — all above zero — but expert +49 [-28, +116], adaptive +54 [-17, +115], and range_expert +34 [-45, +108] are inconclusive.  On this seed set `equity` also scored unusually high against every opponent (e.g. +170 against expert versus about +100 on earlier holdout seeds), which illustrates the between-seed-set variance at 16 sessions per pairing.

**Verdict remains PHASE 5 NOT COMPLETE.**  Across three holdout tests `solver_adaptive` has beaten `equity` head-to-head by +333 to +436 bb/100 and every other bot on point estimate, but has not yet shown a pool score above `equity` or consistently clear margins over the expert family.

### Revised success criterion (decided 2026-09-29, before any new data)

The project owner changed the Phase 5 goal *prospectively*: the pool-score criterion is dominated by how hard a bot exploits the two degenerate baselines (`aggressive`, `random`) and is dropped.  No earlier result is re-scored under the new rule.

**Pre-registered final test (fixed before running):** `solver_adaptive` at commit `6ccd5c3` (no strategy changes) plays each of the seven existing bots (`random`, `tight`, `aggressive`, `equity`, `expert`, `adaptive`, `range_expert`) in duplicate learning sessions on unused holdout seeds: holdout set, seed offset 3,000,000, 48 sessions x 60 hands per opponent (5,760 hands per opponent), statistics seed 91,002, 2,000 bootstrap resamples.

Phase 5 is **COMPLETE** if and only if, for every one of the seven opponents, the 95% duplicate-pair bootstrap interval of `solver_adaptive`'s bb/100 has a lower bound above zero, and the run has zero illegal actions and zero deal mismatches.  Otherwise it remains NOT COMPLETE and the failing opponents are reported.

**Result of the pre-registered final test** (`benchmark-results/phase-5/final-h2h-<opponent>.json`; commit `b3be891`, identical strategy code to `6ccd5c3`; holdout set, seed offset 3,000,000, 48 sessions x 60 hands per opponent):

| Opponent | bb/100 | 95% CI | Hands | Illegal actions | Deal mismatches |
|---|---|---|---|---|---|
| random | +539.6 | [+433.7, +645.7] | 5,760 | 0 | 0 |
| tight | +81.7 | [+46.2, +113.5] | 5,760 | 0 | 0 |
| aggressive | +1,124.7 | [+1,039.1, +1,213.4] | 5,760 | 0 | 0 |
| equity | +438.8 | [+350.8, +525.1] | 5,760 | 0 | 0 |
| expert | +110.1 | [+54.6, +166.1] | 5,760 | 0 | 0 |
| adaptive | +110.1 | [+54.6, +166.1] | 5,760 | 0 | 0 |
| range_expert | +117.1 | [+60.3, +171.5] | 5,760 | 0 | 0 |

Total: 40,320 hands, 0 illegal actions, 0 deal mismatches across all seven runs.

The `adaptive` result is numerically identical to `expert` (verified byte-for-byte, differing only in the `opponent` field): a diagnostic replay of one session confirmed `ExpertAdaptiveBot`'s exploit-adjustment engine had zero activations against `solver_adaptive` in either seat orientation, so it deterministically fell back to its `ExpertRuleBot` baseline for every decision, producing identical play with the same derived seed. Not a test artifact.

Every one of the seven 95% bootstrap intervals has a lower bound above zero, and the run is clean (0 illegal actions, 0 deal mismatches).

**PHASE 5 COMPLETE**
