import json

from simulation.actions import Action
from simulation.bots import RandomBot
from simulation.decision_state import build_decision_observation
from simulation.engine import HandEngine


def engine(seed=17):
    return HandEngine(RandomBot(1), RandomBot(2), stack=1_000, bb=100, seed=seed, hand_id="decision-hand", hand_number=4, match_id="match-1")


def test_preflop_state_has_authoritative_betting_and_identity_fields():
    game = engine()
    observation = build_decision_observation(game, "a")
    state = observation.decision_state
    assert state.hand_id == "decision-hand" and state.match_id == "match-1" and state.hand_number == 4
    assert state.hole_cards == tuple(game.holes["a"]) and state.board_cards == ()
    assert state.pot == 150 and state.amount_to_call == 50
    assert state.hero_street_commitment == 50 and state.opponent_street_commitment == 100
    assert state.effective_stack == 900 and state.effective_stack_bb == 9
    assert set(state.legal_actions) == {"fold", "call", "raise", "all_in"}
    assert state.minimum_legal_target == 200 and state.maximum_legal_target == 1_000
    assert state.position == "in_position" and state.big_blind_player == "b"


def test_postflop_turn_and_river_observations_only_expose_revealed_board():
    game = engine()
    game._action("a", Action("call")); game._action("b", Action("check"))
    for street, count in (("flop", 3), ("turn", 4), ("river", 5)):
        game._next_street()
        observation = build_decision_observation(game, game.state.acting_player)
        assert observation.decision_state.street == street
        assert len(observation.decision_state.board_cards) == count


def test_action_context_tracks_public_order_and_aggressors():
    game = engine()
    game._action("a", Action("raise", 300))
    state = build_decision_observation(game, "b").decision_state
    assert [(item.player, item.action) for item in state.hand_actions] == [("a", "raise")]
    assert state.last_aggressor == state.preflop_aggressor == "a"
    assert state.raises_this_street == 1 and not state.hero_has_initiative


def test_short_all_in_preserves_engine_targets_and_reopening_state():
    game = engine()
    game._action("a", Action("raise", 300))
    game.state.stacks["b"] = 150
    state = build_decision_observation(game, "b").decision_state
    assert state.amount_to_call == 200 and state.maximum_legal_target == 250
    assert state.minimum_legal_target is None and state.raising_reopened
    assert state.legal_actions == ("fold", "all_in")


def test_short_all_in_raise_does_not_reopen_raising_rights():
    game = engine()
    game._action("a", Action("raise", 300))
    game.state.stacks["b"] = 350  # target 450: a 150-chip short raise
    game._action("b", Action("all_in"))
    state = build_decision_observation(game, "a").decision_state
    assert state.current_highest_bet == 450 and not state.raising_reopened
    assert state.amount_to_call == 150 and "raise" not in state.legal_actions


def test_decision_observation_is_deterministic_and_does_not_consume_deck():
    game = engine(42)
    before = list(game.deck.cards)
    first = build_decision_observation(game, "a").as_dict()
    second = build_decision_observation(game, "a").as_dict()
    assert first == second and game.deck.cards == before
    assert json.dumps(first, allow_nan=False)


def test_new_strategy_interface_is_used_without_changing_legacy_bots():
    class DecisionBot(RandomBot):
        def __init__(self): super().__init__(1); self.seen = []
        def decide_decision(self, observation):
            self.seen.append(observation)
            return Action("fold")

    bot = DecisionBot()
    result = HandEngine(bot, RandomBot(2), seed=4).play()
    assert bot.seen and result["winner"] == "b"
