"""The per-player strategy cache and the leaner lock fit must change nothing but speed."""
import numpy as np
import pytest

from solver.cfr import RangeSolver, fit_frequencies
from solver.exploit import tree_locks
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree
from test_solver_exploit import profile


def reference_fit_frequencies(sigma, reach, target, floor=0.02, rounds=12):
    """The implementation before the change, kept verbatim as the reference."""
    total = reach.sum()
    if total <= 0:
        return sigma
    target = np.clip(np.asarray(target, dtype=np.float64), 1e-6, None)
    target = target / target.sum()
    base = (sigma + floor) / (1.0 + floor * len(sigma))
    scale = np.ones(len(sigma))
    fitted = base
    for _ in range(rounds):
        fitted = base * scale[:, None]
        fitted = fitted / fitted.sum(axis=0, keepdims=True)
        aggregate = (fitted * reach).sum(axis=1) / total
        scale = scale * target / np.clip(aggregate, 1e-9, None)
    return fitted


@pytest.mark.parametrize("fortran", [False, True])
@pytest.mark.parametrize("dtype", [np.float64, np.float32])
def test_fit_frequencies_is_bit_identical_to_the_reference(dtype, fortran):
    rng = np.random.default_rng(4)
    for _ in range(200):
        actions, combos = int(rng.integers(2, 6)), int(rng.integers(1, 300))
        sigma = rng.dirichlet(np.ones(actions), size=combos).T.astype(dtype)  # a transposed view: Fortran-ordered
        if not fortran:
            sigma = np.ascontiguousarray(sigma)
        reach = rng.uniform(0.0, 1.0, combos) * (rng.uniform(size=combos) > 0.2)
        target = rng.dirichlet(np.ones(actions))
        assert np.array_equal(fit_frequencies(sigma, reach, target), reference_fit_frequencies(sigma, reach, target))
    zero = np.zeros(3)
    assert fit_frequencies(np.ones((2, 3)) / 2, zero, np.array([0.5, 0.5])) is not None


def build(opponent: int, cached: bool, seed: int = 1) -> RangeSolver:
    rng = np.random.default_rng(seed)
    tree = StreetTree(StreetState("flop", 1, (0, 0), (9_000, 9_000), (500, 500), 100), POSTFLOP_MENU)
    n, m = 40, 36
    d = rng.uniform(-1, 1, (n, m)).astype(np.float32)
    ranges = (rng.uniform(0.2, 1.0, n), rng.uniform(0.2, 1.0, m))
    locks = tree_locks(tree, opponent, "flop", profile("high"), {"aggressive": 0.6, "call": 0.8})
    assert locks, "the profile must lock at least one opponent node"
    solver = RangeSolver(tree, ranges, d, np.ones((n, m), dtype=bool), locks=locks)
    solver._policy_cache = cached
    return solver


@pytest.mark.parametrize("opponent", [0, 1])
def test_cached_locked_solve_is_bit_identical_to_recomputing(opponent):
    cached, plain = build(opponent, True), build(opponent, False)
    for _ in range(40):
        cached.iterate()
        plain.iterate()
    for node in cached.regret:
        assert np.array_equal(cached.regret[node], plain.regret[node]), node
        assert np.array_equal(cached.strategy_sum[node], plain.strategy_sum[node]), node
    average_cached, average_plain = cached.final_policy(), plain.final_policy()
    assert all(np.array_equal(average_cached[node], average_plain[node]) for node in average_plain)
    assert cached.exploitability() == plain.exploitability()


@pytest.mark.parametrize("opponent", [0, 1])
def test_policy_calls_match_a_fresh_computation_at_every_step(opponent):
    solver = build(opponent, True)
    reference = build(opponent, False)
    for _ in range(6):
        for traverser_pass in range(2):  # mimic the two policy() calls inside one iterate()
            assert all(np.array_equal(a, b) for a, b in zip(solver.policy(solver.current).values(), reference.policy(reference.current).values()))
        solver.iterate()
        reference.iterate()


def test_unlocked_solve_is_unchanged_by_the_cache():
    cached, plain = build(0, True, 2), build(0, False, 2)
    cached.locks = plain.locks = {}
    for _ in range(25):
        cached.iterate()
        plain.iterate()
    assert all(np.array_equal(cached.regret[node], plain.regret[node]) for node in cached.regret)


def test_average_policy_is_never_served_from_the_cache():
    solver = build(1, True)
    for _ in range(5):
        solver.iterate()
    current_first = solver.policy(solver.current)
    assert not any(np.array_equal(current_first[node], solver.final_policy()[node]) for node in current_first)
