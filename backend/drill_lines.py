"""Public action lines ending immediately before Hero's drill decision."""
from simulation.actions import Action


OPEN = Action("raise", 250)
MIN_OPEN = Action("raise", 200)
BIG_OPEN = Action("raise", 300)
THREE_BET = Action("raise", 750)
CALL = Action("call")
CHECK = Action("check")
SMALL_FLOP_BET = Action("bet", 165)
HALF_POT = Action("bet", 250)
PLAYED_FLOP = (OPEN, CALL, CHECK, SMALL_FLOP_BET, CALL)
PASSED_FLOP = (OPEN, CALL, CHECK, CHECK)

# Hero is always seat a. The first tuple field is the button, which controls
# the first actor on each street. Street and legality are verified by HandEngine.
LINES = {
    "preflop_open": (("a", ()),),
    "preflop_defend": (("b", (OPEN,)), ("b", (MIN_OPEN,)), ("b", (BIG_OPEN,))),
    "preflop_three_bet": (("a", (OPEN, THREE_BET)), ("b", (OPEN,)), ("b", (BIG_OPEN,))),
    "flop_cbet": (
        ("a", (OPEN, CALL, CHECK)), ("a", (BIG_OPEN, CALL, CHECK)), ("b", (OPEN, THREE_BET, CALL)),
    ),
    "flop_defend": (
        ("b", (OPEN, CALL, CHECK, SMALL_FLOP_BET)),
        ("b", (MIN_OPEN, CALL, CHECK, Action("bet", 400))),
        ("a", (OPEN, CALL, HALF_POT)),
    ),
    "turn": (
        ("a", (*PLAYED_FLOP, CHECK)), ("a", (*PASSED_FLOP, HALF_POT)), ("b", PLAYED_FLOP),
    ),
    "river_call": (
        ("a", (*PLAYED_FLOP, CHECK, CHECK, Action("bet", 410))),
        ("b", (*PLAYED_FLOP, CHECK, CHECK, CHECK, Action("bet", 420))),
        ("a", (*PASSED_FLOP, CHECK, CHECK, HALF_POT)),
    ),
    "river_bluff": (
        ("a", (*PLAYED_FLOP, CHECK, CHECK, CHECK)),
        ("b", (*PLAYED_FLOP, CHECK, CHECK)),
        ("a", (*PASSED_FLOP, CHECK, CHECK, CHECK)),
    ),
}
