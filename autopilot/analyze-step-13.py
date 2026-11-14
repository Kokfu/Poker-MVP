"""Step 13 offline feasibility: Slumbot fold/call/raise frequency vs. our bet size bucket.

Reads existing Slumbot JSONL logs (no live runs).  For every bet/raise by OUR bot that Slumbot
answered, records street, size bucket (to_call / pot-before-the-bet) and Slumbot's response.
Amounts in the action strings are street-level 'bet-to' totals (verified by settlement check).
Usage: python autopilot/analyze-step-13.py > benchmark-results/step-13-feasibility.txt
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from solver.exploit import beta_interval, beta_cdf  # Clopper-Pearson style Beta interval, no SciPy


def chi2_p(rows):
    """Pearson chi-square homogeneity p-value (Wilson-Hilferty approx. for the chi-square tail)."""
    tot = sum(map(sum, rows)); cs = [sum(c) for c in zip(*rows)]
    stat = sum((o - sum(r) * cs[j] / tot) ** 2 / (sum(r) * cs[j] / tot) for r in rows for j, o in enumerate(r))
    df = (len(rows) - 1) * (len(cs) - 1)
    z = ((stat / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2)), stat, df

ROOT = Path(__file__).resolve().parent.parent / "benchmark-results" / "phase-5"
FILES = ["slumbot-learning-clean", "slumbot-learning-instrumented", "slumbot-solver-adaptive-learning",
         "slumbot-solver-adaptive-long", "slumbot-expert", "slumbot-solver"]
BUCKETS = [("<=0.5", 0.0, 0.5), ("0.5-1.0", 0.5, 1.0), (">1.0", 1.0, 1e9)]


def bucket(r):
    for name, lo, hi in BUCKETS:
        if r <= hi:
            return name
    return BUCKETS[-1][0]


def parse(action):
    out, street, i = [], 0, 0
    while i < len(action):
        c = action[i]
        if c == "/":
            street += 1; i += 1
        elif c in "kcf":
            out.append((street, c, None)); i += 1
        else:
            j = i + 1
            while j < len(action) and action[j].isdigit():
                j += 1
            out.append((street, "b", int(action[i + 1:j]))); i = j
    return out


def walk(h):
    """Yield (street, actor, token, amt, pot_before, to_call_before) and check folder loss."""
    client_btn = h["client_position"] == "button"
    commit = {"btn": 50, "bb": 100}
    carried = 0  # chips from closed streets (each side equal)
    events, cur_street = [], 0
    first_actor = {0: "btn"}
    actor = "btn"
    last_street = 0
    for street, tok, amt in parse(h["action"]):
        if street != last_street:
            carried += 2 * commit["btn"]  # closed-street pot; commitments are equal
            commit = {"btn": 0, "bb": 0}
            actor = "bb"
            last_street = street
        opp = "bb" if actor == "btn" else "btn"
        pot_before = carried + commit["btn"] + commit["bb"]
        to_call = commit[opp] - commit[actor]
        events.append((street, actor, tok, amt, pot_before, to_call, commit[opp]))
        if tok == "b":
            commit[actor] = amt
        elif tok == "c":
            commit[actor] = commit[opp]
        actor = opp
    return client_btn, events, carried, commit


def main():
    rows = []  # (file, street, bucket, response, ratio)
    bad = 0
    nhands = 0
    for f in FILES:
        for line in (ROOT / (f + ".jsonl")).read_text().splitlines():
            h = json.loads(line)
            if h.get("desync") or not h.get("action"):
                continue
            nhands += 1
            client_btn, ev, carried, commit = walk(h)
            # settlement sanity for fold endings
            if h["action"].endswith("f"):
                folder = ev[-1][1]
                loss = carried // 2 + commit[folder]  # folder's total contribution
                client_is_folder = (folder == "btn") == client_btn
                exp = -loss if client_is_folder else loss
                # winner nets the folder's total contribution
                if exp != h["winnings"]:
                    bad += 1
            for k, e in enumerate(ev[:-1]):
                street, actor, tok, amt, pot_before, to_call, _ = e
                if tok != "b":
                    continue
                client_acts = (actor == "btn") == client_btn
                if not client_acts:
                    continue
                nxt = ev[k + 1]
                # bet/raise size relative to the pot once the opponent's bet is matched
                opp_commit = e[6]
                street_pot = pot_before - carried  # chips on this street before our action
                matched_pot = carried + 2 * opp_commit if opp_commit else pot_before
                ratio = (amt - opp_commit) / max(matched_pot, 1)
                resp = {"f": "fold", "c": "call", "b": "raise"}[nxt[2]] if nxt[2] in "fc" else "raise"
                rows.append((f, street, bucket(ratio), resp, ratio))
    print(f"hands used: {nhands}; fold-settlement mismatches vs reconstruction: {bad}")
    print(f"client bets/raises answered by Slumbot: {len(rows)}\n")

    def ci(k, n):
        return beta_interval(k, n, 0.95) if n else (float("nan"),) * 2

    def table(title, subset):
        print(f"== {title}  (n={len(subset)})")
        grid = []
        for name, _, _ in BUCKETS:
            sub = [r for r in subset if r[2] == name]
            n = len(sub)
            counts = {x: sum(1 for r in sub if r[3] == x) for x in ("fold", "call", "raise")}
            grid.append([counts["fold"], counts["call"], counts["raise"]])
            cells = []
            for x in ("fold", "call", "raise"):
                lo, hi = ci(counts[x], n)
                cells.append(f"{x} {counts[x]}/{n}={counts[x]/n if n else float('nan'):.2f} [{lo:.2f},{hi:.2f}]")
            print(f"  {name:8s} " + "  ".join(cells))
        g = [r for r in grid if sum(r)]
        if len(g) >= 2:
            cols = [j for j in range(3) if sum(r[j] for r in g)]
            p, st, df = chi2_p([[r[j] for j in cols] for r in g])
            print(f"  chi-square homogeneity across buckets: stat={st:.1f} df={df} p~{p:.4f}")
        print()

    table("ALL STREETS", rows)
    for s, nm in enumerate(["preflop", "flop", "turn", "river"]):
        table(nm, [r for r in rows if r[1] == s])
    print(f"opportunities per 1,000 hands (all bots pooled, {nhands} hands):")
    for s, nm in enumerate(["preflop", "flop", "turn", "river"]):
        print("  " + nm + ": " + ", ".join(
            f"{b[0]} {1000*sum(1 for r in rows if r[1]==s and r[2]==b[0])/nhands:.0f}" for b in BUCKETS))
    # by file (client bot differs) for the aggregate fold rate per bucket
    print("\nfold rate by bucket per log (postflop only):")
    for f in FILES:
        sub = [r for r in rows if r[0] == f and r[1] > 0]
        print("  " + f + ": " + ", ".join(
            f"{b[0]} {sum(1 for r in sub if r[2]==b[0] and r[3]=='fold')}/{sum(1 for r in sub if r[2]==b[0])}" for b in BUCKETS))


if __name__ == "__main__":
    main()
