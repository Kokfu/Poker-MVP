import json
import subprocess
import sys

import pytest

from research.kuhn import cfr
from research.kuhn.cfr import KuhnCFRTrainer, regret_matching
from research.kuhn.evaluation import best_response, expected_value, metrics
from research.kuhn.game import Action, Card, DEALS, KuhnState, TERMINAL_HISTORIES

def pure(actions, selected): return {a: float(a == selected) for a in actions}
def uniform_policy():
    policy = {}
    for histories in ([(), (Action.CHECK, Action.BET)], [(Action.CHECK,), (Action.BET,)]):
        for card in Card:
            for history in histories:
                history_key = "-".join(action.value for action in history)
                actions = (Action.CHECK, Action.BET) if history in ((), (Action.CHECK,)) else (Action.FOLD, Action.CALL)
                policy[f"{card.value}|{history_key}"] = {a: 1 / len(actions) for a in actions}
    return policy

def accumulated_values(trainer):
    return {
        key: (
            {action: value for action, value in node.regrets.items()},
            {action: value for action, value in node.strategy_sum.items()},
        )
        for key, node in trainer.infosets.items()
    }

def assert_accumulated_values_close(left, right):
    assert left.keys() == right.keys()
    for key in left:
        for left_values, right_values in zip(left[key], right[key]):
            assert left_values == pytest.approx(right_values, abs=1e-15)

def test_game_tree_and_terminal_utilities():
    assert len(DEALS) == 6 and all(a != b for a, b in DEALS)
    root = KuhnState((Card.J, Card.Q)); assert root.acting_player == 0 and root.legal_actions == (Action.CHECK, Action.BET)
    assert root.apply(Action.CHECK).legal_actions == (Action.CHECK, Action.BET)
    assert root.apply(Action.BET).legal_actions == (Action.FOLD, Action.CALL)
    assert root.apply(Action.CHECK).apply(Action.BET).legal_actions == (Action.FOLD, Action.CALL)
    assert TERMINAL_HISTORIES == {"check-check", "bet-fold", "bet-call", "check-bet-fold", "check-bet-call"}
    assert KuhnState((Card.K, Card.J), (Action.CHECK, Action.CHECK)).utility_p0() == 1
    assert KuhnState((Card.J, Card.K), (Action.BET, Action.CALL)).utility_p0() == -2
    assert KuhnState((Card.Q, Card.K), (Action.BET, Action.FOLD)).utility_p0() == 1
    assert KuhnState((Card.K, Card.Q), (Action.CHECK, Action.BET, Action.FOLD)).utility_p0() == -1

def test_information_set_privacy():
    a = KuhnState((Card.J, Card.Q)); b = KuhnState((Card.J, Card.K))
    assert a.information_set() == b.information_set() == "J|"
    a = KuhnState((Card.Q, Card.J), (Action.CHECK,)); b = KuhnState((Card.K, Card.J), (Action.CHECK,))
    assert a.information_set() == b.information_set() == "J|check"
    assert "Q" not in KuhnState((Card.J, Card.Q)).information_set()

@pytest.mark.parametrize("regrets, expected", [
    ({Action.CHECK: 0, Action.BET: 0}, (0.5, 0.5)), ({Action.CHECK: -1, Action.BET: -3}, (0.5, 0.5)),
    ({Action.CHECK: 2, Action.BET: -1}, (1, 0)), ({Action.CHECK: 1, Action.BET: 3}, (0.25, 0.75)),
])
def test_regret_matching(regrets, expected):
    result = regret_matching(regrets, (Action.CHECK, Action.BET))
    assert (result[Action.CHECK], result[Action.BET]) == expected and sum(result.values()) == 1

def test_cfr_determinism_diagnostic_and_normalization():
    a = KuhnCFRTrainer().train(1, diagnostic=True); b = KuhnCFRTrainer().train(1, diagnostic=True)
    assert a.last_diagnostic == b.last_diagnostic and len(a.last_diagnostic) > 0
    a.train(100); b.train(100)
    assert a.strategy_table() == b.strategy_table() and len(a.infosets) == 12
    for strategy in a.average_strategy().values(): assert sum(strategy.values()) == pytest.approx(1) and all(0 <= p <= 1 for p in strategy.values())

def test_one_iteration_regrets_and_strategy_sums_match_exact_uniform_fixtures():
    trainer = KuhnCFRTrainer().train(1)
    root_j = trainer.infosets["J|"]
    # With uniform sigma_0, J faces Q and K.  At either root, u(check)=-5/4,
    # u(bet)=-1/2, and u=-7/8, so each chance outcome contributes +/-1/16.
    assert root_j.regrets == pytest.approx({Action.CHECK: -1 / 8, Action.BET: 1 / 8})
    # Root own reach is one; two deals each add (1/6) * (1/2) to each action.
    assert root_j.strategy_sum == pytest.approx({Action.CHECK: 1 / 6, Action.BET: 1 / 6})

def test_one_iteration_is_invariant_to_reversed_chance_deal_order(monkeypatch):
    forward = KuhnCFRTrainer().train(1)
    monkeypatch.setattr(cfr, "DEALS", tuple(reversed(DEALS)))
    reversed_order = KuhnCFRTrainer().train(1)
    assert_accumulated_values_close(accumulated_values(forward), accumulated_values(reversed_order))

def test_multiple_iterations_are_invariant_to_reversed_chance_deal_order(monkeypatch):
    forward = KuhnCFRTrainer().train(25)
    monkeypatch.setattr(cfr, "DEALS", tuple(reversed(DEALS)))
    reversed_order = KuhnCFRTrainer().train(25)
    assert_accumulated_values_close(accumulated_values(forward), accumulated_values(reversed_order))

def test_all_chance_outcomes_use_one_frozen_profile_per_iteration():
    trainer = KuhnCFRTrainer().train(1)
    trainer.train(1, diagnostic=True)
    seen = {}
    for row in trainer.last_diagnostic:
        strategy = tuple(sorted(row["strategy"].items()))
        seen.setdefault(row["infoset"], set()).add(strategy)
    assert len(trainer.last_diagnostic) == 24
    assert all(len(strategies) == 1 for strategies in seen.values())

def test_exact_ev_and_imperfect_information_best_response():
    policy = uniform_policy(); value = expected_value(policy, policy); assert value == pytest.approx(0.125) and -value == pytest.approx(-0.125)
    br_value, br_policy = best_response(policy, 0)
    assert br_value >= value and len(br_policy) == 6
    # A single root-J response action applies against both possible hidden opponent cards.
    assert set(br_policy["J|"].values()) == {0.0, 1.0}
    measure = metrics(policy, policy)
    assert measure["br1_as_u0"] <= measure["player0_ev"] <= measure["br0"]

def test_convergence_is_materially_less_exploitable():
    early = KuhnCFRTrainer().train(10); late = KuhnCFRTrainer().train(5000)
    early_m = metrics(early.average_strategy(), early.average_strategy()); late_m = metrics(late.average_strategy(), late.average_strategy())
    assert late_m["exploitability"] < early_m["exploitability"]
    assert abs(late_m["player0_ev"] + 1 / 18) < 0.03

def test_cli_json_is_deterministic(tmp_path):
    output = tmp_path / "kuhn.json"
    command = [sys.executable, "-m", "research.kuhn.cli", "train", "--iterations", "10", "--output", str(output)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    one = output.read_text(); subprocess.run(command + ["--overwrite"], check=True, capture_output=True, text=True)
    assert one == output.read_text() and json.loads(one)["kuhn_cfr_schema_version"] == "1.0"
