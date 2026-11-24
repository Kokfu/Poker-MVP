# Phase 4K experiment protocol

Freeze the design before running comparative outcomes. All workloads are offline. Use production Coach solver classes, legal sizes, chart and solve budgets. Reset equal 1,500-chip stacks at 50/100 blinds every hand. Train against the same AggressiveBot data-collection policy across opponents. Use a fresh seeded bot per role and training hand and alternate the button. Supply no live profiles during training or to the baseline opponents during evaluation.

## Opponents and training

The four synthetic opponents cross preflop selectivity with aggression. A tight player participates with probability .85 holding a pair, or ace-high with a ten or better kicker, and .09 otherwise. A loose player participates with probability .88 with any holding. The participation gate applies when facing a preflop price, including the small-blind completion. When eligible to raise, an aggressive participant raises 65% of the time. Passive players never raise. Free preflop checks require no participation gate.

Postflop, classify the best five cards as high card, pair, or two pair or better. Passive players bet with probabilities (.02, .08, .35) and aggressive players with (.40, .65, .95). Both use a target of 500 chips, bounded by the legal interval. Postflop they never reraise. For an incremental call no larger than half the effective pot before calling, passive players call with probabilities (.12, .78, .99) and aggressive players with (.28, .74, .99). For larger calls those probabilities are (.03, .45, .94) and (.12, .53, .95). Calls use the effective cost after capping at the remaining stack and excluding unmatched excess from the pot. These rules apply on all postflop streets. Registered equity, expert and solver have their original strategy and are gameplay pilot references. Their hidden-card path and response likelihoods are outside the exact synthetic panel.

The ordered synthetic grid is tight-passive, loose-passive, tight-aggressive, loose-aggressive, followed by equity, expert and solver. Training seed = 41,000,000 + 100,000 × opponent index + 1,000 × stream + hand index (all zero-based). Keep only validated completed histories and freeze both the public OpponentModel snapshot and the revealed-showdown data used by Coach. Use nested prefixes of 3, 30 and 100 hands in exact EV. The two EV replicates are streams 0 and 1. Mismatch flips both axes, keeping size and stream fixed. Candidate retains the Phase 4J prior of 10 pseudo-hands and uses matched share n/(n+10). There is no Phase 4K fitting.

## Exact river holdout

All four scripted decisions use Hero on the button, raise to 250, Villain call, and check/check on flop and turn. Each row is evaluated against all four synthetic opponents. The exact opponent posterior starts uniform conditional on Hero and board blockers and multiplies the opponent's actual probabilities of calling the raise, checking flop, checking turn, and taking the observed river action. Hero's fixed line is conditioned on by design. A checked-to Hero can close the river. All responding Villains use their conditional fold/call rule.

| Hero | Board | Villain on river |
| --- | --- | --- |
| 9h 9d | Kc 9s 3d 5h Js | Bet 500 |
| 6d 5d | Qs 6s 2c 7h Ad | Bet 500 |
| As 4s | Jh 8d 3c 2h 9c | Check |
| Kd Td | Kh 7d 4s Qc 3h | Check |

Primary EV metric is equally weighted mean policy-weighted matched-minus-off bb/decision over all 96 rows, including both streams. Report harm below −1e-6 bb, its count and summed/mean cost, policy action frequencies, posterior TV/equity error, and per-reference/size/stream effects. Use the shared action union to check which action maximizes payoff under each inferred posterior with the true response held fixed. The exact rows are a finite, dependent panel. Their prefixes and reused scenarios do not supply independent population samples.

## Gameplay

Each deal uses the same complete seeded deck, button, stack resets, opponent seed and Hero seed in both arms and both seat orientations. Count validated histories, chip conservation, raw solver probabilities, solver fallbacks, decisions, setup time, gameplay time and peak resident memory. A gameplay statistical unit contains both arms, both orientations and all deals sharing a training profile. Pilot uses stream 2, two deals per opponent and 30 training hands for all seven opponents. Pilot deals start at 42,000,000 + 1,000 × opponent index. The pilot establishes integrity and cost.

If pilot integrity passes and the synthetic pilot runtime extrapolates to at most 900 seconds for the larger benchmark, run stream indices 3–8 for the four synthetic opponents with 30 training hands and two deals per block. Deal seed = 43,000,000 + 100,000 × opponent index + 1,000 × stream + deal index. Both workloads have an external cap (300 s pilot, 1,200 s larger). Each interval resamples whole profile blocks with replacement, using 10,000 percentile-bootstrap draws and statistics seed 44,091. Pooled draws are stratified by opponent with equal weights. Pilot intervals are omitted for one block per opponent. The larger panel has six profile blocks per opponent, so per-opponent intervals will be unstable. Re-run the pilot or a complete mixed-policy block to verify independent determinism. Exact EV cap is 1,200 s.

## Advancement criteria

Require an exact mean improvement of at least +0.10 bb/decision, strictly positive matched means for each opponent and both training streams, and matched EV above mismatched EV. Require a confirmatory gameplay mean of at least +5 bb/100 and a pooled paired 95% lower bound above zero. Require zero unexpected solver fallbacks, illegal actions, invalid mixes, deal mismatches and accounting failures. An unrun or incomplete larger workload cannot pass. The candidate must additionally preserve at least as much matched mean exact EV with lower total harm to warrant a subsequent gameplay trial. Missed gates preclude a strategy promotion from this experiment.
