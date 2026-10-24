# Design: modelling later-street betting in flop and turn solves

Status: **proposal, no code written.  Implementation waits for approval.**

## 1. The problem

`SolverBot` solves one street at a time.  Every non-fold end of the street is a
showdown leaf valued by equity over the remaining cards (`solver/bot.py`
`_full_equity`, `solver/cfr.py` `leaf_scale`): both players are assumed to
check the hand down.  Flop leaves use 30 sampled runouts; turn leaves use all
44 rivers.  River solves are exact and are not affected.

What that gets wrong, in order of likely importance:

1. **Equity realization.**  A drawing hand rarely collects its full equity
   (it folds to a bet, or pays to draw); a strong hand and the player in
   position collect more than their equity (value bets, free cards).  The
   model gives every hand its raw equity.
2. **Position.**  The player in position on the next street is treated the
   same as the player out of position.
3. **Value and bluff incentives.**  A bet that sets up later betting is worth
   more than the leaf shows; check-raise and delayed-bluff lines are
   undervalued.

Measured size of the current solves (read-only measurement on one example
spot per street, 12-core desktop, so indicative rather than averaged): turn tree 45 nodes with 15 showdown leaves,
flop tree 57 nodes with 19 showdown leaves, river tree 33 nodes; a flop or
turn solve takes about 0.5-0.7 s and a whole postflop decision about 1.0 s
(a river decision about 3.6 s because the earlier streets are replayed to
update ranges).  In Slumbot play the mean bot compute was 0.54 s per
decision; in a learning session (opponent locks, re-solves) the partial run
showed about 3.5 s.

## 2. Options

| | Idea | Added cost per decision | Risk |
|---|---|---|---|
| **A. Calibrated realization leaves** | Keep one-street trees.  Add a zero-sum correction to showdown leaves: a position/initiative transfer plus a hand-strength-dependent realization factor, with parameters fitted offline against a full two-street solve | under 5% (extra array work on leaves; parameters are tables) | heuristic: averages over spots, not exact; needs the oracle below to fit and check it |
| **B. Sampled next-street subtrees** | Turn leaves branch into K sampled river cards, each with a small river betting tree (one bet size, no raise), solved inside the same CFR | about x8-x15 on the turn (leaf columns grow from 15 to about 15 x K x 6, and each river card needs its own win matrix); about 5-10 s per turn decision, more on the flop | too slow as designed; needs a separate optimization pass |
| **C. Offline continuation tables** | Pre-solve river-lite games over canonical (pot, stack, texture) buckets and look up hand values, like the preflop charts | small at runtime; large one-off build | biggest build, abstraction error from bucketing |

**Recommendation: a staged plan.**  Build the measuring instrument first,
then Option A; consider B or C only if A leaves a measured gap.

- **Stage 0, oracle (no strategy change).**  An offline research script solves
  the true two-street game for turn spots: the turn tree with every river
  card exactly (44 rivers) and a river tree under each leaf, using the same
  bet menu so only the leaf model differs.  Cost is minutes per spot, so run
  about 200 sampled spots (development seeds) in parallel.  The metric is the
  **extended-game gap**: how much a best-responding opponent gains, in percent
  of the pot, against the current one-street strategy followed by optimal
  river play, compared with the same figure for the oracle's own strategy.
  This gives the first real number for how much the current model costs.
  Do the same for flop spots with the sampled runouts used today.
- **Stage 1, Option A,** fitted to the oracle on the development spots and
  checked on held-out spots.  It ships as a class option
  (`leaf_model = "equity"` stays the default), so existing bots, charts,
  benchmarks and schemas are untouched.  Strategy thresholds and tree
  menus are not changed.
- **Stage 2 (only if justified).**  B restricted to the turn with K = 3
  stratified rivers, or C.

Gates between stages: go from Stage 0 to Stage 1 only if the median
extended-game gap of the current strategy is at least 1.5% of the pot on 100
or more held-out spots (otherwise the model is already good enough and the
work stops); go to Stage 2 only if Stage 1 closes less than 60% of the gap.

## 3. Expected gain (honest)

Not measured yet.  Prior expectation, to be replaced by Stage 0 evidence:

- Stage 1, new versus current `solver_adaptive`, duplicate head-to-head:
  roughly +10 to +30 bb/100, with a real chance of about zero because the
  strongest local opponents are heuristic and the current leaf model already
  beats all of them.
- Stage 2: possibly a further +10 to +30 bb/100.
- Slumbot (currently about -80 to -150 bb/100 with an interval of about
  +-170): any plausible gain here is smaller than the benchmark's noise at
  1,000 hands, so it is a sanity check, not evidence.

## 4. Cost in decision time

| | Mean decision (now) | Stage 1 | Stage 2 (B as designed) |
|---|---|---|---|
| Flop/turn solve | 0.5-0.7 s | +under 5% | 5-10 s (turn), worse on the flop |
| Whole postflop decision | about 1 s | about 1 s | not acceptable without optimization |

Acceptance limits for any shipped variant: mean decision time at most 1.5x
the current mean, 95th percentile at most 6 s.

## 5. Pre-registered test (fixed before any holdout run)

**Candidate:** `solver_adaptive` with the Stage 1 leaf model, at a commit
recorded before the run.  **Baseline:** current `solver_adaptive` (`3a79e0b`
strategy code).  No parameter is tuned on holdout seeds; the holdout is used
once.

**Pilot (development seeds only):** 500 duplicate pairs of candidate versus
baseline to estimate the standard error and to fix the pair count below so the
test has at least 80% power for +20 bb/100.  The pilot cannot be reused as
evidence.

**Primary endpoint:** candidate versus baseline, independent duplicate hands
(cards swapped across seats), holdout seed offset 5,000,000, N pairs where N
comes from the pilot (default 6,000 pairs = 12,000 hands), 2,000 bootstrap
resamples, statistics seed 91,004.  **Pass: lower bound of the 95% interval of
the candidate's bb/100 is above 0.**

**Non-regression endpoint (all must hold):**

1. Learning sessions of candidate versus each of the seven existing bots
   (holdout offset 6,000,000, 48 sessions x 60 hands per opponent, as in the
   Phase 5 final test): every lower bound stays above zero, and no opponent
   shows a paired candidate-minus-baseline interval whose upper bound is
   below zero.
2. Zero illegal actions and zero deal mismatches; bot fallbacks no more than
   0.1 percentage point above baseline.
3. Decision time within the limits in section 4, measured on the same machine
   as the baseline run.

**Reported, not gating:** 1,000-hand Slumbot learning-session runs of both
variants with the same seeds (interval about +-170 bb/100, so only a large
difference could register).

**Stage 0/1 internal gates** (section 2) are stated here too so they cannot be
moved afterwards.  A failed gate or endpoint is reported as a failure and the
variant is not merged.

## 6. What I will not do without approval

Change strategy thresholds, tree menus, preflop charts, the engine, accepted
schemas, or any existing bot's default behaviour; start Stage 0; or run any
holdout seeds.

## 7. Open questions for you

1. Approve Stage 0 (oracle) alone first?  It changes nothing in production and
   gives the first real estimate of the gain.
2. Is a 1.5x mean and 6 s 95th-percentile decision-time limit right for your
   use (Coach and bot)?
3. Should the Coach get a slow "deep" mode later (Option B) even if the bot
   cannot afford it?

## 8. Stage 0 protocol (approved 2026-10-23; fixed before any Stage 0 data)

Code: `backend/research/solver_oracle.py` (research only; nothing in `solver/`
changed).  Tests: `backend/test_research_solver_oracle.py`.

- **Spots.** The first 200 turn spots, in seed order from seed 20,000, reached by
  `solver` playing 100 bb hands against `equity`, `expert`, `aggressive`,
  `tight` and `solver` in rotation (seat alternating by seed).  A spot is
  the public ranges at the root of the turn, as the production bot holds them.
  Spots where a player is already all in are skipped.
- **Games compared.** (a) Production: one-street turn solve, 70 iterations,
  showdown-equity leaves, same pruning; its river strategies are then solved
  for 80 iterations against the ranges it produces.  (b) Oracle: joint turn +
  river CFR with every river card exactly and the production bet menu on both
  streets, 150 iterations.  All-in turn leaves stay equity leaves in both
  (nothing more to bet, so equity over the river is exact).
- **Metric.** Extended-game exploitability of each profile in percent of the
  turn pot (mean best-response gain of the fixed profile, including best
  responses on the river).  **Extra gap = production minus oracle**, which
  removes what the oracle's own residual error contributes.  Also reported:
  range-weighted total-variation distance between the two turn root strategies
  and the root action mixes.
- **Sets.** Spots 1-100 (lowest seeds) are the calibration set Stage 1 may
  fit on.  Spots 101-200 are the held-out set used for the gate.
- **Gate (decided now).** Proceed to Stage 1 only if the **median extra gap on
  the held-out set is at least 1.5% of the pot**.  Below that, the one-street
  model is already close to the two-street game on these spots and the work
  stops.
- **Validity checks reported with the result.** The oracle's own gap must have
  a median under 1.0% of the pot (otherwise it is too unconverged to resolve a
  1.5% difference and the gate result is "inconclusive", not "pass" or "fail");
  zero failed spots; every run's iteration counts as stated.
- **Not measured by Stage 0.** Flop spots; any bb/100 strength effect; decision
  time of a fix.  A passing gate shows the model is imperfect, not that fixing
  it wins hands.

## 9. Stage 0 amendment (approved by the project owner; recorded before the real run)

**Why.**  A timing run on two real spots (seeds 20000 and 20002, both in the
calibration set below) took about 27 minutes each, which puts the 200-spot plan
near 30 hours with the memory free.  It also showed two problems with the
section 8 protocol: production gaps of 124% and 169% of a 400-chip turn pot,
because the pots are small and stacks are about 24 times the pot, so
"percent of the turn pot" is dominated by stack depth; and the production
profile's rivers were solved for fewer iterations than the oracle's, so part of
the difference could be river-solver quality rather than the turn strategy.
Those two spots are the only results seen; no held-out spot has been run.

**Changes (these replace the matching parts of section 8).**

- **Spots:** the first 60 spots in seed order from 20,000 (same capture rule).
  Spots 1-30 are the calibration set; spots 31-60 are the held-out set.
- **Iterations:** oracle 80 (joint turn + river), production turn solve 70 (as
  the bot).  Every profile compared is evaluated with the *same* river
  treatment: each river subgame solved fresh for 60 iterations against the
  ranges that profile produces.  (The bot uses 80 on a real river; 60 keeps
  the run feasible and applies equally to every profile.)
- **Metrics added.**  (a) *Extra gap in big blinds* = (production minus oracle
  extended-game exploitability) / 100 chips.  (b) *Head-to-head loss*: the
  production turn strategy played against the oracle turn strategy, seats
  swapped, both with the neutral river treatment above, measured as the
  production side's expected chips per spot below the oracle-versus-oracle
  value, in big blinds.  This is the closer analogue of a duplicate match
  against a strong opponent than a worst-case best response.  (c) The share of
  hands that reach such a turn spot (spots found per hand tried during
  capture), so a per-spot figure can be turned into a rough per-hand one; the
  conversion is approximate and labelled as such.  The percent-of-pot figures
  are still recorded but no longer decide anything.
- **Gate (fixed now, applied to the 30 held-out spots only).**  Proceed to
  Stage 1 only if all hold:
  1. the median head-to-head loss is at least **1.0 bb per spot** (about 25
     bb/100 if a quarter of hands reach such a spot, the scale at which a fix
     could show in the primary test);
  2. the lower bound of the 95% bootstrap interval of the *mean* head-to-head
     loss (2,000 resamples, statistics seed 91,005) is above **0.5 bb**;
  3. validity: the median oracle gap (matched river treatment) is at most one
     third of the median production gap, and no spot failed.
  If 3 fails the result is **inconclusive** (the oracle is not converged enough
  to resolve the difference); if 3 holds and 1 or 2 fails, Stage 1 does not
  proceed.
- **Calibration set:** only for Stage 1 fitting if the gate passes; it takes no
  part in the gate.
- **Reading the result.**  The oracle plays the two-street abstraction, not real
  opponents, and it shares the production bet menu.  A pass shows that the
  one-street leaf model costs chips against a better model of the same game;
  it does not show that fixing it wins bb/100 against the existing bots.

## 10. Stage 0 result (2026-10-25)

60 spots run, 0 failed, 3 workers, median 577 s per spot.  Gate applied exactly as
fixed in section 9 to the 30 held-out spots.

| | Held-out (30) | Calibration (30) |
|---|---|---|
| Head-to-head loss, median | **0.18 bb/spot** | 0.24 |
| Head-to-head loss, mean [95% bootstrap CI] | 0.32 [0.21, 0.46] | 0.26 [0.20, 0.34] |
| Spots where production beats the oracle | 0 | 0 |
| Production gap / oracle gap, median (% of turn pot) | 37.3 / 3.3 | 38.9 / 2.9 |
| Extra gap, median | 2.44 bb | 2.54 bb |

**Gate: FAILED** (median 0.18 < 1.0 bb; interval lower bound 0.21 < 0.5 bb).
Validity condition held (oracle median gap 17 chips against production 263,
ratio 0.065 against a limit of 0.33; no failed spots), so this is a clean fail,
not "inconclusive".  Per the rule, **Stage 1 does not proceed as designed.**

Other facts: 43% of hands reach such a spot (60 spots in 140 hands), so the
mean loss converts very roughly to 14 bb/100 [9, 20] as a ceiling on what any
turn-model fix could recover, before subtracting what a fix would leave
unrecovered; losses are larger when stacks are shallow relative to the pot
(stack-to-pot under 8: median 0.58 bb, 12 spots; 8-16: 0.31, 16 spots; 16 and
over: 0.10, 32 spots).  The sanity checks held: both profiles are zero-sum to
1e-4 chips, and the no-river-betting reduction test matches the production
solver.

What this does and does not show.  It shows the one-street leaf model is
measurably wrong (production loses to a better model of the same game in every
spot) but cheap against a strong, non-best-responding opponent.  It does not
measure flop spots, other stack depths, or bb/100.  It contradicts the design's
prior of +10 to +30 bb/100 for Stage 1, which would be hard to detect with the
primary test as specified.  Options if this is pursued anyway are listed with
the open questions in the final report, not decided here.
