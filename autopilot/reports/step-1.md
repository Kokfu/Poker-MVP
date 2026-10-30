# Step 1 report: clean Slumbot learning run

Branch `autopilot/step-1` (from `main` 05bab7d). Not merged, not pushed.

**Done:** ran `slumbot_cli --bot solver_adaptive --learn --hands 1000 --seed 7000` alone, detached, to
`benchmark-results/phase-5/slumbot-learning-clean.jsonl` (untracked by git, like the earlier runs;
stdout/stderr files beside it). 1,000 hands, 2,420 bot decisions, 1.73 h. ROADMAP.md has a new entry.

**Results (bb/100, 95% CI, normal approx.)**
- Raw: -198.2 [-440.9, +44.5]. Baseline-adjusted: +20.2 [-63.5, +104.0] (matches CLI summary).
- Desyncs 0, settlement mismatches 0.
- Per-hand wall time (includes Slumbot latency + 0.2 s pause): mean 6.2 s, median 4.7, p95 15.9, max 43.0.
  By 100-hand block, mean 6.1/5.2/5.3/6.8/5.0/8.0/6.5/5.4/7.7/6.3 s; p95 10.6-23.2 s. No early-session slowdown.
- Earlier learning run: mean 8.7 s, p95 27.7, max 73.5 per hand, first 400 hands 11-13 s mean. No-learning: mean 5.4, p95 10.5.
- Versus earlier learning run (unpaired bootstrap): raw -202 [-507, +105], adjusted -60 [-179, +60].
  Versus no-learning: raw -50 [-339, +244], adjusted +99 [-49, +251]. All include zero.
- Seats (raw): button -82, big blind -314 (earlier learning run: -24 / +31).

**Not measured / failed:** current `main` bridge does not record `decision_seconds` or `bot_fallbacks`
(earlier runs were made with instrumentation not on main), so the requested decision-time mean/p95/max and
fallback count are unavailable; I used per-hand elapsed time as a proxy and said so in ROADMAP. I did not
add instrumentation (out of scope) nor rerun.

**Caveats:** free RAM was ~0.8 GB at start (WSL 1.9 GB, browsers, Claude app), so "idle machine" was only partly met;
the speed gain vs the earlier run is confounded with contention. Slumbot deals different cards per session, so all
comparisons are unpaired. Stats scripts were in the scratchpad (not committed). Backend tests were not run: no code changed (docs and result files only).

**Conclusion:** the earlier learning benefit (+159 adj) did not reproduce; learning effect not established; no strategy claim.

**Recommended next:** merge docs; if decision-time/fallback numbers matter for the 6 s Stage 1 limit, a small separate step could restore that logging in the bridge.
