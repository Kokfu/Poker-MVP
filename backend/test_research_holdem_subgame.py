import pytest

from research.holdem.cfr import HoldemSubgameCFRTrainer
from research.holdem.diagnostics_4d import tree_diagnostics, validate_tree
from research.holdem.reduced_exact import exact_metrics, reduced_roots
from research.holdem.subgame import HoldemSubgameState, chance_states, subgame_convention


def _first(state, action_type):
    return next(action for action in state.legal_actions if action.action_type == action_type)


def test_fixed_flop_convention_and_exact_chance_are_bounded_and_collision_free():
    convention = subgame_convention(); outcomes = chance_states(); report = tree_diagnostics()
    assert convention["starting_street"] == "flop" and convention["future_cards"] is False
    assert len(outcomes) == 90 and len(outcomes) == len(set(outcomes))
    assert all(len(set(state.player0_cards + state.player1_cards + ("As", "Kd", "7c"))) == 7 for state in outcomes)
    assert report["bounded"]
    assert {key: report[key] for key in ("chance_nodes", "full_tree_node_count", "information_sets", "terminal_nodes", "max_tree_depth")} == {
        "chance_nodes": 90, "full_tree_node_count": 3510, "information_sets": 56,
        "terminal_nodes": 2250, "max_tree_depth": 4,
    }


def test_information_sets_hide_opponent_cards_but_preserve_visible_abstract_state():
    first, second = chance_states()[0], chance_states()[1]
    assert first.player0_cards == second.player0_cards and first.player1_cards != second.player1_cards
    assert first.information_set() == second.information_set()
    assert first.information_set() != HoldemSubgameState(("Qs", "Js"), ("Ah", "Ad")).information_set()


def test_every_advertised_phase_4c_action_is_legal_and_terminal_utilities_are_zero_sum():
    assert validate_tree() == []
    root = chance_states()[0]
    # Public actions alternate actors even down the aggressive branches.  This
    # also ensures that the Phase 4C decision boundary receives the next
    # player's cards and legal response set, rather than reusing the bettor.
    opened = root.apply(_first(root, "bet"))
    assert root.acting_player == 0 and opened.acting_player == 1
    assert opened.decision_state().acting_player == "1"
    reraised = opened.apply(_first(opened, "all_in"))
    assert reraised.acting_player == 0
    assert reraised.decision_state().acting_player == "0"
    folded = root.apply(_first(root, "all_in")).apply(_first(root.apply(_first(root, "all_in")), "fold"))
    called = opened.apply(_first(opened, "call"))
    assert folded.terminal and called.terminal
    assert folded.utility(0) == -folded.utility(1) and called.utility(0) == -called.utility(1)


def test_every_terminal_in_the_derived_tree_is_zero_sum():
    terminals = []
    def visit(state):
        if state.terminal:
            terminals.append(state)
            return
        for action in state.legal_actions:
            visit(state.apply(action))

    for root in chance_states():
        visit(root)
    assert len(terminals) == 2250
    assert all(state.utility(0) == -state.utility(1) for state in terminals)


def test_vanilla_and_cfr_plus_are_frozen_deterministic_and_plus_truncates():
    vanilla_a = HoldemSubgameCFRTrainer("vanilla").train(10)
    vanilla_b = HoldemSubgameCFRTrainer("vanilla").train(10)
    plus = HoldemSubgameCFRTrainer("cfr_plus").train(10)
    assert vanilla_a.strategy_table() == vanilla_b.strategy_table()
    assert vanilla_a.strategy_document() == vanilla_b.strategy_document()
    assert vanilla_a.last_frozen_profile
    assert any(value < 0 for node in vanilla_a.infosets.values() for value in node.regrets.values())
    assert all(value >= 0 for node in plus.infosets.values() for value in node.regrets.values())
    assert all(sum(row["average_strategy"].values()) == pytest.approx(1) for row in plus.strategy_table())


def test_chance_order_and_repeated_training_do_not_change_accumulated_results():
    forward = HoldemSubgameCFRTrainer("vanilla").train(3)
    reverse = HoldemSubgameCFRTrainer("vanilla")
    # Construction canonicalizes roots for deterministic traversal, so reverse
    # the already-built order to exercise the actual per-iteration deal loop.
    reverse.roots = tuple(reversed(reverse.roots))
    reverse.train(3)
    assert forward.infosets.keys() == reverse.infosets.keys()
    for key, node in forward.infosets.items():
        other = reverse.infosets[key]
        assert node.player == other.player and node.actions == other.actions and node.visits == other.visits
        # Summation order may differ at binary floating-point roundoff only.
        assert node.regrets == pytest.approx(other.regrets, abs=1e-12)
        assert node.strategy_sum == pytest.approx(other.strategy_sum, abs=1e-12)


def test_reduced_holdem_exact_br_validation_respects_hidden_card_information_sets():
    roots = reduced_roots()
    # Distinct chance deals sharing the quoted player's visible state must
    # share their information set despite different opponent cards.
    assert roots[0].information_set() == roots[2].information_set()
    after_check_a = roots[0].apply(_first(roots[0], "check"))
    after_check_b = roots[1].apply(_first(roots[1], "check"))
    assert after_check_a.information_set() == after_check_b.information_set()
    trainer = HoldemSubgameCFRTrainer("vanilla", roots=roots).train(10)
    assert sum(node.player == 0 for node in trainer.infosets.values()) == 2
    assert sum(node.player == 1 for node in trainer.infosets.values()) == 4
    assert all(len(node.actions) == 2 for node in trainer.infosets.values())
    metrics = exact_metrics(trainer)
    assert metrics["br1_as_u0"] <= metrics["player0_ev"] <= metrics["br0"]
    assert metrics["nashconv"] == pytest.approx(metrics["br0"] - metrics["br1_as_u0"])
    assert metrics["exploitability"] == pytest.approx(metrics["nashconv"] / 2)
