# Step 10 report: T1 (local paired, offset 6M) of `solver_adaptive_gated` vs `solver_adaptive`

**Verdict: T1a FAIL, T1b FAIL.** Per the decision rule in `DESIGN_OPPONENT_MODEL.md` section 4, A is not adopted; `base` stays. Not merged, not pushed. Branch `autopilot/step-10` (from `main`, which already contains step 9, 15ef696).

Setup as pre-registered (`autopilot/prereg-step-10.md`, committed before data): offset 6,000,000 (unused), 48 sessions x 60 hands, 8 opponents, statistics seed 91,002, 2,000 resamples, 2 workers, identical seeds in both arms (asserted in analysis). 16 `duplicate_cli pair` runs, `benchmark-results/phase-6/t1-<strategy>-<opp>.json`; analysis `benchmark-results/phase-6/t1-analysis.json` (`autopilot/analyze-step-10.py`). No parameter or gate changed.

## Results (bb/100, 95% CI)
| Opponent | gated | base | paired diff (gated-base) |
|---|---|---|---|
| random | +527.9 [+441.9,+615.1] | +561.3 | -33.4 [-118.1,+57.4] |
| tight | +55.4 [+29.9,+80.1] | +51.5 | +3.9 [-14.1,+20.8] |
| aggressive | +1034.4 [+932.9,+1127.9] | +1139.7 | -105.4 [-236.7,+18.3] |
| equity | +429.4 [+353.1,+502.6] | +444.6 | -15.2 [-54.1,+21.9] |
| expert | +41.0 [-3.5,+86.4] | +59.4 | -18.4 [-51.9,+13.2] |
| adaptive | +41.0 [-3.4,+86.4] | +59.4 | -18.4 [-51.9,+13.2] |
| range_expert | +43.3 [-7.9,+95.3] | +56.9 | -13.7 [-52.5,+24.1] |
| solver | +63.0 [-0.7,+122.8] | +82.4 | -19.4 [-77.0,+36.8] |

- **T1a: fail.** Lower bounds are <= 0 for expert, adaptive, range_expert and solver (solver by only 0.7). 0 illegal actions, 0 fallbacks, 0 deal mismatches in all 16 runs.
- **T1b: fail.** Pooled paired difference over tight/equity/expert/range_expert/solver = -12.5 [-30.1, +4.8], half-width 17.5 (< 40, so not "inconclusive"). The pooled lower bound -30.1 is below -25, and solver's own paired lower bound -77.0 is below -60. Both T1b clauses are breached.
- Flags: aggressive -105 and random -33 are both within the 150 threshold, so no flag. Not gated.

## Reading
Gated was lower than base on 7 of 8 opponents (point estimates), with the pooled loss about 12-13 bb/100; no individual interval excludes zero, so this is "not shown to be harmless", not "proven harmful". Base itself is lower on this seed set than at 5M (expert-family ~57-59 vs ~75), a third data point for the earlier unresolved expert-family question. The gate removes few locks on strong/balanced reads yet costs strength; this is consistent with step 9's note that the gate keeps most locks while changing weights.

## Process / caveats
- Run took ~2.5-5 h per run (not the pre-registered ~8 h total): ~43 h wall time in all (Nov 12 13:55 to Nov 14 08:40, including downtime after the kills).
- The detached job was killed twice with no error in logs (about 5:14 AM Nov 13, and after 22:40 Nov 13). Each time the script was relaunched (me at 9:31 AM; the step-9 session at 2:50 AM Nov 14) and it skipped finished JSONs; every unfinished run restarted from its beginning. No data was mixed across partial runs.
- Backend suite re-run on this branch: 830 passed (480 s). Frontend not touched.
- One run per arm, no multiplicity correction across eight opponents; `adaptive` and `expert` are not independent.
- Result JSONs force-added; `.log` files left untracked.

## Recommended next
Do not adopt A. T2 (step 11) is now moot under the decision rule (T1 failed, so `base` stays regardless); the orchestrator can skip it or run it only for information. Any follow-up (e.g. proposal B, or a cheaper gated variant) needs a new pre-registration and a fresh offset.
