from dataclasses import dataclass
from typing import Literal

ActionType = Literal["fold", "check", "call", "bet", "raise", "all_in"]
@dataclass(frozen=True)
class Action:
    type: ActionType
    # Bet/raise amount is the target total committed for this betting round.
    amount: int | None = None
