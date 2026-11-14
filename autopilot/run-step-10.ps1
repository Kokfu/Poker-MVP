Set-Location "C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend"
New-Item -ItemType Directory -Force ..\benchmark-results\phase-6 | Out-Null
foreach ($o in "tight","equity","expert","range_expert","solver","adaptive","aggressive","random") {
  foreach ($s in "solver_adaptive","solver_adaptive_gated") {
    $out = "..\benchmark-results\phase-6\t1-$s-$o.json"
    if (Test-Path $out) { continue }
    .venv\Scripts\python -m simulation.duplicate_cli pair --pairs 48 --session-hands 60 --seed-set holdout --seed-offset 6000000 --workers 2 --equity-iterations 100 --bootstrap-resamples 2000 --statistics-seed 91002 --output $out --strategy $s --opponent $o *> "..\benchmark-results\phase-6\t1-$s-$o.log"
  }
}
"DONE" | Out-File ..\benchmark-results\phase-6\t1.done
