# Step 4 report: Coach hardening

Branch `autopilot/step-4` (from clean `main`). No solver strategy changes; not merged, not pushed.

## What I did
Ran backend (temp DB, real `coach.sqlite` untouched) + Vite in the browser pane. Entered by hand: hand 1 = hero button 7c2d, preflop fold; hand 2 = hero big blind AsKd, villain raise 300, call, checked down Ah7c2d / Qs / 3h to showdown, villain cards Kc6d shown. Logged both vs "Alice", opened "Review my hands". Also checked 375px width, console, and illegal input via API.

## Checked OK
- Hand flow, undo-free path, need-board prompts, duplicate/short board cards rejected with clear messages.
- Review numbers verified by hand: -0.5bb + 3bb = +2.5bb over 2 hands = 125 bb/100; VPIP 1/2, PFR 0/2, showdown win 1/1.
- API illegal input: raise below min, wrong actor, actions after hand end, bad card, empty name, logging an unfinished hand all return readable 4xx messages; no 500s.
- Mobile 375px: no horizontal overflow in play or review views.
- Console: only error was the 422 from my deliberate duplicate-card test.

## Defects found and fixed
1. **Preflop strategy rows contradicted the headline.** Facing a 300 raise: headline "Raise to 900" but explanation/bars said "Raise to 750" (chart size, bot rescales to the real raise). Fix: bot adds display-only `concrete_labels` to its explanation (`solver/bot.py`, no strategy/sampling change); `coach.explain.concretize` relabels and merges options that land on the same play; chosen label now equals the returned action. After-fix screenshot: `autopilot/reports/step-4/after-preflop-labels-mobile.jpg`. (No "before" screenshot taken; the before text is quoted above.)
2. **"Adjusted to this opponent's tendencies" shown with no effect** (opponent with 1-2 hands, zero locked nodes). New response field `adjusted` (locked_nodes > 0); UI uses it. `exploiting` unchanged.
3. Copy: "Someone folded." now "You folded."/"Villain folded."; "1 hands"/"1 chances" pluralised (Coach profile, log notice, review).

Tests added in `backend/test_coach_explain.py`: labels match action facing a raise, `concretize` relabel/merge, `adjusted` flag semantics. Frontend has no test runner; those UI edits are verified by build + browser only.

## Results
- Focused `test_coach.py` + `test_coach_explain.py`: 30 passed.
- Frontend `npm run build`: passed.
- Full backend suite (`pytest -q`): 817 passed, 8 warnings (third-party deprecation), 447 s.

## Not fixed (minor, noted)
- POT disappears while the board-entry prompt is shown (`need_board` response carries no state).
- Hand-history row shows only the last action, not the result.
- Smoothed stats (e.g. "Plays hand 67%, very low (1)") look strong on 1 observation; labelled low-confidence already.
- Chart sizes can still be clamped by legality; merged rows handle collisions, not tested beyond the unit case.

## Housekeeping
Dev servers I started (backend on 8000, Vite preview) are stopped; temp DB removed. `.claude/launch.json` lives in the parent folder, untouched.

## Recommended next
Review/merge; optionally add `state` (pot) to `need_board` responses.
