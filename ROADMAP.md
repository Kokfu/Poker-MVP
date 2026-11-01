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

**Current status (read this first).**  Phase 5 is merged and released (tag `phase-5-complete`, merge commit `40ff212`).  It is COMPLETE **under the revised, owner-set criterion** (every one of the seven existing bots beaten, 95% interval lower bound above zero, 0 illegal actions, 0 deal mismatches; see "Revised success criterion" below).  It is **not** complete under the original criterion, which also required a pool score above `equity`: that gate failed on three holdout tests (the two below plus the 5I test), `solver_adaptive` never showed a pool score above `equity` (best case difference [-108, +51]), and the owner dropped the pool criterion prospectively on 2026-09-29 rather than the bot passing it.  The "PHASE 5 NOT COMPLETE" verdicts further down are the original-criterion results, kept as history and marked *superseded*.  Whether `solver_adaptive` beats `equity` in pool score on fresh seeds remains an open measurement.

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

Regression (recorded at the first Phase 5 write-up; at release prep the suite is 781 passing): 770 backend tests pass, `pip check` clean, frontend production build passes, Docker Compose build/run verified (Coach and solver answer inside the container; Coach data persists in the `coach-data` volume).

### Verdict

**PHASE 5 NOT COMPLETE** *(original criterion; superseded by the revised criterion below, which gives COMPLETE)*.  The gate requires every head-to-head interval above zero *and* a pool score above the best other bot.  `solver_adaptive` beats every bot on point estimate and six of eight with intervals above zero, but its pool score (+249) trails `equity` (+299; difference interval [-148, +57], inconclusive), and the `tight` and `range_expert` intervals include zero.  `equity`'s pool lead comes from its larger margin against the two degenerate bots (`aggressive`, `random`).

Smallest missing evidence: a pool-score win over `equity` and positive intervals against `tight` and `range_expert`, measured on fresh holdout seeds.

### 5H showdown learning (merged into `phase-5`)

Learns from showdown-revealed cards how strongly an opponent's bets and calls follow hand strength, so node locks treat maniacs' aggression as random rather than strength-ordered.  Development sessions on the same seeds: aggressive +744 (was +612), random +435 (+412), equity +439 (+515), expert +48 (+80) bb/100 — every difference inside noise.  Not merged because it is not shown to avoid losses against sensible opponents; next step is a larger paired evaluation on a fresh holdout range.

Pre-registered fresh-holdout test (holdout seeds offset by 1,000,000, 16 sessions x 60 hands, 53,760 hands, 0 illegal actions/fallbacks/deal mismatches; `benchmark-results/phase-5/session-tournament-holdout2-5h.json`), rule: merge only if the full gate passes.  5H `solver_adaptive` beats **all seven** existing bots with intervals above zero — aggressive +843 [+713, +985], equity +409 [+289, +514], random +381 [+198, +561], expert +110 [+17, +206], adaptive +110 [+16, +205], range_expert +100 [+11, +191], tight +73 [+32, +119] — but its pool score (+289) still trails equity (+316; difference [-108, +51], inconclusive).  Gate not passed.  By decision of the project owner, 5H was merged into `phase-5` as the stronger `solver_adaptive` (774 backend tests pass after the merge); the gate was unchanged at that point, so Phase 5 remained NOT COMPLETE under the original criterion (later superseded; see "Revised success criterion").

### Known limitations

Heads-up only; flop/turn solves value the end of the street by equity over remaining cards (no later-street betting); preflop charts value a seen flop by raw equity; solver decisions take about 1-3 s on a desktop CPU; the Coach is manual entry for study and review only.

### 5I pooled opponent reads (merged)

Diagnosis (development sessions, identical cards): against `aggressive` and `random`, `solver_adaptive` folded far more often than `equity` and bet reckless opponents off hands they would call with, because after 60 hands its postflop reads stood on only 3-11 opportunities per street (weight 0.3).  5I partially pools postflop reads across flop/turn/river: each street's rate is shrunk toward the all-streets rate (10 pseudo-observations) and weighted by the pooled evidence.

Paired A/B on unused development seeds (8 sessions x 60 hands per opponent), change versus the previous `solver_adaptive` in bb/100 [95% CI]: aggressive +358 [-50, +783], random +26 [-159, +213], equity +114 [+21, +221], expert +143 [+60, +226], tight -29 [-66, +22].  Adopted as the `solver_adaptive` default.  A sample-size lock-weight variant gained more against aggressive but lost significantly against tight (-46 [-76, -14]) and was rejected (kept as an off-by-default option).

**Pre-registered final test (fixed before running):** learning-session tournament of the seven existing bots plus `solver_adaptive` on unused holdout seeds (holdout set, seed offset 2,000,000; 16 sessions x 60 hands per pairing).  Phase 5 is COMPLETE if and only if `win_rate_gate(report, "solver_adaptive")` passes: every head-to-head interval above zero, pool score above the best other bot with the paired interval of the difference above zero, and zero illegal actions and deal mismatches.

**Result of the pre-registered 5I test** (`benchmark-results/phase-5/session-tournament-holdout3-5i.json`; 53,760 hands, 0 illegal actions, 0 fallbacks, 0 deal mismatches): gate **not passed**.  Pool: equity +400 [+330, +477], `solver_adaptive` +344 [+287, +398] (difference [-157, +36], inconclusive), range_expert +114.  `solver_adaptive` head-to-head: aggressive +1,167 [+919, +1,404], random +612 [+483, +740], equity +436 [+345, +520], tight +57 [+16, +105] — all above zero — but expert +49 [-28, +116], adaptive +54 [-17, +115], and range_expert +34 [-45, +108] are inconclusive.  On this seed set `equity` also scored unusually high against every opponent (e.g. +170 against expert versus about +100 on earlier holdout seeds), which illustrates the between-seed-set variance at 16 sessions per pairing.

**Verdict remains PHASE 5 NOT COMPLETE** *(original criterion; superseded by the revised criterion below)*.  Across three holdout tests `solver_adaptive` has beaten `equity` head-to-head by +333 to +436 bb/100 and every other bot on point estimate, but has not yet shown a pool score above `equity` or consistently clear margins over the expert family.

### Revised success criterion (decided 2026-09-29, before any new data)

The project owner changed the Phase 5 goal *prospectively*: the pool-score criterion is dominated by how hard a bot exploits the two degenerate baselines (`aggressive`, `random`) and is dropped.  No earlier result is re-scored under the new rule.  Note that this change came after three failed attempts at the original gate; the COMPLETE verdict below is therefore a verdict on the revised, easier-to-state criterion, not a pass of the original one.

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

**Scope of the verdict.**  The final test above ran on the solver code at `b3be891`, before the `perf-solver` speed-up (array-based CFR, leaner equity loop, about 1.47x) was merged.  That change reproduces the old results to floating-point noise but is not bit-identical: 3 of 200 fixed benchmark hands and 2 of 30 spots chose a different action after a regret value sitting almost exactly at zero landed on the other side of the matching threshold (see DEVELOPMENT.md, "Solver performance").  The COMPLETE verdict above is therefore evidence for the `b3be891` solver; the re-measurement below covers the merged faster code.

**Re-measurement on the merged code** (commit `4987a71`, which includes `perf-solver`; `benchmark-results/phase-5/rerun-perf-h2h-<opponent>.json`).  Same test, same seeds, same pass rule as above, stated before the runs started.  The seeds had already been seen, so this re-measures the pre-registered test on new code and is not a fresh holdout.

| Opponent | bb/100 | 95% CI | Original run (`b3be891`) | Illegal | Deal mismatches |
|---|---|---|---|---|---|
| random | +536.7 | [+431.3, +642.8] | +539.6 | 0 | 0 |
| tight | +82.8 | [+47.4, +114.6] | +81.7 | 0 | 0 |
| aggressive | +1,119.5 | [+1,031.8, +1,208.2] | +1,124.7 | 0 | 0 |
| equity | +438.7 | [+350.7, +525.1] | +438.8 | 0 | 0 |
| expert | +111.5 | [+55.3, +167.4] | +110.1 | 0 | 0 |
| adaptive | +111.5 | [+55.3, +167.4] | +110.1 | 0 | 0 |
| range_expert | +118.5 | [+61.6, +172.1] | +117.1 | 0 | 0 |

All seven lower bounds are above zero with 0 illegal actions and 0 deal mismatches over 40,320 hands, and every estimate is within 6 bb/100 of the original run.  `adaptive` again equals `expert` exactly (its exploit engine never activates in these sessions).

**PHASE 5 COMPLETE** (revised criterion) on both the `b3be891` solver and the merged faster solver at `4987a71`.  The original pool-score criterion is still unmet.

### Outside benchmark: Slumbot, 1,000 hands (2026-10-23)

`solver_adaptive` (commit `3a79e0b`, strategy code identical to the Phase 5 verdict) played 1,000 consecutive hands against Slumbot's public API through the existing bridge (200 bb deep, 50/100 blinds, 500 on the button and 500 in the big blind, bot seeds 7,000-7,999; `benchmark-results/phase-5/slumbot-solver-adaptive-long.jsonl`, not tracked by git).  Run and rule stated before starting: report whatever comes out.

| Measure | Result |
|---|---|
| Raw winnings | **-148.7 bb/100**, 95% bootstrap CI [-319.5, +18.4] |
| Baseline-adjusted (Slumbot's own reported baseline subtracted, lower variance) | **-78.4 bb/100**, 95% CI [-202.8, +44.8] |
| Illegal actions | 0 (no desyncs, 0 settlement mismatches against Slumbot's winnings) |
| Bot fallbacks to the rule-based bot | 1 of 3,107 decisions (the action was legal) |
| Decision time (bot compute only) | mean 0.54 s, median 0.55 s, 95th percentile 1.59 s, max 4.1 s |
| Wall clock | 5.4 s per hand including network |

**Verdict: `solver_adaptive` lost to Slumbot on both point estimates; neither interval excludes zero**, so 1,000 hands cannot tell a small loss from a small win.  A loss is the expected direction against a much stronger opponent, and the raw interval is wide (about ±170 bb/100) because a single hand swings 27 bb (standard deviation).  The result shows the bot plays legal, settlement-consistent poker at 200 bb and is not shown to be competitive with Slumbot.  By seat: -215 bb/100 on the button, -83 in the big blind; by half: -201 then -96.  The earlier 300-hand `solver` run (+131 baseline-adjusted [-18, +321]) was likewise inconclusive and is a reminder of how wide these intervals are.

**Caveat on what was measured.**  The bridge builds a fresh bot for every hand and supplies no opponent profile, so `solver_adaptive` could not learn Slumbot's tendencies across hands and played essentially as `solver`.  This benchmark therefore does not test the opponent-adaptation part of the bot.  Bot compute time here is lower than the 1-3 s quoted elsewhere because most Slumbot decisions are preflop chart lookups or small postflop trees.

### Slumbot, 1,000 hands with opponent learning (2026-10-25)

Same bot, same 1,000 hands per run and same bot seeds as the run above, but through the bridge's new learning mode (`run_slumbot_session(learn=True)`, commit `1d392d4`): one `solver_adaptive` instance plays the whole session and sees a growing profile of Slumbot built from the hands already played.  A first attempt died at hand 285 (killed externally, no traceback; its 285 clean hands are kept as `slumbot-solver-adaptive-learning.killed-at-285.jsonl`) and the full run was restarted from hand 1.  `benchmark-results/phase-5/slumbot-solver-adaptive-learning.jsonl` (not tracked by git).

| Measure | No learning (above) | With learning |
|---|---|---|
| Raw winnings | -148.7 bb/100, 95% CI [-319.5, +18.4] | **+3.8 bb/100**, 95% CI [-187.8, +191.4] |
| Baseline-adjusted | -78.4, CI [-202.8, +44.8] | **+80.5**, CI [-3.4, +168.8] |
| Illegal actions / desyncs / settlement mismatches | 0 / 0 / 0 | 0 / 0 / 0 |
| Bot fallbacks | 1 of 3,107 decisions | 2 of 2,405 decisions |
| Decision time, bot compute | mean 0.54 s, p95 1.6 s, max 4.1 s | **mean 2.4 s, median 1.5 s, p95 8.7 s, max 32.5 s** |

**Reading.**  Neither run's interval excludes zero on raw winnings, and the baseline-adjusted learning interval only just includes zero.  Quarter-by-quarter raw results swing by hundreds of bb/100 (+133, -86, -182, +151), which is the noise level of a 1,000-hand sample.  An unpaired bootstrap of the difference between the two runs (exploratory, not pre-registered, each run seen once) gives +159 bb/100 baseline-adjusted [+15, +309] and +152 raw [-91, +396].  That is consistent with learning helping against Slumbot, but it comes from one run per arm and does not establish it.  Learning mode also folds Slumbot out of more hands (2,405 bot decisions against 3,107).  It is **not** evidence that `solver_adaptive` beats Slumbot.

**Cost.**  Learning-mode decisions are much slower than the 1-3 s quoted elsewhere because opponent locks force re-solves at 200 bb: p95 is 8.7 s, above the 6 s limit chosen for any new Stage 1 variant.  That limit would currently not be met by the existing learning bot on this benchmark.

### Slumbot, clean 1,000-hand learning rerun (2026-10-30)

Same bot, same bot seeds (7,000-7,999), same learning mode, run alone on `main` at `05bab7d` (including the learning-mode speed-up) with no other benchmark running; free RAM was about 0.8 GB at start, so the machine was not truly idle.  `benchmark-results/phase-5/slumbot-learning-clean.jsonl` (not tracked by git).  Slumbot deals different cards each session, so comparisons with earlier runs are unpaired.

| Measure | Earlier learning run | Clean rerun |
|---|---|---|
| Raw winnings | +3.8 bb/100, CI [-187.8, +191.4] | **-198.2**, CI [-440.9, +44.5] |
| Baseline-adjusted | +80.5, CI [-3.4, +168.8] | **+20.2**, CI [-63.5, +104.0] |
| Desyncs / settlement mismatches | 0 / 0 | 0 / 0 |
| Bot decisions | 2,405 | 2,420 |
| Wall time per hand (includes Slumbot latency and 0.2 s pause) | mean 8.7 s, p95 27.7 s, max 73.5 s | **mean 6.2 s, p95 15.9 s, max 43.0 s** |
| Total session time | 2.4 h | 1.7 h |

The current bridge no longer writes per-decision times or fallback counts, so decision-time p95 and fallbacks are **not measured** in this rerun; only per-hand wall time is.  Per-100-hand mean hand time stayed between 5.0 and 8.0 s with no early-session spike (the earlier run was 11-13 s for its first 400 hands), consistent with the speed-up and with less contention.  No-learning run for reference: mean 5.4 s, p95 10.5 s per hand.

**Reading.**  The learning benefit seen in the earlier run did not reproduce: raw winnings are -198 bb/100 here (the earlier run's raw interval, and this one, both include zero and overlap heavily).  Unpaired bootstrap, clean rerun minus earlier learning run: -202 raw [-507, +105], -60 baseline-adjusted [-179, +60].  Clean rerun minus no-learning run: -50 raw [-339, +244], +99 baseline-adjusted [-49, +251].  Nothing is distinguishable from zero.  The earlier +159 baseline-adjusted learning effect was most likely noise, so the learning benefit against Slumbot is **not established**; the two learning runs average about -97 raw bb/100.  `solver_adaptive` is not shown to beat Slumbot.

### Slumbot, first learning run with decision-time logging (autopilot step 7, 2026-11-02)

Same bot, seeds (7,000-7,999) and learning mode as the clean rerun, on `main` at `e4a2413` (bridge logging restored in step 6).  `benchmark-results/phase-5/slumbot-learning-instrumented.jsonl` (force-added to git).  A first attempt died at hand 929 when its session ended (partial files kept as `*.killed-at-929.*`, not analysed) and the run was restarted from hand 1.  Free RAM was about 1.2 GB at the first start (about 2.2 GB at the restart; WSL was left running), so the machine was not fully idle.

| Measure | Clean rerun (step 1) | This run |
|---|---|---|
| Raw winnings | -198.2, CI [-440.9, +44.5] | **-34.8**, CI [-232.7, +163.1] |
| Baseline-adjusted | +20.2, CI [-63.5, +104.0] | **+35.1**, CI [-48.6, +118.8] |
| Desyncs / settlement mismatches / bot fallbacks | 0 / 0 / not logged | 0 / 0 / **0** |
| Bot decisions | 2,420 | 2,423 |
| Bot decision time | not logged | **mean 1.41 s, median 1.11 s, p95 4.70 s, max 8.44 s** |
| Decisions above 6 s | not logged | **55 of 2,423 (2.3%)**, none above 10 s |
| Wall time per hand | mean 6.2 s, p95 15.9 s | mean 6.4 s, p95 18.7 s, max 22.9 s |

Decision time by 100-hand block (mean / p95 / max, count above 6 s): 2.19/5.82/8.4 (12), 1.90/5.41/7.6 (5), 1.85/4.81/7.0 (9), 1.03/2.84/7.6 (1), 0.80/2.71/6.1 (1), 0.83/2.56/3.8 (0), 0.84/2.68/3.5 (0), 0.81/2.65/6.6 (2), 1.84/6.20/7.9 (13), 1.80/6.61/7.9 (12).  Time is not monotone in session length; it varies with the mix of spots that need re-solves.

**Reading.**  Against the 6 s limit for a new Stage 1 variant, the p95 (4.7 s) is within it but 2.3% of decisions exceed it and the maximum is 8.4 s, and two late blocks have p95 above 6 s.  So a per-decision cap would be violated occasionally; a limit on the 95th percentile would be met.  The earlier p95 of 8.7 s (first learning run) was not reproduced.  Winnings: unpaired bootstrap difference against the clean rerun is +163 raw [-153, +468] and +15 baseline-adjusted [-102, +130]; every interval includes zero, so the learning effect against Slumbot remains **not established** (three learning runs: +4, -198, -35 raw).  No strategy claim.

### Stage 0 oracle for later-street betting (2026-10-25)

Protocol: `DESIGN_LATER_STREET_BETTING.md` sections 8-9, amended before the real run.  Code: `backend/research/solver_oracle.py` (research only, production solver untouched); 6 tests.  60 turn spots from solver-versus-bot hands (seeds 20,000 and up; 60 spots in 140 hands, so 43% of hands reach such a spot), 30 calibration and 30 held-out; oracle = joint turn + river CFR over all 44 river cards, 80 iterations; every profile evaluated with the same fresh 60-iteration river solves.  Results: `benchmark-results/stage0/results.jsonl` (not tracked).

| Held-out set (30 spots) | Result |
|---|---|
| Head-to-head loss of the production turn strategy against the oracle, seats swapped | median **0.18 bb per spot**, mean 0.32 bb, 95% bootstrap CI of the mean [0.21, 0.46]; 0 of 30 spots favour production |
| Extended-game exploitability, median | production 37% of the turn pot, oracle 3.3% (extra gap 2.4 bb) |
| Validity | median oracle gap is 6.5% of the production gap (limit 33%); no failed spots |

**Gate (fixed before the run): median loss at least 1.0 bb per spot AND mean-loss interval lower bound above 0.5 bb AND valid.  Result: FAILED on both loss conditions (0.18 < 1.0 and 0.21 < 0.5).  Stage 1 does not proceed as designed.**  The calibration set agrees (median 0.24 bb).

**Reading.**  The one-street model is demonstrably imperfect (production loses to the oracle in all 60 spots and its exploitability in the two-street game is about ten times the oracle's), but the cost against a strong, non-best-responding opponent is small: about 0.3 bb per spot, roughly 14 bb/100 [9, 20] if applied to the 43% of hands that reach such a spot.  That is a ceiling on turn-model error only, and a fix would recover part of it, which is below what the planned primary test (powered for +20 bb/100) could detect.  The large exploitability figures are worst-case numbers against a perfect best response and overstate the practical cost.  Losses are larger in shallow spots (stack-to-pot under 8: median 0.58 bb, 12 spots) than deep ones (16 or more: median 0.10 bb, 32 spots).  Not measured: flop spots, shorter stacks than 100 bb, or any effect on bb/100.  The design's prior of +10 to +30 bb/100 for Stage 1 is not supported by this evidence.

## Autopilot step 3: pre-registered fresh-holdout test of the pool measurement (protocol, written 2026-10-30 before any data)

**Status of what is tested.**  Phase 5 is already COMPLETE under the owner's revised criterion (see "Revised success criterion"); this test cannot change that verdict and a failure here is not a release blocker.  It is an open measurement: does `solver_adaptive` (merged `main`, no strategy changes) score above `equity` in pool score on unused seeds?

**Seeds.**  The step prompt suggested offset 2,000,000 as unused; it is not (5I used it, and the final test used 3,000,000; 5H used 1,000,000).  This test uses holdout seed offset **4,000,000**, never used before.

**Format (identical to the 5H/5I holdout runs).**  Eight bots (`random`, `tight`, `aggressive`, `equity`, `expert`, `adaptive`, `range_expert`, `solver_adaptive`), learning-session tournament, `--pairs 16 --session-hands 60`, 100 equity iterations, stacks 10,000, blinds 50/100, 2,000 bootstrap resamples, statistics seed 91,002, via `python -m simulation.duplicate_cli tournament --seed-set holdout --seed-offset 4000000`.  Result: `benchmark-results/phase-5/session-tournament-holdout4.json`.  Worker count is reduced for memory reasons (does not affect results, which are seeded per pair).

**Pass rule (fixed now).**  Primary quantity: D = pool score of `solver_adaptive` minus pool score of `equity`, with the paired 95% percentile bootstrap interval from `bootstrap_pool_samples`.
- ABOVE: lower bound of D > 0.  INCONCLUSIVE: interval includes 0.  BELOW: upper bound < 0.
- Original gate PASSES iff D is ABOVE, every one of the seven head-to-head 95% lower bounds is > 0, and illegal actions and deal mismatches are 0.  Otherwise it does not pass.  (`win_rate_gate`, which compares against the best other bot, is also reported; here that bot is expected to be `equity`.)
- Also reported, not part of the pass rule: the revised criterion (all seven lower bounds > 0, clean play).
- No re-runs on these seeds, no strategy changes; a single run is the result whatever it shows.

**Result of the step-3 test** (`benchmark-results/phase-5/session-tournament-holdout4.json`, gate output in `holdout4.gate.json`; 53,760 hands, 0 illegal actions, 0 fallbacks, 0 deal mismatches): original gate **not passed**; pool difference **INCONCLUSIVE**.  Pool: `solver_adaptive` +291 [+239, +342] (rank 1), `equity` +245 [+147, +345], `range_expert` +190.  D (`solver_adaptive` minus `equity`) = +46 [-37, +120]; `win_rate_gate` interval against the best other bot [-38, +98].  Head-to-head: aggressive +1,047 [+914, +1,177], random +603 [+448, +755], equity +392 [+256, +514] are above zero; tight +29 [-5, +62], expert -7 [-88, +78], adaptive -7 [-92, +80], range_expert -22 [-107, +66] are inconclusive.  The revised criterion would **not** have been met on this seed set (four of seven lower bounds at or below zero).  This is a single 16-session run with wide intervals (the pool point estimate ranks first for the first time, but not distinguishably); it neither changes the owner's Phase 5 verdict nor shows a regression against the 48-session final test, whose expert-family intervals were positive; the two measurements are noisy and not directly comparable.

**Follow-up (autopilot step 5, pre-registered in `autopilot/prereg-step-5.md`):** `solver_adaptive` at `main` 4e191b3 vs the seven bots, holdout seed offset 5,000,000, 48 sessions x 60 hands per opponent, `benchmark-results/phase-5/final-h2h-offset5m-<opponent>.json`.  Revised criterion **met**: bb/100 random +595.0 [+499.8, +686.4], tight +49.7 [+25.5, +73.8], aggressive +1,061.1 [+977.8, +1,142.6], equity +418.0 [+337.2, +495.1], expert +74.2 [+24.7, +124.8], adaptive +75.3 [+25.6, +126.4], range_expert +78.8 [+28.2, +131.5]; 40,320 hands, 0 illegal actions, 0 deal mismatches.  The step-3 weakness against the expert family is read as seed noise; expert-family estimates are about 35-40 bb/100 below the offset-3M run (inside its intervals), so a small real decline is not excluded.  The original pool-score criterion is unchanged.
