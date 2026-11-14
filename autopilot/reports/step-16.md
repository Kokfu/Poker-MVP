# Step 16 report: Coach learning-loop verification

**Verdict: the learning loop works end to end; 29 new tests pass and found no code defect.** Branch `autopilot/step-16` from main; tests and report only, no production code or strategy weights changed. Not merged, not pushed.

## What was added
- `backend/test_coach_learning.py` (29 tests, ~77 s alone; the 3 expensive ones are marked `slow`) and `backend/conftest.py` (registers the `slow` marker; everything still runs by default, `-m "not slow"` deselects).
- Villain histories come from the real engine: an `aggressive` hero vs `tight` / `aggressive` / `equity` villains, 120 hands each, every action recorded and converted to a Coach spot, then logged through `POST /api/coach/hands` into SQLite.

## Results
- (a) **Convergence.** After 10 hands the profile is `unknown` (no label); after 120: tight -> `tight_passive`, aggressive -> `loose_aggressive`, equity -> `loose_passive`. Key stats match each bot (tight VPIP ~0.33, fold-to-raise ~0.46; aggressive VPIP ~0.93, fold-to-raise ~0.07; equity limp ~0.79, raises ~0.005; 150-hand exploratory run, tests assert looser bands).
- (b) **Advice direction.** Cold (no profile) J-high facing a flop bet folds 72%; warmed against the aggressive villain it folds ~0 (call ~1.0) - bluff-catching a wide, bet-heavy player. Button 72o: cold folds 100%, warmed against the never-raising equity limper calls 93%. Different villains give different advice vectors; `exploit=False` reproduces the cold answer exactly.
- (c) **Persistence.** A separate Python process on the same `COACH_DB_PATH` returns an identical opponent list, profile and advice.
- (d) **Bad input.** 21 malformed bodies (bad/duplicate/short cards, bad board size, unknown actor/action, missing/negative/huge amounts, illegal sequences, blinds, stacks, position, villain cards), 3 bad opponent names, incomplete hand logging: all return 422 and store nothing; SQL metacharacters in a name are stored literally. No 500s.
- Browser pass (built-in browser, dev servers on 5173/8000, throwaway DB): Coach tab, typed As Kd, named the opponent, Start hand -> "Raise to 250" 77% with full mix and equity 65%; entered raise, villain fold; "Hand complete +100"; Log hand -> profile card "unknown, 1 hand, needs 20+ hands" with stats. Servers stopped afterwards.

## Observations I did not fix (strategy territory, reported only)
- Warmed advice is extreme: KQo on the button vs the tight and equity profiles becomes pure all-in; mixed cold strategies become near-pure. Plausible for locks but worth an owner look.
- Possible lock oddity: J9 facing a flop bet vs the `tight` villain (flop bet frequency 4%, 23 opportunities) goes fold 72% -> call 98%, and the estimated villain range widens (298 -> 783 combos) when a nitty bettor should narrow it. Not asserted in tests; cause not investigated.
- UI: after one logged hand the profile shows Aggression/VPIP/3-bet at 33% (smoothed prior with 1 observation, labelled "very low"); could mislead a casual reader.
- Expected-direction assertions were chosen after exploring the data (cold vs warm), so they confirm the behaviour rather than pre-register it.

## Checks
Full backend suite: **859 passed, 8 warnings, 740 s** (830 before + 29 new). Frontend `npm run build`: ok.

## Recommended next
Step 17 (release readiness). Optionally have the owner decide whether the all-in/"tight" lock behaviour above merits a separate investigation.
