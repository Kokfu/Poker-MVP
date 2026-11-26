"""Generate timed drills from public simulator decisions."""
from __future__ import annotations

from math import isfinite
from random import Random
from types import SimpleNamespace

from coach.explain import concretize
from simulation.actions import Action
from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine


# Each line ends immediately before the decision to drill. Seat a is Hero.
OPEN = Action("raise", 250)
CALL = Action("call")
CHECK = Action("check")
FLOP_BET = Action("bet", 165)
CHECKED_TURN = (OPEN, CALL, CHECK, FLOP_BET, CALL, CHECK)
LINES = {
    "preflop_open": ("a", ()),
    "preflop_defend": ("b", (OPEN,)),
    "preflop_three_bet": ("a", (OPEN, Action("raise", 750))),
    "flop_cbet": ("a", (OPEN, CALL, CHECK)),
    "flop_defend": ("b", (OPEN, CALL, CHECK, FLOP_BET)),
    "turn": ("a", CHECKED_TURN),
    "river_call": ("a", (*CHECKED_TURN, CHECK, Action("bet", 410))),
    "river_bluff": ("a", (*CHECKED_TURN, CHECK, CHECK)),
}


def classify(street: str, actions, to_call: int, *, can_bluff: bool = False) -> str | None:
    """Classify a decision using (street, actor, action) rows before it."""
    aggression = {"bet", "raise", "all_in"}
    if street == "preflop":
        raises = [actor for _, actor, action in actions if action in aggression]
        if not actions:
            return "preflop_open"
        return "preflop_three_bet" if len(raises) >= 2 else "preflop_defend"
    if street == "flop":
        if to_call:
            return "flop_defend"
        raisers = [actor for phase, actor, action in actions if phase == "preflop" and action in aggression]
        if raisers and raisers[-1] == "hero" and not any(
            phase == "flop" and action in aggression for phase, _, action in actions
        ):
            return "flop_cbet"
    if street == "turn":
        return "turn"
    if street == "river" and to_call:
        return "river_call"
    if street == "river" and can_bluff:
        return "river_bluff"
    return None


class _AtDecision(Exception):
    def __init__(self, observation):
        self.observation = observation


def make_spot(category: str, seed: int) -> tuple[dict, dict] | None:
    button, line = LINES[category]
    actions = iter(line)

    def play(seat, observation):
        action = next(actions, None)
        state = observation.decision_state
        if action is None:
            if seat != "a":
                raise ValueError(f"{category} line did not end at Hero's decision")
            raise _AtDecision(observation)
        if action.type not in state.legal_actions or (
            action.amount is not None
            and not state.minimum_legal_target <= action.amount <= state.maximum_legal_target
        ):
            raise ValueError(f"illegal action in {category} line")
        return action

    hero = SimpleNamespace(decide_decision=lambda o: play("a", o))
    villain = SimpleNamespace(decide_decision=lambda o: play("b", o))
    # Mix stack depths and deals while keeping each line on a tested legal path.
    engine = HandEngine(hero, villain, button=button, seed=seed, stack=Random(seed).choice((5000, 7500, 10000)))
    try:
        engine.play()
    except _AtDecision as stop:
        observation = stop.observation
    else:
        raise ValueError(f"{category} line finished before Hero's decision")

    state = observation.decision_state
    history = [
        {"street": event.street, "actor": "hero" if event.actor == "a" else "villain",
         "action": event.applied_action, "amount": event.target_total}
        for event in engine.history.events if event.event_type == "action_taken"
    ]
    can_bluff = observation.poker_features.made_hand == "high_card"
    if category == "river_bluff" and not can_bluff:
        return None
    if classify(state.street, [(e["street"], e["actor"], e["action"]) for e in history], state.amount_to_call,
                can_bluff=can_bluff) != category:
        raise ValueError(f"{category} line reached the wrong decision")

    advisor = BOT_TYPES["solver_adaptive"](seed=seed)
    advisor.explain_ev = True
    advisor.explain_preflop_ev = True
    advisor.decide_decision(observation)
    explanation = concretize(advisor.last_explanation) or {}
    if explanation.get("source") == "fallback":
        return None
    options = legal_options(explanation, state.legal_actions, state.minimum_legal_target, state.maximum_legal_target)
    if not options or not any(option["ev"] is not None for option in options):
        return None
    # Keep river bluff drills to weak holdings with a meaningful bet in the mix.
    # This uses only Hero's cards, public board, and the answer to this decision.
    if category == "river_bluff" and not any(
        o["action"] in {"bet", "all_in"} and o["frequency"] >= 0.05 for o in options
    ):
        return None

    spot = {
        "category": category, "street": state.street, "position": "button" if button == "a" else "big_blind",
        "hero_cards": state.hole_cards, "board": state.board_cards, "history": history,
        "pot": state.pot, "to_call": state.amount_to_call, "big_blind": state.big_blind,
        "hero_stack": state.hero_stack, "opponent_stack": state.opponent_stack,
        "legal_actions": state.legal_actions, "minimum_target": state.minimum_legal_target,
        "maximum_target": state.maximum_legal_target,
    }
    return spot, {"source": explanation["source"], "options": options}


def legal_options(explanation, legal_actions, minimum, maximum):
    labels = explanation.get("labels", [])
    values = explanation.get("action_ev") or [None] * len(labels)
    options = []
    for label, frequency, ev in zip(labels, explanation.get("probabilities", []), values):
        action, amount = label, None
        if label.startswith(("bet_", "raise_")):
            action, raw = label.split("_", 1)
            amount = int(raw)
            if minimum is None or not minimum <= amount <= maximum:
                continue
        if action in legal_actions:
            options.append({"action": action, "amount": amount, "frequency": frequency,
                            "ev": ev if ev is not None and isfinite(ev) else None})
    return options


def grade(options: list[dict], action: str, amount: int | None, big_blind: int) -> dict:
    best = max(options, key=lambda o: (o["ev"] if o["ev"] is not None else float("-inf"), o["frequency"]))
    choices = [o for o in options if o["action"] == action]
    matched = next((o for o in choices if o["amount"] == amount), None)
    if matched is None and choices and amount is not None:
        matched = min(choices, key=lambda o: abs(o["amount"] - amount))
    cost = None
    if matched is not None and best["ev"] is not None and matched["ev"] is not None:
        cost = round(max(0.0, best["ev"] - matched["ev"]) / big_blind, 3)
    return {
        "best": best, "reference": matched, "cost_bb": cost,
        "correct": matched is not None and matched["amount"] == amount
        and (matched is best or matched["frequency"] >= 0.05),
    }
