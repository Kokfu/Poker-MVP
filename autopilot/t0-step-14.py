"""Step 14: gate T0 of autopilot/prereg-step-13.md (offline, no live runs).

Leave-one-log-out prediction of Slumbot's fold/call/raise on postflop client bets/raises.
  (i)  size-blind street model: p(resp | street) = (k+1)/(n+3)   (Laplace, training logs only)
  (ii) bucketed shrunk model:   p(resp | street, bucket) = (k + m*p_i) / (n + m), m = 20,
       shrunk toward model (i) of the same street (no solver exists offline; this stands in for
       p_eq(b)).  If a training cell has n < 10 the model falls back to (i) for that case
       (the prereg's "left unlocked").
Metric: log-loss on the held-out log's cases.  Per-hand sum of (logloss_i - logloss_ii) is
bootstrapped over hands (2,000 resamples, seed 91002, pooled held-out hands).
PASS iff the 95% lower bound (2.5th percentile) of the mean per-case improvement is > 0.
Usage: python autopilot/t0-step-14.py > benchmark-results/step-14-t0.txt
"""
import importlib.util, math, random, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a13", HERE / "analyze-step-13.py")
a13 = importlib.util.module_from_spec(spec); spec.loader.exec_module(a13)
import json

M, MIN_N, RESAMPLES, SEED = 20, 10, 2000, 91002
RESP = ("fold", "call", "raise")


def collect():
    """Return {file: [hand_cases]} where hand_cases is a list of (street, bucket, resp) for one hand."""
    out = {}
    for f in a13.FILES:
        hands = []
        for line in (a13.ROOT / (f + ".jsonl")).read_text().splitlines():
            h = json.loads(line)
            if h.get("desync") or not h.get("action"):
                continue
            client_btn, ev, carried, commit = a13.walk(h)
            cases = []
            for k, e in enumerate(ev[:-1]):
                street, actor, tok, amt, pot_before, to_call, opp_commit = e
                if tok != "b" or street == 0 or (actor == "btn") != client_btn:
                    continue
                matched = carried + 2 * opp_commit if opp_commit else pot_before
                ratio = (amt - opp_commit) / max(matched, 1)
                nxt = ev[k + 1][2]
                resp = {"f": "fold", "c": "call"}.get(nxt, "raise")
                cases.append((street, a13.bucket(ratio), resp))
            hands.append(cases)
        out[f] = hands
    return out


def main():
    data = collect()
    deltas = []  # per held-out hand: (sum of delta, n cases)
    ll1 = ll2 = ncase = 0.0
    for held in a13.FILES:
        cs, cb = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
        for f in a13.FILES:
            if f == held:
                continue
            for hand in data[f]:
                for s, b, r in hand:
                    cs[s][r] += 1; cb[(s, b)][r] += 1

        def p_i(s, r):
            return (cs[s][r] + 1) / (sum(cs[s].values()) + 3)

        def p_ii(s, b, r):
            n = sum(cb[(s, b)].values())
            if n < MIN_N:
                return p_i(s, r)
            return (cb[(s, b)][r] + M * p_i(s, r)) / (n + M)

        for hand in data[held]:
            d = 0.0; n = 0
            for s, b, r in hand:
                a, c = -math.log(p_i(s, r)), -math.log(p_ii(s, b, r))
                d += a - c; n += 1; ll1 += a; ll2 += c
            if n:
                deltas.append((d, n))
        print(f"held-out {held}: hands with cases {sum(1 for h in data[held] if h)}, cases {sum(len(h) for h in data[held])}")
    N = sum(n for _, n in deltas)
    print(f"\npooled held-out postflop cases: {N} in {len(deltas)} hands")
    print(f"mean log-loss (i) size-blind: {ll1/N:.4f}   (ii) bucketed shrunk (m={M}): {ll2/N:.4f}")
    mean = sum(d for d, _ in deltas) / N
    rng = random.Random(SEED)
    boots = []
    for _ in range(RESAMPLES):
        sd = sn = 0
        for _ in deltas:
            d, n = deltas[rng.randrange(len(deltas))]
            sd += d; sn += n
        boots.append(sd / sn)
    boots.sort()
    lo, hi = boots[int(0.025 * RESAMPLES)], boots[int(0.975 * RESAMPLES) - 1]
    print(f"mean improvement (i)-(ii) per case: {mean:+.4f} nats  95% bootstrap over hands [{lo:+.4f}, {hi:+.4f}]")
    print(f"T0 {'PASS' if lo > 0 else 'FAIL'}  (rule: lower bound > 0)")


if __name__ == "__main__":
    main()
