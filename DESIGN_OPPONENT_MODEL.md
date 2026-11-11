# Design: opponent-model improvement (autopilot step 8)

Status: **PROPOSAL ONLY. Nothing here is implemented or run. The owner must approve before any code is written or any benchmark is started.** Written 2026-11-12 from existing logs and reports; no production file was changed.

## 1. Problem, with evidence

**What the bot does today.** `OpponentModel` (`backend/simulation/opponent_model.py`) keeps per-street *aggregate* frequencies (fold-to-bet, call-vs-bet, raise-vs-bet, bet, check-raise) with Beta(1,1) smoothing and a 4-level confidence label (opportunities <5 / <20 / <50 / >=50). `solver/exploit.py` turns them into node locks with weight 0 / 0.3 / 0.55 / 0.75 (5I adds partial pooling across flop/turn/river). A lock is applied at *every* opponent node where the read exists, whatever the read says.

**What the evidence shows.**

1. *Against balanced opponents learning has not been shown to help.* Slumbot, same seeds, three learning runs: raw +3.8, -198.2, -34.8 bb/100 (steps 1 and 7, ROADMAP); every interval includes zero; unpaired differences between runs are all inside noise (+163 [-153,+468] raw, +15 [-102,+130] adjusted for step 7 vs step 1). The earlier "+159 adjusted" did not reproduce.
2. *The reads themselves are not the weak point.* From the action strings in `slumbot-learning-instrumented.jsonl` and `slumbot-learning-clean.jsonl` (Slumbot decisions facing a bet, my parse, 1,000 hands each):

   | Street | Run (step 7): fold / call / raise, n | Run (step 1): fold / call / raise, n |
   |---|---|---|
   | flop | 56% / 35% / 8%, n=550 | 52% / 40% / 8%, n=513 |
   | turn | 48% / 44% / 8%, n=189 | 44% / 44% / 12%, n=178 |
   | river | 50% / 38% / 12%, n=120 | 46% / 39% / 15%, n=94 |

   The two runs agree within a few points, so the aggregates are stable and, by about hand 400, "high" confidence on the flop (about 55 opportunities per 100 hands) and "medium" on turn/river. A noisy read cannot explain the lack of gain. (Preflop counts are not shown: my parse cannot separate the small blind's opening decision from a response, and preflop reads come from different statistics.)
3. *A balanced opponent has little to exploit in a size-blind aggregate.* A near-equilibrium player's fold rate depends on our bet size, our range and its hand; averaged over our mixed sizes it sits near the indifference level. The model records fold-to-bet with no bet-size or board conditioning (`street_stats` has no size dimension; `SizingProfile` describes the opponent's own bets only), and the lock then pushes the opponent's *whole range* to that average. That is the wrong shape for a mixed-strategy opponent: it can only help if the aggregate departs from what a balanced opponent does, and there is no check that it does.
4. *Locks cost time.* In learning mode 2.3% of decisions (55 of 2,423) exceed 6 s (max 8.44 s, p95 4.70 s, mean 1.41 s; step 7). Opponent-lock re-solves are the stated suspect (step 7 report). The data do not prove it: the log has no lock flag, street, or cache-hit field, and the slow decisions are *not* concentrated where evidence is highest: blocks 1-3 (hands 0-300) have 26 of the 55, blocks 4-8 only 4, blocks 9-10 25. That pattern points to a cold cache early (the code rounds lock masses to 0.05 so profiles share cached preflop re-solves) plus late re-solves when reads move; **this is a hypothesis, not a measurement.**
5. *Locally, reads help against exploitable bots and do not hurt elsewhere.* Step 5 (48 sessions, offset 5M): all seven lower bounds >0; aggressive +1,061, random +595, equity +418, expert/adaptive/range_expert +74 to +79, tight +50. The gain is concentrated in degenerate opponents. Against the expert family and tight the edge is small (about +50 to +80, down 35-40 from the 3M run, inside its CI), and step 3's 16-session run read about 0 (judged seed noise by step 5). So there is no local evidence that more aggressive exploitation is needed, and no evidence of a read-quality problem against sensible opponents.
6. *Power.* Slumbot cannot arbitrate a small effect. Observed raw CIs are about +/-190 bb/100 and adjusted +/-83 per 1,000 hands (adjusted SE about 42). Detecting a 20 bb/100 adjusted effect at 95% needs roughly 17,000 hands (about 30 h per arm, unpaired because Slumbot deals different cards). A Slumbot win-rate gate is therefore not feasible; the test below gates on local paired evidence and latency, and reports Slumbot winnings without gating on them.

**Where reads are weakest (summary).** (a) Against balanced/mixed opponents, because the read is a size-blind aggregate applied unconditionally. (b) Low-sample river and turn reads for the first ~150-400 hands (n<20 means weight 0 to 0.3; 5I pooling mitigates). (c) Not measurable from existing logs: per-decision lock activity, whether a lock changed the chosen action, and the Coach's review data (no per-opponent lock logs there).

## 2. Candidate changes

### A. Deviation-gated locking (lock only when the read is distinguishable from the equilibrium response)
At each opponent node, compare the observed frequency group (e.g. fold / call / raise at that node's street) with the solver's own **unlocked** aggregate frequency at that node. Apply the lock only if the observed rate differs by more than a credible-interval half-width (e.g. Beta posterior 90% interval excludes the unlocked value *and* the difference is at least a minimum margin such as 0.08); otherwise leave the node unlocked. Scale the lock weight by how far the interval is from the unlocked value, not only by sample size.
- *Expected gain:* mostly latency (fewer locked nodes means fewer forced re-solves and a hotter cache) and less exploitation of noise; winnings expected roughly neutral against Slumbot-like opponents (where there was nothing to gain) and neutral against exploitable bots, where deviations are large and the gate passes at once. Not expected to raise win rate by itself.
- *Risk:* a margin that is too strict delays exploitation of real leaks (aggressive/random gains could shrink); needs the unlocked aggregate at each node, which may need an extra unlocked solve or the cached equilibrium solve already made before locking. Moderate implementation size in `solver/exploit.py` plus where locks are consumed.

### B. Bet-size-conditioned reads
Add fold/call/raise-vs-bet statistics by bet-size bucket (<=0.5 pot, 0.5-1.0, >1.0; reuse the existing bucket edges), pooled across streets with shrinkage toward the equilibrium frequency instead of toward the all-streets mean, and look up the bucket that matches the node's bet size.
- *Expected gain:* better-shaped reads against size-sensitive opponents (Slumbot, local `expert`-style bots with size rules); possibly the only change that can *create* new winnings against balanced players.
- *Risk:* triples the number of cells so samples are thin (a 1,000-hand session gives about 55/19/12 facing-bet opportunities per 100 hands per street before bucketing); more complex Coach/profile storage (SQLite schema change); easy to over-fit. Larger change.

### C. Recency-weighted statistics (exponential decay)
Down-weight old observations (half-life about 150 hands) so reads track an opponent who changes. 
- *Expected gain:* small. Slumbot and all seven local bots are stationary in the evidence above, so there is nothing to track. 
- *Risk:* fewer effective samples and noisier reads; no failing evidence motivates it. Not recommended now.

## 3. Recommendation: **A, deviation-gated locking**, with B as a conditional follow-up

It is the only candidate that addresses both measured problems (no benefit against balanced play; 2.3% of decisions over 6 s) with a small change and has a clear failure mode (exploitation of weak opponents shrinks) that the existing local benchmark detects. B is worth a separate proposal only if A shows the lock rate falls and winnings are flat, because then the remaining lever is read shape, not read quantity.

Honest expectation: A is a **speed and robustness** change. It should not be sold as an expected Slumbot win-rate gain. If the owner wants a win-rate gain against balanced opponents, B is the candidate, and it needs its own pre-registration with more cautious power language.

## 4. Pre-registered offline test (for A; to be committed unchanged before any data)

**Variants.** `base` = `solver_adaptive` at the `main` commit current when the owner approves (record the hash). `gated` = `base` plus candidate A with parameters fixed *before* the run: credible level 90%, minimum margin 0.08, weight multiplier = confidence weight x min(1, distance to interval / 0.10). No tuning after seeing results. Instrumentation added in the same change (log per decision: lock count at the node, street, cache hit, whether the unlocked and locked actions differ) so the results can say *why*.

**T1 - strength, local, paired.** `simulation.duplicate_cli tournament`, learning sessions, holdout set, **seed offset 6,000,000 (unused: 1M, 2M, 3M, 4M, 5M are taken)**, 48 sessions x 60 hands per opponent, statistics seed 91,002, 2,000 bootstrap resamples, 2 workers. Opponents: the seven existing bots **plus `solver`** (the in-house balanced opponent; known h2h about +100 for `solver_adaptive` on earlier 16-session runs). `base` and `gated` run on identical seeds/deals, so the paired per-pair difference (gated minus base) is the statistic. Cost about 8 h detached.
- Gate T1a (revised criterion kept): for all eight opponents the 95% interval of `gated` bb/100 has lower bound >0; 0 illegal actions, 0 fallbacks, 0 deal mismatches.
- Gate T1b (no harm): the paired difference, pooled over the five non-degenerate opponents (tight, equity, expert, range_expert, solver; `adaptive` excluded as an exact copy of `expert`), has 95% lower bound > -25 bb/100, **and** no single opponent's paired lower bound is below -60 bb/100. (Margins are chosen against the observed step-5 half-widths of about +/-50 for a single bot; the pooled interval is expected to be tighter. If the observed pooled paired half-width exceeds 40 bb/100 the test is reported **inconclusive**, not passed.)
- The aggressive and random differences are reported, not gated; a drop of more than 150 bb/100 against either is flagged in the report as a cost of the change.

**T2 - decision time, Slumbot, learning mode.** One 1,000-hand live run, `slumbot_cli --bot solver_adaptive --learn --hands 1000 --seed 7000` with the gated variant, machine otherwise idle (record free RAM; stop WSL). Baseline for comparison: step 7 (mean 1.41 s, p95 4.70 s, 55/2,423 = 2.3% above 6 s, max 8.44 s). Because Slumbot deals fresh cards, per-decision comparison is unpaired and one run has block-to-block variation (p95 by block 2.6-6.6 s), so gates are absolute:
- Gate T2a: decision-time **mean <= 1.5 x baseline mean = 2.1 s** and **p95 <= 6.0 s**.
- Gate T2b: share of decisions above 6 s **<= 1.2%** (about half the baseline), with the instrumentation fields showing why any remaining slow decisions occurred.
- Reported, not gated: raw and baseline-adjusted bb/100 with 95% CI, desyncs, fallbacks (must be 0 desyncs/settlement mismatches).

**Decision rule.** Adopt A if T1a, T1b, T2a and T2b all pass. If T1 passes and T2 fails, keep `base`, report the gap, and use the instrumentation to rerun the diagnosis (the problem is then not lock count). If T1b fails or is inconclusive, do not adopt; `base` stays. No gate is changed after seeing data; if a prerequisite fails (e.g. T1 needs a fix), restart from a new offset and say so.

**Not claimed.** No Slumbot win-rate result will be used to claim improvement or loss; if the Slumbot raw/adjusted interval includes zero (expected) it is reported as such. One run per arm; no multiplicity correction across eight opponents (same limitation as step 5).

## 5. Out of scope / not yet checked
- Whether locks actually cause the >6 s decisions (hypothesis only; first thing the instrumentation settles).
- Coach profile storage changes (needed for B, not A).
- The expert-family edge being about 35-40 bb/100 lower at 5M than 3M is unresolved; T1 on a third seed set will add one more data point.
- No tests were run for this design step (only documents were added).
