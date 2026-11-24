# Phase 4J experiment protocol

Frozen before running the comparative EV matrix.

## Hypotheses and arms

- Existing adaptation can help where an aggressive profile predicts the river line and can harm where the same profile overstates bluffing or fold equity. Range accuracy and decision value can move in different directions.
- Off and On use the current Coach path, normal budgets and seed 917. The candidate blends the two concrete action policies using adaptive share `n / (n + k)`, where `n` is completed profile hands. This applies familiar pseudo-count shrinkage to the policy as a whole, including changes mediated by earlier ranges. It treats hands as a proxy for evidence and makes no claim of a calibrated posterior.
- Fit one `k` from 10, 30 and 100 pseudo-hands by maximizing calibration mean EV across the frozen cases, profiles and references. Resolve ties in favor of larger `k`. Report the selected candidate on the holdout without further tuning.

## Cases and fixed reference opponents

Each real Coach spot has 50/100 blinds, 1,500-chip equal opening stacks, a 250 raise/call, and check/check on the flop and turn. Villain acts first on the river and either checks or bets the named amount. Hero acts on the button. Each policy is scored at the identical decision, independent of its own inferred posterior and opponent responses. The reference's prior entering the river is uniform. It conditions on the observed river action using the probabilities below and removes Hero and board blockers. Earlier public actions are held fixed by construction and carry no additional private-card likelihood in this conditional reference.

| Split | Hero | Board | Villain river action |
| --- | --- | --- | --- |
| Calibration | Jc 9d | Qh 7s 2d 4c 8h | Bet 250 |
| Calibration | Ah Qd | Qs 7h 2d 4c 8h | Check |
| Holdout | 8c 8d | Kh 8s 2d 4c Jh | Bet 500 |
| Holdout | 7c 6c | Kh 7s 2d 4c Jh | Bet 500 |
| Holdout | Ac 5c | Qh 7s 2d 4c 8h | Check |
| Holdout | Qc Tc | Qh 7s 2d 4c 8h | Check |

Classify a villain's best five cards as high card, one pair, or two pair or better. The reference uses only public information and its own cards. It has one offered opening bet size per spot. Following a Hero wager it folds or calls, including a short all-in call, with zero probability of reraising.

| Reference | Open bet probability (high card / pair / two pair+) | Call probability (same classes) when extra call ≤ half the pot before Villain calls | Call probability above threshold |
| --- | --- | --- | --- |
| Loose aggressive | .70 / .75 / .95 | .30 / .75 / 1.00 | .15 / .55 / .95 |
| Selective | .05 / .25 / .90 | .05 / .45 / .98 | .01 / .25 / .90 |

For clarity the sizing test uses the pot **including Hero's wager** (excluding Villain's hypothetical call) and caps the wager at the amount Villain can match. Use the five nested Aggressive history prefixes (3, 12, 30, 100, 500) from the same seeded local generator as Phase 4I, with each arm sharing identical evidence. Those histories are a controlled evidence stream, independent of the synthetic reference hands. They do not establish calibration to either reference. The original 12-hand flop spot is a separate reproduction, outside exact river EV coverage. Isolate its preflop and postflop locks with the Phase 4I instrumentation.

## Metrics and gates

Primary metric is uniform mean policy-weighted net bb from the current decision, with exact enumeration over compatible holdings. Report by split, reference and profile size. Include exact EV of each action in the union of the Coach menus, action TV, regret to the best action in that union, and frequency and sum of losses where an adjusted policy trails Off by more than 1e-6 bb. The union optimum is specific to the supported action menu. Diagnose range TV and absolute showdown-equity error against the same reference posterior for each arm. Attribute range estimates to the two component policies.

Positive repeatable benefit requires a positive holdout mean against each reference and in both sparse (≤30) and mature (≥100) groups pooled over references. For recommending the candidate over On also require strictly lower aggregate holdout harm and at least as much holdout mean EV as On. Report finite-panel counts and exact conditional EVs without population significance or win-rate claims. Run the full matrix twice, require matching strategic output, legal normalized probabilities, no fallback in the panel, and successful independent hand-count and chip-settlement controls. Fallback isolation requires identical disabled recommendations with and without a profile and the existing enabled Expert response in the forced error spot.

Cap each matrix replay at 420 seconds and the full backend run at 2,400 seconds. Use one BLAS thread. The development study runs offline. A separate paired gameplay study is conditional on clearing the EV gate.
