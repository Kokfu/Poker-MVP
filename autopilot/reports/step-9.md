# Step 9 report: proposal A (deviation-gated locks) implemented, off by default

Branch `autopilot/step-9` from `main` fa3b538. Not merged, not pushed. T1/T2 not run.

## What was done
- `DESIGN_OPPONENT_MODEL.md`: "Approval" section (date 2026-11-12, `base` = `main` fa3b538). Committed first.
- `solver/exploit.py`: Beta-posterior interval (pure Python, no SciPy), `node_aggregates` (unlocked range-weighted action frequencies), `gate_decision`/`gate_locks`. Constants fixed as approved: level 0.90, margin 0.08, scale 0.10. A node locks if some read group is >= 0.08 from the unlocked frequency AND outside the 90% interval; weight = confidence weight x max over groups of min(1, distance/0.10). The point estimate compared is the smoothed frequency (pooled counts for the interval when pooling is on) - my reading of the spec.
- `solver/bot.py`: `gated_locks` option (`AdaptiveSolverBot(gated_locks=True)`, registry `solver_adaptive_gated`). Postflop: an unlocked solve first, gate, then a locked solve only if any lock survives (otherwise the unlocked solve is used). Preflop: the unlocked reference is the stored chart. Default path unchanged.
- Instrumentation in `explanation["instrumentation"]` and `decision_trace`: street, gated, candidate_locks, locks_applied, cache_hit, unlocked_action_differs. "Differs" is filled only on preflop and in gated mode (None otherwise). Uses a new pure `_pick`; `_sample` is called exactly as before.
- Commits: 752b2a5 (approval), 390ab71 (code+tests), plus a follow-up commit (bot-list test, sanity script, this report).

## Tests
- Golden file `backend/test_data/equiv_learning_main_fa3b538.json` made from unmodified `main` before any code change: 40-hand deterministic learning session vs the fake referee, 98 decisions, 77 sampled strategies, preflop_exploit and postflop_solve both exercised. With the option off, probabilities (full precision), actions and hand results are byte-identical (checked by cmp and by test).
- `test_solver_gated.py`: 12 tests pass (equivalence, Beta math, gate: equal read -> no lock, deviation -> full weight, scaled weight, margin edge, interval edge, group sums, `gate_locks`, reads_out leaves locks unchanged, instrumentation fields).
- Full backend suite: 829 passed, 1 failed (`test_existing_cli_list_bots_still_works`, expected bot list lacked the new name). Fixed; that file re-run alone: 11 passed. The whole suite was NOT re-run after that one-line change.

## Sanity check on stored Slumbot reads (NOT a result)
`backend/gate_sanity.py`, output `benchmark-results/gate-sanity-step9.json`. Reads = step-7 facing-a-bet fold/call/raise rates (flop n=550, turn 189, river 120); uniform ranges, 2 boards per street, one spot each; only facing-a-bet nodes (bet and preflop reads were not parsed). Each spot has 10 candidate opponent locks today.
- Full sample: gate keeps 7/10 (flop), 8/10 (turn), 8/10 (river). Quarter sample (same rates): 7, 6-7, 9.
- So the gate removes only about 20-40% of locks on Slumbot-like reads, not most of them. These reads sit far from equilibrium frequencies in this size-blind aggregate.
- Single-solve wall time was higher gated (about 2.3-4.1 s vs 1.4-2.6 s base) because of the extra unlocked solve, one measurement each on a busy machine.

## Caveats / risk for T2
- Latency may get WORSE, not better: gated needs two solves whenever any lock survives, and most still survive. T2a/T2b are likely at risk; this is the design's stated "extra unlocked solve" cost, now measured roughly.
- Fake-referee baseline has ~21% fallbacks (replay mismatch, pre-existing on `main`); not caused by this change.
- Bit-identity checked only for this one session/seed and the suite.

## Recommended next
Run step 10 (T1) as pre-registered; consider flagging to the owner before step 11 that T2 is likely to fail on latency (optional: cache the unlocked solve by street key; would be a new proposal/changed variant, not a tweak after seeing data).
