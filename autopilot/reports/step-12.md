# Step 12 report: decision rule applied to proposal A

**Verdict: KEEP BASE.** Proposal A (`solver_adaptive_gated`) not adopted. Docs only, no production code changed, so the backend suite was NOT re-run (step 10 re-ran it on its branch: 830 pass). Not merged, not pushed.

**Branch note:** `main` (ac3971b) does not contain step 10 (01e9234); `git branch --contains 01e9234` lists only `autopilot/step-10`. So `autopilot/step-12` was branched from `autopilot/step-10`; it carries the step 10 commits. Merge order: step 10, then step 12.

**Owner decision:** step 11 (T2, live Slumbot decision time) skipped because T1 already failed and the section 4 rule gives keep base whenever T1b fails. T2a/T2b were never measured; nothing is claimed about gated latency.

## Rule applied (from step 10 report only)
- T1a fail: lower bounds <= 0 for expert -3.5, adaptive -3.4, range_expert -7.9, solver -0.7.
- T1b fail: pooled paired -12.5 [-30.1, +4.8] bb/100 (half-width 17.5 < 40, so not inconclusive); pooled lower bound < -25 and solver paired lower bound -77.0 < -60.
- Flags: aggressive -105.4 [-236.7,+18.3], random -33.4 [-118.1,+57.4], under the 150 threshold.
- Gated below base on 7/8 points; no single interval excludes zero ("not shown harmless", not "proven harmful").

## Changes
- `DESIGN_OPPONENT_MODEL.md` new section 6 (verdict); `ROADMAP.md` verdict entry.
- `autopilot/progress.md`: row 10 done, row 11 skipped by owner, row 12 done pending review, row 13 added.
- `autopilot/prompts/step-13.md`: proposed next step.

## Caveats
One run per arm, no multiplicity correction; base itself is lower on this seed set (expert family ~57-59 vs ~75 at 5M), a still-unresolved variance question.

## Recommended next
Step 13 as proposed: offline feasibility + pre-registration for proposal B (bet-size-conditioned reads), design only, owner approval required. Alternative: cleanup/Coach polish.
