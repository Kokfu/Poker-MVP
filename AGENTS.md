# Poker Analyzer Project Instructions

## Repository

Windows path:

C:\Users\kokfu\OneDrive\Documents\Poker\poker-analyzer-mvp

## Source of truth

Before making changes, inspect:

- ARCHITECTURE.md
- DEVELOPMENT.md
- ROADMAP.md
- SIMULATION.md
- SECURITY.md
- current source and tests

Repository state and current source override old chat context.

Do not rely on stale milestone counts, commit hashes, test counts, or previous chat summaries when they can be discovered from the repository.

## Git rules

- Work only on the current requested branch.
- Check the current branch and working tree before editing.
- Never commit, push, merge, amend, tag, or switch branches unless the user explicitly asks.
- Do not discard unrelated work.
- Stop and report if unexpected uncommitted changes exist before starting a new milestone.

## Stable schemas

- Hand history: 1.0
- Dataset: 2.0
- Evaluation: 1.0
- Kuhn CFR research: 1.0

Do not change accepted schemas unless the milestone explicitly requires it.

## Hold'em safety

Existing accepted components must remain stable unless explicitly in scope:

- HandEngine
- ExpertRuleBot
- AdaptiveBot
- RangeAwareExpertBot
- OpponentModel
- Range Intelligence
- Statistical Evaluation

Do not silently change strategy thresholds or poker rules to improve benchmark results.

## Research boundary

Research implementations such as Kuhn CFR must remain isolated from production Hold'em until a milestone explicitly integrates them.

## Engineering invariants

Where applicable, preserve:

- deterministic behavior
- legal poker actions
- total-target bet/raise semantics
- zero-sum chip conservation
- privacy boundaries
- no look-ahead
- isolated research/statistics RNG streams

## Out of scope unless explicitly requested

- external poker-site integration
- OCR or screen scraping
- browser automation
- live poker automation
- real-money actions

## Validation

Use focused tests first.

Before declaring a milestone complete, run the standard regression workflow defined by the poker-regression skill.

## Milestone verdict

Never claim COMPLETE merely because implementation exists.

Completion requires evidence for the milestone's acceptance criteria.

If material acceptance evidence is missing, report:

PHASE <X> NOT COMPLETE