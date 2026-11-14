# Step 15 report: runnability and docs consolidation

**Verdict: a fresh clone works end to end from the docs; docs now agree on status and bot list.** Branch `autopilot/step-15` from main 40e716c; docs only, no code changed. Not merged, not pushed.

## Fresh-clone check (scratch clone outside the project, deleted afterwards)
- `git clone`; `py -3.11 -m venv`, `pip install -r requirements.txt`, `pip check`: clean.
- Backend `pytest -q -p no:cacheprovider` in the clone: **830 passed, 9 warnings, 800 s** (a pyparsing deprecation warning from eval7 among them).
- Frontend `npm ci` + `npm run build`: ok (npm audit prints vulnerability notices, not addressed).
- Started `uvicorn main:app`; `/api/health` OK; `POST /api/coach/advise` (As Kd, button) returned a raise 250 from the preflop chart in 0.45 s; Coach opponents list empty on a new DB.
- `docker compose config` ok and `docker compose build` ok (both images built; I did not `compose up`, so the container run was not re-checked). Built images removed.
- Problems found: README gave no venv-creation step and used only the original machine's absolute paths; no Coach API example anywhere. Both fixed in docs.

## Consolidation
- README: status section; setup steps tested from a fresh clone; bot list and API bot list include `solver_adaptive_gated` (experimental, off by default).
- ARCHITECTURE: bot registry includes `solver_adaptive_gated`; stale "Persistent match mode is Phase 3 work in progress" reworded.
- ROADMAP: the bare "Phase 3 - in progress" heading relabelled as historical (its sub-sections still say what was and was not covered; history not rewritten). Existing Phase 5 status and proposal A verdict were already consistent.
- DEVELOPMENT: new "Project status and how to resume autopilot" (status, A rejected, B pending/not built, how to run tests/benchmarks, Coach API smoke test, autopilot loop).
- Not changed: older point-in-time test counts in ROADMAP (770/781) and DEVELOPMENT (776/778) are dated history; the current count (830) is stated in this report and DEVELOPMENT points at reports.

## Caveats
- DEVELOPMENT/README still contain the original machine's absolute paths in older sections (README now says to substitute); SIMULATION.md was not found to need changes and was only grepped for status/bot terms, not read in full.
- On the project branch (docs changes in place): backend suite **830 passed, 8 warnings, 635 s**; frontend `npm run build` ok.

## Recommended next
Step 16 (Coach learning-loop verification).
