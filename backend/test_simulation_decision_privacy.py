import json

from simulation.bots import RandomBot
from simulation.decision_state import build_decision_observation
from simulation.engine import HandEngine


FORBIDDEN_KEYS = {"opponent_hole_cards", "future_board_cards", "deck", "deck_order", "burn_cards", "remaining_deck", "holes"}


def keys(value):
    if isinstance(value, dict):
        yield from value
        for item in value.values(): yield from keys(item)
    elif isinstance(value, list):
        for item in value: yield from keys(item)


def test_serialized_decision_observation_has_no_hidden_fields_or_cards():
    game = HandEngine(RandomBot(), RandomBot(), seed=18)
    data = build_decision_observation(game, "a").as_dict()
    encoded = json.dumps(data, allow_nan=False)
    assert not FORBIDDEN_KEYS & set(keys(data))
    assert not set(game.holes["b"]) & set(encoded.split('"'))
    assert not set(game.deck.cards) & set(encoded.split('"'))


def test_showdown_does_not_retroactively_leak_into_prior_decision():
    game = HandEngine(RandomBot(), RandomBot(), seed=21)
    before = build_decision_observation(game, "a").as_dict()
    game.play()
    encoded = json.dumps(before, allow_nan=False)
    assert all(card not in encoded for card in game.holes["b"])
    assert all(card not in encoded for card in game.state.community_cards[0:])
