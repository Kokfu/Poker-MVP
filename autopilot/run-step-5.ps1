Set-Location "C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend"
foreach ($o in "random","tight","aggressive","equity","expert","adaptive","range_expert") {
  .venv\Scripts\python -m simulation.duplicate_cli pair --pairs 48 --session-hands 60 --seed-set holdout --seed-offset 5000000 --workers 2 --output "..\benchmark-results\phase-5\final-h2h-offset5m-$o.json" --strategy solver_adaptive --opponent $o *> "..\benchmark-results\phase-5\offset5m-$o.log"
}
"DONE" | Out-File ..\benchmark-results\phase-5\offset5m.done
