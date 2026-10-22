---
name: poker-acceptance
description: Audit a Poker Analyzer milestone and determine whether its COMPLETE verdict is supported by implementation and acceptance evidence.
---

# Poker Acceptance Audit

## Principle

Do not assume a milestone is complete because implementation exists or a previous report says COMPLETE.

Audit the evidence independently.

## Source of truth

Read:

- AGENTS.md
- current ROADMAP.md
- relevant architecture/docs
- implementation
- focused tests
- current git state

Repository state overrides chat summaries.

## Audit checklist

Verify:

1. requested architecture exists;
2. milestone scope was respected;
3. high-risk invariants have direct tests;
4. deterministic behavior is proven where required;
5. privacy/no-look-ahead is proven where required;
6. poker legality and conservation remain valid;
7. mathematical formulas are directly tested where relevant;
8. required API/CLI/integration paths are exercised;
9. statistical claims use appropriate samples and confidence language;
10. schemas remain compatible unless intentionally changed;
11. focused tests pass;
12. standard poker regression passes;
13. final worktree contains only intended changes.

## Benchmark discipline

Do not require a strategy to win every finite benchmark.

Do not retune strategy simply because a benchmark is negative.

Do not call a small sample proof of superiority.

Confidence intervals that include zero are inconclusive.

## Defects discovered during audit

If a correctness defect is found:

- reproduce it deterministically;
- identify root cause;
- prefer the smallest authoritative fix;
- add regression coverage;
- distinguish the defect fix from milestone functionality.

## Verdict

Return exactly one:

`PHASE <X> COMPLETE`

or

`PHASE <X> NOT COMPLETE`

If NOT COMPLETE, clearly identify the smallest missing evidence required for completion.