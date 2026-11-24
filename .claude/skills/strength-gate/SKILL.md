---
name: strength-gate
description: Pre-registered test of whether a bot or strategy change makes the bot stronger, with duplicate deals, fresh holdout seeds and confidence intervals. Use whenever a claim like "better", "stronger" or "beats X" is about to be made, or before making a new bot the default.
---

# Strength gate

Bot strength is only shown by a test written down **before** the data exists. Unit tests and small runs only diagnose. They never show strength.

1. **Write the test into a doc and commit it before any data runs** (`autopilot/prereg-*.md` or a ROADMAP section). It must name:
   - the candidate and baseline arms;
   - the opponents;
   - `simulation.duplicate_cli` mode (`pair` or `tournament`);
   - sessions × hands (for example 48 × 60);
   - `--seed-set holdout` and a fresh `--seed-offset`;
   - statistics seed 91,002 and 2,000 bootstrap resamples;
   - the pass rule (for example, every paired lower bound > 0, or pooled lower > −25 with no single result < −60);
   - the smallest effect the test can detect;
   - the cost in hours.
2. **Pick a seed offset that has never been used.** Grep `ROADMAP.md`, `autopilot/` and `DESIGN_OPPONENT_MODEL.md` for it first. As of 2026-11-25:
   - 1M–7M are used;
   - 8M is reserved by autopilot step 21;
   - so start at 9,000,000 or above.
   Development runs use the default `development` seed set.
3. **Run it in the background.** Free RAM is low, so use 2 workers; the worker count doesn't change results. Write results to `benchmark-results/phase-5/` and force-add what must be kept.
4. **Report every number with its interval in bb/100**, plus hands played, illegal actions, fallbacks and deal mismatches. Apply the pass rule exactly as written. If it fails, the change stays off by default. Don't retune and re-run on the same seeds.
5. **For an outside opponent (optional, uses the network):** `python -m simulation.slumbot_cli --bot <bot> --hands N --output ...`.
   - Use `baseline_adjusted_bb_per_100`.
   - 1,000 hands can't resolve effects smaller than about 200 bb/100, so use Slumbot only as a sanity check.

**Current baseline:** `solver_adaptive` is the default and strongest bot.
- `solver_adaptive_gated` and `solver_adaptive_sized` failed their tests and stay off by default.
- `solver_adaptive` vs `equity` on pool score is still inconclusive.
