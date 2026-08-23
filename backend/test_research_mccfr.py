import math
import random

import pytest

from research.holdem.mccfr import HoldemSubgameExternalSamplingMCCFRTrainer, scaling_report
from research.mccfr import (
    ExternalSamplingMCCFRTrainer,
    external_sampling_regret_updates,
    external_sampling_strategy_sum_increment,
)
from research.kuhn.evaluation import metrics
from research.kuhn.game import Action, Card, KuhnState
from research.kuhn.mccfr import KuhnExternalSamplingMCCFRTrainer, convergence_report


def accumulated_values(trainer):
    return {
        key: (dict(node.regrets), dict(node.strategy_sum))
        for key, node in trainer.infosets.items()
    }


class ScriptedRNG:
    """Minimal deterministic RNG for direct sampling-contract tests."""

    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


def _showdown_utility_p0(deal, magnitude):
    return float(magnitude if deal[0] > deal[1] else -magnitude)


def _p0_value_after_check_opponent_action(deal, opponent_action):
    """Independently evaluate the P0 branch after P0 checks at the root."""
    if opponent_action is Action.CHECK:
        return _showdown_utility_p0(deal, 1)
    # If P1 bets, P0 is still traverser and therefore enumerates its uniformly
    # frozen fold/call policy: fold=-1, call=two-chip showdown utility.
    return 0.5 * (-1.0 + _showdown_utility_p0(deal, 2))


def _p0_value_after_bet_opponent_action(deal, opponent_action):
    """Independently evaluate P0's root bet branch."""
    return 1.0 if opponent_action is Action.FOLD else _showdown_utility_p0(deal, 2)


def test_exhaustive_uniform_kuhn_expected_regret_estimator_matches_exact_cfr():
    """Prove the Q| external-sampling estimator is unbiased without training.

    At Q|, only QJ and QK reach the information set.  In each sampled
    trajectory, P0 enumerates root check/bet; the opponent independently
    samples one continuation for each branch.  Thus there are
    2 deals * 2 check continuations * 2 bet continuations = 8 trajectories,
    each with q_c * q_-i = (1/6) * (1/2) * (1/2) = 1/24.
    """
    uniform = {Action.CHECK: 0.5, Action.BET: 0.5}
    contributing_deals = ((Card.Q, Card.J), (Card.Q, Card.K))

    trajectories = []
    for deal in contributing_deals:
        for sampled_after_check in (Action.CHECK, Action.BET):
            for sampled_after_bet in (Action.FOLD, Action.CALL):
                action_values = {
                    Action.CHECK: _p0_value_after_check_opponent_action(deal, sampled_after_check),
                    Action.BET: _p0_value_after_bet_opponent_action(deal, sampled_after_bet),
                }
                trajectories.append({
                    "chance": "".join(card.value for card in deal),
                    "sampled_opponent_actions": (sampled_after_check, sampled_after_bet),
                    "trajectory_probability": 1.0 / 24.0,
                    "traverser_reach": 1.0,
                    "opponent_reach": 0.25,
                    "chance_reach": 1.0 / 6.0,
                    "estimator": external_sampling_regret_updates(uniform, action_values),
                })

    # Exact full-tree target: average both P1 continuations at each root
    # action, then weight the per-deal counterfactual regret by chance 1/6.
    exact = {action: 0.0 for action in uniform}
    for deal in contributing_deals:
        full_tree_values = {
            Action.CHECK: sum(
                _p0_value_after_check_opponent_action(deal, action)
                for action in (Action.CHECK, Action.BET)
            ) / 2.0,
            Action.BET: sum(
                _p0_value_after_bet_opponent_action(deal, action)
                for action in (Action.FOLD, Action.CALL)
            ) / 2.0,
        }
        full_tree_value = sum(uniform[action] * full_tree_values[action] for action in uniform)
        for action in uniform:
            exact[action] += (1.0 / 6.0) * (full_tree_values[action] - full_tree_value)

    expectation = {
        action: sum(row["trajectory_probability"] * row["estimator"][action] for row in trajectories)
        for action in uniform
    }
    assert len(trajectories) == 8
    assert all(row["trajectory_probability"] == pytest.approx(
        row["chance_reach"] * row["opponent_reach"]
    ) for row in trajectories)
    assert exact == pytest.approx({Action.CHECK: -1.0 / 8.0, Action.BET: 1.0 / 8.0})
    assert expectation == pytest.approx(exact, abs=1e-12)


def test_exhaustive_uniform_kuhn_expected_average_strategy_increment_matches_exact_cfr():
    """Prove Q|'s sampled average-policy increment retains chance reach.

    Q| is a root P0 decision, so own reach and opponent sampling reach are
    both one.  Each relevant Q deal is sampled with q_c=1/6.  The sampled
    increment is therefore 1 * sigma(Q|, a)=1/2; weighting QJ and QK gives
    2 * (1/6) * (1/2)=1/6 for each action, exactly the full-tree increment.
    """
    uniform = {Action.CHECK: 0.5, Action.BET: 0.5}
    trajectories = [
        {
            "chance": deal,
            "trajectory_probability": 1.0 / 6.0,
            "chance_reach": 1.0 / 6.0,
            "opponent_sampling_reach": 1.0,
            "own_reach": 1.0,
            "estimator": external_sampling_strategy_sum_increment(uniform, 1.0, 1.0),
        }
        for deal in ("QJ", "QK")
    ]
    expected = {
        action: sum(row["trajectory_probability"] * row["estimator"][action] for row in trajectories)
        for action in uniform
    }
    exact = {action: 2.0 * (1.0 / 6.0) * uniform[action] for action in uniform}
    assert all(row["trajectory_probability"] == row["chance_reach"] for row in trajectories)
    assert exact == pytest.approx({Action.CHECK: 1.0 / 6.0, Action.BET: 1.0 / 6.0})
    assert expected == pytest.approx(exact, abs=1e-12)


def test_frozen_traversal_contract_uses_post_traverser_zero_snapshot_for_traverser_one():
    """One logical iteration is two sequential, individually frozen passes."""
    probe = KuhnExternalSamplingMCCFRTrainer(0)
    probe_node = probe._node(KuhnState((Card.J, Card.Q)))
    probe_profile = probe._frozen_profile()
    frozen = probe._strategy_from_profile(probe_node, probe_profile)
    probe_node.regrets[Action.BET] = 3.0
    assert probe._strategy_from_profile(probe_node, probe_profile) == frozen

    trainer = KuhnExternalSamplingMCCFRTrainer(0)
    # T0 receives JQ, samples P1 check after P0 checks and P1 fold after P0
    # bets.  That changes J|'s regret-matched policy from uniform to pure bet.
    trainer.rng = ScriptedRNG([0.0, 0.0, 0.0, 0.0, 0.0])
    trainer.train(1)
    first, second = trainer.last_traversal_profiles
    assert first["traverser"] == 0
    assert first["profile"]["J|"] == pytest.approx({Action.CHECK: 0.5, Action.BET: 0.5})
    assert second["traverser"] == 1
    assert second["profile"]["J|"] == pytest.approx({Action.CHECK: 0.0, Action.BET: 1.0})
    # The T0 profile remains the recorded pre-mutation snapshot.
    assert first["profile"]["J|"] != second["profile"]["J|"]


def test_logical_iteration_schedule_reports_two_ordered_traversals_per_iteration():
    trainer = KuhnExternalSamplingMCCFRTrainer(3).train(3)
    assert [(row["iteration"], row["traverser"]) for row in trainer.last_trajectories] == [
        (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1),
    ]
    diagnostics = trainer.diagnostics()
    assert diagnostics["iterations"] == 3
    assert diagnostics["traversals"] == 6
    assert diagnostics["traversals_per_iteration"] == pytest.approx(2.0)


def test_direct_opponent_sampling_uses_frozen_probabilities_and_excludes_zero_probability_actions():
    trainer = KuhnExternalSamplingMCCFRTrainer(0)
    non_uniform = {Action.CHECK: 0.75, Action.BET: 0.25}
    trainer.rng = ScriptedRNG([0.0, 0.749999, 0.75, 0.999999])
    sampled = [trainer._sample_action(non_uniform) for _ in range(4)]
    assert sampled == [Action.CHECK, Action.CHECK, Action.BET, Action.BET]
    assert [non_uniform[action] for action in sampled] == pytest.approx([0.75, 0.75, 0.25, 0.25])

    certain = {Action.CHECK: 1.0, Action.BET: 0.0}
    trainer.rng = ScriptedRNG([0.0, 0.999999])
    assert [trainer._sample_action(certain) for _ in range(2)] == [Action.CHECK, Action.CHECK]


def test_direct_chance_sampling_uses_six_uniform_collision_free_deals_and_rejects_zero_weights():
    trainer = KuhnExternalSamplingMCCFRTrainer(0)
    assert trainer.chance_weights == pytest.approx((1.0 / 6.0,) * 6)
    trainer.rng = ScriptedRNG([0.0, 1.0 / 6.0, 0.999999])
    samples = [trainer._sample_root() for _ in range(3)]
    assert [("".join(card.value for card in root.cards), probability) for root, probability in samples] == pytest.approx([
        ("JQ", 1.0 / 6.0), ("JK", 1.0 / 6.0), ("KQ", 1.0 / 6.0),
    ])
    assert all(root.cards[0] != root.cards[1] for root, _ in samples)
    recorded = KuhnExternalSamplingMCCFRTrainer(0)
    recorded.rng = ScriptedRNG([0.0, 0.0, 0.0, 0.0, 0.0])
    recorded.train(1)
    assert recorded.last_trajectories[0]["chance"] == "JQ"
    assert recorded.last_trajectories[0]["chance_probability"] == pytest.approx(1.0 / 6.0)
    with pytest.raises(ValueError, match="positive"):
        ExternalSamplingMCCFRTrainer(("possible", "impossible"), 0, chance_weights=(1.0, 0.0))


def test_mccfr_does_not_mutate_module_global_random_state():
    before = random.getstate()
    KuhnExternalSamplingMCCFRTrainer(47).train(100)
    assert random.getstate() == before


def test_seeded_mccfr_is_reproducible_including_trajectory_regrets_and_metrics():
    first = KuhnExternalSamplingMCCFRTrainer(41).train(500)
    second = KuhnExternalSamplingMCCFRTrainer(41).train(500)
    assert first.last_trajectories == second.last_trajectories
    assert accumulated_values(first) == pytest.approx(accumulated_values(second))
    assert metrics(first.average_strategy(), first.average_strategy()) == pytest.approx(
        metrics(second.average_strategy(), second.average_strategy())
    )


def test_different_seeds_produce_different_finite_trajectories():
    first = KuhnExternalSamplingMCCFRTrainer(1).train(10)
    second = KuhnExternalSamplingMCCFRTrainer(2).train(10)
    assert first.last_trajectories != second.last_trajectories


def test_chance_sampling_uses_uniform_kuhn_deal_distribution_sanity():
    trainer = KuhnExternalSamplingMCCFRTrainer(5).train(3_000)
    counts = trainer.diagnostics()["chance_sample_counts"]
    assert set(counts) == {"JQ", "JK", "QJ", "QK", "KJ", "KQ"}
    assert sum(counts.values()) == 6_000
    assert all(750 < count < 1_250 for count in counts.values())


def test_external_sampling_enumerates_traverser_actions_and_samples_opponent_actions():
    trainer = KuhnExternalSamplingMCCFRTrainer(11).train(1, diagnostic=True)
    enumerated = [row for row in trainer.last_diagnostic if "enumerated_actions" in row]
    sampled = [row for row in trainer.last_diagnostic if "sampled_opponent_action" in row]
    assert enumerated and sampled
    assert all(len(row["enumerated_actions"]) == 2 for row in enumerated)
    assert all(0.0 < row["sample_probability"] <= 1.0 for row in sampled)
    assert all(row["sampled_opponent_action"] not in {"deck", "rng"} for row in sampled)


def test_uniform_one_iteration_regret_estimator_fixture_and_strategy_sum_correction():
    trainer = KuhnExternalSamplingMCCFRTrainer(11).train(1, diagnostic=True)
    # Seed 11 samples QJ for traverser 0.  At Q|, traverser actions are fully
    # enumerated against J's sampled check/bet continuation: u(check)=1/2,
    # u(bet)=2, and their uniform-policy value is 5/4.
    row = next(item for item in trainer.last_diagnostic if item.get("infoset") == "Q|" and item.get("traverser") == 0)
    assert row["regret_updates"] == pytest.approx({"check": -0.75, "bet": 0.75})
    node = trainer.infosets["Q|"]
    assert node.strategy_sum == pytest.approx({Action.CHECK: 0.5, Action.BET: 0.5})
    assert row["average_strategy_correction"] == pytest.approx(1.0)


def test_kuhn_information_sets_remain_private_under_mccfr():
    assert KuhnState((Card.J, Card.Q)).information_set() == KuhnState((Card.J, Card.K)).information_set()
    trainer = KuhnExternalSamplingMCCFRTrainer(9).train(2_000)
    assert len(trainer.infosets) == 12
    assert all(key.split("|", 1)[0] in {"J", "Q", "K"} for key in trainer.infosets)


def test_numerical_safety_and_probability_normalization():
    trainer = KuhnExternalSamplingMCCFRTrainer(13).train(2_000)
    for node in trainer.infosets.values():
        assert all(math.isfinite(value) for value in (*node.regrets.values(), *node.strategy_sum.values()))
        assert sum(node.strategy().values()) == pytest.approx(1.0)
        assert all(0.0 <= value <= 1.0 and math.isfinite(value) for value in node.strategy().values())
        assert sum(node.average().values()) == pytest.approx(1.0)
        assert all(0.0 <= value <= 1.0 and math.isfinite(value) for value in node.average().values())
    assert all(row["chance_probability"] > 0.0 for row in trainer.last_trajectories)
    assert all(sample["probability"] > 0.0 for row in trainer.last_trajectories for sample in row["opponent_samples"])


def test_kuhn_mccfr_convergence_sanity_and_exact_metrics_report():
    early = KuhnExternalSamplingMCCFRTrainer(7).train(100)
    late = KuhnExternalSamplingMCCFRTrainer(7).train(10_000)
    early_metrics = metrics(early.average_strategy(), early.average_strategy())
    late_metrics = metrics(late.average_strategy(), late.average_strategy())
    assert late_metrics["exploitability"] < early_metrics["exploitability"]
    assert abs(late_metrics["player0_ev"] + 1 / 18) < 0.02
    report = convergence_report((100, 1_000), (7, 17))
    assert len(report["reports"]) == 4
    assert all({"seed", "br0", "br1_as_u0", "nashconv", "exploitability", "iterations_per_second"} <= row.keys()
               for row in report["reports"])


def test_bounded_holdem_mccfr_executes_with_sampling_diagnostics_and_no_private_key_leak():
    trainer = HoldemSubgameExternalSamplingMCCFRTrainer(23).train(50)
    diagnostics = trainer.diagnostics(trainer.all_information_set_keys())
    assert trainer.profile_ev() == pytest.approx(trainer.profile_ev())
    assert 0.0 < diagnostics["fraction_full_tree_visited_per_iteration"] < 1.0
    assert diagnostics["information_sets_touched"] <= 56
    assert diagnostics["finite"]
    assert all(card not in key for key in trainer.infosets for card in ("Ah", "Ad", "Kh", "Kc", "Qs", "Js"))


def test_holdem_scaling_report_compares_exact_traversal_without_exploitability_claim():
    report = scaling_report(10, seed=31)
    exact = report["exact_vanilla_cfr"]
    sampled = report["external_sampling_mccfr"]
    assert exact["nodes_visited_per_iteration"] == 3510
    assert sampled["traversals"] == 20
    assert sampled["traversals_per_iteration"] == pytest.approx(2.0)
    assert sampled["nodes_visited_per_iteration"] < exact["nodes_visited_per_iteration"]
    assert "exploitability" not in sampled


def test_exact_cfr_controls_are_unchanged_and_still_deterministic():
    from research.holdem.cfr import HoldemSubgameCFRTrainer
    from research.kuhn.cfr import KuhnCFRTrainer

    assert KuhnCFRTrainer().train(25).strategy_table() == KuhnCFRTrainer().train(25).strategy_table()
    assert HoldemSubgameCFRTrainer("vanilla").train(3).strategy_document() == HoldemSubgameCFRTrainer("vanilla").train(3).strategy_document()
