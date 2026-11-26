# Status · drills/2026-11-26
Current task: complete.
Completed: timed drills, My leaks, GitHub push checks, phone install, and all three follow-ups.
Validation: 1,174 backend tests, 8 Node tests, TypeScript and production build passed. Desktop and phone browser QA passed.
Open checks: GitHub-hosted run, physical phone installation, and choice of private HTTPS address.

## Morning summary

Branch `drills/2026-11-26`, forked from `overnight/2026-11-26` at `fbd5468`. Work resumed after the 07:00 MYT target when the user asked to continue.

All four features and three follow-ups are committed. Drills staged 24 spots across 8 categories and now generates them from 22 legal simulator action lines. My leaks combines drills, saved Coach hands, and Practice Table hands, with up to 3 ranked examples. The follow-ups add round recovery, both sides of a preflop 3-bet, and review of the 12 most recent attempts per filter.

The final backend run passed 1,174 tests with 8 dependency warnings. All 8 Node tests, TypeScript, and the production build passed. Chromium opened the cached shell at phone width with the web server stopped. The test servers on 8013 and 5177 were stopped after browser QA.

GitHub execution and a physical phone install remain unverified. The first sandboxed npm install and one reinstall under a running Vite process failed. Both were resolved locally. The unchanged lockfile reported four advisories.

### Decisions for you

- Choose the private HTTPS address for friends and the SQLite file that address should use. A server shares the data in its configured SQLite file with people who can open the app. The local preview below stays on this computer. For installation from a phone, open the HTTPS address and use the browser's install or home-screen menu. [PWA installation requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable) · [Safari on iPhone](https://support.apple.com/en-lb/guide/iphone/iphea86e5236/27/ios/27)
- Decide when to verify the first GitHub-hosted run and whether to address the four npm advisories in the existing lockfile before sharing the app.

### Exact commands to try

Run the first block in PowerShell for the API. It uses a fresh temporary copy of the Coach database.

```powershell
$pokerRoot = 'C:\Users\kokfu\OneDrive\Documents\Poker'
$env:COACH_DB_PATH = Join-Path $env:TEMP ('poker-drills-' + [guid]::NewGuid().ToString('N') + '.sqlite')
Copy-Item -LiteralPath "$pokerRoot\poker-analyzer-mvp\backend\data\coach.sqlite" -Destination $env:COACH_DB_PATH -ErrorAction Stop
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
Set-Location "$pokerRoot\poker-analyzer-drills\backend"
& 'C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp\backend\.venv\Scripts\python.exe' -B -m uvicorn main:app --host 127.0.0.1 --port 8013
```

Run the second block in another PowerShell window. Open [the local trainer](http://127.0.0.1:5177/#drills) after Vite starts. The service worker registers on the production build. The regular development launcher serves the app for coding and testing.

```powershell
Set-Location 'C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-drills\frontend'
npm.cmd ci
npm.cmd run build
$env:API_PROXY = 'http://127.0.0.1:8013'
npx.cmd vite preview --host 127.0.0.1 --port 5177 --strictPort
```

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

## Follow-up 2 · Expand drill action lines

- Commit `f25d42e`. The pool now uses 22 legal simulator action lines across 8 categories. The 3-bet category includes making a chart-supported 3-bet and responding to one. Later-street spots now vary position, prior actions, and wager size.
- Focused backend **39 passed** in 11.94 seconds. Full backend at this checkpoint **1,173 passed** with 8 dependency warnings in 945.97 seconds, excluding the next follow-up's draft test. TypeScript, **7 Node tests**, and build passed. Completed a 3-bet round at phone width.

## Follow-up 3 · Review recent attempts

- Commit `7eede34`. Expand Recent attempts in the Trainer to review the latest completed spots with the selected category filter. Each review shows the graded choice, time, cost, cards, action history, best action, and solver mix.
- Focused backend **40 passed** in 10.48 seconds. Final full backend **1,174 passed** with 8 dependency warnings in 1,004.07 seconds. TypeScript, **8 Node tests**, and the production build passed.
- At 390 px, a completed 3-bet round appeared in the category's recent attempts with the saved mix and prior actions. Switching to an unused category showed the empty state. The document fit the 375 px content viewport with no console errors.
