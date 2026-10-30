Autopilot step 4 (use the autopilot-step skill). Task: Coach hardening.
- Start backend and frontend (preview servers; check `.claude/launch.json`), enter two full hands by hand in the Coach tab (one preflop-fold, one to showdown), open the review view, and note every defect (wrong labels, crashes, illegal-action handling, layout at mobile width, console errors).
- Fix defects with tests (backend `test_coach_*`, frontend build must pass). Keep changes small; no solver strategy changes.
- Report what was found and fixed, with a screenshot path for each fixed visual defect.
