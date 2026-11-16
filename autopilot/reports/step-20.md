# Step 20 report: decision rule for proposal B, docs only

**Verdict: KEEP BASE for `solver_adaptive_sized` (B).** The pre-registered rule (`autopilot/prereg-step-13.md`) applied to step 19 gives T1a FAIL, T1b FAIL, T1c FAIL, so no adoption and **no production code changed**. Branch `autopilot/step-20` from main 39459af; not merged, not pushed.

## Numbers used (re-read from `benchmark-results/phase-7/t1-analysis.json`; offset 7,000,000, 48 x 60 hands)
- Pooled paired (sized - base) over tight/equity/expert/range_expert/solver: **-92.4 [-123.4, -62.1]** bb/100, half-width 30.6.
- T1a: lower bounds range_expert -22.0, solver -86.6 (not > 0). T1b: pooled lower -123.4 < -20; equity -352.0 and solver -191.9 below -60. T1c: whole interval below 0.
- Flag: aggressive -554.4 [-657.6, -449.6]; equity -278.6 and solver -123.4 also clearly negative.

## Changes
- `DESIGN_OPPONENT_MODEL.md` new section 8 (verdict, numbers, statement that both A and B failed their pre-registered no-harm tests, untested hypotheses).
- `ROADMAP.md` verdict paragraph after the proposal A one.
- `RELEASE_NOTES.md` update section: B built and tested, failed all gates; both A and B failed no-harm tests; sized and gated are available but off by default; it explicitly supersedes the older "B not built" line, which I left in place.
- `autopilot/prompts/step-21.md` written; `autopilot/progress.md` updated (step 20 done, step 21 optional).

## Step 21 as written
Offset 8,000,000 (grep: unused), 24 sessions x 60 hands, five non-degenerate opponents, gates F1 (pooled lower > -25, no single < -60) and F2 (pooled lower > 0, expected unreachable). Pooled half-width was 17.5 (step 10) to 30.6 (step 19) at 48 sessions, so about 25-43 at 24; detectable effect about 31 bb/100 at best, up to about 55. A one-node preflop change should be a few bb/100, so the test cannot detect it and can only rule out large harm. Cost about 14 h.
**Recommendation: do not run the paired test by default.** Show the fix with a unit test plus the 1-minute step 17a diagnosis; adopt only if the owner accepts "correctness fix, no paired strength evidence"; otherwise stop spending compute on opponent-model changes.

## Checks
Docs and prompts only. Backend suite and frontend build NOT run (no code or test change).
