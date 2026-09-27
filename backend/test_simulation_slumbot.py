"""Phase 5A Slumbot bridge, validated against an independent fake server.

``FakeSlumbot`` is a separate, deliberately simple no-limit referee that speaks
Slumbot's protocol and plays random legal actions.  Agreement between it and
the authoritative HandEngine (zero desyncs, zero server rejections, identical
settlements) is evidence that the bridge maps actions, seats, boards, and
all-ins correctly.  No network is used.
"""
import random

import pytest

from poker_analyzer import EVALUATOR, FULL_DECK
from simulation.actions import Action
from simulation.bots import BOT_TYPES
from simulation.slumbot import (
    SLUMBOT_BIG_BLIND, SLUMBOT_SMALL_BLIND, SLUMBOT_STACK, SlumbotClient,
    SlumbotProtocolError, parse_actions, play_slumbot_hand, run_slumbot_session,
)


class FakeSlumbot:
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.hand_count = 0
        self.errors: list[str] = []
        self.client_totals: list[int] = []

    # --- protocol -------------------------------------------------------
    def post(self, path, body):
        if path == "/api/new_hand":
            self._deal()
            self._bot_turns()
            return self._response()
        if path == "/api/act":
            if body.get("token") != "tok" or self.over or self.to_act != self.client:
                return self._error("not your turn")
            error = self._apply(self.client, body["incr"])
            if error:
                return self._error(error)
            self._bot_turns()
            return self._response()
        return self._error("unknown path")

    def _error(self, message):
        self.errors.append(message)
        return {"error_msg": message}

    def _response(self):
        shown = 5 if self.runout else (0, 3, 4, 5)[self.street]
        response = {"token": "tok", "action": self.action, "client_pos": self.client, "hole_cards": self.holes[self.client], "board": self.board[:shown]}
        if self.over:
            response["winnings"] = self.winnings
            if self.showdown:
                response["bot_hole_cards"] = self.holes[1 - self.client]
        return response

    # --- referee (pos 1 = small blind/button, pos 0 = big blind) ---------
    def _deal(self):
        deck = list(FULL_DECK)
        self.rng.shuffle(deck)
        self.client = self.hand_count % 2
        self.hand_count += 1
        self.holes = {0: deck[0:2], 1: deck[2:4]}
        self.board = deck[4:9]
        self.stacks = {0: SLUMBOT_STACK - SLUMBOT_BIG_BLIND, 1: SLUMBOT_STACK - SLUMBOT_SMALL_BLIND}
        self.bets = {0: SLUMBOT_BIG_BLIND, 1: SLUMBOT_SMALL_BLIND}
        self.totals = dict(self.bets)
        self.street, self.to_act, self.last_raise = 0, 1, SLUMBOT_BIG_BLIND
        self.acted = {0: False, 1: False}
        self.action, self.over, self.showdown, self.runout, self.winnings = "", False, False, False, None

    def _legal(self, player):
        other = 1 - player
        legal = ["f"] if self.bets[other] > self.bets[player] else ["k"]
        if self.bets[other] > self.bets[player]:
            legal.append("c")
        top = self.bets[player] + self.stacks[player]
        if top > self.bets[other] and self.stacks[other] > 0:
            minimum = min(self.bets[other] + self.last_raise, top)
            pot = sum(self.totals.values())
            for size in {minimum, self.bets[other] + pot, top}:
                if minimum <= size <= top:
                    legal.append(f"b{size}")
        return legal

    def _apply(self, player, incr):
        other = 1 - player
        if incr == "f":
            if self.bets[other] <= self.bets[player]:
                return "cannot fold"
            self.action += "f"
            return self._finish(winner=other)
        if incr == "k":
            if self.bets[other] != self.bets[player]:
                return "cannot check"
            self.action += "k"
        elif incr == "c":
            if self.bets[other] <= self.bets[player]:
                return "nothing to call"
            amount = min(self.bets[other] - self.bets[player], self.stacks[player])
            self._put(player, amount)
            self.action += "c"
        elif incr.startswith("b"):
            target = int(incr[1:])
            top = self.bets[player] + self.stacks[player]
            if target > top or target <= self.bets[other]:
                return "bad bet size"
            if target - self.bets[other] < self.last_raise and target != top:
                return "raise too small"
            self.last_raise = max(self.last_raise, target - self.bets[other])
            self._put(player, target - self.bets[player])
            self.action += incr
        else:
            return "bad incr"
        self.acted[player] = True
        closed = self.bets[0] == self.bets[1] and self.acted[0] and self.acted[1]
        closed = closed or (incr == "c" and not (self.street == 0 and player == 1 and not self.acted[0]))
        if incr == "c" and self.stacks[player] == 0 and self.bets[player] < self.bets[other]:
            closed = True
        if not closed:
            self.to_act = other
            return None
        if 0 in self.stacks.values():
            self.runout = True
            self.action += "/" * (3 - self.street)
            return self._finish(winner=None)
        if self.street == 3:
            return self._finish(winner=None)
        self.street += 1
        self.action += "/"
        self.bets, self.acted, self.last_raise, self.to_act = {0: 0, 1: 0}, {0: False, 1: False}, SLUMBOT_BIG_BLIND, 0
        return None

    def _put(self, player, amount):
        self.stacks[player] -= amount
        self.bets[player] += amount
        self.totals[player] += amount

    def _finish(self, winner):
        self.over = True
        # Return any unmatched excess before settlement.
        matched = min(self.totals.values())
        if winner is None:
            self.showdown = True
            scores = {p: EVALUATOR.score(self.holes[p], self.board) for p in (0, 1)}
            winner = None if scores[0] == scores[1] else min(scores, key=scores.get)
        client_paid = min(self.totals[self.client], matched) if winner is not None else 0
        self.winnings = 0 if winner is None else (matched if winner == self.client else -client_paid)
        if winner is not None and winner != self.client:
            self.winnings = -min(self.totals[self.client], matched) if self.showdown else -self.totals[self.client]
        if winner == self.client and not self.showdown:
            self.winnings = self.totals[1 - self.client]
        self.client_totals.append(self.winnings)
        return None

    def _bot_turns(self):
        while not self.over and self.to_act != self.client:
            choice = self.rng.choice(self._legal(self.to_act))
            assert self._apply(self.to_act, choice) is None


def client(seed=0):
    return SlumbotClient(FakeSlumbot(seed), token="tok")


def test_parse_actions_handles_streets_bets_and_runouts():
    assert parse_actions("b300c/kb200c/kk/") == [(0, "b300"), (0, "c"), (1, "k"), (1, "b200"), (1, "c"), (2, "k"), (2, "k")]
    assert parse_actions("b20000c///") == [(0, "b20000"), (0, "c")]
    with pytest.raises(SlumbotProtocolError):
        parse_actions("b/")


def test_server_errors_raise():
    fake = FakeSlumbot()
    session = SlumbotClient(fake, token="tok")
    session.new_hand()
    with pytest.raises(SlumbotProtocolError):
        session.act("zz")


@pytest.mark.parametrize("bot", ["random", "aggressive", "tight", "equity", "expert", "adaptive"])
def test_bridge_stays_in_sync_with_independent_referee(bot):
    fake = FakeSlumbot(seed=len(bot))
    session = SlumbotClient(fake, token="tok")
    results, summary = run_slumbot_session(lambda i: BOT_TYPES[bot](seed=i, equity_iterations=50), 150, session)
    assert fake.errors == []
    assert summary["desyncs"] == 0, [r.desync for r in results if r.desync]
    assert summary["settlement_mismatches"] == 0
    assert all(r.settlement_verified for r in results)
    assert [r.winnings for r in results] == fake.client_totals
    assert {r.client_position for r in results} == {"button", "big_blind"}


def test_range_expert_bridge_sync():
    fake = FakeSlumbot(seed=99)
    results, summary = run_slumbot_session(lambda i: BOT_TYPES["range_expert"](seed=i, equity_iterations=50), 25, SlumbotClient(fake, token="tok"))
    assert fake.errors == [] and summary["desyncs"] == 0 and summary["settlement_mismatches"] == 0


class IllegalBot:
    """Always requests an impossible raise; the bridge must legalize it."""
    def decide(self, observation):
        return Action("raise", 10**9)


def test_illegal_requests_are_legalized_before_sending():
    fake = FakeSlumbot(seed=5)
    results, summary = run_slumbot_session(lambda i: IllegalBot(), 40, SlumbotClient(fake, token="tok"))
    assert fake.errors == [] and summary["desyncs"] == 0 and summary["settlement_mismatches"] == 0
