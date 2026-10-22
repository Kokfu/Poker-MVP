"""Direct Phase 4F acceptance fixtures for future public turn chance."""
from __future__ import annotations

import math
import random

import pytest

from research.mccfr import external_sampling_regret_updates, external_sampling_strategy_sum_increment
from research.holdem.cfr import HoldemSubgameCFRTrainer
from research.holdem.diagnostics_4f import turn_tree_diagnostics, validate_turn_tree
from research.holdem.turn_exact import reduced_turn_report, reduced_turn_roots
from research.holdem.turn_mccfr import TurnChanceExternalSamplingMCCFRTrainer
from research.holdem.turn_subgame import FIXED_FLOP, TurnHoldemState, turn_chance_states, turn_subgame_convention


def _first(state, action_type):
    return next(action for action in state.legal_actions if action.action_type == action_type)


def _to_turn_after_checks(state):
    return state.apply(_first(state, "check")).apply(_first(state.apply(_first(state, "check")), "check"))


def _assert_profiles_close(first, second):
    assert first.keys() == second.keys()
    for key in first:
        assert first[key] == pytest.approx(second[key], abs=1e-12)


def test_turn_card_removal_is_conditional_uniform_and_does_not_leak_hidden_cards():
    first = TurnHoldemState(("Ah", "Ad"), ("Kh", "Kc"))
    second = TurnHoldemState(("Ah", "Ad"), ("Qs", "Js"))
    chance = _to_turn_after_checks(first)
    cards = chance.remaining_turn_cards()
    assert chance.chance and cards == ("Qs", "Js", "Ts")
    assert all(card not in set(FIXED_FLOP + first.player0_cards + first.player1_cards) for card in cards)
    assert [probability for _, _, probability in chance.chance_outcomes()] == pytest.approx([1 / 3] * 3)
    assert sum(probability for _, _, probability in chance.chance_outcomes()) == pytest.approx(1.0)
    # Different hidden opponent cards alter the physical turn set but cannot
    # alter Player 0's earlier visible flop information set.
    assert first.remaining_turn_cards() != second.remaining_turn_cards()
    assert first.information_set() == second.information_set()
    assert all(card not in first.information_set() for card in first.remaining_turn_cards())


def test_turn_is_public_only_after_chance_and_phase_4c_updates_its_visible_bucket():
    root = TurnHoldemState(("Qs", "Js"), ("Ah", "Ad"))
    chance = _to_turn_after_checks(root)
    children = {card: child for card, child, _ in chance.chance_outcomes()}
    assert root.decision_state().board_cards == FIXED_FLOP
    assert children["Ts"].decision_state().board_cards == FIXED_FLOP + ("Ts",)
    assert children["Kh"].decision_state().board_cards == FIXED_FLOP + ("Kh",)
    assert children["Ts"].information_set() != children["Kh"].information_set()
    assert all(card not in root.information_set() for card in root.remaining_turn_cards())


def test_street_transition_preserves_pot_stacks_and_street_local_total_targets():
    root = turn_chance_states()[0]
    opened = root.apply(_first(root, "bet"))
    chance = opened.apply(_first(opened, "call"))
    assert chance.chance and not chance.terminal
    turn = chance.chance_outcomes()[0][1]
    decision = turn.decision_state()
    assert decision.street == "turn"
    assert decision.pot == 200 and decision.hero_stack == decision.opponent_stack == 50
    assert decision.hero_street_commitment == decision.opponent_street_commitment == 0
    assert decision.maximum_legal_target == 50
    assert all(action.target_total is None or action.target_total <= 50 for action in turn.legal_actions)
    all_in = turn.apply(_first(turn, "all_in"))
    called = all_in.apply(_first(all_in, "call"))
    assert called.terminal and not called.legal_actions
    # A flop all-in call is terminal and cannot incorrectly create a turn node.
    flop_all_in = root.apply(_first(root, "all_in"))
    assert flop_all_in.apply(_first(flop_all_in, "call")).terminal


def test_larger_tree_is_guarded_and_reduced_exact_control_is_deterministic_zero_sum():
    report = turn_tree_diagnostics()
    assert report["bounded"] and report["full_tree_node_count"] == 70_560
    assert report["chance_nodes"] == 1_050 and report["information_sets_by_street"] == {"flop": 56, "turn": 190}
    assert validate_turn_tree() == []
    forward = HoldemSubgameCFRTrainer(roots=reduced_turn_roots()).train(10)
    reverse = HoldemSubgameCFRTrainer(roots=reduced_turn_roots(reverse_turn_order=True)).train(10)
    _assert_profiles_close(forward.average_strategy(), reverse.average_strategy())
    exact = reduced_turn_report(10)
    metrics = exact["metrics"]
    assert exact["scope"].startswith("reduced exact") and exact["information_sets"] == 6
    assert metrics["player0_ev"] == pytest.approx(-metrics["player1_ev"])
    assert metrics["br1_as_u0"] <= metrics["player0_ev"] <= metrics["br0"]
    assert metrics["exploitability"] == pytest.approx(metrics["nashconv"] / 2)


def test_future_turn_external_sampling_is_once_per_reached_traversal_and_seeded():
    roots = reduced_turn_roots()
    first = TurnChanceExternalSamplingMCCFRTrainer(19, roots=roots).train(30, diagnostic=True)
    second = TurnChanceExternalSamplingMCCFRTrainer(19, roots=roots).train(30, diagnostic=True)
    other = TurnChanceExternalSamplingMCCFRTrainer(20, roots=roots).train(30)
    assert first.last_trajectories == second.last_trajectories
    _assert_profiles_close(first.average_strategy(), second.average_strategy())
    assert first.last_trajectories != other.last_trajectories
    assert sum(first.future_chance_sample_counts.values()) == 60
    assert all(sum("future_chance" in sample for sample in row["opponent_samples"]) == 1
               for row in first.last_trajectories)
    assert all(sample["chance_probability"] == pytest.approx(0.5)
               for row in first.last_trajectories for sample in row["opponent_samples"] if "future_chance" in sample)
    assert any("sampled_future_chance" in row for row in first.last_diagnostic)
    before = random.getstate()
    TurnChanceExternalSamplingMCCFRTrainer(3, roots=roots).train(5)
    assert random.getstate() == before


def test_expected_future_chance_regret_and_average_estimators_equal_exact_frozen_tree():
    """Exhaustively weight both real turn cards and frozen opponent branches.

    The reduced configuration forces flop check/check, then uses the actual
    two-card turn chance and Phase 4C turn actions.  At each turn, Player 0
    compares check/bet while Player 1's check/bet or fold/call branch is
    sampled uniformly.  Any sampled bet after Player 0 checks is resolved by
    Player 0's frozen uniform fold/call continuation.  This independently
    enumerates the same tiny full tree used by the exact control.
    """
    chance = _to_turn_after_checks(reduced_turn_roots()[0].base)
    root_strategy = {"check": 0.5, "bet": 0.5}
    expected = {action: 0.0 for action in root_strategy}
    exact = {action: 0.0 for action in root_strategy}
    average_expected = {action: 0.0 for action in root_strategy}
    average_exact = {action: 0.0 for action in root_strategy}
    trajectories = 0
    for _, turn, chance_probability in chance.chance_outcomes():
        check = _first(turn, "check")
        bet = _first(turn, "bet")
        after_check = turn.apply(check)
        after_bet = turn.apply(bet)
        check_values = []
        for opponent in (action for action in after_check.legal_actions
                         if action.action_type == "check" or action.label == "bet_half_pot"):
            child = after_check.apply(opponent)
            if child.terminal:
                check_values.append(child.utility_p0())
            else:  # frozen uniform fold/call response to the sampled bet
                check_values.append(sum(response_probability * child.apply(response).utility_p0()
                                        for response, response_probability in zip(child.legal_actions, (0.5, 0.5))))
        bet_values = [after_bet.apply(opponent).utility_p0()
                      for opponent in after_bet.legal_actions if opponent.action_type in {"fold", "call"}]
        assert len(check_values) == len(bet_values) == 2
        full_values = {"check": sum(check_values) / 2, "bet": sum(bet_values) / 2}
        full_value = sum(root_strategy[action] * full_values[action] for action in root_strategy)
        for action in root_strategy:
            exact[action] += chance_probability * (full_values[action] - full_value)
            average_exact[action] += chance_probability * root_strategy[action]
        for check_value in check_values:
            for bet_value in bet_values:
                sampled = external_sampling_regret_updates(root_strategy, {"check": check_value, "bet": bet_value})
                probability = chance_probability * 0.5 * 0.5
                for action in root_strategy:
                    expected[action] += probability * sampled[action]
                    average_expected[action] += probability * external_sampling_strategy_sum_increment(root_strategy, 1.0, 1.0)[action]
                trajectories += 1
    assert trajectories == 8
    assert expected == pytest.approx(exact, abs=1e-12)
    assert average_expected == pytest.approx(average_exact, abs=1e-12)
    assert all(math.isfinite(value) for value in (*expected.values(), *average_expected.values()))


def test_convention_explicitly_excludes_river_and_full_game_claims():
    convention = turn_subgame_convention()
    assert convention["river"] == "absent"
    assert "not full heads-up no-limit Hold'em" in convention["scope"]
