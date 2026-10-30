# Step 3 report: pre-registered fresh-holdout pool test

**Branch** `autopilot/step-3` from clean `main` (b56874b). No strategy/code changes. Backend tests and frontend build NOT run (no code touched).

## Done
- Protocol committed before data (382ad6d): ROADMAP section, states Phase 5 is COMPLETE under the revised criterion and this is an open measurement, not a release blocker.
- Deviation from prompt: seed offset **4,000,000**, not 2,000,000 — 2M was already used by 5I, 3M by the final test, 1M by 5H.
- Run: `simulation.duplicate_cli tournament`, 8 bots, holdout, 16 pairs x 60-hand sessions, 100 equity iters, stats seed 91,002, 2,000 resamples (same as 5I). Workers 4 instead of 10 (low RAM; results are per-pair seeded, so unaffected).
- Result committed with ROADMAP paragraph.

## Result (53,760 hands, 0 illegal, 0 fallbacks, 0 deal mismatches)
Pool bb/100: solver_adaptive +291 [+239, +342], equity +245 [+147, +345], range_expert +190.
D = solver_adaptive - equity = +46 [-37, +120] -> **INCONCLUSIVE**; win_rate_gate best-other interval [-38, +98].
Head-to-head (bb/100): aggressive +1,047 [+914,+1,177]; random +603 [+448,+755]; equity +392 [+256,+514] (above 0). tight +29 [-5,+62]; expert -7 [-88,+78]; adaptive -7 [-92,+80]; range_expert -22 [-107,+66] (inconclusive).
**Original gate: NOT PASSED** (D not above 0; 4 of 7 head-to-head lower bounds <= 0). Revised criterion would also not be met on this seed set.

## Caveats
- Single run, wide intervals; point estimates vs the expert family are ~0 here vs ~+100 in earlier 16-session holdouts and positive in the 48-session final test. This is a notable weaker result and could be seed noise or a real regression of the merged code vs 5H/5I; not distinguishable. A larger paired run (e.g. 48+ sessions per pairing, new offset 5,000,000, pre-registered) would settle it.
- Raw files: session-tournament-holdout4.json, holdout4.gate.json.

## Recommendation
Do not change the Phase 5 status; record honestly. Owner call whether to run the larger pre-registered follow-up.
