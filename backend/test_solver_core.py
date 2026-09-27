"""Phase 5 solver core: combos, equity matrices, trees, and range CFR."""
import random
from itertools import combinations

import numpy as np
import pytest

from poker_analyzer import EVALUATOR, FULL_DECK
from solver.cfr import RangeSolver
from solver.combos import (
    CLASS_COMBO_COUNT, COMBO_CLASS, COMBO_COUNT, COMBOS, HAND_CLASSES, card_mask, combo_index, compatible, hand_class,
)
from solver.equity import equity_matrix, runout_boards
from solver.tree import POSTFLOP_MENU, PREFLOP_MENU, SizeMenu, StreetState, StreetTree, legal_abstract_actions


def test_combo_tables():
    assert COMBO_COUNT == 1326 and len(HAND_CLASSES) == 169
    assert CLASS_COMBO_COUNT.sum() == 1326
    assert CLASS_COMBO_COUNT[HAND_CLASSES.index("AA")] == 6
    assert CLASS_COMBO_COUNT[HAND_CLASSES.index("AKs")] == 4
    assert CLASS_COMBO_COUNT[HAND_CLASSES.index("AKo")] == 12
    assert hand_class(("Kd", "As")) == "AKo" and hand_class(("7h", "7c")) == "77"
    assert COMBOS[combo_index(("Kd", "As"))] in (("As", "Kd"), ("Kd", "As"))
    assert all(HAND_CLASSES[COMBO_CLASS[i]] == hand_class(COMBOS[i]) for i in range(0, COMBO_COUNT, 37))


def test_compatibility_and_card_masks():
    rng = random.Random(3)
    rows = np.array(rng.sample(range(COMBO_COUNT), 60))
    cols = np.array(rng.sample(range(COMBO_COUNT), 70))
    matrix = compatible(rows, cols)
    for i, a in enumerate(rows):
        for j, b in enumerate(cols):
            assert matrix[i, j] == (not set(COMBOS[a]) & set(COMBOS[b]))
    mask = card_mask(["As", "Kd"])
    assert mask.sum() == 101  # 51 + 51 - 1 shared combo
    assert all(mask[i] == bool({"As", "Kd"} & set(COMBOS[i])) for i in range(COMBO_COUNT))


def test_river_matrix_matches_reference_evaluator():
    board = ["As", "Kd", "7c", "2h", "9s"]
    rng = random.Random(8)
    live = np.where(~card_mask(board))[0]
    rows = np.array(sorted(rng.sample(list(live), 40)))
    cols = np.array(sorted(rng.sample(list(live), 40)))
    d, compat = equity_matrix(board, rows, cols)
    for i, a in enumerate(rows):
        for j, b in enumerate(cols):
            if not compat[i, j]:
                assert d[i, j] == 0 and set(COMBOS[a]) & set(COMBOS[b])
                continue
            first, second = EVALUATOR.score(list(COMBOS[a]), board), EVALUATOR.score(list(COMBOS[b]), board)
            assert d[i, j] == (1 if first < second else -1 if first > second else 0)


def test_turn_matrix_is_exact_average_over_rivers():
    board = ["Qs", "Jd", "4c", "4h"]
    a, b = combo_index(("As", "Ks")), combo_index(("9h", "9d"))
    d, compat = equity_matrix(board, np.array([a]), np.array([b]))
    total = count = 0
    for river in FULL_DECK:
        if river in board or river in COMBOS[a] or river in COMBOS[b]:
            continue
        full = board + [river]
        first, second = EVALUATOR.score(list(COMBOS[a]), full), EVALUATOR.score(list(COMBOS[b]), full)
        total += (first < second) - (first > second)
        count += 1
    assert compat[0, 0] and d[0, 0] == pytest.approx(total / count)


def test_runout_sampling_is_deterministic_and_complete():
    assert len(runout_boards(["As", "Kd", "7c", "2h"], None)) == 48
    assert len(runout_boards(["As", "Kd", "7c"], None)) == 1176
    assert runout_boards(["As", "Kd", "7c"], 30) == runout_boards(["As", "Kd", "7c"], 30)
    assert all(len(set(board)) == 5 for board in runout_boards([], 200))


def _walk(tree):
    return [node for node in tree.nodes if node.kind == "decision"]


def test_tree_targets_follow_engine_rules():
    root = StreetState("flop", 1, (0, 0), (9_000, 9_000), (1_000, 1_000), 100)
    tree = StreetTree(root, POSTFLOP_MENU)
    for node in _walk(tree):
        state = node.state
        minimum = state.highest + state.last_full_raise
        for kind, target in node.actions:
            if kind in ("bet", "raise"):
                assert minimum <= target < state.commit[node.player] + state.stack[node.player]
            if kind == "fold":
                assert state.highest > state.commit[node.player]
    for node in tree.nodes:
        if node.kind == "leaf":
            assert node.contribution[0] == node.contribution[1]
        if node.kind != "decision":
            assert sum(node.contribution) <= 20_000


def test_preflop_limp_lets_big_blind_act_and_check_closes():
    root = StreetState("preflop", 0, (50, 100), (9_950, 9_900), (0, 0), 100)
    tree = StreetTree(root, PREFLOP_MENU)
    after_limp = tree.nodes[tree.nodes[tree.root].children[tree.nodes[tree.root].labels.index("call")]]
    assert after_limp.kind == "decision" and after_limp.player == 1 and "check" in after_limp.labels
    closed = tree.nodes[after_limp.children[after_limp.labels.index("check")]]
    assert closed.kind == "leaf" and closed.contribution == (100, 100)


def test_short_stack_offers_only_all_in_above_call():
    state = StreetState("turn", 0, (0, 300), (250, 5_000), (500, 500), 100)
    labels = [label for label, _, _ in legal_abstract_actions(state, POSTFLOP_MENU)]
    assert labels == ["fold", "call"]  # 250 behind cannot even cover the 300 bet
    state = StreetState("turn", 0, (0, 100), (400, 5_000), (500, 500), 100)
    labels = [label for label, _, _ in legal_abstract_actions(state, POSTFLOP_MENU)]
    assert labels[:2] == ["fold", "call"] and labels[-1] == "all_in"


def _polarized(iterations):
    root = StreetState("river", 0, (0, 0), (100, 100), (50, 50), 10)
    tree = StreetTree(root, SizeMenu(by_depth=((1.0,),), all_in_merge=1.01))
    solver = RangeSolver(tree, (np.array([0.5, 0.5]), np.array([1.0])), np.array([[1.0], [-1.0]]), np.ones((2, 1), bool))
    return solver, solver.solve(iterations, measure=True)


def test_cfr_recovers_textbook_river_equilibrium():
    solver, result = _polarized(3_000)
    root = result.tree.nodes[result.tree.root]
    bet = root.labels.index("all_in")
    assert result.average[root.index][bet, 0] == pytest.approx(1.0, abs=0.01)   # nuts always bet
    assert result.average[root.index][bet, 1] == pytest.approx(0.5, abs=0.02)   # air bluffs half
    facing = result.tree.nodes[root.children[bet]]
    assert result.average[facing.index][facing.labels.index("call"), 0] == pytest.approx(0.5, abs=0.02)
    assert solver.expected_values()[0] == pytest.approx(25.0, abs=0.5)
    assert result.exploitability < 0.1


def test_cfr_exploitability_shrinks():
    early = _polarized(20)[1].exploitability
    late = _polarized(2_000)[1].exploitability
    assert late < early and late < 0.1


def test_fit_frequencies_matches_targets_and_keeps_ordering():
    from solver.cfr import fit_frequencies
    sigma = np.array([[0.9, 0.5, 0.1], [0.1, 0.5, 0.9]])  # combo 0 prefers action 0
    reach = np.array([1.0, 1.0, 1.0])
    fitted = fit_frequencies(sigma, reach, np.array([0.2, 0.8]))
    assert np.allclose(fitted.sum(axis=0), 1.0)
    assert (fitted * reach).sum(axis=1)[0] / reach.sum() == pytest.approx(0.2, abs=0.01)
    assert fitted[0, 0] > fitted[0, 1] > fitted[0, 2]  # ordering preserved


def test_node_lock_produces_exploitative_response():
    root = StreetState("river", 0, (0, 0), (100, 100), (50, 50), 10)
    tree = StreetTree(root, SizeMenu(by_depth=((1.0,),), all_in_merge=1.01))
    facing = tree.nodes[tree.nodes[tree.root].children[tree.nodes[tree.root].labels.index("all_in")]]
    call = facing.labels.index("call")
    fold = facing.labels.index("fold")
    solver = RangeSolver(tree, (np.array([0.5, 0.5]), np.array([1.0])), np.array([[1.0], [-1.0]]), np.ones((2, 1), bool),
                         locks={facing.index: (1.0, (((call,), 1.0), ((fold,), 0.0)))})
    result = solver.solve(2_000)
    bet = tree.nodes[tree.root].labels.index("all_in")
    assert result.average[tree.root][bet, 0] == pytest.approx(1.0, abs=0.02)  # value bet the nuts
    assert result.average[tree.root][bet, 1] < 0.05  # never bluff a calling station
    assert result.average[facing.index][call, 0] > 0.9  # locked play is reported
