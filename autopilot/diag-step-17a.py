"""Step 17a diagnosis (read-only): why does a `tight` villain profile WIDEN the villain's estimated range
at a flop bet and flip J9 facing the bet from fold 72% to call 98%?

Run from the repo root:  backend\\.venv\\Scripts\\python.exe autopilot\\diag-step-17a.py
Imports the step 16 test helpers; patches nothing permanently (wrappers only print).
"""
import os, sys, tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
import numpy as np
from coach.service import Spot, SpotAction, advise, spot_to_dict
from coach.store import HandStore
from solver.bot import SolverBot
from test_coach_learning import simulated_spots

SPOT = Spot(hero_cards=["Jc", "9d"], hero_position="big_blind", board=["Qh", "7s", "2d"],
            actions=[SpotAction("villain", "raise", 250), SpotAction("hero", "call"),
                     SpotAction("hero", "check"), SpotAction("villain", "bet", 200)])


def eff(w):
    t = w.sum()
    return float(t * t / (w * w).sum()) if t > 0 else 0.0


def trace(label, opponent, store):
    orig_apply, orig_pre = SolverBot._apply_strategy, SolverBot._preflop_policy
    log = []

    def apply(weights, solve, node, choice):
        out = orig_apply(weights, solve, node, choice)
        n = solve.tree.nodes[node]
        agg = (solve.average[node] * weights[solve.combos[n.player]][None, :]).sum(1) / max(weights[solve.combos[n.player]].sum(), 1e-12)
        log.append(f"  flop step node{node} player{n.player} {n.labels[choice]}: combos {eff(weights):.0f} -> {eff(out):.0f}; "
                   f"range mass kept {out.sum() / max(weights.sum(), 1e-12):.3f}; aggregate mix {dict(zip(n.labels, np.round(agg, 3)))}")
        return out
    SolverBot._apply_strategy = staticmethod(apply)

    def pre(self, depth, opp, locks):
        policy = orig_pre(self, depth, opp, locks)

        def wrapped(node):
            return policy(node)
        log.append(f"  preflop locks on villain nodes: {len(locks)}; "
                   + ("; ".join(f"node{k}: weight {v[0]} groups {[(g[0], round(g[1], 2)) for g in v[1]]} strength {v[2]}" for k, v in list(locks.items())[:4])))
        return wrapped
    SolverBot._preflop_policy = pre
    try:
        res = advise(SPOT, opponent=opponent, store=store)
    finally:
        SolverBot._apply_strategy, SolverBot._preflop_policy = orig_apply, orig_pre
    e = res["explanation"]
    print(f"[{label}] probs {dict(zip(e['labels'], e['probabilities']))} villain_effective_combos {e.get('villain_effective_combos')} "
          f"equity {e.get('hero_equity_vs_range')} exploit {e['exploit']}")
    print("\n".join(log))
    makeup = e.get("villain_range_makeup", [])[:5]
    print("  villain range makeup (top):", [(m["type"], m["share"]) for m in makeup])


def variants(store):
    """Read-only what-if: override the lock `strength` (hand-strength correlation) after tree_locks builds it."""
    import solver.bot as sb
    orig = sb.tree_locks
    for name, fn in (("strength forced 1.0 everywhere", lambda k, v: 1.0),
                     ("strength = aggressive corr (0.893) on preflop unopened-SB node0 only", lambda k, v: 0.89 if k == 0 and v[2] == 0.54 else v[2])):
        def patched(*a, _fn=fn, **kw):
            locks = orig(*a, **kw)
            return {k: (v[0], v[1], _fn(k, v)) for k, v in locks.items()}
        sb.tree_locks = patched
        try:
            trace("warm, " + name, "V", store)
        finally:
            sb.tree_locks = orig


if __name__ == "__main__":
    store = HandStore(os.path.join(tempfile.mkdtemp(), "c.sqlite"))
    for spot in simulated_spots("tight", 150):
        store.add("V", spot_to_dict(spot))
    trace("cold", None, store)
    trace("warm tight profile", "V", store)
    variants(store)
