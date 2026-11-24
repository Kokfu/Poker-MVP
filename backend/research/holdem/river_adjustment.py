"""Research-only bound on river policy changes against fold/call replies."""
from math import fsum

from research.holdem.phase_4k import to_action


MAX_LOSS_BB = 0.50


def payoff_endpoints(state, action):
    """For loss, split and win, return the possible net chip transfers."""
    hero, villain, response = state.branch(action)
    if action.type == "fold":
        return ((0,), (0,), (0,))
    matched = min(hero, villain)
    paid = matched - state.hero_commit
    pot = state.pot - state.hero_commit - state.villain_commit + 2 * matched
    showdown = (-paid, (pot + state.hero_gets_odd_chip) // 2 - paid, pot - paid)
    return tuple((value, state.pot) if response else (value,) for value in showdown)


def lower_transfer(state, incumbent, repaired):
    """Minimum incremental chips over showdown results and independent replies.

    Use the same result for all actions against a holding. Each aggression's
    continuation is independently free to fold or call. Linear averaging over
    holdings and probabilistic replies cannot make the result any smaller.
    """
    menu = sorted(incumbent.keys() | repaired.keys())
    shifts = [repaired.get(key, 0.) - incumbent.get(key, 0.) for key in menu]
    endpoints = [payoff_endpoints(state, to_action(key)) for key in menu]
    return min(fsum(min(shift * value for value in points)
                    for shift, points in zip(shifts, outcome, strict=True))
               for outcome in zip(*endpoints, strict=True))


def bounded_adjustment(state, incumbent, repaired, big_blind):
    """Mix in the maximum fraction of the proposed change within the budget."""
    if state.villain_stack == 0 or state.hero_stack <= state.villain_commit - state.hero_commit:
        return incumbent.copy(), 0., None
    bound = lower_transfer(state, incumbent, repaired)
    budget = MAX_LOSS_BB * big_blind
    fraction = min(1., budget / -bound) if bound < 0 else 1.
    menu = sorted(incumbent.keys() | repaired.keys())
    mix = {key: (1 - fraction) * incumbent.get(key, 0.) + fraction * repaired.get(key, 0.)
           for key in menu}
    return mix, fraction, bound / big_blind
