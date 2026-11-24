# Phase 4W verification protocol

Frozen on 19 November 2026 before reading any Phase 4W holdout results. Architecture acceptance and strategy promotion have independent verdicts. Both local research flags default to off.

## Arms

| Arm | Execution |
| --- | --- |
| A | Incumbent Coach or Match solver, with the feature flag disabled |
| B | Same live entry points and chooser with the corresponding persistent-range flag enabled |
| C | Phase 4V's offline `DecoupledReplay` adapter on the same Coach decision and profile |

Compare shared chart, betting geometry, stack semantics, profile, public board prefix and seed 917. Use the existing DCFR iteration schedule. B and C use the 0.005 relative weight cutoff and at most 896 columns per seat. Use the normal adaptive lock mode when a profile exists. The gated and sized Match variants keep their respective preflop and final-solve locks. The exact reference appears only after A and B have produced policies.

## Architecture and compatibility

- Replay all six Phase 4V Coach lines, including the profiled collapse from tight-aggressive stream 131 at three completed hands and its no-profile control. Run every open Hero decision through the services and complete each entered hand. Compare all stable disabled responses against the original Phase 4V archive. Repeat the profiled river with cold equity caches.
- For all postflop nominal decisions compare A, B and C. Compare full B and C posterior arrays in process with absolute tolerance 1e-15, exact global column mappings, concrete policy TV below 1e-12, seeded action, and fallback. For both collapse lines repeat each postflop decision at 32, 128, 384 and 896 columns with ranked selection and weighted seeds 17 and 29. B and C must each retain bit-identical posteriors across projections. Require matched B/C mappings and policy at each setting. Measure A-versus-B changes without requiring policy parity.
- At each B observation and board reveal check the actual posterior against independently applying the likelihood or blocker mask to the previous posterior and renormalizing. Check support monotonicity, read-only posterior arrays, no shared solver memory, legal concrete policies and unit sums within 1e-12. Sparse controls must cover true zero likelihood, Hero-only contradictions, board deletion, single-column projection, explicit fallback and no resurrected holdings. The repaired historical river must have 990 Hero-compatible holdings. The archived disabled empty-range fallback and injected zero-support fallback are expected controls.
- Rerun the five archived Match fixtures with both flags, and add gated solver versus tight and sized solver versus tight at seed 42, 15 bb, two hands. Include the enabled single-hand Replay service with solver versus tight, seed 42 and default starting stacks. Validate each history through public decoding, legal actions and accounting for each event, refunds, closed settlement, alternating buttons and stack continuity. For archived fixtures compare disabled outcomes and timelines directly with Phase 4V. Compare traced and untraced histories in both arms. The three Match fixtures without solver bots must agree across flags.
- Reproduce all deterministic records under Python hash seeds 13 and 31. Check both flag states in focused tests and preserve all existing backend tests. Run the research regression, frontend production build, Coach rendering and local Coach, Match and Replay smoke coverage. No schema or engine-rule changes.

## Fresh exact-EV holdout

Development uses deal seed 447101, four boards and training stream 301. The fresh holdout uses deal seed 447102, eight board indices, independent training streams 311, 312 and 313, and all four fixed Phase 4K synthetic styles for 96 decisions. Use the Phase 4Q generator with orientation by stream index and the 0/3/30/100 profile rotation by board and stream. Starting depths are 9/15/30 bb. Historical and development rows do not enter the promotion analysis. A source and case manifest covers the evaluated code, inputs and this protocol and is verified before both fresh runs. Holdout failure or missing data counts against promotion.

Score full-precision legalized mixes against the Phase 4S/4U synthetic reference posterior with exact enumeration of all compatible opponent holdings and the fixed style's fold/call reply law. A versus B uses a common payoff map over the union of both concrete menus. Duplicate concrete actions sum their policy mass. Compute exact net transfers in chips, including unmatched refunds and the odd chip, then divide by the big blind. Cross-check amounts with separate net-transfer accounting. Report regret against the best action in the union. The reference models a single river decision and a fold/call reply. Its result is conditional to the synthetic cases and does not estimate actual heads-up gameplay win rate.

Report mean paired B−A EV and a two-sided crossed bootstrap 95% interval using 10,000 resamples and seed 44003. Resample whole boards and training streams, keeping styles together in each cell. Report per-style means, loss count above 0.01 bb, worst loss, mean/median/max regret, all-in cover mass and seeded closing decisions, and fallback counts. Report a deterministic fallback as the actual one-action policy if one occurs, and separately record failure of the reliability gate.

Promotion requires all inherited gates in both hash-seed runs.

- Mean B−A at least +0.05 bb and a strictly positive lower 95% bound.
- Worst B−A at least −0.50 bb. At most 10% of rows may lose more than 0.01 bb.
- Every style's mean B−A at least −0.03 bb.
- Complete paired rows, legal and normalized policies, exact payoff agreement, no unexpected fallback, and at least one real mix change.
- No positive-exact-EV closing call loses call mass by more than 1e-12, and no new seed-selected fold on a profitable closing call.
- Maximum 15 s per replay, B median at most twice A, and process peak resident memory at most 768 MiB.
- Identical deterministic records across hash seeds and matching frozen files and schedule.

## Measurement and decisions

Use a single BLAS thread and alternate paired order. Warm the same board-equity caches outside the holdout timers and measure per-arm engine replay and advice. Exclude training and scoring from replay timings and include them in process peak memory. For architecture also measure end-to-end Coach service workflows, Match history workflows, C replay, the cold control, updates, likelihood fitting, working-set sizes and fallback counts. Report median, nearest-rank p95 and maximum. Use 15 s for every timed replay and nominal workflow. Report an overage as a failed check. Measure the expanded projection matrix as individual decision replays. Bound each architecture and holdout process at 1,200 s on Windows.

Architecture acceptance requires correct ownership, board and observation updates, the historical recovery, deterministic legal advised actions, no unexpected fallback, preserved disabled behavior, compatible histories and the resource limits. Strategy needs every separate promotion gate. Outcome A keeps the repair behind the flag for targeted safety validation. Outcome B permits planning a separate paired gameplay experiment. Outcome C requires a targeted architecture repair. All outcomes leave both flags disabled by default.
