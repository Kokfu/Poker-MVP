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
| 2 | Reconcile Phase 5 status: ROADMAP says "NOT COMPLETE" (pool gate) while tag `phase-5-complete` exists; fix docs/wording | prompts/step-2.md | [x] done (89ba92c): docs consistent; premise was stale (revised criterion already COMPLETE) |
| 3 | Pre-registered fresh-holdout test of the pool criterion (`solver_adaptive` vs `equity`) | prompts/step-3.md | [x] done (696eb4e): pool comparison inconclusive, original gate not passed |
| 4 | Coach hardening: end-to-end UI check in the browser, fix defects, add tests | prompts/step-4.md | [x] done (4fb4440): 3 defects fixed, 817 tests pass |
| 5 | Settle step 3's weak expert-family result: larger pre-registered run (48 sessions, offset 5,000,000) | prompts/step-5.md | [x] done (ca22b0e): all seven lower bounds > 0; step 3 weakness read as noise |
| 6 | Restore Slumbot decision-time/fallback logging; Coach pot-during-board-prompt and history result | prompts/step-6.md | [x] done (6b59e09): bridge logging restored, Coach pot+history result, 818 tests pass |
| 7 | First Slumbot learning run with restored decision-time/fallback logging | prompts/step-7.md | [x] done (58fd341): p95 4.7 s, 55/2423 decisions >6 s, learning effect not established |
| 8 | Design-only: opponent-model improvement proposal with pre-registered test (wait for owner approval) | prompts/step-8.md | [x] done (d181c86): design only, proposal A awaiting owner approval |
| 9 | Implement proposal A (gated locks) off-by-default + instrumentation + equivalence tests (OWNER APPROVED 2026-11-12) | prompts/step-9.md | [x] done (390ab71): solver_adaptive_gated added, default path byte-identical, 830 tests pass |
| 10 | Run pre-registered T1 (local paired, offset 6M, ~8-16 h) | prompts/step-10.md | [x] done (01e9234): T1a fail, T1b fail (pooled -12.5 [-30.1,+4.8]); pending review/merge |
| 11 | Run pre-registered T2 (live Slumbot decision time) | prompts/step-11.md | [-] SKIPPED by owner (T1 failed; rule gives keep base) |
| 12 | Apply decision rule; adopt or keep base; propose step 13 | prompts/step-12.md | [x] done pending review: verdict KEEP BASE, docs only |
| 13 | Next step proposed by step 12 (see prompt) | prompts/step-13.md | [ ] todo (needs owner OK) |

## Log
(main appends one line per reviewed step: date, step, verdict, branch/commit, caveats)
- 2026-10-30 step 1 accepted: docs-only; adj +20 [-64,+104], learning benefit not established; decision-time/fallback logging missing from bridge (candidate follow-up).
- 2026-10-30 step 2 accepted: docs only; ROADMAP/SIMULATION now label original-vs-revised criterion; tag kept (optional extra tag is owner's call); holdout pool numbers not re-verified.
- 2026-10-31 step 3 accepted: seed offset 4M, D=+46 [-37,+120] inconclusive; weaker vs expert family (~0) than earlier holdouts - noise or regression unresolved; larger 48-session run at offset 5M is an owner decision.
- 2026-10-31 step 4 accepted: preflop label/headline mismatch fixed (display-only), adjusted flag, copy; backend 817 pass, frontend build ok. Open minor: pot hidden during board prompt, history row shows last action only. ALL PLANNED STEPS DONE; main is 6 commits+ ahead of origin, unpushed.
- 2026-11-01 step 5 accepted: offset 5M, 48 sessions, all 7 lower bounds >0, 0 illegal/mismatch; expert family ~35-40 bb/100 below offset-3M (inside its CI), small real decline not excluded; no multiplicity correction.
- 2026-11-01 step 6 accepted: instrumentation only (fallback definition reconstructed, may not match old runs); 818 backend pass, frontend build ok. ALL STEPS 1-6 DONE; unpushed.
- 2026-11-12 step 7 accepted (numbers re-derived from jsonl): decision p95 4.70 s, max 8.44, 55/2423 >6 s; raw -35 [-233,+163]; three learning runs +4/-198/-35 raw, effect not established.
- 2026-11-12 step 8 accepted (design only). AUTOPILOT ENDED by owner; nothing further queued. Proposal A (deviation-gated locking) needs explicit approval before any build.
- 2026-11-12 owner approved proposal A and asked autopilot to continue until stopped; steps 9-12 queued. Pushing still needs owner OK.
- 2026-11-12 step 9 accepted: golden file independently regenerated from fa3b538 (40 hands, cmp identical); full suite 830 pass (re-run by main). Caveats: with pooling on, the Beta interval uses all-streets pooled counts while the compared point is the street-shrunk rate (implementer's reading, now fixed for T1/T2); gate kept 70-90% of locks on Slumbot reads and needs an extra unlocked solve, so T2 latency gates are at risk.
