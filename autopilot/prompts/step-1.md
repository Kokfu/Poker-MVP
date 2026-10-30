Autopilot step 1 (use the autopilot-step skill). Task: measure `solver_adaptive` in learning mode against the real Slumbot on a clean machine.
- Close/avoid other heavy jobs; check free RAM first and record it.
- Run 1,000 hands with `python -m simulation.slumbot_cli --learn` (see SIMULATION.md and the earlier runs in `benchmark-results/phase-5/slumbot-solver-adaptive-learning.jsonl` for the method), detached, output to `benchmark-results/phase-5/slumbot-learning-clean.jsonl`.
- Report: bb/100 with 95% CI, decision time mean/p95/max by 100-hand block (to expose contention), fallbacks, desyncs; compare honestly with the earlier learning run (p95 8.7 s) and the non-learning run.
- Add a short ROADMAP.md entry with the result, whatever it is. No strategy changes.
