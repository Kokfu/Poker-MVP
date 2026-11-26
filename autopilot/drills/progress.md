# Status · drills/2026-11-26
Current task: follow-ups 2 and 3 from the morning checks.
Completed: timed drills, My leaks, push workflow, phone shell, and drill recovery.
Validation: 1,150 backend tests and 7 Node tests passed at the recovery checkpoint.
Next: verify all action-line variants and the recent-attempt review, then record the final checks.

## Morning summary

Branch `drills/2026-11-26`, forked from `overnight/2026-11-26` at `fbd5468`. Work resumed after the 07:00 MYT target when the user asked to continue.

Four requested features are committed. The trainer staged 24 spots across 8 categories. My leaks combined all three sources and showed 3 ranked examples. Chromium parsed the standalone manifest, activated the service worker, and opened the app shell with the web server stopped. The GitHub workflow remains unverified on GitHub.

## Task 1 · Timed drills

- Commit `07da698`. The producer staged 24 spots in SQLite across 8 categories. Turns default to 15 seconds, and answers use the saved solver mix and EV. The trainer records score, elapsed time and estimated cost in BB per category.
- Backend `python -m pytest -q -p no:cacheprovider` passed **1,145 tests** with 8 dependency warnings in 1,276.87 seconds. The earlier focused run passed 41 tests before the river-bluff test was added. The final run includes 11 trainer tests.
- Frontend `npx.cmd tsc -b`, `node --test test/*.test.mjs` (3 passed) and `npm.cmd run build` passed. In the browser, I verified F/C/B/A and numeric Enter at 1,240 px, and a 3-second expiry and score persistence at 390 px. The score table initially overflowed on phones. After the fix, document width matched the 375 px content viewport with no console errors.
- The sandboxed npm install stalled, the offline cache was incomplete, and the sandbox denied the dependency junction. The networked `npm.cmd ci` succeeded in this worktree. The browser could reach both dedicated ports after the servers were started outside the AppContainer.

## Task 2 · My leaks

- Commit `3b63602`. Uses saved drill grades and replays completed Coach and Practice Table hands against available prior opponent history. Shows differences and estimated cost by street, position, spot type and source, plus the last 6 sessions. Each ranked drill category has a sample hand and a shortcut that starts that category.
- Focused backend **23 passed** in 7.92 seconds. Full backend **1,148 passed** with 8 dependency warnings in 5,057.16 seconds. Frontend type-check, **4 Node tests**, and build passed.
- Browser QA used 5 graded drill answers, 1 drill timeout, 2 Coach hands, and 1 Practice Table hand in the scratch database. At phone width, three examples fit without horizontal overflow. The River call shortcut started a timed River call spot. No console errors appeared during the checks.

## Task 3 · Automatic tests

- Commit `9151f91`. The workflow runs two jobs on each push, one for the full Python suite and one for `npm ci`, TypeScript, Node tests, and the production build.
- The unchanged backend commands passed **1,148** tests under the existing Python 3.11 venv. All **8 pinned Python dependencies** matched and `pip check` passed. Local `npm.cmd ci`, `npx.cmd tsc -b`, **4 Node tests**, and `npm.cmd run build` passed. Actionlint 1.7.12 passed after moving the temporary database path into the pytest step.
- Windows initially locked a Vite dependency during reinstall. The exact workflow commands passed after stopping the dedicated Vite instance. `npm ci` reported 1 moderate and 3 high advisories in the existing lockfile. GitHub execution remains unverified.

## Task 4 · Phone install

- Commit `7fe4bed`. Standalone manifest, 4 PNG icons, and a versioned offline app shell. API requests use the network.
- TypeScript, **7 Node tests** including 3 PWA tests, and the production build passed. The backend was unchanged from the **1,148-pass** run.
- Chromium parsed the manifest with no errors and confirmed an activated service worker. At 390 px with the dedicated web server stopped, a reload opened the cached app and its offline notice without horizontal overflow. The embedded browser could not report install-promotion eligibility. A physical phone install and a phone-accessible HTTPS address remain unverified.

## Follow-up 1 · Restore interrupted drills

- Commit `f014603`. Reloads and tab switches restore the same spot and its original server deadline. Completed answers reopen with their grade.
- Focused backend **16 passed** in 30.86 seconds. Full backend **1,150 passed** with 8 dependency warnings in 2,038.38 seconds. Frontend type-check, **7 Node tests**, and build passed.
- Browser QA restored the same cards after switching tabs and reloading, with the countdown at 28 seconds after a 30-second start. A reload after answering restored the same feedback.
