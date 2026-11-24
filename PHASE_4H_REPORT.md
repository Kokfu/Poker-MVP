# Phase 4H — Unopened small-blind opponent-lock correction

**Phase 4H complete.** The 17 November 2026 verification passed the coefficient, policy-equivalence, legality, normalization and fallback criteria.

## Root cause and mathematical validation

The heads-up preflop chart starts with the button/SB acting, no voluntary raises, and commitments of 50 and 100 chips. The 50-chip deficit is the cost to limp. Since the big blind posts automatically, the SB is choosing how to open the pot. Before the edit, `node_lock` handled this node as opening (raise, limp or fold), while `tree_locks` detected a wager from the commitment deficit and assigned the response coefficient. The pre-edit diagnosis and a copy of the control source are preserved in the [evidence directory](benchmark-results/phase-4h-2026-11-17/).

For each private hand, the lock fitter uses `s × fitted(hand) + (1 − s) × target`. The fitted policy retains hand-dependent action selection and the target is the same distribution for every hand. A separate confidence weight blends this result with the solver policy. Both mixtures preserve normalization for coefficients in [0, 1]. The established response rule uses the mean of aggression and calling correlation. The opening rule uses aggression alone, as it already did at the BB decision after an SB limp. Rounding to two decimals remains part of the lock and cache contract.

With aggression/calling inputs of 0.89/0.19, the former mean is 0.54 and the opening coefficient is 0.89. The flat share inside the lock falls from 46% to 11%. With inputs of 0.20/0.80, the mean is 0.50 and the opening coefficient is 0.20. The flat share rises from 50% to 80%. The expected coefficients were specified independently of the implementation. The maximum error on the affected rows was zero against the 1e-12 tolerance.

| Depth (bb) | 0.89 / 0.19 before | After | 0.20 / 0.80 before | After |
| ---: | ---: | ---: | ---: | ---: |
| 15 | 0.54 | 0.89 | 0.50 | 0.20 |
| 30 | 0.54 | 0.89 | 0.50 | 0.20 |
| 60 | 0.54 | 0.89 | 0.50 | 0.20 |
| 100 | 0.54 | 0.89 | 0.50 | 0.20 |
| 200 | 0.54 | 0.89 | 0.50 | 0.20 |

The shared classification is called by the adaptive bots and Coach through preflop re-solving. The gated variant can independently drop the lock. The sized variant also reaches this preflop path, while its size-conditioned replacements operate postflop. The base solver without profile locks loads the stored chart. Postflop uses the same lock builder and continues to classify a player with a commitment deficit as facing a wager. Chart data, action groups, confidence weights, sizing, solver budgets, response formats and fallback handling were preserved. A changed root lock can change the coupled preflop re-solve and the ranges passed to downstream streets.

## Files changed

- [backend/solver/exploit.py](backend/solver/exploit.py) shares the existing preflop opening classification between group selection and coefficient selection.
- [backend/test_solver_phase_4h.py](backend/test_solver_phase_4h.py) exercises all five shipped depths, both seat orientations, independent numeric expectations, exact chart access, cold locks, normalized advice and deterministic recommendations.
- [backend/test_data/equiv_learning_phase_4h.json](backend/test_data/equiv_learning_phase_4h.json) records the corrected deterministic 40-hand transcript. The shared fixture in `backend/conftest.py`, the exact checks in `backend/test_solver_gated.py` and `backend/test_solver_sized.py`, and the description in `backend/equiv_learning.py` identify the versioned reference. The earlier transcript files are retained.
- [PHASE_4H_REPORT.md](PHASE_4H_REPORT.md) records results and reproduction steps. Raw JSON and local comparison scripts are in the new ignored evidence directory. The prior audit, historical results and pre-existing working-tree edits were preserved.

## Regression tests and control matrix

The 40-row matrix crossed five depths, two coefficient pairs, both opponent orientations and high versus very-low confidence. Only the ten warm SB-root tuples changed, and only their coefficient fields changed. This covers the BB after a limp and responses to voluntary raises and shoves throughout each chart. Across the 30 unaffected rows, all 456 policy-array comparisons matched the control exactly, including a rerun with the locked-policy cache cleared between arms. All resulting decision columns were finite, nonnegative and normalized to 1e-6. All 12 postflop lock maps matched across flop, turn, river, both orientations and both coefficient pairs.

Conditioning on the SB's ordinary open raise before blocking known cards illustrates the direction of the range change. Effective combos are `(sum weights)^2 / sum(weights^2)`. The magnitude varies with depth and the re-solved policy.

| Depth (bb) | Aggression 0.89 before → after | Aggression 0.20 before → after |
| ---: | ---: | ---: |
| 15 | 791.2 → 525.7 | 828.4 → 1,008.5 |
| 30 | 726.5 → 428.9 | 839.0 → 1,144.1 |
| 60 | 1,273.9 → 1,121.5 | 1,277.5 → 1,302.9 |
| 100 | 1,294.0 → 1,132.7 | 1,290.3 → 1,313.6 |
| 200 | 1,299.8 → 1,209.1 | 1,300.4 → 1,317.6 |

- Phase 4H pytest file passed **20 tests** in 9.53 s, with seven eval7 dependency deprecation warnings. The first run revealed that the synthetic Coach profile lacked required summary fields. The fixture now supplies an actual snapshot with specified estimates.
- The Coach HTTP route smoke passed in 4.30 s, covering advice, validation and hand logging.
- `pip check` found no broken requirements. `npm.cmd run build` passed, and `node --test test/coach-strategy.test.mjs` passed its Coach solver/fallback render test.
- The final single-process Windows backend regression passed **904 tests** in 1,109.65 s, including the Phase 4G research controls and the two exact learning checks. Its eight warnings came from Starlette and eval7 dependency deprecations. The initial full run passed 902 tests and surfaced the two expected comparisons to the earlier transcript.
- `git diff --check` passed with the pre-existing LF/CRLF advisory. The work remains local on `main` at `3e89367`.

The offline 40-hand learning transcript changed when the corrected lock was exercised. Replaying with the captured control reproduced the stabilization transcript exactly. The first 55 full-precision probability vectors also match the treatment. The first difference occurs at a preflop exploit decision. The control recorded 100 decisions and the treatment recorded 105, with eight changed hand results and zero solver fallbacks in either transcript. The initial solver and Coach regression passed 128 tests and failed the two comparisons to the stabilization transcript. Both tests passed in an independent 117.32 s rerun using the new fixture and the same exact probability, action, outcome and full-record comparisons.

## Paired development benchmark

The pre-edit control and treatment used the same production duplicate evaluation against TightBot at 100 bb with 50/100 blinds, 100 equity iterations, and development seeds 1,124,600–1,124,611. Each arm played each deal both ways, for 24 hands per arm. The same opponent profile and showdown correlations came from the 150 completed TightBot hands in Step 17a. This fixed history activates the lock in a small panel and holds evidence constant across arms. It is a warmed one-hand test with no learning during the panel. Both arms used one thread for BLAS and the same solver budgets, bot seeds and deal schedule. The harness swapped in only the captured pre-edit `tree_locks` for the control. All histories and zero-sum results passed existing checks, and all duplicate deals matched both hole pairs and the shared revealed-board prefix.

| Measure | Control | Treatment |
| --- | ---: | ---: |
| Net bb/100 vs TightBot | +54.17 | +54.17 |
| Paired 95% interval vs TightBot | [+16.67, +87.50] | [+16.67, +87.50] |
| Uses of affected root lock | 5 at 0.54 | 5 at 0.89 |
| Invalid actions | 0 | 0 |
| Engine substitutions | 0 | 0 |
| Solver-to-Expert fallbacks | 0 | 0 |
| Duplicate deal mismatches | 0 | 0 |
| Wall time (s) | 22.01 | 20.25 |
| CPU time (s) | 21.03 | 18.47 |
| Peak Windows working set (MiB) | 172.77 | 173.46 |

The paired treatment-minus-control estimate was **0.00 bb/100** with a 95% percentile bootstrap interval of **[0.00, 0.00]**, using 2,000 resamples of matched deal-pair differences and statistics seed 91,002. All 24 seat-level outcomes matched. The interval is degenerate because every observed difference was zero. The sample included five uses of the affected lock, so playing-strength impact is **inconclusive**.

All observed solver action counts matched. Preflop counts were 7 all-ins, 7 calls and 1 fold (46.7%, 46.7% and 6.7%). Postflop counts were 5 all-ins, 2 checks, 1 call and 1 fold (55.6%, 22.2%, 11.1% and 11.1%). The observed wall and CPU deltas were −1.76 s and −2.56 s, and peak memory was +0.70 MiB using unrounded values. These single-process measurements span the evaluation and bootstrap after fixture preparation. The resource effect remains inconclusive given the single trial and concurrent regression activity.

## Coach behavior

Replayed the fixed Step 17a Jc 9d spot as Hero in the BB on Qh 7s 2d, facing 200 into 500 after calling the SB open. The Coach rebuilt the public profile from a temporary SQLite store. Showdown correlations were approximately 0.893 for aggression and 0.195 for calling. Seed 917 selected the following legal actions. Every response used `postflop_solve`, had normalized rounded probabilities and avoided fallback.

| Profile setting | Recommendation | Fold | Call | Raise to 1,100 | Villain effective combos | Hero equity |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Exploitation off, either arm | Fold | 71.51% | 27.14% | 1.36% | 298.5 | 20.63% |
| Exploitation on, control | Call | 0.23% | 99.77% | 0.00% | 783.4 | 30.84% |
| Exploitation on, treatment | Call | 0.82% | 99.18% | 0.00% | 318.4 | 27.46% |

All-in was 0.00% in each row. Exploit-on advice took 3.36 s in the control and 3.01 s in treatment. The range narrowed substantially in this spot and the call remained nearly pure. The 22.22% pot-odds threshold follows from `200 / (500 + 200 + 200)`; this comparison is descriptive because future betting and the solver's action values also matter.

## Reproduction on Windows

Run from `backend` in the project's Python environment. HTTP tests need working local sockets. Use the external subprocess timeout and disable the periodic pytest traceback dump, which the audit associated with an access violation. The commands run the normal assertions. To regenerate evidence, copy the scripts and control source into a new sibling directory and update `$phase`.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$py = '.\.venv\Scripts\python.exe'
$phase = '../benchmark-results/phase-4h-2026-11-17'
& $py "$phase/run_bounded.py" 180 $py -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0 test_solver_phase_4h.py
& $py "$phase/run_bounded.py" 2400 $py -m pytest -q -p no:cacheprovider -o faulthandler_timeout=0
& $py "$phase/run_bounded.py" 240 $py "$phase/matrix.py"
foreach ($mode in 'coach', 'panel') {
    foreach ($arm in 'control', 'treatment') {
        & $py "$phase/run_bounded.py" 600 $py "$phase/compare.py" $arm $mode
        if ($LASTEXITCODE -ne 0) { throw "$mode $arm failed" }
    }
}
& $py "$phase/summarize.py"
```

## Remaining limitations and Phase 4I

The comparison covers one frozen opponent profile, one benchmark depth and a small development panel. Live pool returns, adaptation over time and full-game exploitability remain unmeasured. Postflop range inference uses limited action sizes and single-street solves, and the corrected opening coefficient can move hand-strength mixing in either direction.

For Phase 4I, use separate development seeds to estimate the variance of paired learning-session differences and size a holdout for a predeclared minimum bb/100 effect. Freeze the opponent pool, seeds, budgets and success thresholds before examining holdout results. Track opening-lock exposure, illegal actions, engine substitutions and solver-to-Expert fallbacks along with the paired effect.
