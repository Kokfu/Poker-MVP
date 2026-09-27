"""Replay a manually entered heads-up spot through the engine and advise.

Seats are fixed: the user ("hero") is seat ``a`` and the opponent ("villain")
is seat ``b``; ``hero_position`` chooses the button.  Stacks are the stacks
at the start of the hand, bet/raise amounts are street totals (the engine's
target semantics), and board cards are entered as the streets are reached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from poker_analyzer import FULL_DECK
from simulation.actions import Action
from simulation.engine import HandEngine
from simulation.opponent_model import OpponentModel

from .store import HandStore

Actor = Literal["hero", "villain"]
HERO, VILLAIN = "a", "b"
STREET_BOARD = {"flop": 3, "turn": 4, "river": 5}


@dataclass
class SpotAction:
    actor: Actor
    action: str
    amount: int | None = None


@dataclass
class Spot:
    hero_cards: list[str]
    board: list[str] = field(default_factory=list)
    hero_position: Literal["button", "big_blind"] = "button"
    small_blind: int = 50
    big_blind: int = 100
    hero_stack: int = 10_000
    villain_stack: int = 10_000
    actions: list[SpotAction] = field(default_factory=list)
    villain_cards: list[str] | None = None  # optional, only when shown at showdown

    def validate(self) -> None:
        cards = list(self.hero_cards) + list(self.board) + list(self.villain_cards or [])
        if len(self.hero_cards) != 2:
            raise ValueError("enter exactly two hero cards")
        if len(self.board) not in (0, 3, 4, 5):
            raise ValueError("the board must have 0, 3, 4, or 5 cards")
        if self.villain_cards is not None and len(self.villain_cards) != 2:
            raise ValueError("villain cards must be exactly two cards when given")
        if any(card not in FULL_DECK for card in cards):
            raise ValueError("cards use notation like As, Kd, Th, 7c")
        if len(set(cards)) != len(cards):
            raise ValueError("duplicate cards are not allowed")
        if not 0 < self.small_blind <= self.big_blind:
            raise ValueError("blinds must be positive and the small blind no larger than the big blind")
        if self.hero_stack <= 0 or self.villain_stack <= 0:
            raise ValueError("stacks must be positive")
        for step in self.actions:
            if step.actor not in ("hero", "villain") or step.action not in ("fold", "check", "call", "bet", "raise", "all_in"):
                raise ValueError(f"unsupported action {step.actor}:{step.action}")
            if step.action in ("bet", "raise") and (step.amount is None or step.amount <= 0):
                raise ValueError("bet and raise need a positive street-total amount")


class _Stop(Exception):
    def __init__(self, status: str, payload: dict[str, Any]):
        super().__init__(status)
        self.status, self.payload = status, payload


class _CoachDeck:
    """Hero cards, then villain cards (real if shown, else placeholders), then the entered board."""

    def __init__(self, spot: Spot):
        known = set(spot.hero_cards) | set(spot.board) | set(spot.villain_cards or [])
        placeholder = [card for card in reversed(FULL_DECK) if card not in known][:2]
        self.seats = [list(spot.hero_cards), list(spot.villain_cards or placeholder)]
        self.board, self.calls, self.dealt = list(spot.board), 0, 0

    def deal(self, count: int = 1) -> list[str]:
        if self.calls < 2:
            self.calls += 1
            return list(self.seats[self.calls - 1])
        if self.dealt + count > len(self.board):
            street = {0: "flop", 3: "turn", 4: "river"}[self.dealt]
            raise _Stop("need_board", {"street": street, "cards_needed": STREET_BOARD[street]})
        cards = self.board[self.dealt:self.dealt + count]
        self.dealt += count
        return cards


def _state(observation, engine) -> dict[str, Any]:
    return {
        "street": observation.street,
        "pot": observation.pot,
        "to_call": observation.amount_to_call,
        "legal_actions": list(observation.legal_actions),
        "minimum_target": observation.minimum_target_to,
        "maximum_target": observation.maximum_target_to,
        "hero_stack": engine.state.stacks[HERO],
        "villain_stack": engine.state.stacks[VILLAIN],
        "board": list(engine.state.community_cards),
    }


class _ScriptedSeat:
    def __init__(self, script: "_Script", seat: str):
        self.script, self.seat = script, seat

    def decide(self, observation) -> Action:
        return self.script.next(self.seat, observation)


class _Script:
    def __init__(self, spot: Spot, advisor=None):
        self.actions, self.position, self.advisor, self.engine = list(spot.actions), 0, advisor, None

    def next(self, seat: str, observation) -> Action:
        actor = "hero" if seat == HERO else "villain"
        if self.position >= len(self.actions):
            status = "hero_to_act" if actor == "hero" else "villain_to_act"
            raise _Stop(status, {"state": _state(observation, self.engine)})
        step = self.actions[self.position]
        if step.actor != actor:
            raise ValueError(f"action {self.position + 1}: it is {actor}'s turn, but {step.actor} was entered")
        if step.action not in observation.legal_actions:
            raise ValueError(f"action {self.position + 1}: {step.action} is not legal here; legal: {', '.join(observation.legal_actions)}")
        if step.action in ("bet", "raise"):
            low, high = observation.minimum_target_to, observation.maximum_target_to
            if low is None or not low <= step.amount <= high:
                raise ValueError(f"action {self.position + 1}: {step.action} total must be between {low} and {high}")
        self.position += 1
        return Action(step.action, step.amount if step.action in ("bet", "raise") else None)


class _AdvisorSeat(_ScriptedSeat):
    """Hero seat: replays entered actions, then asks the solver at the first open decision."""

    def decide_decision(self, observation) -> Action:
        script = self.script
        if script.position >= len(script.actions) and script.advisor is not None:
            advisor = script.advisor
            action = advisor.decide_decision(observation)
            raise _Stop("hero_to_act", {"advice": {"action": action.type, "amount": action.amount}, "explanation": advisor.last_explanation})
        return self.decide(script.engine.observe(HERO))


def _replay(spot: Spot, advisor=None, profile=None):
    spot.validate()
    script = _Script(spot, advisor)
    engine = HandEngine(
        _AdvisorSeat(script, HERO), _ScriptedSeat(script, VILLAIN),
        starting_stacks={HERO: spot.hero_stack, VILLAIN: spot.villain_stack},
        bb=spot.big_blind, small_blind=spot.small_blind,
        button=HERO if spot.hero_position == "button" else VILLAIN,
        hand_id="coach-hand", deck=_CoachDeck(spot),
        opponent_profile_provider=(lambda player: profile if player == HERO else None) if profile is not None else None,
    )
    script.engine = engine
    try:
        result = engine.play()
    except _Stop as stop:
        return stop.status, stop.payload, engine
    if result["illegal_actions"]:
        raise ValueError(f"illegal entry: {result['illegal_diagnostics'][0]}")
    if script.position != len(script.actions):
        raise ValueError(f"the hand ended after action {script.position}; remove the later actions")
    return "hand_complete", {"result": result}, engine


def _hand_complete_payload(spot: Spot, payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    showdown = result["showdown"]
    summary = {"showdown": showdown, "board": list(result["state"].community_cards)}
    if not showdown or spot.villain_cards:
        summary["hero_net"] = result["stacks"][HERO] - spot.hero_stack
    return {"status": "hand_complete", "summary": summary}


def profile_for(store: HandStore, opponent: str):
    model = OpponentModel(VILLAIN)
    for stored in store.hands(opponent):
        spot = spot_from_dict(stored)
        status, payload, _ = _replay(spot)
        if status == "hand_complete":
            model.update(payload["result"]["history"])
    return model


def advise(spot: Spot, opponent: str | None = None, exploit: bool = True, store: HandStore | None = None, seed: int = 0) -> dict[str, Any]:
    from solver.bot import AdaptiveSolverBot, SolverBot

    profile_snapshot = None
    if opponent:
        model = profile_for(store or HandStore(), opponent)
        profile_snapshot = model.snapshot() if model.hands_observed else None
    advisor = (AdaptiveSolverBot if exploit and profile_snapshot is not None else SolverBot)(seed=seed)
    status, payload, engine = _replay(spot, advisor, profile_snapshot)
    if status == "hand_complete":
        return _hand_complete_payload(spot, payload)
    response: dict[str, Any] = {"status": status, **payload}
    if status == "hero_to_act":
        response["state"] = _state(engine.observe(HERO), engine)
        response["exploiting"] = advisor.exploit
        response["opponent_profile"] = profile_summary(profile_snapshot)
    return response


def log_hand(spot: Spot, opponent: str, store: HandStore | None = None) -> dict[str, Any]:
    store = store or HandStore()
    status, payload, _ = _replay(spot)
    if status != "hand_complete":
        raise ValueError("only completed hands can be logged; finish entering the actions")
    store.add(opponent, spot_to_dict(spot))
    return {"logged": True, "opponent_profile": profile_summary(profile_for(store, opponent).snapshot())}


def profile_summary(snapshot) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    stats = {name: {"frequency": round(value.smoothed_frequency, 3), "opportunities": value.opportunities, "confidence": value.confidence}
             for name, value in snapshot.statistics.items()
             if name in ("vpip", "preflop_raise", "limp", "three_bet", "fold_to_raise", "aggressive")}
    streets = {street: {name: {"frequency": round(value.smoothed_frequency, 3), "opportunities": value.opportunities, "confidence": value.confidence}
                        for name, value in values.items() if name in ("bet", "fold_to_bet", "call_vs_bet", "raise_vs_bet")}
               for street, values in snapshot.street_statistics.items()}
    return {"hands_observed": snapshot.hands_observed, "classification": snapshot.classification, "preflop": stats, "postflop": streets}


def spot_to_dict(spot: Spot) -> dict[str, Any]:
    return {
        "hero_cards": list(spot.hero_cards), "board": list(spot.board), "hero_position": spot.hero_position,
        "small_blind": spot.small_blind, "big_blind": spot.big_blind, "hero_stack": spot.hero_stack,
        "villain_stack": spot.villain_stack, "villain_cards": spot.villain_cards,
        "actions": [{"actor": a.actor, "action": a.action, "amount": a.amount} for a in spot.actions],
    }


def spot_from_dict(values: dict[str, Any]) -> Spot:
    return Spot(
        hero_cards=list(values["hero_cards"]), board=list(values.get("board") or []),
        hero_position=values.get("hero_position", "button"), small_blind=int(values.get("small_blind", 50)),
        big_blind=int(values.get("big_blind", 100)), hero_stack=int(values.get("hero_stack", 10_000)),
        villain_stack=int(values.get("villain_stack", 10_000)), villain_cards=values.get("villain_cards"),
        actions=[SpotAction(a["actor"], a["action"], a.get("amount")) for a in values.get("actions") or []],
    )
