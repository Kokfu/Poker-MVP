---
name: coach-ui-test
description: Run the Poker Coach web app on a scratch copy of the database and test it in the built-in browser pane, including keyboard entry. Use after changing frontend/ or the coach API, or when asked to try or screenshot the Coach.
---

# Testing the Coach in the browser

## Start it safely

- **Never test against the real data in `backend/data/coach.sqlite`.** Saving and deleting there loses the user's opponent profiles.
- The backend reads `COACH_DB_PATH` (`backend/coach/store.py`). Point it at a copy in `%TEMP%`.
- Ready-made launch configs live in `..\.claude\launch.json` (the Poker folder):
  - **`coach-8012`** is the preferred one. It starts the API on 127.0.0.1:8012 and the web page on port 5176, in one process, with a scratch copy of the database (`..\.claude\coach-dev-8012.cmd`).
  - `backend-8011` and `frontend-8011` are an older two-process pair.
- Ports 8000 and 5173 are often in use by the user's own "Start Poker Coach" or by another chat. Don't stop processes you didn't start.
- The desktop app allows at most 5 dev servers per folder. Prefer combined launchers.
- If you need a new config, copy `coach-dev-8012.cmd`:
  - use `cd /d` into the folder, then `start "name" /b "%CD%\.venv\Scripts\python.exe" ...`;
  - `start /d` hangs.

## Drive it

- **Use `computer` with `action: "key"`.** The pane's `type` action sends no keydown events, so it can't test the keyboard shortcuts.
- **Card entry:** a rank key, then a suit key (`a` `s`, `t` `d`, `1` `0` `d`).
- **Hand keys:**
  - `Enter`: start the hand, or follow the advice;
  - `F` / `C` / `B` / `A`: fold, check or call, bet or raise, all-in;
  - digits then `Enter`: a typed amount;
  - `Z`: undo;
  - `N`: next hand;
  - `P`: switch position during setup.
- **Window key listeners must register in `useLayoutEffect`.** With `useEffect`, fast key bursts lose keys.
  - Card typing listens in the capture phase.
  - Page shortcuts check `event.defaultPrevented`.
- **Check these:**
  - no errors in the console (`read_console_messages`);
  - phone width (`resize_window` with `preset: "mobile"`);
  - one full hand from setup to "Next hand", including a typed board and undo.

## Clean up

- Clear the pane's localStorage keys that start with `coach.`, reset the viewport to `desktop`, and stop servers you started.
- Share a screenshot as proof. Don't ask the user to check by hand.
