from simulation.actions import Action
from simulation.match import MatchConfig, PersistentMatchRunner


class ProfileBot:
    def __init__(self): self.profiles = []
    def decide_decision(self, observation):
        self.profiles.append(observation.opponent_profile)
        legal = observation.decision_state.legal_actions
        return Action("check" if "check" in legal else "call" if "call" in legal else "fold")


def test_match_delivers_predecision_opponent_profile_and_retains_models():
    a, b = ProfileBot(), ProfileBot()
    runner = PersistentMatchRunner(a, b, MatchConfig(max_hands=2, seed=91))
    runner.run()
    assert a.profiles and b.profiles
    assert a.profiles[0].hands_observed == 0
    assert b.profiles[0].hands_observed == 0
    assert runner.model_of_a.hands_observed == 2
    assert runner.model_of_b.hands_observed == 2
    # The first profile within hand two includes hand one, never its own action.
    assert any(profile.hands_observed == 1 for profile in a.profiles + b.profiles)
