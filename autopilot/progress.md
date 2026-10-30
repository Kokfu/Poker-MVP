# Autopilot progress

Orchestrator = the "main" chat. Each step runs in its own new chat (low context), using the
prompt in `autopilot/prompts/step-N.md` and the `autopilot-step` skill
(`.claude/skills/autopilot-step/SKILL.md`).

Loop: main starts step N in a new chat -> step chat works on branch `autopilot/step-N`, commits,
writes its report to `autopilot/reports/step-N.md`, stops -> main reviews (diff, tests, honesty of
claims) -> main merges locally into `main` (no push) and ticks the box below -> main starts step N+1.

Standing rules (every step): report outcomes faithfully including failures; pre-register any
pass/fail gate in a doc before running data; no strategy changes without an equivalence or
paired-evidence check; keep commits small; never push, force-push, tag, or delete branches
(main asks the user); long jobs run detached and their result files stay in `benchmark-results/`.

| # | Step | Prompt | Status |
|---|------|--------|--------|
| 1 | Clean 1,000-hand Slumbot learning run on an idle machine; record speed-up and learning effect | prompts/step-1.md | [x] done (9f313f8): learning benefit not reproduced |
| 2 | Reconcile Phase 5 status: ROADMAP says "NOT COMPLETE" (pool gate) while tag `phase-5-complete` exists; fix docs/wording | prompts/step-2.md | [ ] todo |
| 3 | Pre-registered fresh-holdout test of the pool criterion (`solver_adaptive` vs `equity`) | prompts/step-3.md | [ ] todo |
| 4 | Coach hardening: end-to-end UI check in the browser, fix defects, add tests | prompts/step-4.md | [ ] todo |

## Log
(main appends one line per reviewed step: date, step, verdict, branch/commit, caveats)
- 2026-10-30 step 1 accepted: docs-only; adj +20 [-64,+104], learning benefit not established; decision-time/fallback logging missing from bridge (candidate follow-up).
