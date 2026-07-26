import pytest

from simulation.actions import Action
from simulation.bots import (
    AggressiveBot,
    EquityBot,
    RandomBot,
    TightBot,
)
from simulation.engine import SimulationRunner
from simulation.match import MatchConfig, run_match


class FoldBot:
    def __init__(self):
        self.observations = []

    def decide(self, observation):
        self.observations.append(observation)
        if "fold" in observation.legal_actions:
            return Action("fold")
        return Action("check")


class PassiveBot:
    def __init__(self):
        self.observations = []

    def decide(self, observation):
        self.observations.append(observation)
        if "check" in observation.legal_actions:
            return Action("check")
        if "call" in observation.legal_actions:
            return Action("call")
        if "all_in" in observation.legal_actions:
            return Action("all_in")
        return Action("fold")


class AllInBot:
    def __init__(self):
        self.observations = []

    def decide(self, observation):
        self.observations.append(observation)
        if "all_in" in observation.legal_actions:
            return Action("all_in")
        if "call" in observation.legal_actions:
            return Action("call")
        if "check" in observation.legal_actions:
            return Action("check")
        return Action("fold")


def fold_match(max_hands=3):
    return run_match(
        FoldBot(),
        FoldBot(),
        MatchConfig(
            starting_stack_a=1000,
            starting_stack_b=1000,
            small_blind=5,
            big_blind=10,
            max_hands=max_hands,
            seed=42,
        ),
    )


def test_stacks_carry_forward_between_hands():
    result = fold_match(2)
    first, second = result.per_hand_summaries
    assert first.ending_stacks == second.starting_stacks
    assert first.starting_stacks == {"a": 1000, "b": 1000}
    assert first.ending_stacks == {"a": 995, "b": 1005}
    assert second.ending_stacks == {"a": 1000, "b": 1000}


def test_button_and_blinds_alternate_every_hand():
    result = fold_match(3)
    assert [
        (
            hand.button_player,
            hand.small_blind_player,
            hand.big_blind_player,
        )
        for hand in result.per_hand_summaries
    ] == [
        ("a", "a", "b"),
        ("b", "b", "a"),
        ("a", "a", "b"),
    ]


def test_match_ends_when_a_player_is_eliminated():
    result = run_match(
        AllInBot(),
        AllInBot(),
        MatchConfig(
            starting_stack_a=100,
            starting_stack_b=100,
            small_blind=5,
            big_blind=10,
            max_hands=10,
            seed=7,
        ),
    )
    assert result.termination_reason == "elimination"
    assert 0 in result.final_stacks.values()
    assert result.hands_played <= 10


def test_match_ends_at_configured_hand_limit():
    result = fold_match(3)
    assert result.hands_played == 3
    assert result.termination_reason == "hand_limit"
    assert all(stack > 0 for stack in result.final_stacks.values())


def test_equal_stacks_at_hand_limit_report_a_tie():
    result = fold_match(2)
    assert result.termination_reason == "hand_limit"
    assert result.final_stacks == {"a": 1000, "b": 1000}
    assert result.winner == "tied"


def test_match_conserves_the_initial_chip_total():
    result = fold_match(7)
    assert sum(result.starting_stacks.values()) == 2000
    assert sum(result.final_stacks.values()) == 2000
    assert all(
        sum(hand.ending_stacks.values()) == 2000
        for hand in result.per_hand_summaries
    )


def test_match_net_results_are_exact_opposites():
    result = fold_match(3)
    assert result.bot_a_net_chips == -result.bot_b_net_chips
    assert result.bot_a_net_chips + result.bot_b_net_chips == 0
    assert all(
        hand.net_chips["a"] == -hand.net_chips["b"]
        for hand in result.per_hand_summaries
    )


def test_match_never_produces_negative_stacks():
    result = run_match(
        AllInBot(),
        AllInBot(),
        MatchConfig(135, 80, 7, 13, 10, 91),
    )
    assert all(stack >= 0 for stack in result.final_stacks.values())
    assert all(
        stack >= 0
        for hand in result.per_hand_summaries
        for stack in hand.ending_stacks.values()
    )


def test_every_match_hand_settles_exactly_once():
    result = fold_match(5)
    assert all(
        hand.settlement_count == 1 and hand.settlement_complete
        for hand in result.per_hand_summaries
    )


def test_settled_hand_state_is_clean_before_next_hand():
    result = fold_match(4)
    for current, following in zip(
        result.per_hand_summaries,
        result.per_hand_summaries[1:],
    ):
        assert current.settlement_complete
        assert current.ending_stacks == following.starting_stacks


def test_same_seed_and_configuration_are_reproducible():
    config = MatchConfig(1000, 1000, 5, 10, 20, 123)
    first = run_match(RandomBot(123), RandomBot(124), config)
    second = run_match(RandomBot(123), RandomBot(124), config)
    assert first == second


def test_independent_simulation_still_resets_stacks_each_hand():
    bot_a = PassiveBot()
    result = SimulationRunner(
        bot_a,
        PassiveBot(),
        hands=4,
        starting_stack_bb=100,
        seed=42,
    ).run(include_hand_results=True)
    first_observation_by_hand = {}
    for observation in bot_a.observations:
        first_observation_by_hand.setdefault(observation.hand_id, observation)
    assert len(first_observation_by_hand) == 4
    assert all(
        observation.hero_stack + observation.current_bet == 10_000
        for observation in first_observation_by_hand.values()
    )
    assert len(result["hand_results"]) == 4


def test_phase_two_simulation_result_structure_is_unchanged():
    result = SimulationRunner(
        FoldBot(),
        FoldBot(),
        hands=2,
        seed=9,
    ).run()
    required = {
        "simulation_id",
        "seed",
        "bot_a",
        "bot_b",
        "bb",
        "hands_played",
        "bot_a_wins",
        "bot_b_wins",
        "ties",
        "bot_a_net_chips",
        "bot_b_net_chips",
        "showdowns",
        "fold_ended_hands",
        "illegal_actions",
        "bot_a_bb_per_100",
        "bot_b_bb_per_100",
    }
    assert required <= result.keys()
    assert "match_id" not in result
    assert "termination_reason" not in result


def test_short_stacked_small_blind_posts_safely():
    result = run_match(
        PassiveBot(),
        PassiveBot(),
        MatchConfig(25, 1000, 50, 100, 1, 5),
    )
    hand = result.per_hand_summaries[0]
    assert hand.small_blind_player == "a"
    assert hand.starting_stacks["a"] == 25
    assert hand.showdown
    assert len(hand.board) == 5
    assert hand.settlement_complete
    assert abs(hand.net_chips["a"]) == 25
    assert sum(hand.ending_stacks.values()) == 1025


def test_short_stacked_big_blind_posts_safely_and_gets_a_response():
    bot_a = PassiveBot()
    bot_b = PassiveBot()
    result = run_match(
        bot_a,
        bot_b,
        MatchConfig(1000, 75, 50, 100, 1, 8),
    )
    hand = result.per_hand_summaries[0]
    preflop = bot_a.observations[0]
    assert hand.big_blind_player == "b"
    assert preflop.street == "preflop"
    assert preflop.amount_to_call == 25
    assert "call" in preflop.legal_actions
    assert bot_b.observations == []
    assert hand.showdown and len(hand.board) == 5
    assert hand.settlement_complete


def test_all_in_blind_runs_out_and_settles():
    result = run_match(
        PassiveBot(),
        PassiveBot(),
        MatchConfig(40, 1000, 50, 100, 1, 21),
    )
    hand = result.per_hand_summaries[0]
    assert hand.showdown
    assert hand.fold_ended is False
    assert len(hand.board) == 5
    assert hand.settlement_count == 1
    assert hand.settlement_complete


def test_match_result_winner_and_hand_limit_reason_are_correct():
    result = fold_match(1)
    assert result.termination_reason == "hand_limit"
    assert result.final_stacks == {"a": 995, "b": 1005}
    assert result.winner == "Bot B"


def test_elimination_result_winner_and_reason_are_correct():
    result = run_match(
        AllInBot(),
        AllInBot(),
        MatchConfig(100, 100, 5, 10, 10, 7),
    )
    expected = "Bot A" if result.final_stacks["a"] else "Bot B"
    assert result.termination_reason == "elimination"
    assert result.winner == expected


@pytest.mark.parametrize(
    "bot_type",
    [RandomBot, TightBot, AggressiveBot, EquityBot],
)
def test_built_in_bots_complete_matches_without_illegal_actions(bot_type):
    result = run_match(
        bot_type(seed=31, equity_iterations=50),
        RandomBot(seed=32),
        MatchConfig(500, 500, 5, 10, 5, 31),
    )
    assert result.hands_played >= 1
    assert result.illegal_action_count == 0
    assert result.fallback_diagnostic_count == 0
    assert all(hand.settlement_complete for hand in result.per_hand_summaries)


def test_match_observations_preserve_private_card_isolation():
    bot_a = PassiveBot()
    bot_b = PassiveBot()
    run_match(
        bot_a,
        bot_b,
        MatchConfig(500, 500, 5, 10, 2, 17),
    )
    forbidden = {
        "opponent_cards",
        "opponent_hole_cards",
        "villain_cards",
        "future_cards",
        "deck",
        "deck_order",
        "remaining_deck",
        "rng_state",
    }
    observations = bot_a.observations + bot_b.observations
    assert observations
    assert all(not (forbidden & vars(observation).keys()) for observation in observations)
    assert all(
        len(observation.hole_cards) == 2
        and not set(observation.hole_cards) & set(observation.community_cards)
        for observation in observations
    )


def test_match_configuration_validation_is_strict():
    with pytest.raises(ValueError):
        MatchConfig(starting_stack_a=0)
    with pytest.raises(ValueError):
        MatchConfig(starting_stack_b=-1)
    with pytest.raises(ValueError):
        MatchConfig(small_blind=101, big_blind=100)
    with pytest.raises(ValueError):
        MatchConfig(max_hands=0)
