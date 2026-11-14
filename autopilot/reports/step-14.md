# Step 14 report: gate T0 for proposal B (offline replay)

**T0 PASSES mechanically.** Lower bound of the improvement is +0.113 nats > 0. B is NOT built; orchestrator decides. Branch `autopilot/step-14` from main 3e2b9d6; not merged/pushed. Docs/scripts only, no backend code touched, so no test suite was run.

## What was done
- `autopilot/t0-step-14.py` (stdlib + `analyze-step-13.py` helpers) committed BEFORE its output `benchmark-results/step-14-t0.txt`. Prereg and gates unchanged.
- Leave-one-log-out over the six step-13 Slumbot logs: train on five, predict Slumbot's fold/call/raise on postflop client bets/raises in the sixth; metric log-loss; bootstrap over held-out hands (2,000 resamples, seed 91,002).

## Result
- 3,514 held-out cases in 2,471 hands (per log: 785/859/812/756/77/225).
- Log-loss (i) size-blind street model 0.9271; (ii) bucketed shrunk (m=20) 0.8013.
- Improvement (i)-(ii): **+0.1257 nats/case, 95% bootstrap [+0.1130, +0.1383]** -> T0 PASS.

## Implementation choices the prereg left open (fixed in the script before running, not tuned)
- (i) = Laplace (k+1)/(n+3) per street. (ii) shrinks toward (i) of the same street, because no solver frequency p_eq(b) exists offline; so T0 tests "size matters beyond street", not the solver-prior version.
- Training cell with n<10 falls back to (i) (prereg: "left unlocked").
- Bootstrap resamples hands pooled across held-out logs (not within-log); intervals ignore that the logs come from similar bot runs against one opponent.

## Caveats
- Large and expected: bet size largely determines folding by pot odds, so a size-aware predictor beating a size-blind one is almost guaranteed (step 13 chi-square p<0.0001). T0 is a weak gate; passing does NOT show a size-conditioned lock would beat base play, and says nothing about the T1 no-harm/benefit gates, which remain power-limited (~22 bb/100 detectable pooled; step 10 showed a mild change cost ~12 bb/100).
- Single opponent (Slumbot), logs from same bot family, sizing mix depends on our bot; expert/solver logs have few cases (77/225).
- Did not test deviation from equilibrium (the real question for exploitation); a size-blind equilibrium baseline would be needed.

## Recommended next
Do not build B (~50 h, can only detect >=22 bb/100). T0 pass is a necessary, not sufficient, condition; proceed to step 15 unless the owner wants B for its own sake.
