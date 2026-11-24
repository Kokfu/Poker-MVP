"""Research-only replay projection and closing-river sensitivity policy."""
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from research.holdem.phase_4o import PriorTrace
from research.holdem.phase_4r import RangeSupportError, conditional_range
from solver.bot import SolverBot, _full_equity
from solver.combos import COMBOS, COMBO_COUNT, card_mask, combo_index


MAX_COLUMNS = 896
ODDS_RATIO = 2.0


@dataclass(frozen=True)
class WorkingSet:
    ids: np.ndarray
    positive: int
    retained: float

    @property
    def omitted(self):
        return 1.0 - self.retained


def working_set(weights, blocked, required, compatible=None):
    """Return sorted global IDs with an explicit probability mass ledger."""
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("invalid persistent reach")
    legal = np.where(blocked, 0.0, weights)
    scale = legal.max()
    if scale == 0:
        reason = "all positive holdings blocked" if weights.any() else "zero model reach"
        raise RangeSupportError(reason)
    if compatible is not None and not legal[compatible].any():
        raise RangeSupportError("no Hero-compatible opponent reach")

    keep = legal > PriorTrace.prune * scale
    forced = required
    if compatible is not None:
        forced = int(np.argmax(np.where(compatible, legal, 0.0)))
    if forced is not None:
        keep[forced] = True

    ids = np.flatnonzero(keep)
    if len(ids) > MAX_COLUMNS:
        order = np.argsort(-legal[ids], kind="stable")
        ids = ids[order[:MAX_COLUMNS]]
        if forced is not None and forced not in ids:
            ids[-1] = forced
        ids.sort()
    scaled = legal / scale
    return WorkingSet(ids, int(np.count_nonzero(legal)), min(1.0, float(scaled[ids].sum() / scaled.sum())))


def update_reach(weights, ids, likelihoods):
    """Project a solved action row onto persistent reach without adding support."""
    if (not np.isfinite(likelihoods).all() or (likelihoods < 0).any()
            or (likelihoods > 1 + 1e-12).any()):
        raise ValueError("invalid observed action likelihood")
    # Common rescaling is immaterial to the posterior. Keep unusually small
    # reach away from underflow before multiplying by action probabilities.
    scale = weights.max()
    prior = weights / scale if 0 < scale < 1e-30 else weights
    kept = prior[ids]
    solved = kept * likelihoods
    total = kept.sum()
    if total <= 0:
        raise RangeSupportError("observed action has no weighted likelihood donors")
    observed = solved.sum()
    if observed <= 0:
        reason = ("observed action unsupported on omitted reach"
                  if np.count_nonzero(prior) > np.count_nonzero(kept)
                  else "observed action has zero model reach")
        raise RangeSupportError(reason)
    updated = prior * (observed / total)
    updated[ids] = solved
    return updated


class ResearchReplay(PriorTrace):
    """Observe the incumbent or project public reach onto bounded CFR columns."""

    def __init__(self, separate=False):
        super().__init__()
        self.separate = separate
        self.projections = []

    def trace(self, spot, profile=None):
        node, ds, advice = super().trace(spot, profile)
        self.live_node = node
        return node, ds, advice

    def _decide(self, ds, profile=None):
        self.actions.clear()
        self.roots.clear()
        self.projections.clear()
        self.estimate = None
        self.probabilities = None
        if hasattr(self, "pre_bet"):
            del self.pre_bet
        self.decision_street = ds.street
        if self.separate:
            # A Coach spot can reuse the same hand ID with edited history,
            # stacks or profile. Scope projected solves to this replay.
            self.memory = None
        return super()._decide(ds, profile)

    def _solve(self, state, board, ranges, hero_combo, hero, profile=None):
        if not self.separate:
            return super()._solve(state, board, ranges, hero_combo, hero, profile)
        blocked = card_mask(board)
        compatible = ~card_mask(COMBOS[hero_combo])
        projection = []
        solver_reach = []
        for player, weights in enumerate(ranges):
            try:
                selection = working_set(weights, blocked, hero_combo if player == hero else None,
                                        compatible if player != hero else None)
            except RangeSupportError as error:
                raise RangeSupportError(f"{state.street}, seat {player}: {error}") from error
            reach = np.zeros(COMBO_COUNT)
            reach[selection.ids] = weights[selection.ids]
            scale = reach.max()
            if 0 < scale < 1e-30:
                reach /= scale
            projection.append(selection)
            solver_reach.append(reach)

        # The incumbent solver already accepts dense combo-indexed reach.
        # Select columns once here, then have it use those positive columns.
        explain_ev = self.explain_ev
        self.prune, self.explain_ev = 0, state.street == self.decision_street
        try:
            solved = super()._solve(state, board, solver_reach, hero_combo, hero, profile)
        finally:
            self.prune, self.explain_ev = PriorTrace.prune, explain_ev
        for selection, columns in zip(projection, solved.combos, strict=True):
            if not np.array_equal(selection.ids, columns):
                raise AssertionError("working-set column mapping changed")
        self.projections.append((state.street, tuple(projection)))
        return solved

    def _apply_strategy(self, weights, solve, node, choice):
        if not self.separate:
            return super()._apply_strategy(weights, solve, node, choice)
        current = solve.tree.nodes[node]
        try:
            updated = update_reach(weights, solve.combos[current.player], solve.average[node][choice])
        except RangeSupportError as error:
            raise RangeSupportError(f"{current.state.street}, seat {current.player}: {error}") from error
        self.actions.append((weights, solve, node, choice, updated))
        return updated

    def _range_report(self, board, hero_combo, villain):
        if self.separate and board:
            try:
                self.estimate = conditional_range(villain, card_mask((*board, *COMBOS[hero_combo])))
            except RangeSupportError as error:
                raise RangeSupportError(f"{self.decision_street} decision: {error}") from error
            return SolverBot._range_report(self, board, hero_combo, self.estimate)
        return super()._range_report(board, hero_combo, villain)


def closing_bounds(outcome_mass, net_payoffs):
    """Sharp bounds under normalized per-holding multipliers in [1, 2]."""
    values = []
    for split in (1, 2):
        lower_weights = outcome_mass.copy()
        upper_weights = outcome_mass.copy()
        lower_weights[:split] *= ODDS_RATIO
        upper_weights[split:] *= ODDS_RATIO
        values.append((float(lower_weights @ net_payoffs / lower_weights.sum()),
                       float(upper_weights @ net_payoffs / upper_weights.sum())))
    return min(lower for lower, _ in values), max(upper for _, upper in values)


def closing_policy(bot, node, ds):
    """Return a modified chooser policy and diagnostic for a terminal cover."""
    if (ds.street != "river" or node.labels != ["fold", "call"]
            or set(ds.legal_actions) - {"fold", "call", "all_in"} or bot.estimate is None):
        return bot.probabilities, None

    live, equity, _ = _full_equity(tuple(ds.board_cards), bot.flop_runouts)
    hero = int(np.searchsorted(live, combo_index(ds.hole_cards)))
    posterior = bot.estimate[live]
    results = equity[hero]
    masses = np.array([posterior[results == result].sum() for result in (-1, 0, 1)])
    if not np.isclose(masses.sum(), 1, rtol=0, atol=1e-12):
        raise AssertionError("terminal outcomes do not partition the posterior")
    call_leaf = bot.river.tree.nodes[node.children[1]]
    cost = min(ds.hero_stack, ds.amount_to_call)
    pot = sum(call_leaf.contribution)
    tie = (pot + int(ds.acting_player == "b")) // 2
    payoffs = np.array([-cost, tie - cost, pot - cost])
    lower, upper = closing_bounds(masses, payoffs)
    nominal = float(masses @ payoffs)
    if lower <= 0:
        mix = np.array([1., 0.])
    else:
        mix = bot.probabilities
    return mix, {"lower": lower, "upper": upper, "nominal": nominal, "suppresses_cover": lower <= 0}
