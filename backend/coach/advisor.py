"""Reuse exact postflop solves across Coach requests for the same hand."""
from collections import OrderedDict
from threading import Lock

from solver.bot import AdaptiveSolverBot


_SOLVES = OrderedDict()
_SOLVES_LOCK = Lock()
_MAX_SOLVES = 4  # keep one hand's streets, with room for an off-tree re-solve


class CoachAdvisor(AdaptiveSolverBot):
    exact_preflop_cache = True

    def __init__(self, *, seed: int, exploit: bool, cache_solves: bool):
        super().__init__(seed=seed)
        self.exploit = exploit
        self.pool_streets = exploit
        self.cache_solves = cache_solves

    def _solve(self, root_state, board, ranges, hero_combo, hero, profile=None, *, working_ids=None):
        # Persistent-range research supplies its own projection of working IDs.
        if not self.cache_solves or self.capture_river_shadow or working_ids is not None:
            return super()._solve(root_state, board, ranges, hero_combo, hero, profile, working_ids=working_ids)

        # A solve depends on the exact start state, both ranges and the opponent
        # reads that feed postflop locks. It never uses the sampling RNG.
        reads = None if profile is None else (
            tuple((street, tuple(sorted(stats.items()))) for street, stats in sorted(profile.street_statistics.items())),
            tuple(sorted(self._strength_correlation().items())),
        )
        key = (root_state, tuple(board), hero_combo, hero, reads,
               tuple((weights.dtype.str, weights.tobytes()) for weights in ranges),
               self.iterations[root_state.street], self.pool_streets, self.postflop_menu, self.flop_runouts, self.prune, self.explain_ev)
        with _SOLVES_LOCK:
            cached = _SOLVES.get(key)
            if cached is not None:
                _SOLVES.move_to_end(key)
                return cached
        solved = super()._solve(root_state, board, ranges, hero_combo, hero, profile)
        # StreetSolve's policy and EV data are read-only after solving. Compute
        # misses outside the lock so one hand cannot stall unrelated cache hits.
        with _SOLVES_LOCK:
            _SOLVES[key] = solved
            _SOLVES.move_to_end(key)
            if len(_SOLVES) > _MAX_SOLVES:
                _SOLVES.popitem(last=False)
        return solved
