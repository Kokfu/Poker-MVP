# Status · drills/2026-11-26
Current task: 2 of 5, My leaks.
Completed: timed drills in `07da698` on the worktree forked from `fbd5468`.
Validation: 1,145 backend tests and 3 Node tests passed. Desktop and phone browser checks passed.
Next: finish the full leak-report regression and record its commit.

## Morning summary

Target handoff is 07:00 MYT on 26 November 2026. The branch is `drills/2026-11-26`.

## Task 1 · Timed drills

- Commit `07da698`. The producer staged 24 spots in SQLite across 8 categories. Turns default to 15 seconds, and answers use the saved solver mix and EV. The trainer records score, elapsed time and estimated cost in BB per category.
- Backend `python -m pytest -q -p no:cacheprovider` passed **1,145 tests** with 8 dependency warnings in 1,276.87 seconds. The earlier focused run passed 41 tests before the river-bluff test was added. The final run includes 11 trainer tests.
- Frontend `npx.cmd tsc -b`, `node --test test/*.test.mjs` (3 passed) and `npm.cmd run build` passed. In the browser, I verified F/C/B/A and numeric Enter at 1,240 px, and a 3-second expiry and score persistence at 390 px. The score table initially overflowed on phones. After the fix, document width matched the 375 px content viewport with no console errors.
- The sandboxed npm install stalled, the offline cache was incomplete, and the sandbox denied the dependency junction. The networked `npm.cmd ci` succeeded in this worktree. The browser could reach both dedicated ports after the servers were started outside the AppContainer.
