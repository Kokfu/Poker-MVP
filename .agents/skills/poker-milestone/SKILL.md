---
name: poker-milestone
description: Implement a Poker Analyzer milestone safely while preserving accepted baselines and producing evidence-based completion reports.
---

# Poker Milestone Workflow

## Before editing

1. Read the repository-root `AGENTS.md`.
2. Inspect the current branch and working tree.
3. Inspect recent commits and milestone tags.
4. Read `ROADMAP.md` and the architecture, source, and tests relevant to the milestone.
5. Treat current repository state as the source of truth.
6. Stop if unexpected uncommitted work exists.

## Plan before implementation

Before making substantial changes:

1. Identify the milestone objective.
2. Identify accepted components that must remain unchanged.
3. Identify the highest-risk correctness invariants.
4. Identify the focused tests needed to prove those invariants.
5. Keep implementation scope limited to the milestone.

Do not implement later roadmap phases early.

## Implementation rules

- Preserve accepted components outside scope.
- Prefer deterministic implementations.
- Preserve zero-sum and chip-conservation invariants where applicable.
- Preserve privacy and no-look-ahead boundaries.
- Preserve existing schema compatibility unless explicitly in scope.
- Do not silently retune strategy to improve benchmark results.
- Do not modify frontend unless explicitly in scope.
- Do not commit, push, merge, amend, tag, or switch branches.

If a pre-existing correctness defect is discovered:

1. reproduce it deterministically;
2. identify the root cause;
3. make the smallest authoritative fix;
4. add regression coverage;
5. clearly distinguish the fix from the milestone's intended feature.

## Testing

Run focused tests first.

High-risk mathematical, poker-rule, privacy, deterministic, or statistical behavior should have direct tests rather than relying only on end-to-end outcomes.

Then use the `poker-regression` skill.

Do not weaken existing tests to make a milestone pass.

## Benchmarks and evaluation

Do not treat a small positive benchmark as proof of superiority.

Do not modify strategy merely because a finite benchmark is negative.

Use the repository's statistical evaluation framework when the milestone requires strategy comparison.

Clearly label small samples and inconclusive confidence intervals.

## Completion

A milestone is COMPLETE only when all material requested acceptance criteria have evidence.

Implementation alone is insufficient.

If anything material remains missing, return:

`PHASE <X> NOT COMPLETE`

Otherwise return:

`PHASE <X> COMPLETE`

Do not hide incomplete validation.

## Final report

Summarize:

- files added and modified;
- architecture implemented;
- important invariants;
- focused test results;
- acceptance diagnostics;
- full regression result;
- compatibility impact;
- known limitations;
- final git status;
- exact milestone verdict.