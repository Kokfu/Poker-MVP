# C3 practice browser verification

The same local app served the production frontend and its API on `127.0.0.1:18012`. Its SQLite path pointed into the temporary directory.

1. Opened **Practice table** and started as Button / SB. The opponent seat was labelled **Solver bot** and the opening pot was 150 chips.
2. Called 50. The bot acted on its own and raised. Calling the 150 displayed the flop. The bot bet 500, with Fold and Call 500 available.
3. Fold completed the hand at −250 chips and displayed one hand observed by the bot. The interface displayed no bot hole cards on the fold.
4. **Next practice hand** opened hand 2 as Big blind. The bot acted first.
5. The browser reported zero console errors. The scratch origin was sent a storage-clearing response and the test tab was closed.

Backend focused tests covered capability scoping, unavailable and stale actions, street-total bounds, zero-sum settlement, learning after settlement, and a separate all-in showdown with legitimate card reveal. This check used loopback on the host. A second device on the LAN was outside this run.
