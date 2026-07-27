from __future__ import annotations

import random
import time
import uuid

from poker_analyzer import EVALUATOR

from .actions import Action
from .cards import Deck
from .dataset import JsonlDataset, SCHEMA_VERSION
from .game_state import GameState, Observation
from .history import (
    HISTORY_SCHEMA_VERSION,
    HandHistory,
    HandHistoryEvent,
)
from .statistics import Statistics


class HandEngine:
    """Authoritative local heads-up engine. Actions use target commitments."""

    def __init__(
        self,
        bot_a,
        bot_b,
        stack=10000,
        bb=100,
        seed=None,
        hand_id="hand-0",
        button="a",
        dataset=None,
        simulation_id="local",
        hand_number=1,
        simulation_seed=None,
        starting_stacks=None,
        small_blind=None,
        match_id=None,
    ):
        initial_stacks = (
            {"a": stack, "b": stack}
            if starting_stacks is None
            else dict(starting_stacks)
        )
        if set(initial_stacks) != {"a", "b"} or any(
            type(value) is not int or value < 0 for value in initial_stacks.values()
        ):
            raise ValueError(
                "starting_stacks must contain non-negative integer stacks for a and b"
            )
        if type(bb) is not int or bb <= 0:
            raise ValueError("bb must be a positive integer")
        sb = bb // 2 if small_blind is None else small_blind
        if type(sb) is not int or sb <= 0 or sb > bb:
            raise ValueError(
                "small_blind must be a positive integer no greater than bb"
            )

        self.bots = {"a": bot_a, "b": bot_b}
        self.bb = bb
        self.sb = sb
        self.hand_seed = seed
        self.deck = Deck(seed)
        self.holes = {"a": self.deck.deal(2), "b": self.deck.deal(2)}
        self.dataset = dataset or JsonlDataset()
        self.state = GameState(
            hand_id,
            button,
            button,
            stacks=dict(initial_stacks),
            current_bets={"a": 0, "b": 0},
            minimum_raise=bb,
            current_highest_bet=0,
            last_full_raise_size=bb,
            pending_players=set(),
            acted_since_full_raise={"a": False, "b": False},
            raising_reopened={"a": True, "b": True},
        )
        self.total = sum(initial_stacks.values())
        self.starting_stacks = dict(initial_stacks)
        self.folded = None
        self.illegal = 0
        self.illegal_diagnostics = []
        self.simulation_id = simulation_id
        self.simulation_seed = simulation_seed
        self.hand_number = hand_number
        self._records = []
        self.showdown_count = 0
        self.settlement_count = 0
        self._automatic_runout_recorded = False
        self.history = HandHistory(
            history_schema_version=HISTORY_SCHEMA_VERSION,
            hand_id=hand_id,
            match_id=match_id,
            hand_number=hand_number,
            hand_seed=seed,
            simulation_seed=simulation_seed,
            button_player=button,
            small_blind_player=button,
            big_blind_player=self.other(button),
            small_blind_amount=sb,
            big_blind_amount=bb,
            starting_stack_a=initial_stacks["a"],
            starting_stack_b=initial_stacks["b"],
        )

        initial = self._snapshot()
        self._emit_history("hand_started", initial)
        self._post_blind(button, self.sb, "small_blind")
        self._post_blind(self.other(button), self.bb, "big_blind")

        opponent = self.other(button)
        if self.state.stacks[button] > 0 and (
            self.state.stacks[opponent] > 0
            or self.state.current_bets[button] < self.state.current_highest_bet
        ):
            self.state.pending_players = {button}
        self.state.amount_to_call = (
            self.state.current_highest_bet - self.state.current_bets[button]
        )
        if not self.state.pending_players and any(
            stack == 0 for stack in self.state.stacks.values()
        ):
            self._return_unmatched_excess()

    def other(self, player):
        return "b" if player == "a" else "a"

    def _snapshot(self):
        return {
            "street": self.state.street,
            "board": list(self.state.community_cards),
            "pot": self.state.pot,
            "stack_a": self.state.stacks["a"],
            "stack_b": self.state.stacks["b"],
            "commitment_a": self.state.current_bets["a"],
            "commitment_b": self.state.current_bets["b"],
            "current_highest_bet": self.state.current_highest_bet,
            "settlement_complete": (
                self.state.street == "complete"
                and self.state.pot == 0
                and self.state.current_bets == {"a": 0, "b": 0}
                and not self.state.pending_players
                and self.state.acting_player is None
            ),
        }

    def _emit_history(self, event_type, before=None, actor=None, **details):
        before = before or self._snapshot()
        after = self._snapshot()
        event = HandHistoryEvent(
            event_index=len(self.history.events),
            event_type=event_type,
            street=after["street"],
            actor=actor,
            board=after["board"],
            pot_before=before["pot"],
            pot_after=after["pot"],
            stack_a_before=before["stack_a"],
            stack_a_after=after["stack_a"],
            stack_b_before=before["stack_b"],
            stack_b_after=after["stack_b"],
            street_commitment_a_before=before["commitment_a"],
            street_commitment_a_after=after["commitment_a"],
            street_commitment_b_before=before["commitment_b"],
            street_commitment_b_after=after["commitment_b"],
            current_highest_bet_before=before["current_highest_bet"],
            current_highest_bet_after=after["current_highest_bet"],
            settlement_complete=after["settlement_complete"],
            **details,
        )
        self.history.append(event)
        return event

    def _commit(self, player, amount, kind):
        amount = min(amount, self.state.stacks[player])
        self.state.stacks[player] -= amount
        self.state.current_bets[player] += amount
        self.state.pot += amount
        if kind != "blind":
            self.state.action_history.append(
                {"player": player, "type": kind, "amount": amount}
            )
        return amount

    def _post_blind(self, player, assigned_amount, blind_type):
        before = self._snapshot()
        posted = self._commit(player, assigned_amount, "blind")
        self.state.current_highest_bet = max(self.state.current_bets.values())
        self._emit_history(
            "blind_posted",
            before,
            actor=player,
            blind_type=blind_type,
            assigned_amount=assigned_amount,
            posted_amount=posted,
            post_was_all_in=self.state.stacks[player] == 0,
        )

    def _return_unmatched_excess(self):
        a_commitment = self.state.current_bets["a"]
        b_commitment = self.state.current_bets["b"]
        if a_commitment == b_commitment:
            return 0
        covering, short = (
            ("a", "b") if a_commitment > b_commitment else ("b", "a")
        )
        if self.state.stacks[short] != 0:
            return 0
        excess = (
            self.state.current_bets[covering] - self.state.current_bets[short]
        )
        before = self._snapshot()
        self.state.current_bets[covering] -= excess
        self.state.stacks[covering] += excess
        self.state.pot -= excess
        self.state.current_highest_bet = max(self.state.current_bets.values())
        self._emit_history(
            "unmatched_excess_returned",
            before,
            actor=covering,
            returned_to=covering,
            returned_amount=excess,
        )
        return excess

    def legal(self, player):
        call = (
            self.state.current_highest_bet - self.state.current_bets[player]
        )
        stack = self.state.stacks[player]
        if call == 0:
            actions = ["check"]
            if not stack or not self.state.raising_reopened[player]:
                return actions
            if self.state.current_highest_bet == 0:
                return actions + ["bet", "all_in"]
            maximum = self.state.current_bets[player] + stack
            minimum = (
                self.state.current_highest_bet + self.state.last_full_raise_size
            )
            if maximum >= minimum:
                actions.append("raise")
            if maximum > self.state.current_highest_bet:
                actions.append("all_in")
            return actions
        actions = ["fold", "call"]
        maximum = self.state.current_bets[player] + stack
        minimum = (
            self.state.current_highest_bet + self.state.last_full_raise_size
        )
        if stack and stack <= call:
            actions = ["fold", "all_in"]
        elif stack > call and self.state.raising_reopened[player]:
            if maximum >= minimum:
                actions += ["raise", "all_in"]
            elif maximum > self.state.current_highest_bet:
                actions += ["all_in"]
        return actions

    def observe(self, player):
        call = (
            self.state.current_highest_bet - self.state.current_bets[player]
        )
        maximum = self.state.current_bets[player] + self.state.stacks[player]
        can_increase = (
            maximum > self.state.current_highest_bet
            and self.state.raising_reopened[player]
        )
        minimum = (
            (
                self.bb
                if self.state.current_highest_bet == 0
                else self.state.current_highest_bet
                + self.state.last_full_raise_size
            )
            if can_increase
            else None
        )
        return Observation(
            self.state.hand_id,
            player,
            "BTN" if self.state.button_player == player else "BB",
            self.state.street,
            list(self.holes[player]),
            list(self.state.community_cards),
            self.state.pot,
            self.state.stacks[player],
            self.state.stacks[self.other(player)],
            self.state.current_bets[player],
            call,
            self.state.last_full_raise_size,
            minimum,
            maximum,
            maximum,
            self.legal(player),
            list(self.state.action_history),
        )

    def _record_illegal(self, diagnostic):
        self.illegal += 1
        self.illegal_diagnostics.append(diagnostic)
        self.state.action_history.append(
            {
                "player": diagnostic["player"],
                "type": "illegal_action",
                "requested": diagnostic["requested"],
            }
        )

    @staticmethod
    def _all_in_classification(
        applied_action,
        target,
        amount_to_call,
        highest_before,
        last_full_raise_before,
    ):
        if applied_action != "all_in":
            return "not_applicable"
        if target < highest_before:
            return "short_call"
        if amount_to_call > 0 and target == highest_before:
            return "exact_call"
        if target > highest_before:
            increment = target - highest_before
            return (
                "full_raise"
                if increment >= last_full_raise_before
                else "short_raise"
            )
        return "non_raising_all_in"

    def _action(self, player, action):
        before = self._snapshot()
        legal = list(self.legal(player))
        observation = self.observe(player)
        requested_action = action.type
        requested_target = action.amount
        applied_action = requested_action
        fallback_reason = None

        if requested_action not in legal:
            applied_action = "check" if "check" in legal else "fold"
            fallback_reason = "ACTION_TYPE_NOT_ALLOWED"
            self._record_illegal(
                {
                    "reason": fallback_reason,
                    "player": player,
                    "requested": requested_action,
                    "target": action.amount,
                    "legal": legal,
                }
            )

        call = (
            self.state.current_highest_bet - self.state.current_bets[player]
        )
        highest_before = self.state.current_highest_bet
        last_full_raise_before = self.state.last_full_raise_size
        raising_before = dict(self.state.raising_reopened)
        pending_before = sorted(self.state.pending_players)
        acting_before = self.state.acting_player
        minimum = observation.minimum_target_to
        maximum = observation.maximum_target_to

        target = None
        if applied_action == "call":
            target = self.state.current_bets[player] + call
        elif applied_action in ("bet", "raise"):
            target = action.amount or 0
        elif applied_action == "all_in":
            target = (
                self.state.current_bets[player] + self.state.stacks[player]
            )

        if applied_action in ("bet", "raise"):
            legal_minimum = (
                self.state.current_highest_bet + self.state.last_full_raise_size
            )
            if (
                target < legal_minimum
                or target
                > self.state.current_bets[player] + self.state.stacks[player]
            ):
                fallback_reason = "TARGET_OUT_OF_RANGE"
                self._record_illegal(
                    {
                        "reason": fallback_reason,
                        "player": player,
                        "requested": applied_action,
                        "target": target,
                        "minimum": legal_minimum,
                        "maximum": self.state.current_bets[player]
                        + self.state.stacks[player],
                    }
                )
                applied_action = "check" if call == 0 else "fold"
                target = None

        return_unmatched_after_action = False
        if applied_action == "fold":
            self.folded = player
            self.state.pending_players.clear()
            self.state.action_history.append({"player": player, "type": "fold"})
        elif applied_action == "check":
            self.state.pending_players.discard(player)
            self.state.acted_since_full_raise[player] = True
            self.state.action_history.append({"player": player, "type": "check"})
        elif applied_action == "call":
            self._commit(player, call, "call")
            self.state.pending_players.discard(player)
            self.state.acted_since_full_raise[player] = True
            other = self.other(player)
            if (
                self.state.street == "preflop"
                and player == self.state.button_player
                and self.state.stacks[other] > 0
                and not self.state.acted_since_full_raise[other]
            ):
                self.state.pending_players.add(other)
        elif applied_action == "all_in" and target <= highest_before:
            self._commit(player, self.state.stacks[player], "all_in")
            self.state.pending_players.discard(player)
            self.state.acted_since_full_raise[player] = True
            return_unmatched_after_action = target < highest_before
        else:
            previous = self.state.current_highest_bet
            increment = target - previous
            self._commit(
                player,
                target - self.state.current_bets[player],
                applied_action,
            )
            self.state.current_highest_bet = target
            full = increment >= self.state.last_full_raise_size
            if full:
                self.state.last_full_raise_size = increment
                self.state.raising_reopened = {"a": True, "b": True}
                self.state.acted_since_full_raise = {"a": False, "b": False}
            self.state.acted_since_full_raise[player] = True
            other = self.other(player)
            self.state.pending_players = {other}
            if not full:
                self.state.raising_reopened[other] = (
                    not self.state.acted_since_full_raise[other]
                )

        if applied_action == "call":
            # A capped or zero-stack call records the actual resulting
            # commitment, never the unreachable theoretical wager.
            target = self.state.current_bets[player]
        amount_paid = (
            before[f"stack_{player}"] - self.state.stacks[player]
        )
        all_in_classification = self._all_in_classification(
            applied_action,
            target,
            call,
            highest_before,
            last_full_raise_before,
        )
        self._emit_history(
            "action_taken",
            before,
            actor=player,
            requested_action=requested_action,
            requested_target_total=requested_target,
            applied_action=applied_action,
            legal_actions=legal,
            fallback_used=fallback_reason is not None,
            fallback_reason=fallback_reason,
            amount_to_call_before=call,
            amount_paid=amount_paid,
            target_total=target,
            minimum_legal_target=minimum,
            maximum_legal_target=maximum,
            action_classification=applied_action,
            all_in_classification=all_in_classification,
            raising_reopened_before=raising_before,
            raising_reopened_after=dict(self.state.raising_reopened),
            last_full_raise_size_before=last_full_raise_before,
            last_full_raise_size_after=self.state.last_full_raise_size,
            pending_players_before=pending_before,
            pending_players_after=sorted(self.state.pending_players),
            acting_player_before=acting_before,
            acting_player_after=self.state.acting_player,
        )
        if return_unmatched_after_action:
            self._return_unmatched_excess()
        return applied_action

    def _decision_record(self, player, observation, action, elapsed):
        target = None
        if action.type == "call":
            target = observation.current_bet + observation.amount_to_call
        elif action.type in ("bet", "raise"):
            target = action.amount
        elif action.type == "all_in":
            target = observation.all_in_target_to
        classification = {
            "fold": "fold",
            "check": "free_check",
            "call": "normal_call",
            "bet": "opening_bet",
            "raise": "full_raise",
        }.get(action.type)
        all_in_classification = None
        if action.type == "all_in":
            if target < self.state.current_highest_bet:
                all_in_classification = "short_all_in_call"
            elif target == self.state.current_highest_bet:
                all_in_classification = "exact_all_in_call"
            elif (
                observation.minimum_target_to is not None
                and target < observation.minimum_target_to
            ):
                all_in_classification = "short_all_in_raise"
            else:
                all_in_classification = "full_all_in_raise"
            classification = all_in_classification
        return {
            "schema_version": SCHEMA_VERSION,
            "simulation_id": self.simulation_id,
            "hand_id": self.state.hand_id,
            "hand_number": self.hand_number,
            "decision_index": len(self._records),
            "seed": self.simulation_seed,
            "bot_name": type(self.bots[player]).__name__,
            "acting_player": player,
            "position": observation.position,
            "street": observation.street,
            "hero_cards": observation.hole_cards,
            "board_cards": observation.community_cards,
            "hero_stack": observation.hero_stack,
            "opponent_stack": observation.opponent_stack,
            "starting_stack": self.starting_stacks[player],
            "big_blind": self.bb,
            "pot": observation.pot,
            "hero_street_commitment": observation.current_bet,
            "opponent_street_commitment": self.state.current_bets[
                self.other(player)
            ],
            "current_highest_bet": self.state.current_highest_bet,
            "amount_to_call": observation.amount_to_call,
            "last_full_raise_size": observation.minimum_raise,
            "raising_reopened": self.state.raising_reopened[player],
            "pending_players": sorted(self.state.pending_players),
            "minimum_target_to": observation.minimum_target_to,
            "maximum_target_to": observation.maximum_target_to,
            "all_in_target_to": observation.all_in_target_to,
            "legal_actions": observation.legal_actions,
            "chosen_action": {"type": action.type, "amount": action.amount},
            "chosen_target_to": target,
            "action_classification": classification,
            "all_in_classification": all_in_classification,
            "decision_time_ms": elapsed,
        }

    def _round(self, first):
        player = first
        acted = []
        while self.folded is None and self.state.pending_players:
            if player not in self.state.pending_players:
                player = self.other(player)
            self.state.acting_player = player
            observation = self.observe(player)
            started = time.perf_counter()
            action = self.bots[player].decide(observation)
            elapsed = (time.perf_counter() - started) * 1000
            self._records.append(
                self._decision_record(player, observation, action, elapsed)
            )
            applied = self._action(player, action)
            acted.append((player, applied, elapsed))
            player = self.other(player)
        return acted

    def _next_street(self):
        transitions = {
            "preflop": ("flop", 3),
            "flop": ("turn", 1),
            "turn": ("river", 1),
        }
        next_street, card_count = transitions[self.state.street]
        before_street = self._snapshot()
        self.state.current_bets = {"a": 0, "b": 0}
        self.state.current_highest_bet = 0
        self.state.last_full_raise_size = self.bb
        self.state.pending_players = (
            {"a", "b"} if all(self.state.stacks.values()) else set()
        )
        self.state.acted_since_full_raise = {"a": False, "b": False}
        self.state.raising_reopened = {"a": True, "b": True}
        self.state.acting_player = self.other(self.state.button_player)
        self.state.street = next_street
        self._emit_history("street_started", before_street)

        before_board = self._snapshot()
        new_cards = self.deck.deal(card_count)
        self.state.community_cards += new_cards
        self._emit_history(
            "board_revealed",
            before_board,
            new_cards=list(new_cards),
        )

    def _record_automatic_runout_if_needed(self):
        if (
            not self._automatic_runout_recorded
            and self.folded is None
            and not self.state.pending_players
            and any(stack == 0 for stack in self.state.stacks.values())
            and self.state.street != "river"
        ):
            snapshot = self._snapshot()
            self._emit_history("automatic_runout_started", snapshot)
            self._automatic_runout_recorded = True

    def _record_showdown(self):
        before_street = self._snapshot()
        self.state.street = "showdown"
        self.state.acting_player = None
        self.state.pending_players.clear()
        self._emit_history("street_started", before_street)
        snapshot = self._snapshot()
        self._emit_history(
            "showdown",
            snapshot,
            revealed_hole_cards={
                "a": list(self.holes["a"]),
                "b": list(self.holes["b"]),
            },
        )

    def _settle(self, winner, showdown):
        ending_type = "showdown" if showdown else "fold"
        history_winner = winner if winner is not None else "tied"
        pot_before_award = self.state.pot
        if winner is None:
            awarded_a = self.state.pot // 2
            awarded_b = self.state.pot - awarded_a
        else:
            awarded_a = self.state.pot if winner == "a" else 0
            awarded_b = self.state.pot if winner == "b" else 0

        before_award = self._snapshot()
        self.state.stacks["a"] += awarded_a
        self.state.stacks["b"] += awarded_b
        self.state.pot = 0
        self._emit_history(
            "pot_awarded",
            before_award,
            winner=history_winner,
            ending_type=ending_type,
            pot_before_award=pot_before_award,
            awarded_to_a=awarded_a,
            awarded_to_b=awarded_b,
        )

        before_settlement = self._snapshot()
        self.state.current_bets = {"a": 0, "b": 0}
        self.state.current_highest_bet = 0
        self.state.pending_players.clear()
        self.state.acting_player = None
        self.state.street = "complete"
        self._emit_history(
            "hand_settled",
            before_settlement,
            winner=history_winner,
            ending_type=ending_type,
            commitments_cleared=True,
            pending_players_cleared=True,
            acting_player_cleared=True,
        )

        self.history.final_stack_a = self.state.stacks["a"]
        self.history.final_stack_b = self.state.stacks["b"]
        self.history.winner = history_winner
        self.history.ending_type = ending_type
        self.history.final_board = list(self.state.community_cards)
        self.history.showdown = showdown
        self.history.settlement_complete = True
        self.history.illegal_action_count = self.illegal
        self.history.fallback_diagnostics = [
            dict(item) for item in self.illegal_diagnostics
        ]

    def play(self):
        decisions = []
        for street in ("preflop", "flop", "turn", "river"):
            if self.folded is not None:
                break
            if street != "preflop":
                self._next_street()
            self._record_automatic_runout_if_needed()
            if not self.state.pending_players:
                continue
            decisions += self._round(
                self.state.button_player
                if street == "preflop"
                else self.other(self.state.button_player)
            )
            self._record_automatic_runout_if_needed()

        if self.folded is not None:
            winner = self.other(self.folded)
            showdown = False
        else:
            self._record_showdown()
            showdown = True
            self.showdown_count += 1
            score_a = EVALUATOR.score(
                self.holes["a"], self.state.community_cards
            )
            score_b = EVALUATOR.score(
                self.holes["b"], self.state.community_cards
            )
            winner = (
                "a"
                if score_a < score_b
                else "b"
                if score_b < score_a
                else None
            )

        self.settlement_count += 1
        self._settle(winner, showdown)
        assert sum(self.state.stacks.values()) == self.total

        for record in self._records:
            player = record["acting_player"]
            net = self.state.stacks[player] - self.starting_stacks[player]
            record.update(
                {
                    "winner": winner,
                    "showdown": showdown,
                    "net_chips": net,
                    "final_reward_bb": net / self.bb,
                    "hand_ended_by": "showdown" if showdown else "fold",
                }
            )
            self.dataset.write(record)
        return {
            "winner": winner,
            "showdown": showdown,
            "stacks": dict(self.state.stacks),
            "illegal_actions": self.illegal,
            "illegal_diagnostics": self.illegal_diagnostics,
            "actions": decisions,
            "state": self.state,
            "history": self.history,
        }


class SimulationRunner:
    def __init__(
        self,
        bot_a,
        bot_b,
        hands=100,
        starting_stack_bb=100,
        seed=None,
        equity_iterations=1000,
        dataset_path=None,
        dataset_overwrite=False,
    ):
        self.bot_a = bot_a
        self.bot_b = bot_b
        self.hands = hands
        self.seed = seed
        self.bb = 100
        self.stack = starting_stack_bb * self.bb
        self.equity_iterations = equity_iterations
        self.dataset = JsonlDataset(dataset_path, dataset_overwrite)

    def run(self, include_hand_results: bool = False):
        rng = random.Random(self.seed)
        stats = Statistics(
            str(uuid.uuid4()),
            self.seed,
            type(self.bot_a).__name__,
            type(self.bot_b).__name__,
            self.bb,
        )
        began = time.perf_counter()
        self.hand_results = []
        self.illegal_diagnostics = []
        for index in range(self.hands):
            engine = HandEngine(
                self.bot_a,
                self.bot_b,
                self.stack,
                self.bb,
                rng.randrange(2**31),
                f"hand-{index}",
                "a" if index % 2 == 0 else "b",
                self.dataset,
                stats.simulation_id,
                index + 1,
                self.seed,
            )
            result = engine.play()
            stats.hands_played += 1
            stats.illegal_actions += result["illegal_actions"]
            self.illegal_diagnostics += [
                {**diagnostic, "hand_number": index + 1}
                for diagnostic in result["illegal_diagnostics"]
            ]
            delta = result["stacks"]["a"] - self.stack
            stats.bot_a_net_chips += delta
            stats.bot_b_net_chips -= delta
            assert -self.stack <= delta <= self.stack
            assert result["stacks"]["b"] - self.stack == -delta
            self.hand_results.append(
                {
                    "hand_number": index + 1,
                    "net_a": delta,
                    "net_b": -delta,
                    "settled_once": (
                        result["state"].pot == 0
                        and not result["state"].pending_players
                    ),
                }
            )
            if result["winner"] == "a":
                stats.bot_a_wins += 1
            elif result["winner"] == "b":
                stats.bot_b_wins += 1
            else:
                stats.ties += 1
            stats.showdowns += int(result["showdown"])
            stats.fold_ended_hands += int(not result["showdown"])
            for player, action, _ in result["actions"]:
                stats.record_action(player, action)
            for _street in {
                item["type"]
                for item in result["state"].action_history
                if item["type"] not in ("blind",)
            }:
                pass
        stats.duration_ms = (time.perf_counter() - began) * 1000
        assert stats.bot_a_net_chips + stats.bot_b_net_chips == 0
        output = stats.as_dict()
        if include_hand_results:
            output["hand_results"] = self.hand_results
        return output
