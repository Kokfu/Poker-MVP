---
name: poker-regression
description: Run the standard Poker Analyzer regression workflow with the correct backend working directory, focused research tests, dependency checks, frontend build, and Git hygiene.
---

# Poker Regression

Use this skill when validating a milestone, bug fix, research change, or acceptance result.

Do not treat passing test count alone as sufficient evidence. Preserve deterministic poker behavior, legality, privacy, zero-sum accounting, total-target semantics, and accepted research controls.

## 1. Pre-regression checks

From repository root:

```powershell
git branch --show-current
git status --short
git diff --check