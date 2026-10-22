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
```

If unexpected unrelated modifications exist, stop before changing or discarding them.

Do not commit, push, tag, merge, amend, switch branches, or discard unrelated work unless explicitly requested.

## 2. Focused tests first

Run tests most directly related to the changed area before the full suite.

For Poker research milestones, backend Python tests MUST run with `backend` as the working directory.

This matters because subprocess-based tests execute modules such as:

- `python -m simulation.cli`
- `python -m research.kuhn.cli`

and therefore require `backend` to be the Python module root.

## 3. Research regression on Windows

From repository root:

```powershell
Push-Location backend

$researchTests = Get-ChildItem -File -Filter "test_research*.py" |
    ForEach-Object { $_.FullName }

& ".\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider $researchTests

Pop-Location
```

Record:

- passed;
- failed;
- warnings;
- runtime.

Do not hide failures.

## 4. Full backend regression on Windows

From repository root:

```powershell
Push-Location backend

& ".\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider
& ".\.venv\Scripts\python.exe" -m pip check

Pop-Location
```

Do not run the standard backend pytest suite from repository root unless subprocess PYTHONPATH behavior has explicitly been configured for it.

A repository-root run can produce false `ModuleNotFoundError` failures for `simulation` or `research` modules.

## 5. Frontend regression

From repository root:

```powershell
Push-Location frontend

npm run build

Pop-Location
```

The production build must complete successfully.

## 6. Poker invariants

Where relevant, verify:

- deterministic behavior;
- legal actions;
- total-target bet/raise semantics;
- short all-in behavior;
- zero-sum chip conservation;
- hidden-information privacy;
- no future-information leakage;
- isolated RNG behavior;
- accepted schema compatibility;
- accepted exact research controls.

Do not infer these properties only from a high overall test count when direct fixtures are required.

## 7. Research-control compatibility

For CFR/MCCFR milestones, preserve accepted controls unless the milestone explicitly changes them.

Check relevant controls such as:

- Kuhn Vanilla CFR;
- Kuhn CFR+;
- Kuhn MCCFR;
- Hold'em abstraction;
- bounded exact Hold'em CFR;
- existing MCCFR research games.

Do not retune accepted algorithms merely to improve a new benchmark.

## 8. Final hygiene

From repository root:

```powershell
git diff --check
git status --short
```

LF/CRLF conversion advisories alone are not whitespace errors.

Confirm that only intended milestone files remain modified or untracked.

## 9. Regression report

Report at minimum:

- focused test result;
- research regression result where applicable;
- full backend result;
- pip check;
- frontend production build;
- git diff --check;
- important poker invariants;
- retained-control compatibility;
- final Git status.

Clearly distinguish:

- implementation failure;
- test-environment failure;
- acceptance-evidence gap;
- harmless warnings.

Never convert an environment/configuration failure into a code change unless evidence shows the implementation is actually defective.
