import json
import random

from simulation.actions import Action
from simulation.bots import TightBot
from simulation.engine import HandEngine
from simulation.opponent_model import OpponentModel, confidence_for


def played_history(seed=71):
    return HandEngine(TightBot(seed=1), TightBot(seed=2), seed=seed).play()["history"]


def test_empty_profile_is_finite_and_json_safe():
    payload = OpponentModel("a").snapshot().as_dict()
    assert payload["hands_observed"] == 0
    assert payload["statistics"]["vpip"]["raw_frequency"] == 0.0
    assert "NaN" not in json.dumps(payload, allow_nan=False)


def test_completed_histories_accumulate_public_action_counts_deterministically():
    first, second = OpponentModel("a"), OpponentModel("a")
    histories = [played_history(72), played_history(73)]
    for model in (first, second):
        for history in histories: model.update(history)
    assert first.snapshot().as_dict() == second.snapshot().as_dict()
    assert first.snapshot().hands_observed == 2
    assert first.snapshot().decisions_observed > 0
    stats = first.snapshot().statistics
    assert stats["fold"].opportunities == first.snapshot().decisions_observed
    assert stats["aggressive"].occurrences + stats["passive"].occurrences == first.snapshot().decisions_observed


def test_smoothing_and_confidence_thresholds_are_centralized():
    model = OpponentModel("a")
    model.stats["vpip"].opportunities, model.stats["vpip"].occurrences = 3, 2
    estimate = model.snapshot().statistics["vpip"]
    assert estimate.raw_frequency == 2 / 3
    assert estimate.smoothed_frequency == 3 / 5
    assert [confidence_for(n) for n in (0, 5, 20, 50)] == ["very_low", "low", "medium", "high"]


def test_model_update_does_not_consume_rng():
    rng = random.Random(88); expected = random.Random(88)
    model = OpponentModel("a"); model.update(played_history(74))
    assert rng.randrange(100000) == expected.randrange(100000)
