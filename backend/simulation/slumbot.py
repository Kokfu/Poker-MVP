"""Bridge for benchmarking local bots against Slumbot's public API (Phase 5A).

Slumbot (slumbot.com) is a strong heads-up no-limit bot that publishes an API
specifically so other bots can measure themselves against it: 50/100 blinds,
20,000-chip stacks reset every hand, and ``bN`` means "my total on this
street is N" — the same total-target semantics as the local engine.

Each Slumbot hand is replayed through the authoritative ``HandEngine``: our
bot plays one seat, a proxy replays Slumbot's actions in the other seat, and a
remote deck supplies Slumbot's board as it is revealed.  Legal actions,
observations, and range tracking therefore come from the same code as local
play.  Any disagreement between the engine and the server is reported as a
desync, never silently patched.  Slumbot's reported winnings are authoritative
and are cross-checked against the engine settlement when cards are known.

This talks only to Slumbot's bot-benchmark API; it is not a poker-site client.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import random
import time
from typing import Any, Callable, Protocol
import urllib.error
import urllib.request

from poker_analyzer import FULL_DECK
from .actions import Action
from .engine import HandEngine

SLUMBOT_HOST = "slumbot.com"
SLUMBOT_STACK = 20_000
SLUMBOT_SMALL_BLIND = 50
SLUMBOT_BIG_BLIND = 100


class SlumbotProtocolError(RuntimeError):
    """The server rejected a request or returned an unusable response."""


class SlumbotDesync(RuntimeError):
    """The local engine and the server disagree about the hand."""


class Transport(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class HttpTransport:
    def __init__(self, host: str = SLUMBOT_HOST, timeout: float = 30.0, retries: int = 3, backoff_seconds: float = 2.0):
        self.base = f"https://{host}"
        self.timeout, self.retries, self.backoff_seconds = timeout, retries, backoff_seconds

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")
                if error.code < 500 or attempt == self.retries:
                    raise SlumbotProtocolError(f"HTTP {error.code} from {path}: {detail}") from error
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == self.retries:
                    raise SlumbotProtocolError(f"network error on {path}: {error}") from error
            time.sleep(self.backoff_seconds * (2 ** attempt))
        raise AssertionError("unreachable")


class SlumbotClient:
    """Minimal token-carrying client; the server may rotate the token."""

    def __init__(self, transport: Transport | None = None, token: str | None = None):
        self.transport = transport or HttpTransport()
        self.token = token

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.transport.post(path, body)
        if not isinstance(response, dict):
            raise SlumbotProtocolError(f"non-object response from {path}")
        if response.get("error_msg"):
            raise SlumbotProtocolError(f"{path}: {response['error_msg']}")
        if response.get("token"):
            self.token = response["token"]
        return response

    def new_hand(self) -> dict[str, Any]:
        return self._post("/api/new_hand", {"token": self.token} if self.token else {})

    def act(self, incr: str) -> dict[str, Any]:
        return self._post("/api/act", {"token": self.token, "incr": incr})


def parse_actions(action: str) -> list[tuple[int, str]]:
    """Split a Slumbot action string into ``(street_index, token)`` pairs."""
    tokens: list[tuple[int, str]] = []
    street, index = 0, 0
    while index < len(action):
        char = action[index]
        if char == "/":
            street += 1
            index += 1
        elif char in "kcf":
            tokens.append((street, char))
            index += 1
        elif char == "b":
            end = index + 1
            while end < len(action) and action[end].isdigit():
                end += 1
            if end == index + 1:
                raise SlumbotProtocolError(f"bet without size in {action!r}")
            tokens.append((street, action[index:end]))
            index = end
        else:
            raise SlumbotProtocolError(f"unexpected character {char!r} in {action!r}")
    return tokens


class _HandBridge:
    def __init__(self, client: SlumbotClient, response: dict[str, Any]):
        self.client = client
        self.applied = 0
        self.engine: HandEngine | None = None
        self.client_seat = "a" if response.get("client_pos") == 1 else "b"  # 1 = small blind/button
        self.remote_seat = "b" if self.client_seat == "a" else "a"
        self._accept(response)

    def _accept(self, response: dict[str, Any]) -> None:
        self.response = response
        self.tokens = parse_actions(response.get("action", ""))
        if response.get("winnings") is not None and response.get("bot_hole_cards") and self.engine is not None:
            # Real cards replace the placeholders before any showdown evaluation.
            self.engine.holes[self.remote_seat] = list(response["bot_hole_cards"])

    @property
    def board(self) -> list[str]:
        return list(self.response.get("board") or [])

    @property
    def finished(self) -> bool:
        return self.response.get("winnings") is not None

    def next_remote_token(self) -> str:
        if self.applied >= len(self.tokens):
            raise SlumbotDesync("engine expects a Slumbot action the server has not sent")
        token = self.tokens[self.applied][1]
        self.applied += 1
        return token

    def send(self, incr: str) -> None:
        if self.finished:
            raise SlumbotDesync("engine asked for an action after the server ended the hand")
        self._accept(self.client.act(incr))
        if self.applied >= len(self.tokens) or self.tokens[self.applied][1] != incr:
            raise SlumbotDesync(f"server did not echo action {incr!r}: {self.response.get('action')!r}")
        self.applied += 1


class RemoteDeck:
    """Deals the two seats' hole cards, then Slumbot's board as revealed."""

    def __init__(self, bridge: _HandBridge, seat_cards: dict[str, list[str]]):
        self.bridge, self.seat_cards, self.calls, self.board_dealt = bridge, seat_cards, 0, 0

    def deal(self, count: int = 1) -> list[str]:
        if self.calls < 2:
            cards = self.seat_cards["ab"[self.calls]]
            self.calls += 1
            return list(cards)
        board = self.bridge.board
        if len(board) < self.board_dealt + count:
            raise SlumbotDesync("engine dealt a street the server has not revealed")
        cards = board[self.board_dealt:self.board_dealt + count]
        self.board_dealt += count
        self._move_placeholders(board)
        return list(cards)

    def _move_placeholders(self, board: list[str]) -> None:
        """Keep the unknown seat's placeholder cards off the revealed board."""
        engine, seat = self.bridge.engine, self.bridge.remote_seat
        if engine is None or self.bridge.finished and self.bridge.response.get("bot_hole_cards"):
            return
        blocked = set(board) | set(engine.holes[self.bridge.client_seat])
        if blocked & set(engine.holes[seat]):
            engine.holes[seat] = [card for card in reversed(FULL_DECK) if card not in blocked][:2]


def _limits(observation) -> tuple[tuple[str, ...], int | None, int, int, int, int]:
    """(legal, min target, max target, street commitment, stack, highest bet) for either observation type."""
    state = getattr(observation, "decision_state", None)
    if state is not None:
        return (tuple(state.legal_actions), state.minimum_legal_target, state.maximum_legal_target,
                state.hero_street_commitment, state.hero_stack, state.current_highest_bet)
    return (tuple(observation.legal_actions), observation.minimum_target_to, observation.maximum_target_to,
            observation.current_bet, observation.hero_stack, observation.current_bet + observation.amount_to_call)


def to_incr(action: Action, observation) -> tuple[Action, str]:
    """Legalize ``action`` exactly as the engine would, then encode it."""
    legal, minimum, maximum, commitment, stack, highest = _limits(observation)
    kind, amount = action.type, action.amount
    if kind not in legal:
        kind, amount = ("check" if "check" in legal else "fold"), None
    if kind in ("bet", "raise") and (amount is None or minimum is None or not minimum <= amount <= maximum):
        kind, amount = ("check" if highest == commitment else "fold"), None
    if kind == "fold" and "check" in legal:
        kind = "check"  # never fold when checking is free; keeps both sides in sync
    if kind == "check":
        return Action("check"), "k"
    if kind == "call":
        return Action("call"), "c"
    if kind == "fold":
        return Action("fold"), "f"
    if kind == "all_in":
        target = commitment + stack
        return Action("all_in"), (f"b{target}" if target > highest else "c")
    return Action(kind, amount), f"b{amount}"


def from_token(token: str, observation) -> Action:
    legal, _, maximum, _, _, _ = _limits(observation)
    if token == "k":
        action = Action("check")
    elif token == "c":
        action = Action("call") if "call" in legal else Action("all_in")
    elif token == "f":
        action = Action("fold")
    else:
        target = int(token[1:])
        if target >= maximum and "all_in" in legal:
            action = Action("all_in")
        else:
            action = Action("raise" if "raise" in legal else "bet", target)
    if action.type not in legal:
        raise SlumbotDesync(f"Slumbot action {token!r} is not legal locally: {legal}")
    return action


class _RemoteSeat:
    """Engine-facing stand-in for Slumbot; it only replays server actions."""

    def __init__(self, bridge: _HandBridge):
        self.bridge = bridge

    def decide(self, observation) -> Action:
        return from_token(self.bridge.next_remote_token(), observation)


class _ClientSeat:
    def __init__(self, bot, bridge: _HandBridge):
        self.bot, self.bridge = bot, bridge

    def __getattr__(self, name):  # range-equity settings, seeds, traces
        return getattr(self.bot, name)

    def decide(self, observation) -> Action:
        return self._send(self.bot.decide(observation), observation)

    def _send(self, action: Action, observation) -> Action:
        applied, incr = to_incr(action, observation)
        self.bridge.send(incr)
        return applied


class _DecisionClientSeat(_ClientSeat):
    def decide_decision(self, observation) -> Action:
        return self._send(self.bot.decide_decision(observation), observation)


@dataclass
class SlumbotHandResult:
    hand_index: int
    client_position: str
    hole_cards: list[str]
    board: list[str]
    action: str
    winnings: int | None
    baseline_winnings: int | None = None
    engine_net: int | None = None
    settlement_verified: bool | None = None
    desync: str | None = None
    decisions: int = 0
    elapsed_seconds: float = 0.0
    bot_hole_cards: list[str] = field(default_factory=list)


def play_slumbot_hand(client: SlumbotClient, bot, hand_index: int = 0) -> SlumbotHandResult:
    started = time.perf_counter()
    response = client.new_hand()
    bridge = _HandBridge(client, response)
    hole = list(response.get("hole_cards") or [])
    if len(hole) != 2:
        raise SlumbotProtocolError("new_hand did not return two hole cards")
    # Opponent cards are unknown until showdown; placeholders never reach our
    # bot's observation and are replaced before any showdown evaluation.
    placeholder = [card for card in reversed(FULL_DECK) if card not in hole][:2]
    seat_cards = {bridge.client_seat: hole, bridge.remote_seat: placeholder}
    seat_class = _DecisionClientSeat if hasattr(bot, "decide_decision") else _ClientSeat
    client_seat = seat_class(bot, bridge)
    seats = {bridge.client_seat: client_seat, bridge.remote_seat: _RemoteSeat(bridge)}
    engine = HandEngine(
        seats["a"], seats["b"],
        starting_stacks={"a": SLUMBOT_STACK, "b": SLUMBOT_STACK},
        bb=SLUMBOT_BIG_BLIND, small_blind=SLUMBOT_SMALL_BLIND, button="a",
        hand_id=f"slumbot-{hand_index}", deck=RemoteDeck(bridge, seat_cards),
    )
    bridge.engine = engine
    engine.range_trackers.pop(bridge.remote_seat, None)  # its "known cards" are placeholders
    if bridge.finished and response.get("bot_hole_cards"):
        engine.holes[bridge.remote_seat] = list(response["bot_hole_cards"])
    desync = None
    engine_net = None
    try:
        result = engine.play()
        if result["illegal_actions"]:
            raise SlumbotDesync(f"engine applied fallbacks: {result['illegal_diagnostics']}")
        if not bridge.finished or bridge.applied != len(bridge.tokens):
            raise SlumbotDesync("engine finished before the server")
        engine_net = result["stacks"][bridge.client_seat] - SLUMBOT_STACK
    except SlumbotDesync as error:
        desync = str(error)
        _finish_passively(bridge)
    final = bridge.response
    winnings = final.get("winnings")
    return SlumbotHandResult(
        hand_index=hand_index,
        client_position="button" if bridge.client_seat == "a" else "big_blind",
        hole_cards=hole, board=bridge.board, action=final.get("action", ""),
        winnings=winnings, baseline_winnings=final.get("baseline_winnings"),
        engine_net=engine_net,
        settlement_verified=None if engine_net is None or winnings is None else engine_net == winnings,
        desync=desync, decisions=sum(1 for _ in engine._records if _["acting_player"] == bridge.client_seat),
        elapsed_seconds=time.perf_counter() - started,
        bot_hole_cards=list(final.get("bot_hole_cards") or []),
    )


def _finish_passively(bridge: _HandBridge, limit: int = 20) -> None:
    """After a desync, end the hand on the server without further strategy."""
    for _ in range(limit):
        if bridge.finished:
            return
        for incr in ("k", "c", "f"):
            try:
                bridge._accept(bridge.client.act(incr))
                break
            except SlumbotProtocolError:
                continue
        else:
            raise SlumbotProtocolError("could not finish desynced hand")
    if not bridge.finished:
        raise SlumbotProtocolError("desynced hand did not finish")


def summarize_slumbot(results: list[SlumbotHandResult], bootstrap_resamples: int = 2_000, statistics_seed: int = 91_003) -> dict[str, Any]:
    played = [r for r in results if r.winnings is not None]
    bb = [r.winnings / SLUMBOT_BIG_BLIND for r in played]
    n = len(bb)
    def rate(values):
        return 100.0 * sum(values) / len(values) if values else 0.0
    rng = random.Random(statistics_seed)
    samples = sorted(rate([bb[rng.randrange(n)] for _ in range(n)]) for _ in range(bootstrap_resamples)) if n else []
    interval = {"lower": samples[int(0.025 * (len(samples) - 1))], "upper": samples[int(0.975 * (len(samples) - 1))]} if samples else {"lower": 0.0, "upper": 0.0}
    baseline = [(r.winnings - r.baseline_winnings) / SLUMBOT_BIG_BLIND for r in played if r.baseline_winnings is not None]
    return {
        "hands": n,
        "bb_per_100": rate(bb),
        "confidence_interval_95": interval,
        "baseline_adjusted_bb_per_100": rate(baseline) if baseline else None,
        "desyncs": sum(r.desync is not None for r in results),
        "settlement_mismatches": sum(r.settlement_verified is False for r in results),
        "mean_seconds_per_hand": sum(r.elapsed_seconds for r in results) / len(results) if results else 0.0,
    }


def run_slumbot_session(bot_factory: Callable[[int], Any], hands: int, client: SlumbotClient | None = None, pause_seconds: float = 0.0, on_hand: Callable[[SlumbotHandResult], None] | None = None) -> tuple[list[SlumbotHandResult], dict[str, Any]]:
    """Play ``hands`` sequential hands (one at a time per token, as Slumbot asks)."""
    client = client or SlumbotClient()
    results = []
    for index in range(hands):
        result = play_slumbot_hand(client, bot_factory(index), index)
        results.append(result)
        if on_hand:
            on_hand(result)
        if pause_seconds:
            time.sleep(pause_seconds)
    return results, summarize_slumbot(results)


def result_dict(result: SlumbotHandResult) -> dict[str, Any]:
    return asdict(result)
