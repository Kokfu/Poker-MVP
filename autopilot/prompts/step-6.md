Autopilot step 6 (use the autopilot-step skill). Task: two small fixes.
(a) Slumbot bridge instrumentation: `simulation/slumbot.py` should again record per-decision `decision_seconds` and `bot_fallbacks` in each hand's result (earlier runs had this; current main does not - see ROADMAP "Slumbot, clean 1,000-hand learning rerun"). Must not change bot behaviour; add tests with the fake referee and update SIMULATION.md.
(b) Coach: keep showing the pot while the board-entry prompt is displayed (`need_board` responses carry no state) and show the result on each hand-history row. Backend tests + frontend build + a browser check with a screenshot.
Run the full backend suite at the end.
