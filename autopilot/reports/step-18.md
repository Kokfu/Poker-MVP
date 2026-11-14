# Step 18 report: proposal B (`solver_adaptive_sized`) built, off by default, not tested

**Done: B built as pre-registered; default path byte-identical; T1 NOT run.** Branch `autopilot/step-18` from main 64d06cb+; not merged, not pushed. Full backend suite **873 passed** (859 + 14 new), 8 warnings, 787 s. Frontend untouched, build not re-run.

## What was built
- `simulation/opponent_model.py`: `size_bucket` (edges <=0.5 / 0.5-1.0 / >1.0), `SizedStats`, `OpponentModel.sized_stats`: for each postflop bet/raise by the other player, the modelled player's fold/call/raise reply bucketed by raise amount / pot after matching its own street bet (the T0 definition), pooled over streets. Exposed as `OpponentProfileSnapshot.sized_statistics` (ignored by equality, dropped from `as_dict`). Deviation from the prompt: the stat is always collected (cheap, derived) but only the sized bot reads it; no existing serialised output changes.
- `solver/exploit.py`: `facing_size_ratio`, `sized_node_lock` (posterior (k + 20 p_eq)/(n + 20), p_eq = unlocked aggregate of the action group at that node; n < 10 -> node unlocked, no fallback cell; weight = base confidence weight of n), `sized_locks` (replaces only opponent facing-a-bet nodes, base locks kept elsewhere; strength = base facing formula), `sized_needs_aggregates`.
- `solver/bot.py`: `sized_reads` flag, `SizedAdaptiveSolverBot`, registry `solver_adaptive_sized` (`simulation/bots.py`). In `_solve`, an extra unlocked solve (same iterations, as the gate) runs only when some facing node has a bucket with n >= 10. Instrumentation `instrumentation["sized"]` (facing_nodes, locked, thin, base_facing_locks, bucket n) only for the sized bot.
- Coach: new table `sized_reads (opponent, street_class, bucket, opportunities, folds, calls, raises)`, `CREATE IF NOT EXISTS`, a derived cache written by `log_hand` and cleared by both delete routes; the Coach's advice path does not read it. Hands table untouched.
- Docs: DESIGN_OPPONENT_MODEL section 7, README/ARCHITECTURE bot lists. The step 17a preflop small-blind strength quirk is deliberately NOT fixed.

## Tests (`backend/test_solver_sized.py`, 14; plus list-bots test updated)
Golden-file bit-identity with the flag off (unchanged file, existing gated test also passes); flags; bucket edges incl. 0.5/0.5001/1.0/1.0001; scripted hands giving exact cell counts and the raise-over-bet ratio (0.33); no serialisation/equality change; shrinkage math against an independent computation (m=20, weight 0.55 for n=30); n<10 unlocked and other buckets never used; facing nodes replaced, others equal to base; instrumentation only for sized; a Coach spot where the sized bot actually locks; DB creation on a pre-B database, idempotent reopen, round trip/replace/cleanup, log_hand refresh.

## Sanity (NOT a result; `backend/sized_sanity.py`, `benchmark-results/step-18-sized-sanity.json`)
Slumbot-like reads (step 9 per-street reads; step 13 pooled bucket cells 2177/518/819), uniform ranges, 2 boards per street, one solve each. Base locks 10 nodes (9 facing + 1 other). Sized: all 9 facing nodes locked (10 total) at full sample, at a tenth (n=217/51/81) and with cells 43/10/16; with cells 10/2/4 only 1 of 9 facing nodes locks (8 thin) = 2 total. Solve time: sized 1.3-2.3 s vs base 0.9-1.7 s (one measurement each, busy machine, about +0.4-0.9 s). Says nothing about strength.

## T0 re-run?
The built lookup differs from what T0 modelled (T0: street x bucket cells shrunk toward a size-blind street model; build: postflop-pooled bucket cells shrunk toward the solver's unlocked aggregate, which cannot be modelled offline). I ran `autopilot/t0b-step-18.py` (committed before its output; pooled cells, pooled size-blind comparator; NOT a gate): improvement +0.128 nats/case, 95% [+0.114, +0.141], same conclusion as T0 (+0.126 [+0.113, +0.138]). The solver-prior part remains untested offline.

## Caveats
- Cost risk for T1: one extra solve per postflop street solve with qualifying cells (latency not measured live). No Slumbot or local paired run was made.
- Hand-derived cells assume at most one reply per bet within a street; replies after a short all-in count as call.
- The sized cache table is informational only until the Coach is wired to the sized bot (not done; out of scope).

## Recommended next
Step 19 (T1 at offset 7M, about 40 h) as pre-registered; the base arm must be fresh at that offset.
