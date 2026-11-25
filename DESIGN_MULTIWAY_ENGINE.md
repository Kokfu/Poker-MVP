# Multiway practice and agent engine

Add a separate no-limit Hold’em engine for tables with three to six seats. Its first clients would be a local practice table with one human and two to five play-chip bots, and an offline agent runner with the same rules. Two-seat practice, existing evaluations, Coach replay, and solver bots continue through their existing entry points. The current `HandEngine` is the reference for shared invariants and stays outside the implementation changes.

## Engine and state

Keep ordered seat IDs around the button. The initial table has fixed seats, positive integer stacks, small and big blinds, and no antes, straddles, or rake. The button advances clockwise between hands. In a multiway hand, the next two seats post the blinds, preflop begins left of the big blind, and postflop begins at the first eligible seat left of the button. A hand that loses all but two contenders keeps its original positions. A table with two seated players at the start of a hand uses the existing heads-up entry point.

Each seat has its starting stack, current stack, street commitment, total contribution, and a status of active, folded, or all-in. The engine holds private cards and the deck. A public snapshot holds the board, button, blinds, pending actors, current wager, last full raise increment, and aggregate contributions. History records an ordered event and a before/after accounting snapshot on each state transition.

Reuse `Action` and the existing card evaluator. Define a separate multiway state and seat-scoped observation. The observation contains the actor's own cards, the common board, seat statuses, stacks and commitments, the price of a call, and legal action bounds. Keep candidate range generation optional in the bot layer. It uses only public cards and earlier public actions.

## Betting

- Accept actions from the current actor only. The API can reject a stale revision before handing an action to the engine. Bet and raise amounts are total chips committed on the current street.
- Set the preflop wager and minimum full increment to the nominal big blind. The amount actually posted remains the short stack's contribution if the big blind is all-in. Reset the street wager on each new street and require at least a big blind for a normal opening bet.
- Keep the wager level at which each seat last acted. A seat that has yet to act may raise. A seat that already acted may raise again once the current wager is at least one full increment above the level it last faced. A short all-in increases the wager if applicable and makes active seats below it respond. It leaves the full raise increment unchanged. Put the cumulative short-raise examples in tests before integrating the engine. [Poker TDA 2026 rules 45 and 49](https://www.pokertda.com/view-poker-tda-rules/)
- For a 100-chip opening wager followed by short all-ins to 150 and 200, the opener is facing another 100 and may raise to at least 300. Change the second short all-in to 190 and the opener can still call or fold but cannot raise. A later seat that already called 150 uses 150 as its own reopening reference.
- Advertise a normal raise only when the player's stack supports the full minimum. A short all-in can call even when the raising right is closed. An increasing all-in must satisfy the same reopening rule. When only one player with chips remains, let them resolve an outstanding call or fold and skip further uncontestable betting.
- Close a street when all active seats have acted and matched the wager, folded, or gone all-in. If only one contender remains, settle by fold. If no further contested decision exists, run out the board and settle once.

## Pot layers and settlement

Calculate ascending contribution levels from every seat, including folded seats. Each layer contains the level's increment multiplied by the number of contributors who reached it. Each seat that reached the layer and is still in the hand can win it. Refund an unmatched layer with a single contributor. Award each contested layer to its eligible best hand or split it among tied winners. Award odd chips in clockwise order starting left of the button among the tied winners. Apply these steps independently to each layer. [Poker TDA 2026 rules 21 and 23](https://www.pokertda.com/view-poker-tda-rules/)

For contributions of 500, 300, 100 and 300 chips where the fourth seat folded, the main pot is 400 and eligible to the first three seats. The side pot is 600 and eligible to the first two. Return the unmatched 200 to the first seat. Evaluate each shown hand once and reuse the score for all eligible layers.

Check conservation at every transition using the sum of stacks plus committed chips. Settlement returns every chip exactly once, clears commitments and pending actors, and gives a zero-sum vector of per-seat net results. Keep histories with pot-layer awards and per-seat outcomes under a separate versioned multiway schema. Do not reinterpret an existing heads-up history as a multiway file.

## Practice and offline agent integration

The practice table can use its current seat capability, turn revision, and timer with a separate multiway table adapter. Give each bot the observation for its own seat. Return the human's cards and public state to their browser. Reveal opponent cards only from legitimate showdown events under a documented reveal rule. Use the same action validator on submitted, bot, and expired-turn actions. Save multiway practice histories separately until Coach can review them against per-seat ranges and eligible pots. The current manual heads-up Coach store expects one opponent and one settlement amount.

Start the offline agent with bots written against the multiway observation. The current heads-up solver's two-player zero-sum tree cannot supply multiplayer policies. Begin with deterministic legal-action, tight, and equity baselines. Give opponent models separate seat identities and update them only after a hand settles. The new multiway advice range updater can supply a feature, with pot eligibility accounted for before a strategy interprets equity as a call value.

For evaluation, fix complete private and public deal schedules and rotate the candidate across seats against a fixed roster. Keep deck, policy, and statistics random streams independent. Separate independent duplicate evaluations from experiments that learn across sessions. Aggregate payoffs by seat rotation and report legality, fallbacks, conservation, and deal integrity before interpreting performance. Keep results with a separate multiway report type.

## Implementation and acceptance order

1. Build the transition model and verify blind order, skipped seats, turn progression, and legal total-target bounds with deterministic scripted hands for each table size.
2. Cover one and several short all-ins, exact/short calls, reopening at different last-action levels, and a short blind. Generate legal traces across short stacks. Require that every advertised action is executable and every transition conserves chips.
3. Verify side-pot eligibility for folded and all-in seats, refunds, ties and odd chips, one-survivor folds, and automatic runout. Compare against a separate small reference settlement function and require the same trace under repeated seeds.
4. Add an observation privacy test for every seat and every street. Confirm that moving backward in history cannot retain cards first shown later. Register the new practice adapter and verify two concurrent tables with independent deadlines.
5. Add offline seat-rotation evaluation and replayable diagnostic reports. Run the existing backend and browser regressions with the accepted heads-up fixtures before promoting either adapter.
