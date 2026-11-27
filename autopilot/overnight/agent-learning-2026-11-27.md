# Overnight agent learning diagnostic

The two development runs used clean per-opponent profiles. Each ran 24
duplicate sessions with 60 hands per orientation, for 2,880 hands per
opponent. The seed offsets were 113700 for `expert` and 116700 for
`range_expert`. Each seat's saved profile went from zero to 1,440 observed
hands. The job ran from 18:27 to 19:29 MYT on November 26.

| Opponent | First 12 sessions, bb/100 [95% interval] | Last 12 sessions, bb/100 [95% interval] | Late minus early, bb/100 [95% interval] |
| --- | ---: | ---: | ---: |
| `expert` | +16.53 [−100.46, +126.31] | −27.55 [−122.19, +67.91] | −44.08 [−190.74, +107.16] |
| `range_expert` | −47.38 [−133.95, +49.01] | −95.10 [−186.11, −1.81] | −47.72 [−178.54, +78.81] |

The percentile intervals resample the 12 session scores in each half 2,000
times with statistics seed 91002. Each resample pairs the two seat outcomes
already combined in a session score. The learning profile evolves between
sessions, so these intervals describe the observed session variation under
that schedule. Both late-minus-early intervals include zero. The diagnostic
leaves the effect of learning unresolved. All 5,760 hands had zero illegal
actions, action or solver fallbacks, and deal mismatches.

The profile mode stores completed sessions and aggregate profiles in
`jobs/profiles/expert.profile.json` and
`jobs/profiles/range_expert.profile.json`. The CLI summaries are
`jobs/nov27-expert.summary.json` and
`jobs/nov27-range_expert.summary.json`. These local files hold session-level
results and do not record individual actions or board cards.

## Matched fresh-profile control

The fresh-profile controls are queued. Each would reuse the matching
development seeds and reset both players' public profiles at the start
of each session while allowing updates within that session. The analysis
checks the two arms start identically, verifies the aligned schedule,
and reports the paired difference across all, first-half, and last-half
sessions. Its intervals describe variation along the observed schedule.

```powershell
Push-Location backend
$env:OPENBLAS_NUM_THREADS = '1'
.venv/Scripts/python.exe -m simulation.agent_cli --run nov27-carry-control-expert --opponent expert --sessions 24 --session-hands 60 --seed-offset 113700 --output-dir ../autopilot/overnight/jobs --progress
.venv/Scripts/python.exe -m simulation.agent_cli --run nov27-carry-control-range_expert --opponent range_expert --sessions 24 --session-hands 60 --seed-offset 116700 --output-dir ../autopilot/overnight/jobs --progress
Pop-Location
backend/.venv/Scripts/python.exe autopilot/overnight/analyze_learning_carryover.py expert
backend/.venv/Scripts/python.exe autopilot/overnight/analyze_learning_carryover.py range_expert
```
