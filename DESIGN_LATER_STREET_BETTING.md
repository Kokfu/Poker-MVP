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
