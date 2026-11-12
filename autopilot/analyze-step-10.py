"""T1 analysis: per-opponent and pooled paired differences (gated - base). Run from backend/: .venv\Scripts\python ..\autopilot\analyze-step-10.py"""
import json, random, sys, pathlib
sys.path.insert(0, ".")
from simulation.evaluation import _percentile_interval
D = pathlib.Path("../benchmark-results/phase-6")
OPPS = ["random", "tight", "aggressive", "equity", "expert", "adaptive", "range_expert", "solver"]
POOL = ["tight", "equity", "expert", "range_expert", "solver"]
BB, HANDS, SEED, RES = 100, 120, 91002, 2000

def load(s, o):
    d = json.load(open(D / f"t1-{s}-{o}.json"))
    return d, {p["seed"]: p["net_seat_a"] + p["net_seat_b"] for p in d["raw_pairs"]}

def boot(vals):
    n = len(vals); rng = random.Random(SEED)
    r = [100.0 * sum(vals[rng.randrange(n)] for _ in range(n)) / (HANDS * n * BB) for _ in range(RES)]
    return 100.0 * sum(vals) / (HANDS * n * BB), _percentile_interval(r, 0.95)

out = {"per_opponent": {}, "gated_vs_opp": {}, "flags": {}}
diffs = {}
for o in OPPS:
    gd, g = load("solver_adaptive_gated", o); bd, b = load("solver_adaptive", o)
    assert g.keys() == b.keys(), f"seed mismatch {o}"
    seeds = sorted(g)
    diffs[o] = [g[s] - b[s] for s in seeds]
    est, ci = boot(diffs[o])
    m = gd["metrics"]
    out["per_opponent"][o] = {"diff": est, "lo": ci["lower"], "hi": ci["upper"], "base_bb100": bd["metrics"]["bb_per_100"]}
    out["gated_vs_opp"][o] = {"bb100": m["bb_per_100"], "lo": m["confidence_interval"]["lower"], "hi": m["confidence_interval"]["upper"],
        "illegal": m["illegal_actions"], "fallbacks": m["fallback_actions"], "deal_mismatches": m["deal_mismatches"]}
n = len(diffs["tight"])
pooled = [sum(diffs[o][i] for o in POOL) / len(POOL) for i in range(n)]
est, ci = boot(pooled)
out["pooled"] = {"diff": est, "lo": ci["lower"], "hi": ci["upper"], "half_width": (ci["upper"] - ci["lower"]) / 2}
T1a = all(v["lo"] > 0 for v in out["gated_vs_opp"].values()) and all(v["illegal"] == 0 and v["fallbacks"] == 0 and v["deal_mismatches"] == 0 for v in out["gated_vs_opp"].values())
single_ok = all(out["per_opponent"][o]["lo"] >= -60 for o in POOL)
if out["pooled"]["half_width"] > 40: T1b = "inconclusive"
else: T1b = "pass" if (out["pooled"]["lo"] > -25 and single_ok) else "fail"
out["T1a"] = "pass" if T1a else "fail"; out["T1b"] = T1b
out["flags"] = {o: out["per_opponent"][o]["diff"] < -150 for o in ("aggressive", "random")}
json.dump(out, open(D / "t1-analysis.json", "w"), indent=1)
print(json.dumps(out, indent=1))
