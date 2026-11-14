Autopilot step 17 (use the autopilot-step skill). Release readiness, no pushing. 
- Read `autopilot/progress.md`, the ROADMAP Phase 5 status and all reports 9-16. Write `RELEASE_NOTES.md` (what the project is, what is verified with numbers and intervals, what is NOT claimed, known limitations, how to run). Suggest a tag name and annotated-tag message in the report but do NOT create or push tags.
- Check git hygiene: `git status` clean, large result files tracked or ignored deliberately (note what `benchmark-results` ignores), no secrets/tokens/personal data committed (grep for tokens/keys/emails in tracked files; SECURITY.md must match reality).
- Run the full backend suite and frontend build once more on the final tree.
- Propose in the report the remaining optional work (owner decisions): push to GitHub, tag, proposal B build if T0 passed, anything else with evidence.
