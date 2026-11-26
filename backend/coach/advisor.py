"""Reuse exact postflop solves across Coach requests for the same hand."""
from solver.bot import AdaptiveSolverBot, StreetSolve
from solver.exact_cache import ExactCache


_SOLVES = ExactCache[StreetSolve](4)  # one hand's streets plus an off-tree re-solve


class CoachAdvisor(AdaptiveSolverBot):
    exact_preflop_cache = True

    def __init__(self, *, seed: int, exploit: bool, cache_solves: bool, disk_path=None):
        super().__init__(seed=seed)
        self.exploit = exploit
        self.pool_streets = exploit
        self.cache_solves = cache_solves
        self.disk_path = disk_path

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
        solve_street = super()._solve
        # StreetSolve's policy and EV data are read-only after solving. Compute
        # misses outside the lock so one hand cannot stall unrelated cache hits.
        def compute():
            return solve_street(root_state, board, ranges, hero_combo, hero, profile)

        if self.disk_path is None or not self.explain_ev or self.gated_locks or self.sized_reads:
            return _SOLVES.get_or_compute(key, compute)
        from .solve_disk import load_or_compute

        return _SOLVES.get_or_compute(key, lambda: load_or_compute(
            self.disk_path, key, root_state, self.postflop_menu, ranges, compute,
        ))
