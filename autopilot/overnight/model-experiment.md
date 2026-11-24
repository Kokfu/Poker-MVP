# A2 off-tree sizing experiment

`solver_adaptive_interpolated` is available as an explicit `duplicate_cli pair` arm. For an opponent's normal postflop bet or raise strictly between two sizes of the same kind, it blends the two actions' per-combo likelihoods in log-size space. It follows the incumbent's nearest tree branch for traversal and uses the real pot and commitments for its off-tree re-solve. Exact sizes, unbracketed sizes, all-ins and the default bot retain the original likelihood rule.

Development screen used identical seed schedules for each arm, offset 25,000, statistics seed 91,002, 2,000 resamples and one worker per run. The outputs contain seat-swapped session results and integrity counts. Reproduce from `backend/`:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
foreach ($opponent in 'tight','equity','expert','aggressive') {
    $pairs = if ($opponent -eq 'expert') { 2 } else { 3 }
    $hands = if ($opponent -eq 'expert') { 6 } else { 8 }
    foreach ($strategy in 'solver_adaptive','solver_adaptive_interpolated') {
        ./.venv/Scripts/python.exe -m simulation.duplicate_cli pair --strategy $strategy --opponent $opponent --pairs $pairs --session-hands $hands --seed-set development --seed-offset 25000 --workers 1
    }
}
```

| Opponent | Hands per arm | Baseline bb/100 [95% interval] | Candidate bb/100 [95% interval] | Paired difference [95% interval] |
| --- | ---: | ---: | ---: | ---: |
| Tight | 48 | -5.7 [-64.1, 31.3] | -5.7 [-64.1, 31.3] | 0.0 [0.0, 0.0] |
| Equity | 48 | 199.0 [-109.4, 731.3] | 199.0 [-109.4, 731.3] | 0.0 [0.0, 0.0] |
| Expert | 24 | 402.6 [68.0, 737.2] | 378.4 [68.0, 688.8] | -24.2 [-48.4, 0.0] |
| Aggressive | 48 | 914.6 [171.9, 1318.8] | 914.6 [171.9, 1318.8] | 0.0 [0.0, 0.0] |

Both arms had zero illegal actions, action fallbacks and deal mismatches across 336 hands. Paired intervals resample the session-wise candidate-minus-baseline net. Identical outputs on a few sessions produce a degenerate interval and offer little evidence about how often the experiment activates against those opponents. The only changed result here was negative. The experiment remains opt-in, and this screen does not warrant a holdout run.
