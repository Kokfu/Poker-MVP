"""Offline river reply forecasts and paired policy sensitivity.

Inputs are the public betting tree, board-only holding tiers, Hero's cards
and public action counts. Selection of CFR columns is outside this module.
"""
from dataclasses import dataclass
from itertools import product
from math import log, log1p

import numpy as np

from research.holdem.decoupled_replay import hand_tiers
from solver.bot import _full_equity
from solver.combos import card_mask, combo_index
from solver.exploit import beta_interval


@dataclass(frozen=True)
class ReplyGeometry:
    cost: int
    pot_before_wager: int
    effective_stack: int
    refundable: int

    @property
    def pot_before_call(self):
        return self.pot_before_wager + self.cost


def reply_geometry(state):
    actor, other = state.to_act, 1 - state.to_act
    own, offered = state.commit[actor], state.commit[other]
    effective_stack = min(own + state.stack[actor], offered + state.stack[other]) - own
    cost = min(offered - own, effective_stack)
    if cost <= 0:
        raise ValueError("reply requires a live wager")
    return ReplyGeometry(cost, sum(state.base) + 2 * own, effective_stack, offered - own - cost)


def river_counts(snapshot):
    stats = snapshot.street_statistics.get("river", {}) if snapshot is not None else {}
    fold, raises = stats.get("fold_to_bet"), stats.get("raise_vs_bet")
    if fold is None or raises is None:
        return 0, 0, 0
    n, f, r = fold.opportunities, fold.occurrences, raises.occurrences
    if raises.opportunities != n or min(f, r, n - f - r) < 0:
        raise ValueError("inconsistent river counts")
    return f, n - f - r, r


@dataclass(frozen=True)
class ResponseAssumptions:
    continue_at_half_pot: tuple
    raise_given_continue: tuple

    @classmethod
    def from_counts(cls, folds, calls, raises):
        n, continuing = folds + calls + raises, calls + raises
        # Uniform continuation prior and Beta(1, 7) aggression prior.
        # The interval helper implements a uniform prior on its inputs.
        c = beta_interval(continuing, n, level=.975)
        r = beta_interval(raises, continuing + 6, level=.975)
        return cls((c[0], (continuing + 1) / (n + 2), c[1]),
                   (r[0], (raises + 1) / (continuing + 8), r[1]))


def shifted_probability(probability, shift):
    odds_multiplier = np.exp(shift)
    return probability * odds_multiplier / (1 - probability + probability * odds_multiplier)


# Each pair of endpoints moves consistently across reply nodes. Add two
# scenarios for the unidentified hand gradient and allocation across sizes.
NOMINAL = (1, 1, True, "uniform")
REPLY_MODELS = (NOMINAL, *product((0, 2), (0, 2), (True, False), ("smallest", "largest")))


def forecast(node, tiers, assumptions, model=NOMINAL):
    c, r, hand_gradient, split = model
    geometry = reply_geometry(node.state)
    kinds = [kind for kind, _ in node.actions]
    if set(kinds) - {"fold", "call", "raise", "all_in"} or kinds.count("fold") != 1 or kinds.count("call") != 1:
        raise ValueError("expected a legal facing-wager menu")
    # Half-pot continued odds are the anchor. Use the effective, collectible
    # price for the odds tilt, including when the offered target overhangs.
    shift = (tiers - 1) * log(3) if hand_gradient else 0.
    price = log(geometry.pot_before_call / (3 * geometry.cost))
    continuing = np.broadcast_to(
        shifted_probability(assumptions.continue_at_half_pot[c], shift + price), tiers.shape)
    result = np.zeros((len(kinds), len(tiers)))
    aggression = [i for i, kind in enumerate(kinds) if kind in ("raise", "all_in")]
    raised = 0.
    if aggression:
        pressure = -log1p(geometry.cost / geometry.effective_stack)
        raised = continuing * shifted_probability(assumptions.raise_given_continue[r], shift + pressure)
        targets = aggression if split == "uniform" else [aggression[0 if split == "smallest" else -1]]
        result[targets] = raised / len(targets)
    result[kinds.index("fold")] = 1 - continuing
    result[kinds.index("call")] = continuing - raised
    if not np.isfinite(result).all() or (result < 0).any() or not np.allclose(result.sum(axis=0), 1, atol=1e-12, rtol=0):
        raise AssertionError("invalid reply distribution")
    return result


def compatible_ids(hero, board):
    return np.flatnonzero(~card_mask((*hero, *board)))


def posterior_models(bot, ids):
    """Nominal range, then fixed-factor omissions of one public evidence source.

    Hold the other already-estimated likelihood vectors fixed. These are
    alternative input models, with no implied confidence level for reach.
    """
    nominal = bot.estimate[ids]
    models = {"nominal": nominal}
    villain = 1 - bot.live_node.player
    observations = [entry for entry in bot.observations if entry.step.player == villain]
    if not observations:
        models["uninformative_chart"] = np.full(len(ids), 1 / len(ids))
        return models
    factors = [entry.law.observed(entry.step)[ids] for entry in observations]
    chart = observations[0].prior[ids]
    omissions = (("uninformative_chart", np.ones(len(ids)), factors),
                 *((f"omit_{entry.step.street}_{i}", chart, factors[:i] + factors[i + 1:])
                   for i, entry in enumerate(observations)))
    for key, prior, evidence in omissions:
        weights = prior * np.prod(evidence, axis=0) if evidence else prior
        total = weights.sum()
        if not np.isfinite(total) or total <= 0:
            raise ValueError("invalid alternative posterior support")
        models[key] = weights / total
    return models


def holding_values(tree, root, outcomes, replies, hero_policy, hero_gets_odd_chip):
    """Per-holding net-chip payoffs, relative to folding at the root."""
    hero = root.player
    sunk = root.state.contribution(hero)

    def value(index):
        node = tree.nodes[index]
        spent = node.contribution[hero] - sunk
        pot = sum(node.contribution)
        if node.kind == "fold":
            return np.full(len(outcomes), (pot if node.player != hero else 0) - spent)
        if node.kind == "leaf":
            return np.where(outcomes > 0, pot, np.where(outcomes == 0, (pot + hero_gets_odd_chip) // 2, 0)) - spent
        policy = hero_policy[node.index] if node.player == hero else replies[node.index]
        return sum(probability * value(child) for child, probability in zip(node.children, policy, strict=True))

    return np.array([value(child) for child in root.children])


def proposed_mix(incumbent, values):
    if values @ incumbent >= values.max() - 1e-9:
        return incumbent.copy()
    result = np.zeros_like(incumbent)
    result[np.argmax(values)] = 1.
    return result


def gate(incumbent, proposal, scenario_values):
    """Use the same policy contrast in each scenario. Zero retains the incumbent."""
    deltas = scenario_values @ (proposal - incumbent)
    bounds = (float(deltas.min()), float(deltas.max()))
    accepted = bounds[0] > 1e-9
    return (proposal if accepted else incumbent), bounds, accepted


@dataclass(frozen=True)
class ReplyEvaluation:
    root: object
    tree: object
    nodes: tuple
    ids: np.ndarray
    tiers: np.ndarray
    outcomes: np.ndarray
    hero_policy: dict
    odd_chip: bool
    counts: tuple
    assumptions: ResponseAssumptions

    def forecasts(self, model=NOMINAL):
        return {node.index: forecast(node, self.tiers, self.assumptions, model) for node in self.nodes}

    def values(self, replies):
        return holding_values(self.tree, self.root, self.outcomes, replies, self.hero_policy, self.odd_chip)


def prepare_evaluation(bot, snapshot):
    """Use full compatible showdown outcomes and a fixed Hero continuation."""
    root, tree = bot.live_node, bot.river.tree
    ds = bot.decision_state
    board, hero = tuple(ds.board_cards), tuple(ds.hole_cards)
    ids = compatible_ids(hero, board)
    live, outcomes, _ = _full_equity(board, bot.flop_runouts)
    hero_combo = combo_index(hero)
    results = outcomes[np.searchsorted(live, hero_combo), np.searchsorted(live, ids)]
    # Continuation is held fixed across model scenarios and both root mixes.
    column = np.searchsorted(bot.river.combos[root.player], hero_combo)
    hero_policy = {node.index: bot.river.average[node.index][:, column] for node in tree.nodes
                   if node.kind == "decision" and node.player == root.player}
    nodes = tuple(node for node in tree.nodes if node.kind == "decision" and node.player != root.player)
    legal, tiers = hand_tiers(board)
    counts = river_counts(snapshot)
    assumptions = ResponseAssumptions.from_counts(*counts)
    return ReplyEvaluation(root, tree, nodes, ids, tiers[np.searchsorted(legal, ids)], results,
                           hero_policy, ds.acting_player == "b", counts, assumptions)


def scenario_values(evaluation, ranges, nominal_values):
    weights = np.stack(list(ranges.values()))
    values = [weights @ nominal_values.T]
    if evaluation.nodes:
        values.extend(weights @ evaluation.values(evaluation.forecasts(model)).T for model in REPLY_MODELS[1:])
    return np.concatenate(values)
