# Step 6 report: Slumbot decision timing/fallbacks, Coach pot and history result

Branch `autopilot/step-6` (from `main` a005388). Not merged, not pushed.

## Done
**(a) Slumbot bridge instrumentation** (`backend/simulation/slumbot.py`, `SIMULATION.md`)
- `SlumbotHandResult` again carries `decision_seconds` (one entry per client decision; times only the bot's
  `decide`/`decide_decision`, not Slumbot network latency) and `bot_fallbacks` (requested actions that
  `to_incr` replaced with a legal one before sending). Both appear in `result_dict` / the jsonl.
- `summarize_slumbot` adds `bot_fallbacks`, `decision_seconds_p95`, `decision_seconds_max` (check against the 6 s limit).
- Instrumentation only: the action sent to Slumbot is unchanged; no strategy code touched.
- Definition caveat: "fallback" here is bridge legalization of the bot's request (as in `IllegalBot`), my reconstruction;
  the old logging's exact definition is not in `main`, so counts may not be comparable to old runs.
- Tests (fake referee): `IllegalBot` run asserts fallbacks > 0 and summary equals per-hand sum;
  new `test_decision_time_and_fallbacks_are_recorded_per_hand` (12 hands, 10 ms bot: lengths == decisions,
  each >= 9 ms, 0 fallbacks, p95 <= max < 6 s, fields in `result_dict`).

**(b) Coach** (`backend/coach/service.py`, `backend/main.py`, `frontend/src/Coach.tsx`)
- `need_board` responses now include `pot`; the UI shows POT while the board prompt is displayed.
- `GET /api/coach/opponents/{name}/hands` rows gain `result` = `{showdown, hero_net}` (replayed via new
  `hand_result`; `null` if a stored hand no longer replays). History rows show the signed net, e.g. `+100`.
- Tests: `test_coach.py` need_board now expects `pot: 500`; hands list asserts `result == {showdown False, hero_net 100}`.

## Checks run
- Full backend suite: **818 passed** (447 s). Frontend `npm run build`: ok.
- Browser check (dev server on 5173, backend on 8000 with a temp `COACH_DB_PATH`, so the real coach DB was untouched):
  big blind, villain raise to 250, hero call -> "Enter the flop" prompt with POT 500; opponent "Reg" history row shows
  "Villain: Fold · +100". Observed via screenshots in the session; no screenshot files committed.
- Dev servers stopped; temp launch config removed.

## Not done / caveats
- No live Slumbot run, so real decision-time numbers are still unmeasured; the logging is now there for the next run.
- History net uses the stored spot; for showdowns with unknown villain cards `hero_net` is null and no result is shown.
- History is fetched only when a hand starts (existing behaviour, unchanged).

## Recommended next
Review/merge; when the next Slumbot run happens, report p95/max `decision_seconds` against 6 s.
