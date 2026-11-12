# Step 8 report: opponent-model design (design only)

Branch `autopilot/step-8` from clean `main`. Not merged, not pushed. No production code changed, no benchmark run, no backend tests run (docs only).

**Done:** wrote `DESIGN_OPPONENT_MODEL.md` (proposal awaiting owner approval).

**Findings used (from existing files):**
- Slumbot learning runs: +3.8 / -198.2 / -34.8 raw bb/100, all intervals include zero; benefit not established.
- Parsed Slumbot action strings (steps 1 and 7 jsonl): facing-bet fold rates are stable between runs (flop 52-56%, turn 44-48%, river 46-50%), so the reads are accurate; lack of gain is not read noise. Preflop not separable by my parse.
- Model facts from code: reads are size-blind per-street aggregates; locks apply wherever a read exists, regardless of whether it differs from equilibrium.
- Decision time (step 7): p95 4.70 s but 55/2,423 (2.3%) above 6 s; 26 of them in hands 0-300, 25 in hands 800-1000, only 4 in between. Not explained by lock confidence alone; log has no lock/cache fields, so cause is a hypothesis.
- Slumbot is underpowered: about 17,000 hands (~30 h) per arm for a 20 bb/100 adjusted effect; so no Slumbot win-rate gate.

**Candidates:** A deviation-gated locking (recommended; mainly latency/robustness), B bet-size-conditioned reads (only candidate that could add winnings vs balanced play; larger, thin samples), C recency decay (not motivated).

**Pre-registered test (for A):** T1 paired local run, offset 6,000,000, 48 sessions x 60 hands, eight opponents including `solver`; gates: all lower bounds >0, pooled non-degenerate paired lower bound > -25, none below -60, else inconclusive. T2 one live Slumbot 1,000-hand learning run: mean <= 2.1 s, p95 <= 6 s, >6 s share <= 1.2%; winnings reported not gated. Parameters fixed in the doc.

**Caveats:** margins/thresholds (0.08, 90%, -25/-60, 1.2%) are my choices, owner may change them before approval; the 1.2% target is stricter than the stated budget. Parse script was in the scratchpad (not committed). Same-seed Slumbot comparisons are unpaired.

**Recommended next:** owner decides whether to approve A (or ask for B); nothing runs until then.
