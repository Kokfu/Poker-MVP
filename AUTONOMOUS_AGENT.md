# Autonomous practice agent

The agent plays complete heads-up Hold’em hands on the local simulator, a service that explicitly provides a bot benchmark, or the app's own chip-only practice table. Screen-reading, OCR, auto-clicking and automation of third-party poker sites or clients are excluded. The agent uses practice chips and has no payment or wagering integration.

## Hand loop

1. **Observe.** The referee emits a seat-scoped `DecisionObservation` with the agent's cards, public actions and board, visible chips and engine-authoritative legal actions and targets. Attach the opponent's existing `OpponentModel` snapshot built from earlier settled hands.
2. **Decide.** Use the existing `solver_adaptive` bot. Its mixed-action RNG stays separate from deal and statistics RNG. A decision receives the snapshot only, with no hidden cards, future board, deck or remote credentials.
3. **Act.** Submit the selected action to the referee as a fold, check, call, bet, raise or all-in. Bets and raises use street-total targets. The referee owns legality, next player and street transitions. Count fallbacks so the logs surface any degraded decision path.
4. **Learn.** Allow the engine to settle and validate the hand. Feed its public history to the opponent model and invoke the bot's completed-hand hook for legitimately shown cards. Produce future snapshots from that evidence. A failed or incomplete hand cannot update the model.

## Simulator

The simulator runs without a browser or network. Each evaluation session consists of two seat orientations of the same seeded deals, with independent bots and learning profiles. The button alternates inside each orientation, and stacks reset each hand. Commit a session to a JSONL ledger only after both orientations settle, validate and agree on the deal. Restart reconstructs the schedule from the recorded configuration, skips committed sessions and repeats a partially played session from its first seed.

The CLI reports total hands, bb/100, a session-bootstrap 95% interval, illegal actions, fallbacks and deal mismatches. Treat a short run as an operational check. Strength claims require the separate pre-registered gate. Simulation logs may include reproducible synthetic deal seeds. Practice table responses and logs must keep their actual deal seeds private.

Run from `backend/`. Reuse the same options and add `--resume` after an interruption:

```powershell
./.venv/Scripts/python.exe -m simulation.agent_cli --run demo --opponent tight --sessions 3 --session-hands 4 --seed-offset 27000
./.venv/Scripts/python.exe -m simulation.agent_cli --run demo --opponent tight --sessions 3 --session-hands 4 --seed-offset 27000 --resume
```

The outputs are `benchmark-results/agent/demo.jsonl` and `demo.summary.json`. Pass `--output-dir` to keep a test run elsewhere.

## Slumbot benchmark (optional)

The existing `simulation.slumbot_cli` uses Slumbot's public bot benchmark API. It represents the public opponent actions and cards in the same local engine, whose settlement is checked against the service. Keep this a separately invoked network mode. Use `baseline_adjusted_bb_per_100` when interpreting results and report bridge errors and desynchronization. Keep the simulator and practice table usable offline.

## LAN practice table

A friend opens the app from their browser on the host's trusted LAN and starts a heads-up table with one human seat and one seat visibly labelled **Solver bot**. A table-scoped capability authorizes that human seat. The server owns the deal, action validation, hand sequence, profiles and settlement. It replies with the human's cards and public state. Show the bot's cards only when revealed at a legitimate showdown.

For the first build, keep tables in memory on one server process. A per-table lock and turn revision reject stale and concurrent submissions. Run the bot synchronously until the human has a decision or the hand settles. Rebuild a paused hand from its private seed and accepted actions, replaying past bot actions without scoring them again. Keep the bot instance and public profile through settled hands, alternate button, and reset play-chip stacks before each hand.

Acceptance includes a full browser hand, legal target bounds, stale-action rejection, chip conservation, no hidden responses, and a second hand with the prior public profile available. A server restart ends practice tables. Durable human-table recovery, spectator permissions and larger tables are follow-up work.

Start the app with `Start Poker Coach.cmd`. Each player opens the host address printed by the launcher and chooses **Practice table → Start practice table** to get their own table. Keep the page open to retain the seat. The initial build was verified in a browser against the local app, with the existing LAN launcher as its network entry point.
