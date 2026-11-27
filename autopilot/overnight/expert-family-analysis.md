# Solver results against expert-style bots

These development runs examine where `solver_adaptive` gained or lost chips.
They use the local simulator's duplicate deals, 100 bb starting stacks and
60 hands per seat orientation. The two orientations of each session share
deals. The solver and opponent play both positions.

The overnight November 26–27 runs against `expert` and `range_expert` start with empty
profiles and carry each seat's public opponent model into its next session.
Each covers 24 sessions and 2,880 hands. The earlier independent ledgers
use different development deals and start a new profile in each session.
The earlier tournament played `adaptive` on 12 sessions and 1,440 hands.
The original row names `adaptive` first, so the report expresses its chip
results from the solver's perspective.

| Opponent | Earlier development run, bb/100 [95% interval] | Earlier hands | With profiles saved across sessions, bb/100 [95% descriptive interval] |
| --- | ---: | ---: | ---: |
| `expert` | +32.73 [−46.20, +116.13] | 2,880 | −5.51 [−79.35, +69.54] |
| `adaptive` | +80.05 [−31.22, +181.88] | 1,440 | — |
| `range_expert` | +139.93 [+42.91, +254.36] | 2,880 | −71.24 [−132.32, −6.06] |

All intervals resample session scores 2,000 times at statistics seed
91002. In the saved-profile runs, later sessions train on earlier ones.
Their intervals describe variation across the observed schedule. The
two expert-style comparisons also use different deal schedules, so the
change in the raw rates cannot isolate the effect of saved profiles.

The raw agent ledgers record session seeds and totals. The replay
reconstructs decision cohorts from those seeds and records aggregate
counts and solver chip results. The terminal street is the last street
with a betting action. An all-in on the flop can therefore be a flop
finish even when a river card is dealt before showdown. Position comes
from the actual button each hand.

Decision cohorts include the first occurrence of each spot type on each
street within a hand. Preflop categories are an unopened pot, a limped
pot, and facing a raise. Postflop categories are a free check, facing a
bet, and facing a raise in the betting sequence. The decision rows
attribute the whole hand's net chips to each qualifying cohort. Rows
overlap and the observed groups depend on both players' actions, so
their returns cannot identify the effect of an individual action.

## Expert

All 24 replayed sessions matched the saved ledger. The solver finished
at +37.62 bb/100 in 1,440 button hands and −48.64 bb/100 in 1,440
big-blind hands. The table gives the hand count and rate within each
position and terminal street. The last column divides each street's
net by all 2,880 hands, so the four contributions sum to the match rate.

| Terminal betting street | BTN hands / bb/100 | BB hands / bb/100 | Contribution to match bb/100 |
| --- | ---: | ---: | ---: |
| Preflop | 1,208 / +111.09 | 1,064 / +39.11 | +61.05 |
| Flop | 113 / −5.72 | 187 / −1.27 | −0.31 |
| Turn | 40 / −221.95 | 100 / +4.69 | −2.92 |
| River | 79 / −892.44 | 89 / −1,257.20 | −63.33 |

River-ending hands account for −63.33 bb/100 of the match, slightly more
than the +61.05 from preflop-ending hands. The solver faced a river bet
in 81 hands and folded 43, called 23, raised 3, and went all-in 12 times
on the first such decision. Nine river hands included a facing-raise
decision. That small cohort is sensitive to individual stacks.

## Adaptive

The current solver replayed the 12 recorded development seeds in the
original matchup orientation and finished at +142.33 bb/100. The local
tournament archive reports +80.05 bb/100 on that schedule. It contains an
aggregate row without individual session or decision records. The cells
below therefore describe the current-build replay. Treat the archive's
interval as specific to its original result. The replay produced zero
illegal actions, fallbacks, or duplicate-deal mismatches.
The older Phase 5 solver code predates completed-hand showdown reads.
The archive lacks a source revision, so it cannot establish which
implementation changes contributed to the difference.

| Terminal betting street | BTN hands / bb/100 | BB hands / bb/100 | Contribution to match bb/100 |
| --- | ---: | ---: | ---: |
| Preflop | 264 / +143.52 | 523 / +66.31 | +50.40 |
| Flop | 147 / +340.12 | 83 / −561.12 | +2.38 |
| Turn | 101 / +229.33 | 46 / +334.87 | +26.78 |
| River | 208 / +299.21 | 68 / +414.16 | +62.78 |

The replay returned +240.67 bb/100 on the button and +43.99 bb/100 in
the big blind over 720 hands each. Big-blind flop endings contributed
−32.34 bb/100 to the match. The solver faced a river bet in 135 hands
and gained chips in that cohort (+319.46 bb/100). Turn and river
facing-raise cohorts each contain just seven hands.

## Range expert

All 24 replayed sessions matched the saved ledger. The solver finished
at +14.60 bb/100 on the button and −157.08 bb/100 in the big blind,
with 1,440 hands in each position. The biggest postflop loss came from
flop endings. The 67 flop-committed showdowns lost 2,100 bb combined,
while the 206 flop folds gained 127.60 bb.

| Terminal betting street | BTN hands / bb/100 | BB hands / bb/100 | Contribution to match bb/100 |
| --- | ---: | ---: | ---: |
| Preflop | 1,220 / +140.82 | 1,068 / +57.85 | +81.10 |
| Flop | 107 / −743.35 | 166 / −709.05 | −68.49 |
| Turn | 39 / −793.69 | 101 / −765.48 | −37.59 |
| River | 74 / −544.32 | 105 / −885.36 | −46.26 |

When the big blind first faced a flop raise, it called in 32 of 52
hands. The 16 of those 52 facing a price above 25% included 10 calls,
3 folds and 3 all-ins. On the river, 41 big-blind hands facing a first
bet above that price included 15 calls, 16 folds, 9 all-ins, and one
raise. The price is the call amount divided by the final pot if called.
The synthetic replay contains no unknown-action or illegal decisions.

## Decision cohorts

Each cell gives hands and whole-hand bb/100 within the cohort, pooled
over both positions. Across all three replays, all 7,200 hands passed
duplicate-deal verification with zero illegal actions or fallbacks.

| Street and spot | Expert | Adaptive | Range expert |
| --- | ---: | ---: | ---: |
| Preflop unopened | 1,440 / +37.62 | 720 / +240.67 | 1,440 / +14.60 |
| Preflop limped | 315 / −29.66 | 163 / +357.86 | 307 / −701.32 |
| Preflop facing raise | 182 / −1,062.21 | 188 / −57.86 | 178 / −930.15 |
| Flop check available | 511 / −285.78 | 510 / +172.90 | 496 / −627.09 |
| Flop facing bet | 108 / −373.95 | 215 / +228.86 | 118 / −1,100.77 |
| Flop facing raise | 50 / −1,430.44 | 10 / −1,496.30 | 52 / −2,768.58 |
| Turn check available | 254 / −509.50 | 298 / +396.64 | 261 / −625.97 |
| Turn facing bet | 159 / −683.67 | 173 / +330.32 | 155 / −1,340.97 |
| Turn facing raise | 21 / −2,909.33 | 7 / −2,528.00 | 26 / −2,795.69 |
| River check available | 130 / −878.32 | 173 / +198.08 | 136 / −615.48 |
| River facing bet | 81 / −1,551.23 | 135 / +319.46 | 84 / −1,642.39 |
| River facing raise | 9 / −5,196.00 | 7 / −178.71 | 11 / −2,665.64 |

## Ranked hypotheses

1. **River opponent locks may overstate the case for continuing from
   the big blind.** River-ending losses recur against expert and range
   expert, with more negative rates in the big blind. The positive
   adaptive result makes it useful to test a narrow change and cap
   collateral harm. Prior investment and the action-dependent sample
   can also explain part of these losses.
2. **The flop response to pressure may commit too many chips against
   range expert.** Showdowns whose last betting action was on the flop
   account for 2,100 bb of losses. Review the legal action menu, SPR,
   and ranges at these decisions on development deals. Showdowns alone
   cannot establish which decision gave up value.
3. **Carried profiles may lag a changing action mix.** Expert and range
   expert recorded lower late-session rates, with both late-minus-early
   intervals including zero. The earlier reset-profile runs used other
   deals. A fresh-profile arm on the same deal schedule is needed to
   separate deal mix from carryover.

## Strength-gate draft for the river hypothesis

Freeze `solver_adaptive` as the baseline. Register an opt-in
`solver_adaptive_bb_river_unlock` arm that uses the baseline policy
through the turn. When the solver is in the big blind on the river
and faces a positive amount to call, re-solve the current river state
with opponent node locks disabled. Preserve the baseline ranges at that
state, legal action menu, iteration budget, RNG, fallback, and every
other spot. Require development unit coverage for the trigger and both
seats before freezing the candidate. The draft requires an implementation
and a committed pre-registration before opening holdout data.

Run `python -m simulation.duplicate_cli pair` from `backend` once per
arm per opponent against `expert`, `adaptive` and `range_expert`.
Use the identical settings per arm and opponent
`--seed-set holdout --seed-offset 9010000 --pairs 48 --session-hands 60
--starting-stack 10000 --small-blind 50 --big-blind 100
--equity-iterations 100 --statistics-seed 91002 --bootstrap-resamples
2000 --workers 2`. Reserve the offset for this draft. A repository
search found no existing use of that offset or effective first seed
16,010,000. Use two workers with one BLAS thread each. Save each report
under `benchmark-results/phase-5/` with this trial's candidate, baseline
and opponent names. The design has 5,760 hands per opponent and arm,
34,560 hands across all six runs. Allow roughly 7–12 hours on this host,
based on the observed replay times and slower range-expert matchups.

Match each baseline and candidate session by seed, both orientations
and hand count. Compute candidate-minus-baseline bb/100 within each
session, then a 95% percentile interval over sessions. The primary
endpoint is the equal-weight mean of expert and range-expert paired
differences at each seed. Pass if its lower bound is above zero, both
primary opponents' individual lower bounds exceed −60 bb/100, and the
adaptive lower bound exceeds −60 bb/100. Require all arms and opponents
to have zero illegal actions, action or solver fallbacks, and deal
mismatches. Add a diagnostic counter for solver fallbacks to the
evaluation report before freezing the test. If that coverage is
missing or the primary interval half-width exceeds 60 bb/100, report
the outcome as inconclusive. At 48 sessions and an assumed 200 bb/100
paired standard deviation, the planning estimate for 80% power at the
two-sided 5% level is about 81 bb/100. Report all intervals and the
trigger counts. Leave the default in place if the gate fails.

No holdout was run. The development aggregates diagnose where results
are concentrated and leave the proposed strategy untested.

## Reproduce the development replays

Run these from the repository root with `OPENBLAS_NUM_THREADS=1`. The
expert and range-expert commands read the local profile ledgers in
`autopilot/overnight/jobs/profiles/`. The adaptive command reads the
existing development tournament in `benchmark-results/phase-5/`.
Choose new output names if these files already exist.

```powershell
backend/.venv/Scripts/python.exe autopilot/overnight/replay_expert_family.py expert --output autopilot/overnight/jobs/expert-check.summary.json
backend/.venv/Scripts/python.exe autopilot/overnight/replay_expert_family.py adaptive --output autopilot/overnight/jobs/adaptive-check.summary.json
backend/.venv/Scripts/python.exe autopilot/overnight/replay_expert_family.py range_expert --output autopilot/overnight/jobs/range-expert-check.summary.json
```
