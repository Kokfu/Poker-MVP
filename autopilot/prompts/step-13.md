Autopilot step 13 (use the autopilot-step skill). PROPOSED by step 12; needs owner approval before running. Design and feasibility only, no production code.

Evidence so far: three Slumbot learning runs show no established benefit (+4/-198/-35 raw); locking gives large gains only against weak bots; proposal A (gated locks) failed T1 (pooled -12.5 [-30.1,+4.8], keep base). Fewer or weaker locks cost strength, so the remaining lever is read SHAPE, not read quantity: proposal B (bet-size-conditioned reads, `DESIGN_OPPONENT_MODEL.md` section 2B), the only candidate that could create winnings against balanced players. It is also risky (3x thinner cells, SQLite schema change), so do not build it blind.

Task:
1. Offline feasibility, no new live runs: from existing Slumbot logs/JSONL (steps 1, 7) and the local benchmark session data, count facing-bet opportunities per size bucket (<=0.5 pot, 0.5-1.0, >1.0) per street per 1,000 hands, and measure whether Slumbot's fold/call/raise frequencies differ by bucket beyond sampling noise (Beta intervals). If buckets are indistinguishable or too thin, report "B not worth building" and stop.
2. If feasible: write a pre-registration (new section in `DESIGN_OPPONENT_MODEL.md` or `autopilot/prereg-step-13.md`) with variant parameters, shrinkage toward equilibrium frequency, a fresh seed offset (7,000,000; verify unused), T1-style paired local gates incl. a no-harm clause using the observed step 10 half-widths (~+/-17 pooled), and a power statement saying what effect size is detectable. Commit it before any data. Do not implement.
3. Report recommendation and cost (hours) for the build + run steps; owner decides.
Cheaper alternative if the owner declines B: cleanup/docs consolidation and Coach polish only.
