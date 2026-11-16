# Release notes (2026-11-14, end of autopilot steps 1-17)

## What this is
Poker Analyzer MVP is a local, educational, offline-first heads-up No-Limit Hold'em toolkit: an Analyzer, a deterministic simulator and persistent matches, a replay viewer, a Phase 5 solver bot (`solver`: preflop charts plus a real-time range solve each postflop street) and an opponent-adapting variant (`solver_adaptive`), a duplicate-deal evaluation harness, an opt-in Slumbot benchmark bridge, and a **Coach** tab where you type your own hand, get a solver recommendation with its action mix and equity, and log finished hands so the Coach learns each opponent's type. It is for study and research. It does not play for you and does not touch any poker site.

## What is verified (numbers are bb/100, 95% intervals)
- **Phase 5 is COMPLETE under the owner's revised criterion** (set prospectively on 2026-09-29): `solver_adaptive` beats each of the seven older bots with every interval lower bound above zero, 0 illegal actions, 0 fallbacks, 0 deal mismatches. Latest independent run (step 5; holdout seed offset 5,000,000, 48 sessions x 60 hands per opponent, 40,320 hands): random +595 [+500, +686], tight +50 [+26, +74], aggressive +1,061 [+978, +1,143], equity +418 [+337, +495], expert +74 [+25, +125], adaptive +75 [+26, +126], range_expert +79 [+28, +132]. `adaptive` is nearly identical to `expert` (not independent evidence). A step 3 run at offset 4M had the expert family near 0 and the later run did not reproduce that; read as seed noise, a small real decline is not excluded. One run per seed set, no multiplicity correction.
- **Opponent-model proposal A** (`solver_adaptive_gated`, off by default) was built and pre-registered tested at offset 6,000,000 and **failed**: pooled paired difference vs `solver_adaptive` -12.5 [-30.1, +4.8]; the default stays unchanged.
- **Coach loop** (step 16): scripted end-to-end tests show profiles converge from `unknown` (under 20 hands) to the right type for tight, aggressive and equity villains after 120 hands, advice changes in the expected direction once warmed, profiles and advice survive a process restart, and 21 kinds of malformed input are rejected with 422 and store nothing.
- **Runnability** (step 15): a fresh `git clone` installs, builds the frontend, serves Coach advice and builds both Docker images following the docs; backend suite 830 passed there.
- **Final tree**: backend suite and frontend build results are in `autopilot/reports/step-17.md`.

## What is NOT claimed
- Not "strong poker" in general. The original Phase 5 criterion (pool score above `equity`) was **not** met on three holdouts; `solver_adaptive` was not shown to beat `equity` in pool score.
- Not shown to beat Slumbot or to profit against it: three 1,000-hand live learning runs gave raw +4, -198 [-441, +45] and -35 [-233, +163]; two later runs' baseline-adjusted results were +20 [-64, +104] and +35 [-49, +119]. All intervals include zero. A 1,000-hand run cannot resolve effects below roughly 200 bb/100.
- Learning (opponent adaptation) benefit against Slumbot is **not established**. The win-rate effect of learning is unmeasured at available sample sizes.
- Local bots are heuristic archetypes, not balanced opponents; results versus them say little about humans.
- Proposal B (bet-size-conditioned reads) is **not built**: it passed only the weak offline gate T0 (size-aware prediction beats size-blind by +0.126 nats/case, [+0.113, +0.138]), which is close to guaranteed by pot odds; a build would cost about 50 h and could detect only gains of 22 bb/100 or more.
- Real-time decision limits against Slumbot: p95 4.7 s, 55 of 2,423 decisions above 6 s in the one instrumented run.

## Known limitations
- Heads-up only; no multiway, tournaments, rake or ICM. Coach seats and stacks are entered by hand; only completed hands can be logged.
- Warmed (opponent-adjusted) advice can be near-pure and extreme (for example all-in with KQo); one possible lock oddity against a very tight villain is recorded in `autopilot/reports/step-16.md` and not investigated.
- Profile cards show smoothed percentages after a single hand (labelled "very low" confidence).
- The full backend suite takes about 12 minutes on the development machine.
- `benchmark-results/` is git-ignored; only selected results were force-added (45 files: final head-to-heads, step 5 and 10 results, three Slumbot logs). Other logs live only on the original machine.
- Older docs contain absolute paths from the original machine.

## How to run
See README ("Local development") and DEVELOPMENT.md ("Project status and how to resume autopilot"). In short: `py -3.11 -m venv backend\.venv`, `pip install -r requirements.txt`, `pytest -q -p no:cacheprovider`, `npm ci && npm run build` in `frontend`, then uvicorn on 8000 and Vite on 5173 (or `docker compose up --build`).


## Update (2026-11-16, autopilot steps 18-20): proposal B tested and not adopted
- **Opponent-model proposal B** (`solver_adaptive_sized`, bet-size-conditioned reads) was built (step 18) and pre-registered tested at offset 7,000,000 (step 19) and **failed all three gates**: pooled paired difference vs a fresh `solver_adaptive` -92.4 [-123.4, -62.1] bb/100; large losses versus aggressive (-554), equity (-279) and solver (-123). Verdict KEEP BASE; `solver_adaptive` is unchanged.
- **Both A and B failed their pre-registered no-harm tests.** `solver_adaptive_gated` (A) and `solver_adaptive_sized` (B) are available as bot types but are **off by default** and not recommended; the Coach does not use them.
- This supersedes the line above saying B is "not built": it was built (873 backend tests passed at step 18/19) and tested. The T0 gate passed but did not predict strength.
