"""Opt-in live replay with independent public reach, belief and CFR inputs."""
from copy import copy
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from research.holdem.decoupled_replay import BOARD_LENGTH, CFRWorkingSet, OpponentActionLikelihood, PersistentRange
from solver.bot import STREETS
from solver.combos import card_mask


@dataclass(frozen=True)
class SolveInputs:
    ids: tuple[np.ndarray, np.ndarray]
    reaches: tuple[np.ndarray, np.ndarray]
    omitted_public_mass: tuple[float, float]
    omitted_opponent_mass: float


class ReplayBeliefs:
    """Reconstruct each prefix solely from chart and public action likelihoods.

    The actor's posterior excludes Hero blockers at every update. The separate
    board-only reaches model public information and counterfactual CFR pairs.
    Keeping Hero cards out of the public likelihood fit avoids granting the
    modeled opponent knowledge it did not have at the time of the action.
    """

    def __init__(self, hero, hero_cards):
        self.hero, self.villain = hero, 1 - hero
        self.hero_cards = tuple(hero_cards)
        self.public_reaches = (PersistentRange(), PersistentRange())
        self.opponent = self._condition_opponent(self.public_reaches)
        self.likelihood = OpponentActionLikelihood()
        self.update_seconds = 0.
        self.likelihood_seconds = 0.

    @property
    def board(self):
        return self.public_reaches[self.hero].board

    def _condition_opponent(self, public_reaches):
        opponent = public_reaches[self.villain].conditioned(self.hero_cards)
        opponent.setflags(write=False)
        return opponent

    def _publish(self, reaches, *, condition_opponent):
        opponent = self._condition_opponent(reaches) if condition_opponent else self.opponent
        self.public_reaches, self.opponent = tuple(reaches), opponent

    def observe(self, player, likelihood):
        started = perf_counter()
        reaches = list(self.public_reaches)
        reaches[player] = copy(reaches[player])
        reaches[player].observe(likelihood)
        self._publish(reaches, condition_opponent=player == self.villain)
        self.update_seconds += perf_counter() - started

    def reveal(self, board):
        started = perf_counter()
        reaches = tuple(copy(reach) for reach in self.public_reaches)
        for reach in reaches:
            reach.reveal(board)
        self._publish(reaches, condition_opponent=True)
        self.update_seconds += perf_counter() - started

    def replay_postflop(self, replay, board_cards, profile):
        for street in STREETS[1:STREETS.index(replay.street) + 1]:
            board = tuple(board_cards[:BOARD_LENGTH[street]])
            self.reveal(board)
            for step in replay.steps:
                if step.street != street:
                    continue
                started = perf_counter()
                law = self.likelihood.distribution(step.before, board, self.public_reaches[step.player].weights,
                                                   profile if step.player == self.villain else None)
                observed = law.observed(step)
                self.likelihood_seconds += perf_counter() - started
                self.observe(step.player, observed)

    def project(self, hero_combo, selection=None):
        selector = selection or CFRWorkingSet()
        compatible = ~card_mask(self.hero_cards)
        selections = tuple(selector.select(
            reach.weights, reach.blocked, hero_combo if player == self.hero else None,
            compatible if player == self.villain else None)
            for player, reach in enumerate(self.public_reaches))
        ids = tuple(item.ids for item in selections)
        projected = tuple(np.zeros_like(reach.weights) for reach in self.public_reaches)
        for mapping, scratch, reach in zip(ids, projected, self.public_reaches, strict=True):
            scratch[mapping] = reach.weights[mapping]
            mapping.setflags(write=False)
        return SolveInputs(ids, projected, tuple(item.omitted for item in selections),
                           max(0., 1. - float(self.opponent[ids[self.villain]].sum())))

    def diagnostics(self, working=None):
        opponent = self.opponent
        result = {"opponent_positive": int(np.count_nonzero(opponent)),
                  "opponent_effective": float(1 / (opponent @ opponent)),
                  "opponent_total": float(opponent.sum())}
        if working is not None:
            result.update(omitted_public_mass=working.omitted_public_mass,
                          omitted_opponent_mass=working.omitted_opponent_mass)
        return result
