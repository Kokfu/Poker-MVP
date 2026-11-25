# B1 Coach latency

Two successive API timing runs used separate fresh processes, one BLAS worker, 16 generated spots repeated three times, and synthetic SQLite histories in temporary directories. Half of the spots used a named opponent with 150 generated hands. Flop, turn and river requests for each hand were ordered as they would arrive during entry. The cache-off control used the same code and fixtures with both caches disabled. An earlier baseline, measured before any optimization, was 897 ms preflop and 2,997 ms postflop at p95. The process and system load vary between runs, so the final comparison below places the runs back to back.

| Requests | Count | Baseline median / p95 (ms) | Cached median / p95 (ms) |
| --- | ---: | ---: | ---: |
| Preflop, all | 12 | 308 / 1,762 | 13 / 1,514 |
| Preflop, first | 4 | 419 / 1,762 | 274 / 1,514 |
| Preflop, repeat | 8 | 151 / 400 | 9 / 17 |
| Postflop, all | 36 | 1,446 / 3,787 | 29 / 2,274 |
| Postflop, first | 12 | 1,515 / 3,903 | 899 / 3,003 |
| Postflop, repeat | 24 | 1,446 / 3,367 | 17 / 45 |

The repeat-request cohort meets both targets. Across all requests, p95 still exceeds 300 ms preflop and 600 ms postflop. First-time chart/profile work and new or off-tree postflop solves remain the main costs in this sample. This synthetic workload measures the local API through ASGI, with no network round-trip.

All 48 normalized response hashes matched. Normalization excludes only reported solve time and the runtime cache-hit diagnostic. Action, amount, frequencies, EV, range report, and profile fields match exactly. A focused test also verifies that a turn request reuses its prior flop solve and that adding or deleting logged hands selects the current profile.

The exact solve cache holds four results and keys on engine state, board, both ranges, hero combo, profile inputs, and solve settings. The eight-entry profile cache hashes a single ordered SQLite snapshot and retains derived stats. The river shadow observer and projected research solves bypass the shared solve cache.

From the repository root:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:POKER_COACH_SOLVE_CACHE = '0'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py
$env:POKER_COACH_SOLVE_CACHE = '1'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py
```

## November 26 cold path

One direct profiling run used a synthetic opponent with 150 logged hands and one BLAS worker. The first named preflop request took 5.82 s under cProfile, including 1.07 s to import the solver, 0.97 s to rebuild the opponent profile, and 3.65 s to compute the locked chart policy. The first named flop request took 7.56 s, including 3.75 s for the other seat's locked preflop policy, 0.87 s for new-board equity, and 3.76 s for the full street solve including equity. Profiling shared the machine with the diagnostic and regression, so these numbers are a breakdown under load.

The server now loads charts and class equity before serving requests. A background thread prepares the default 100 bb preflop policy for both hero positions against each of the two opponents with the most logged hands. It uses the normal advisory path and only reads existing Coach profiles. An unseen postflop board still incurs an exact solve.

Three fresh processes each served 48 distinct inputs through the ASGI API with one BLAS worker and synthetic SQLite data. The set contained 12 preflop and 36 postflop requests. Each request was measured on its first use. The agent diagnostic shared the machine.

| Version | Startup (ms) | Preflop median / p95 (ms) | Postflop median / p95 (ms) |
| --- | ---: | ---: | ---: |
| Warmup off | 39 | 11 / 4,222 | 2,255 / 4,360 |
| Warmup on | 640 | 13 / 30 | 3,140 / 5,071 |
| Warmup and faster board equity | 1,099 | 7 / 56 | 1,248 / 4,939 |

All 48 advice hashes matched in both comparisons. Preflop met the 300 ms target. Postflop exceeded the 600 ms target. The timed cohort includes requests arriving while the warmup thread runs. Raw samples and process start and finish times are in [jobs](jobs/coach-48-spots.log).

For a local comparison, run from the repository root with the backend virtual environment installed:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:POKER_COACH_SOLVE_CACHE = '1'
$control = Join-Path $env:TEMP 'poker-coach-48-unwarmed.json'
$env:POKER_COACH_WARMUP = '0'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py --suit-variants 3 --repeats 1 > $control
$env:POKER_COACH_WARMUP = '1'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py --suit-variants 3 --repeats 1 --expect $control
```

The board microbenchmark alternated the control and candidate six times in the same process. Median matrix construction dropped from 429 to 327 ms on the sampled flop, 881 to 708 ms on the exact turn, and 93 to 68 ms on the river. Both matrices and compatibility masks matched bit for bit. A separate buffer-reuse experiment in the lock fitter was slower in all four measured shapes, so the fitter stays on its prior implementation.

### Exact board-ranking experiment on the resumed run

The experiment compared two fresh API processes on the same 48 distinct spots, with warmup and the solve cache enabled, one BLAS worker and the expert diagnostic running. The candidate precomputes evaluator card pairs and filters blocked combos by their card masks. Every normalized advice hash matched.

| Version | Startup (ms) | Preflop median / p95 (ms) | Postflop median / p95 (ms) |
| --- | ---: | ---: | ---: |
| Archived control | 1,047 | 13 / 170 | 2,472 / 3,999 |
| Exact board-ranking candidate | 825 | 13 / 52 | 2,380 / 3,496 |

Six alternating matrix runs per shape matched bit for bit. Median exact turn time was 746 → 558 ms for 1,326 × 1,326 combos and 496 → 338 ms for 750 × 670 combos. The API timing reflects a single pair of sequential runs under shared load. Postflop still exceeds the target. Commit 975387d contains the exact board-ranking change. The later quiet comparison is below.

### Quiet warmup comparison

Once the diagnostic worker had exited, four fresh single-worker processes used independent synthetic SQLite databases and one fixed set of 48 first-use inputs. Each process started measuring immediately after the app became ready. The order was warmup off, on, on, off. All normalized advice hashes matched across the four runs.

| Warmup | Startup (ms) | Preflop median / p95 (ms) | Postflop median / p95 (ms) |
| --- | ---: | ---: | ---: |
| Off, first | 15 | 5 / 972 | 678 / 1,195 |
| On, first | 310 | 5 / 19 | 878 / 1,171 |
| On, second | 292 | 5 / 15 | 902 / 1,137 |
| Off, second | 24 | 6 / 903 | 648 / 1,129 |

Both warmed runs met the 300 ms preflop target. None met the 600 ms postflop target. The warmup thread was allowed to overlap first-use requests. [Run timestamps and arguments](jobs/coach-quiet-48.log)

### Independent boards and stack depths

The representative workload uses two positions, four starting depths from 25 to 200 big blinds, anonymous and two generated opponent profiles, and 36 independent postflop boards. The 48 first-use inputs include checked and bet streets as well as open, limped, and re-raised preflop pots. Both runs used one BLAS worker, fresh databases and fresh API processes. All 48 advice hashes matched.

| Street | Spots | Warmup off median / p95 (ms) | Warmup on median / p95 (ms) |
| --- | ---: | ---: | ---: |
| Preflop | 12 | 828 / 1,338 | 398 / 2,825 |
| Flop | 12 | 728 / 1,155 | 719 / 1,187 |
| Turn | 12 | 1,277 / 2,166 | 1,326 / 2,199 |
| River | 12 | 1,963 / 3,194 | 1,886 / 3,165 |
| All postflop | 36 | 1,154 / 2,693 | 1,173 / 2,927 |

The preflop target met by the 100 bb workload remains open over this wider set. This comparison includes first requests arriving during startup warmup and independent boards for each postflop advice request. [Raw timings](jobs/coach-representative.log)

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:POKER_COACH_SOLVE_CACHE = '1'
$env:POKER_COACH_WARMUP = '0'
$representativeControl = Join-Path $env:TEMP 'coach-representative-control.json'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py --representative --repeats 1 > $representativeControl
$env:POKER_COACH_WARMUP = '1'
backend/.venv/Scripts/python.exe autopilot/overnight/time_coach.py --representative --repeats 1 --expect $representativeControl
```
