# Step 7 report: first Slumbot learning run with decision-time logging

Branch `autopilot/step-7` (from `main` e4a2413). Not merged, not pushed.

**Done:** ran `slumbot_cli --bot solver_adaptive --learn --hands 1000 --seed 7000` detached to
`benchmark-results/phase-5/slumbot-learning-instrumented.jsonl` (force-added to git; stdout/stderr stay local).
1,000 hands, 2,423 bot decisions, 1.78 h. ROADMAP.md has a new entry. No code or strategy changes.

**Results (bb/100, 95% CI, normal approx.)**
- Raw: -34.8 [-232.7, +163.1]. Baseline-adjusted: +35.1 [-48.6, +118.8] (matches CLI summary).
- Desyncs 0, settlement mismatches 0, bot_fallbacks 0.
- Bot decision seconds (thinking only): mean 1.41, median 1.11, p95 4.70, max 8.44. Decisions above 6 s: 55 of 2,423 (2.3%), none above 10 s.
- By 100-hand block, mean/p95/max: 2.19/5.82/8.4, 1.90/5.41/7.6, 1.85/4.81/7.0, 1.03/2.84/7.6, 0.80/2.71/6.1, 0.83/2.56/3.8, 0.84/2.68/3.5, 0.81/2.65/6.6, 1.84/6.20/7.9, 1.80/6.61/7.9. Counts above 6 s per block: 12,5,9,1,1,0,0,2,13,12.
- Per-hand wall time (incl. Slumbot latency): mean 6.4 s, p95 18.7 s, max 22.9 s (step 1: 6.2 / 15.9 / 43.0).
- Versus step 1 (same seeds, unpaired bootstrap, 5,000 resamples): raw +163 [-153, +468], adjusted +15 [-102, +130]. Both include zero.
- Seats (raw): button -120, big blind +51.

**Failed / caveats**
- First attempt died at hand 929 when its session ended (not a crash in the bot); learning state cannot be resumed, so it was restarted from hand 1. Partial files kept locally as `*.killed-at-929.*`, not analysed.
- Machine not fully idle: free RAM ~1.2 GB at first start, ~2.2 GB at restart; WSL left running. Timing could be affected by contention.
- Slumbot deals different cards per session, so all comparisons are unpaired. Stats script was in /tmp (not committed).
- Single run; fallback definition was reconstructed in step 6 so 0 fallbacks may not match old runs' definition.

**Tests:** backend `pytest -q`: 818 passed. Frontend untouched (no build).

**Conclusion:** p95 decision time (4.7 s) is within 6 s, but 2.3% of decisions and two late blocks' p95 exceed it; max 8.4 s. Learning effect against Slumbot still not established (three learning runs: +4, -198, -35 raw). No strategy claim.

**Recommended next:** if a hard per-decision 6 s cap matters, investigate the slow re-solve spots (opponent-lock re-solves) before any Stage 1 work; otherwise merge the docs and result file.
