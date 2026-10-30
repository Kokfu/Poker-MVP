Autopilot step 3 (use the autopilot-step skill). Task: pre-registered test of the Phase 5 pool criterion.
- First, in a new section of ROADMAP.md, commit the protocol: fresh holdout seeds offset 2,000,000 (not used before), same session format as the 5H holdout (16 sessions x 60 hands per opponent, all seven existing bots), unchanged gate (pool score of `solver_adaptive` not below `equity` with CI above or including zero favouring it, and beats each bot with CI above 0). Decide the exact pass rule before running.
- Then run the existing tournament harness (see how `session-tournament-holdout2-5h.json` was produced), detached, results to `benchmark-results/phase-5/session-tournament-holdout4.json`.
- Report pass/fail honestly with intervals. No strategy changes in this step.
