# Step 17 report: release readiness

**Verdict: release notes written; git hygiene clean apart from one owner-level item (author email in history).** Branch `autopilot/step-17` from main 2526592. Docs only (`RELEASE_NOTES.md`, this report). No tag created or pushed; not merged, not pushed.

## Done
- `RELEASE_NOTES.md`: what the project is; verified results with intervals (step 5 offset-5M table, proposal A fail, Coach loop, fresh-clone run); explicit "not claimed" list (original pool criterion unmet, no Slumbot win shown, learning benefit unestablished, B not built); limitations; how to run. Numbers were taken from reports 1, 5, 7, 10, 14 and ROADMAP, not re-derived. Nothing is said about push state.
- Final-tree checks: see "Checks" below.

## Git hygiene (tracked files: 268; 129 commits; tags: phase-2 ... phase-5-complete, none created now)
- `git status` clean on a fresh branch from main.
- Secrets: grep of tracked text for key/secret/token/password patterns, AWS/GitHub/`sk-` key shapes and PEM headers found only the Slumbot bridge's in-memory session token handling and test fixtures (`token="tok"`); no real credential. `.env.example` contains only `VITE_API_URL=http://127.0.0.1:8000`. Tracked Slumbot logs hold cards, actions, winnings and timings only (no token field). No `.env`, SQLite, key or certificate file is tracked.
- Personal data: the only email in tracked file contents is the `noreply@anthropic.com` co-author trailer in the skill file. **All 128 human-authored commits carry the owner's git author email (a gmail address)**, now in the already-pushed history; rewriting would need a force-push, so it is an owner decision (usually accepted for a personal repo, or avoided by a noreply address going forward). The username `kokfu` also appears in absolute paths in README/DEVELOPMENT/SIMULATION/AGENTS.md and two run scripts (local Windows paths, not secrets).
- `.gitignore` ignores `benchmark-results/` wholesale, `backend/data/` (Coach SQLite), `.env*` (except `.env.example`), venv, node_modules, dist. 45 result files under `benchmark-results/` were force-added deliberately (final/rerun head-to-heads, step 5 and 10 JSON, three Slumbot logs, the step 13/14 outputs); the rest (killed partials, other logs) exist only on the original machine. Largest tracked files are the Slumbot logs (~0.4 MB each) and solver data (<0.25 MB); nothing large.
- SECURITY.md matches reality: no credential store; ports bound to 127.0.0.1 (docker-compose.yml); CORS allows only localhost:5173 / 127.0.0.1:5173 with GET/POST/DELETE; Slumbot bridge is opt-in. Minor staleness only (a "Phase 2" AI-training line); not edited.
- The "pushed history" check was done on the current local history; I did not inspect the remote or GitHub's view.

## Checks
Final tree (only docs added since main): backend suite **859 passed, 8 warnings, 714 s**; frontend `npm run build` ok.

## Suggested tag (not created)
`v0.5.0` (or keep the repo's convention: `phase-5-release`). Annotated message: "Poker Analyzer MVP 0.5.0: Phase 5 complete under the revised criterion (solver_adaptive beats all seven older bots, offset-5M lower bounds all > 0); Coach with opponent learning; proposal A rejected, B not built; see RELEASE_NOTES.md."

## Optional work (owner decisions)
1. Decide on the author-email exposure (accept, or use a GitHub noreply address from now on).
2. Tag as above if wanted; push tag separately.
3. Proposal B: T0 passed only weakly; evidence says do not build (~50 h, detects >= ~22 bb/100). Skip unless wanted for its own sake.
4. Investigate the Coach lock oddity from step 16 (tight villain: fold 72% -> call 98%, villain range widens) and the extreme near-pure warmed advice; this is the one finding with a plausible user-visible defect.
5. Replace absolute paths in older doc sections; trim SECURITY.md's stale Phase 2 line.
6. A bigger Slumbot run (about 100,000 hands, ~170 h) is the only way to resolve live effects of 20 bb/100; not worth it unless the claim matters.
