---
name: poker-regression
description: Run the standard Poker Analyzer regression and compatibility checks before accepting a milestone.
---

# Poker Regression Workflow

## Repository

Use the repository root discovered from Git.

Do not rely on stale test counts from chat or previous milestones.

## Before regression

Run:

```powershell
git branch --show-current
git status --short
git diff --check