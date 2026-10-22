---
name: poker-cfr-research
description: Implement and audit CFR-family poker research with correct information sets, counterfactual reach probabilities, average strategies, best responses, and exploitability measurement.
---

# Poker CFR Research Rules

## Research boundary

CFR research remains isolated from production Hold'em until a milestone explicitly integrates it.

Do not automatically register research strategies as Hold'em bots.

## Information sets

An information set may contain only information available to the acting player.

Never include:

- opponent hidden cards;
- future public cards;
- deck order;
- future actions.

States with identical player-visible information must map to the same information set.

## Vanilla CFR mathematics

Regret matching uses:

```text
positive_regret[a] = max(cumulative_regret[a], 0)