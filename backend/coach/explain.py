"""Turn the solver's raw explanation into what the Coach shows: options, EV, range, one-line reason."""
from __future__ import annotations

from typing import Any

SOURCE_NAMES = {"preflop_chart": "preflop chart", "preflop_exploit": "preflop re-solve against the opponent's reads",
                "postflop_solve": "real-time solve of this street", "fallback": "rule-based fallback"}


def pretty(label: str) -> str:
    """'raise_250' -> 'Raise to 250', 'all_in' -> 'All-in' (the same wording as the Coach screen)."""
    if label == "all_in":
        return "All-in"
    kind, _, amount = label.partition("_")
    if amount:
        return f"{'Bet' if kind == 'bet' else 'Raise to'} {amount}"
    return kind.capitalize()


def _percent(value: float) -> str:
    return f"{round(value * 100):d}%"


def _chips(value: float) -> str:
    return f"{value:+,.0f}"


def concretize(explanation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Relabel preflop options with the amounts actually playable at this table.

    The chart is stored at its own bet sizes; the bot rescales them to the real
    raise, so the chart label ("raise_750") can differ from the action it
    returns ("raise 900").  Options that land on the same play are merged."""
    concrete = (explanation or {}).get("concrete_labels")
    if not explanation or not concrete or len(concrete) != len(explanation.get("labels") or []):
        return explanation
    probabilities, evs = explanation["probabilities"], explanation.get("action_ev")
    order: list[str] = []
    merged: dict[str, list[float]] = {}
    for index, label in enumerate(concrete):
        if label not in merged:
            order.append(label)
            merged[label] = [0.0, 0.0]
        merged[label][0] += probabilities[index]
        if evs is not None:
            merged[label][1] += probabilities[index] * evs[index]
    result = {key: value for key, value in explanation.items() if key != "concrete_labels"}
    result["labels"] = order
    result["probabilities"] = [round(merged[label][0], 4) for label in order]
    if evs is not None:
        result["action_ev"] = [round(merged[label][1] / merged[label][0], 1) if merged[label][0] else evs[concrete.index(label)] for label in order]
    result["chosen"] = concrete[explanation["labels"].index(explanation["chosen"])]
    return result


def build(advice: dict[str, Any], explanation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Structured explanation for the action the solver chose; ``None`` without an explanation."""
    if not explanation:
        return None
    source = explanation.get("source", "")
    labels, probabilities = explanation.get("labels") or [], explanation.get("probabilities") or []
    evs = explanation.get("action_ev")
    options = [{"label": label, "frequency": probabilities[i], **({"ev": evs[i]} if evs is not None else {})}
               for i, label in enumerate(labels) if i < len(probabilities)]
    chosen = next((o for o in options if o["label"] == explanation.get("chosen")), None)
    equity = explanation.get("hero_equity_vs_range")
    effective = explanation.get("villain_effective_combos")
    opponent_range = {"effective_combos": effective, "top_classes": explanation.get("villain_top_classes") or [],
                      "makeup": explanation.get("villain_range_makeup") or []} if effective is not None else None
    exploit = explanation.get("exploit") or {}
    result: dict[str, Any] = {
        "source": source, "action": advice["action"], "amount": advice.get("amount"), "chosen": explanation.get("chosen"),
        "frequency": chosen["frequency"] if chosen else None, "ev": chosen.get("ev") if chosen else None,
        "equity": equity, "options": options, "opponent_range": opponent_range,
        "exploiting": bool(exploit.get("active")), "reason": reason(explanation, options, chosen),
    }
    if evs is not None:
        result["ev_note"] = ("EV is the chips you expect to win from here on, counting only the chips you still have to put in "
                             "(folding is 0). Flop and turn values treat the end of the street as equity over the remaining cards, "
                             "so they are approximate.")
    return result


def reason(explanation: dict[str, Any], options: list[dict[str, Any]], chosen: dict[str, Any] | None) -> str:
    source = explanation.get("source", "")
    if source == "fallback":
        return f"The solver could not handle this spot ({explanation.get('reason', 'unknown')}), so the rule-based bot chose."
    if chosen is None:
        return "No option detail was available for this decision."
    parts = [f"{pretty(chosen['label'])} is played {_percent(chosen['frequency'])} of the time with this hand ({SOURCE_NAMES.get(source, source)})"]
    if chosen["frequency"] < 0.9 and len(options) > 1:
        parts[0] += "; the solver mixes here, so this is one of its valid plays"
    equity, effective = explanation.get("hero_equity_vs_range"), explanation.get("villain_effective_combos")
    if equity is not None:
        width = "" if effective is None else f" (a {'wide' if effective > 300 else 'narrow' if effective < 100 else 'medium'} range, about {effective:.0f} hands)"
        parts.append(f"your equity against the opponent's estimated range is {_percent(equity)}{width}")
    if chosen.get("ev") is not None:
        others = [o for o in options if o is not chosen and o.get("ev") is not None]
        if others:
            best = max(others, key=lambda o: o["ev"])
            gap = "best EV" if chosen["ev"] >= best["ev"] else f"{_chips(chosen['ev'] - best['ev'])} chips versus {pretty(best['label'])}"
            parts.append(f"EV {_chips(chosen['ev'])} chips ({gap})")
        else:
            parts.append(f"EV {_chips(chosen['ev'])} chips")
    exploit = explanation.get("exploit") or {}
    if exploit.get("active") and exploit.get("locked_nodes"):
        parts.append(f"adjusted to a {str(exploit.get('classification', 'unknown')).replace('_', ' ')} read from {exploit.get('hands_observed', 0)} logged hands")
    return "; ".join(parts) + "."
