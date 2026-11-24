"""Offline aggregation of observable, completed heads-up histories."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256

from simulation.history import HandHistory, HandHistoryEvent, validate_hand_history

VERSION = 2
ACTIONS = ("fold", "check", "call", "bet", "raise", "shove")
AGGRESSION = {"bet", "raise", "all_in"}
STREETS = ("preflop", "flop", "turn", "river")


@dataclass(frozen=True, order=True)
class Situation:
    street: str
    position: str
    previous: str
    aggression_depth: int
    size_bucket: int
    depth_bucket: int
    spr_bucket: int
    closing: bool
    legal: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    event_index: int
    situation: Situation
    offered: int
    collectible: int
    matched_pot: int
    effective_stack: int
    big_blind: int
    response: str | None

    @property
    def wager_to_pot(self):
        return self.collectible / self.matched_pot if self.matched_pot else None

    @property
    def stack_to_pot(self):
        return self.effective_stack / self.matched_pot if self.matched_pot else None


def bucket(numerator, denominator, edges):
    return sum(numerator > edge * denominator for edge in edges) if denominator else -1


def situation(street, position, previous, aggression_depth, collectible,
              matched_pot, effective_stack, bb, closing, legal):
    return Situation(street, position, previous, min(aggression_depth, 3),
                     bucket(collectible, matched_pot, (0, .375, .75, 1.125)),
                     bucket(effective_stack, bb, (10, 30, 100)),
                     bucket(effective_stack, matched_pot, (1, 3, 8)), closing,
                     tuple(action for action in ACTIONS if action in legal))


def response_kind(action, price, stack, increased):
    if action == "all_in":
        return "shove" if increased else "call" if price and stack <= price else None
    return action if action in ACTIONS else None


def extract(history: HandHistory, seat: str) -> tuple[tuple[Observation, ...], int]:
    """Return eligible public observations and count decisions with unknown eligibility."""
    other = "b" if seat == "a" else "a"
    previous: HandHistoryEvent | None = None
    depth = 0
    observations = []
    unknown = 0
    for event in history.events:
        if event.event_type != "action_taken" or event.street not in STREETS:
            continue
        if previous is not None and previous.street != event.street:
            previous, depth = None, 0
        if event.actor == seat:
            price = event.amount_to_call_before
            own = getattr(event, f"street_commitment_{seat}_before")
            stack = getattr(event, f"stack_{seat}_before")
            their_stack = getattr(event, f"stack_{other}_before")
            prior = previous.applied_action if previous else "start"
            if (price is None or price != event.current_highest_bet_before - own
                    or stack <= 0 or not event.legal_actions
                    or any(action not in ACTIONS[:-1] + ("all_in",) for action in event.legal_actions)
                    or (previous is not None and previous.fallback_used is not False)):
                unknown += 1
            else:
                facing_wager = bool(price and previous and previous.actor == other
                                    and previous.current_highest_bet_after > previous.current_highest_bet_before)
                offered = price if facing_wager else 0
                collectible = min(offered, stack)
                matched = event.pot_before - price
                effective = min(stack, their_stack + price)
                # Aggression into a player who cannot put in more chips is uncollectible.
                legal = {response_kind(action, price, stack, stack > price)
                         for action in event.legal_actions
                         if their_stack > 0 or action not in AGGRESSION
                         or (action == "all_in" and stack <= price)}
                closing = bool(facing_wager and (their_stack == 0 or stack <= price))
                kind = response_kind(event.applied_action, price, stack,
                                     event.current_highest_bet_after > event.current_highest_bet_before)
                response = kind if (event.fallback_used is False and kind in legal
                                    and event.applied_action in event.legal_actions) else None
                if matched < 0 or not legal or None in legal:
                    unknown += 1
                else:
                    context = situation(event.street, "button" if history.button_player == seat else "big_blind",
                                        prior, depth, collectible, matched, effective,
                                        history.big_blind_amount, closing, legal)
                    observations.append(Observation(event.event_index, context, offered, collectible,
                                                    matched, effective, history.big_blind_amount, response))
        depth += event.current_highest_bet_after > event.current_highest_bet_before
        previous = event
    return tuple(observations), unknown


@dataclass
class Counts:
    opportunities: int = 0
    responses: Counter = field(default_factory=Counter)

    def add(self, observation):
        self.opportunities += 1
        if observation.response is not None:
            self.responses[observation.response] += 1

    @property
    def observed(self):
        return sum(self.responses.values())

    def evidence(self):
        return {"opportunities": self.opportunities, "observed": self.observed,
                "missing": self.opportunities - self.observed, "responses": {
                    action: self.responses[action] for action in ACTIONS}}


class ProfileV2:
    """Single-writer accumulator for one caller-namespaced opponent identity.

    Importers provide a stable source hand ID and the opponent's seat for each hand.
    The same ID must travel with copies. Missing legacy fields receive no imputation.
    """
    version = VERSION

    def __init__(self, opponent_id: str):
        if not opponent_id:
            raise ValueError("stable opponent identity required")
        self.opponent_id = opponent_id
        self._seen: dict[str, bytes] = {}
        self.pooled = defaultdict(Counts)
        self.conditional = defaultdict(Counts)
        self.unknown = 0

    @property
    def hands_observed(self):
        return len(self._seen)

    def update(self, source_hand_id: str, history: HandHistory, seat: str) -> bool:
        if not source_hand_id or seat not in {"a", "b"}:
            raise ValueError("stable source hand ID and explicit opponent seat required")
        if not history.settlement_complete or history.big_blind_amount <= 0:
            raise ValueError("settled hand with a positive big blind required")
        if not validate_hand_history(history).valid:
            raise ValueError("invalid or unsupported hand history")
        observations, unknown = extract(history, seat)
        fingerprint = sha256(repr((seat, observations, unknown)).encode()).digest()
        if source_hand_id in self._seen:
            if self._seen[source_hand_id] != fingerprint:
                raise ValueError("conflicting evidence for the same source hand ID")
            return False
        for observation in observations:
            context = observation.situation
            self.conditional[context].add(observation)
            self.pooled[context.street, context.legal].add(observation)
        self.unknown += unknown
        self._seen[source_hand_id] = fingerprint
        return True


def predict(legal, pooled, conditional=None):
    """Common add-one pooled law, optionally updated by a two-count Dirichlet prior."""
    total = sum(pooled.get(action, 0) for action in legal)
    baseline = {action: (pooled.get(action, 0) + 1) / (total + len(legal)) for action in legal}
    if conditional is None:
        return baseline
    n = sum(conditional.get(action, 0) for action in legal)
    return {action: (conditional.get(action, 0) + 2 * probability) / (n + 2)
            for action, probability in baseline.items()}


def forecast(profile, context, use_context):
    pooled = profile.pooled.get((context.street, context.legal))
    cell = profile.conditional.get(context) if use_context else None
    # Leave the cell out of its own empirical prior.
    counts = pooled.responses.copy() if pooled else Counter()
    if cell is not None:
        counts.subtract(cell.responses)
    return predict(context.legal, counts, cell.responses if cell is not None else None)
