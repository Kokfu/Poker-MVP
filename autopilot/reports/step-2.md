# Step 2 report: reconcile Phase 5 status (docs only)

**Branch** `autopilot/step-2` (from `main` 0783a9c). Docs-only: frontend build and backend tests not run (no code touched).

## Finding
The prompt's premise was partly stale. ROADMAP.md does not end at "NOT COMPLETE": it ends at **PHASE 5 COMPLETE** (lines ~299, ~317), decided under a *revised* criterion the owner set prospectively on 2026-09-29 (all seven opponents' 95% lower bounds > 0, 0 illegal, 0 deal mismatches). The earlier "NOT COMPLETE" verdicts are the original-criterion results (pool score vs `equity`), left unlabeled, so the doc contradicted itself. README, ARCHITECTURE, DEVELOPMENT make no completeness claim about Phase 5 (grep found none).

## Changes
- ROADMAP.md: added a "Current status" paragraph at the top of Phase 5 (merged and released, tag `phase-5-complete`, merge `40ff212`; COMPLETE under revised criterion; original pool criterion never passed; pool-vs-`equity` still an open measurement). Marked the three "NOT COMPLETE" verdicts as original-criterion/superseded; added that the criterion change followed three failed gate attempts; labelled the final verdict "(revised criterion)".
- SIMULATION.md: the `win_rate_gate` description is the original criterion and does not reproduce the COMPLETE verdict; `solver_adaptive` fails it on all holdout runs so far.

## Numbers verified
All 14 rows (7 opponents x `final-h2h-*` and `rerun-perf-h2h-*`) in ROADMAP's two tables checked against the JSON files: bb/100, CI, hands (5,760), illegal (0), mismatches (0) all match. I did not re-verify the holdout/5H/5I pool numbers (+249/+299, +289/+316, +344/+400) against their files; I only kept the quoted text.

## Not done / caveats
- Tag not moved or deleted. 
- Test counts in ROADMAP (770/781/774) are not re-checked.

## Recommendation on the tag
`phase-5-complete` points at the merge of a release that is COMPLETE only under the revised criterion. Keep it (moving tags breaks references; it correctly marks the release), but do not describe it as passing the original gate. If you want the name to be precise, add a new annotated tag (e.g. `phase-5-revised-criterion`) at the same commit, owner's call. Step 3 (fresh-holdout pool test) is the way to actually settle the original question.
