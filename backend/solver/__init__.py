"""Phase 5 range-based heads-up solver used by the ``solver`` bot.

Layout:

* ``combos``  – the 1,326 hole-card combos, blockers, and 169 starting-hand classes
* ``equity``  – eval7 rank vectors and combo-versus-combo equity matrices
* ``tree``    – one-street betting trees that follow the engine's legal-target rules
* ``cfr``     – vectorized discounted CFR over whole ranges
* ``preflop`` – offline preflop charts (solved once, loaded at runtime)
* ``bot``     – ``SolverBot``: preflop chart + real-time postflop re-solving

Everything here sees only player-visible state (hero cards, public board,
public actions); ranges are public beliefs, never reads of hidden cards.
"""
