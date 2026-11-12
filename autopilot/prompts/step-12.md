Autopilot step 12 (use the autopilot-step skill). Task: apply the decision rule of `DESIGN_OPPONENT_MODEL.md` section 4 to the step 10 and 11 reports, mechanically.
- Write the verdict (adopt / keep base / inconclusive) into the design doc and ROADMAP with the numbers.
- If ADOPT: make gated locking the default for `solver_adaptive` (keep an option to turn it off), run the full backend suite, and update README/ARCHITECTURE/DEVELOPMENT. If not adopt: change nothing in production code.
- Then write `autopilot/prompts/step-13.md` proposing the single most valuable next step given all evidence (candidates: proposal B bet-size-conditioned reads with its own pre-registration; more Coach work; cleanup), and append it as row 13 in `autopilot/progress.md`.
