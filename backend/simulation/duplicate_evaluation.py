"""Duplicate-deal heads-up evaluation (Phase 5A).

Every seed is played twice with identical cards.  The engine deals seat A's
hole cards, then seat B's, then the board from one seeded deck, and seat A is
always the button, so swapping the bots between seats gives each bot exactly
the cards and position its opponent held.  The pair total cancels most card
luck; each pair is one statistical unit.

With ``session_hands > 1`` each unit is a *session*: the same two bot
instances play that many consecutive hands (stacks reset each hand, button
alternating), and each side's ``OpponentModel`` profile of the other grows
hand by hand exactly as in persistent matches.  The whole session is replayed
with seats swapped on identical cards, so learning is measured without card
luck.

This is a separate report type with its own schema version; the accepted
evaluation schema 1.0 is unchanged.  Holdout seeds are reserved for final
acceptance runs so strategy development cannot be fitted to them.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
import math
import os
import random
import statistics
from itertools import combinations
from typing import Any, Literal, Sequence

from .bots import BOT_TYPES
from .engine import HandEngine
from .evaluation import _bot, _json_safe, _percentile_interval, _validate_history_and_conservation, interpret_interval
from .opponent_model import OpponentModel


DUPLICATE_SCHEMA_VERSION = "1.0"
SEED_SETS = {"development": 1_000_000, "holdout": 7_000_000}
SeedSet = Literal["development", "holdout"]


@dataclass(frozen=True)
class DuplicateConfig:
    starting_stack: int = 10_000
    small_blind: int = 50
    big_blind: int = 100
    pairs: int = 500
    seed_set: SeedSet = "development"
    seed_offset: int = 0
    equity_iterations: int = 100
    bootstrap_resamples: int = 2_000
    statistics_seed: int = 91_002
    confidence_level: float = 0.95
    workers: int = 1
    session_hands: int = 1  # 1 = memoryless independent hands

    def __post_init__(self) -> None:
        if self.seed_set not in SEED_SETS:
            raise ValueError("seed_set must be development or holdout")
        for name in ("starting_stack", "small_blind", "big_blind", "pairs", "equity_iterations", "bootstrap_resamples", "workers", "session_hands"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed_offset) is not int or self.seed_offset < 0:
            raise ValueError("seed_offset must be a non-negative integer")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind cannot exceed big_blind")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")

    def seeds(self) -> tuple[int, ...]:
        """First hand seed of every unit (one hand, or one session)."""
        base = SEED_SETS[self.seed_set] + self.seed_offset
        return tuple(base + index * self.session_hands for index in range(self.pairs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DuplicatePair:
    """Strategy results for one deal (or session) played from both seats.

    In independent mode seat A is always the button, so ``net_seat_a`` is the
    button result and ``net_seat_b`` the big-blind result.
    """
    seed: int
    net_seat_a: int
    net_seat_b: int
    illegal_actions: int
    fallback_actions: int
    deal_verified: bool
    hands_per_seat: int = 1

    @property
    def net(self) -> int:
        return self.net_seat_a + self.net_seat_b

    @property
    def hands(self) -> int:
        return 2 * self.hands_per_seat


def _play_hand(config: DuplicateConfig, strategy: str, opponent: str, seed: int, strategy_seat: str):
    strategy_bot = _bot(strategy, seed, "strategy", config.equity_iterations)
    opponent_bot = _bot(opponent, seed, "opponent", config.equity_iterations)
    first, second = (strategy_bot, opponent_bot) if strategy_seat == "a" else (opponent_bot, strategy_bot)
    engine = HandEngine(
        first, second,
        starting_stacks={"a": config.starting_stack, "b": config.starting_stack},
        bb=config.big_blind, small_blind=config.small_blind,
        seed=seed, simulation_seed=seed, button="a",
        hand_id=f"duplicate-{seed}-{strategy_seat}",
    )
    holes = (tuple(engine.holes["a"]), tuple(engine.holes["b"]))
    result = engine.play()
    net_a = result["stacks"]["a"] - config.starting_stack
    net_b = result["stacks"]["b"] - config.starting_stack
    _validate_history_and_conservation(result["history"], net_a, net_b)
    net = net_a if strategy_seat == "a" else net_b
    return net, holes, tuple(result["state"].community_cards), result["illegal_actions"], len(result["illegal_diagnostics"])


def notify_completed_hand(seats, history) -> None:
    """Give bots that opt in the finished, validated public history.

    Only bots defining ``observe_completed_hand`` are called; the history
    contains hole cards solely when both were revealed at showdown."""
    for seat, bot in zip(("a", "b"), seats):
        hook = getattr(bot, "observe_completed_hand", None)
        if hook is not None:
            hook(history, seat)


def _same_deal(first, second) -> bool:
    (holes_a, board_a), (holes_b, board_b) = first, second
    shared = min(len(board_a), len(board_b))
    return holes_a == holes_b and board_a[:shared] == board_b[:shared]


def _play_sessions(config: DuplicateConfig, strategy: str, opponent: str, start: int):
    """Both seat orientations of one session, interleaved hand by hand.

    Each orientation keeps its own persistent bot instances and opponent
    models; interleaving only lets per-board caches serve both replays.
    """
    sides = {}
    for strategy_seat in ("a", "b"):
        strategy_bot = _bot(strategy, start, "strategy", config.equity_iterations)
        opponent_bot = _bot(opponent, start, "opponent", config.equity_iterations)
        seats = (strategy_bot, opponent_bot) if strategy_seat == "a" else (opponent_bot, strategy_bot)
        sides[strategy_seat] = {"seats": seats, "models": {"a": OpponentModel("a"), "b": OpponentModel("b")},
                                "net": 0, "illegal": 0, "fallback": 0, "deals": []}
    for index in range(config.session_hands):
        seed = start + index
        for strategy_seat, side in sides.items():
            models = side["models"]
            engine = HandEngine(
                side["seats"][0], side["seats"][1],
                starting_stacks={"a": config.starting_stack, "b": config.starting_stack},
                bb=config.big_blind, small_blind=config.small_blind,
                seed=seed, simulation_seed=start, button="a" if index % 2 == 0 else "b",
                hand_id=f"session-{start}-{index}", hand_number=index + 1, match_id=f"session-{start}",
                # Each player sees the profile of the *other* seat built from completed hands.
                opponent_profile_provider=lambda player, models=models: models["b" if player == "a" else "a"].snapshot(),
            )
            holes = (tuple(engine.holes["a"]), tuple(engine.holes["b"]))
            result = engine.play()
            net_a = result["stacks"]["a"] - config.starting_stack
            net_b = result["stacks"]["b"] - config.starting_stack
            _validate_history_and_conservation(result["history"], net_a, net_b)
            models["a"].update(result["history"])
            models["b"].update(result["history"])
            notify_completed_hand(side["seats"], result["history"])
            side["net"] += net_a if strategy_seat == "a" else net_b
            side["illegal"] += result["illegal_actions"]
            side["fallback"] += len(result["illegal_diagnostics"])
            side["deals"].append((holes, tuple(result["state"].community_cards)))
    return sides["a"], sides["b"]


def play_duplicate_pair(config: DuplicateConfig, strategy: str, opponent: str, seed: int) -> DuplicatePair:
    if config.session_hands > 1:
        side_a, side_b = _play_sessions(config, strategy, opponent, seed)
        return DuplicatePair(
            seed=seed, net_seat_a=side_a["net"], net_seat_b=side_b["net"],
            illegal_actions=side_a["illegal"] + side_b["illegal"], fallback_actions=side_a["fallback"] + side_b["fallback"],
            deal_verified=all(_same_deal(x, y) for x, y in zip(side_a["deals"], side_b["deals"])), hands_per_seat=config.session_hands,
        )
    button_net, holes_a, board_a, illegal_a, fallback_a = _play_hand(config, strategy, opponent, seed, "a")
    blind_net, holes_b, board_b, illegal_b, fallback_b = _play_hand(config, strategy, opponent, seed, "b")
    return DuplicatePair(
        seed=seed, net_seat_a=button_net, net_seat_b=blind_net,
        illegal_actions=illegal_a + illegal_b, fallback_actions=fallback_a + fallback_b,
        deal_verified=_same_deal((holes_a, board_a), (holes_b, board_b)),
    )


def _single_threaded_workers() -> None:
    # Worker processes already run in parallel; multi-threaded BLAS inside
    # each of them would oversubscribe the CPU.  Children inherit this.
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")


def _run_seed_chunk(job: tuple[dict[str, Any], str, str, tuple[int, ...]]) -> list[DuplicatePair]:
    config_values, strategy, opponent, seeds = job
    config = DuplicateConfig(**config_values)
    return [play_duplicate_pair(config, strategy, opponent, seed) for seed in seeds]


def run_duplicate_pairs(config: DuplicateConfig, strategy: str, opponent: str, executor: ProcessPoolExecutor | None = None) -> tuple[DuplicatePair, ...]:
    """Results are identical for every worker count; chunks keep seed order."""
    for name in (strategy, opponent):
        if name not in BOT_TYPES:
            raise ValueError(f"unknown bot: {name}")
    seeds = config.seeds()
    if config.workers == 1 and executor is None:
        return tuple(_run_seed_chunk((config.as_dict(), strategy, opponent, seeds)))
    chunk = max(1, math.ceil(len(seeds) / (config.workers * 4)))
    jobs = [(config.as_dict(), strategy, opponent, seeds[i:i + chunk]) for i in range(0, len(seeds), chunk)]
    if executor is not None:
        return tuple(pair for part in executor.map(_run_seed_chunk, jobs) for pair in part)
    _single_threaded_workers()
    with ProcessPoolExecutor(max_workers=config.workers) as pool:
        return tuple(pair for part in pool.map(_run_seed_chunk, jobs) for pair in part)


def _bb100(pair_nets: Sequence[float], big_blind: int, hands_per_pair: int = 2) -> float:
    return 100.0 * sum(pair_nets) / (hands_per_pair * len(pair_nets) * big_blind) if pair_nets else 0.0


def summarize_pairs(pairs: Sequence[DuplicatePair], config: DuplicateConfig, stream: int = 0) -> dict[str, Any]:
    nets = [pair.net for pair in pairs]
    n = len(nets)
    per_pair = pairs[0].hands if pairs else 2
    estimate = _bb100(nets, config.big_blind, per_pair)
    rng = random.Random(config.statistics_seed + stream)
    resampled = [_bb100([nets[rng.randrange(n)] for _ in range(n)], config.big_blind, per_pair) for _ in range(config.bootstrap_resamples)] if n else []
    interval = _percentile_interval(resampled, config.confidence_level) if n else {"lower": 0.0, "upper": 0.0, "confidence_level": config.confidence_level}
    seat_units = [value / config.big_blind for pair in pairs for value in (pair.net_seat_a, pair.net_seat_b)]
    duplicate_se = 100.0 * statistics.stdev(nets) / config.big_blind / per_pair / math.sqrt(n) if n > 1 else 0.0
    unpaired_se = 100.0 * statistics.stdev(seat_units) / (per_pair / 2) / math.sqrt(len(seat_units)) if len(seat_units) > 1 else 0.0
    return {
        "pairs": n,
        "hands": per_pair * n,
        "bb_per_100": estimate,
        "standard_error_bb_per_100": duplicate_se,
        "unpaired_standard_error_bb_per_100": unpaired_se,
        "variance_reduction": 1.0 - (duplicate_se / unpaired_se) ** 2 if unpaired_se else 0.0,
        "confidence_interval": interval,
        "interpretation": interpret_interval(estimate, interval),
        "seat_a_bb_per_100": 100.0 * sum(p.net_seat_a for p in pairs) / config.big_blind / (n * per_pair / 2) if n else 0.0,
        "seat_b_bb_per_100": 100.0 * sum(p.net_seat_b for p in pairs) / config.big_blind / (n * per_pair / 2) if n else 0.0,
        "illegal_actions": sum(p.illegal_actions for p in pairs),
        "fallback_actions": sum(p.fallback_actions for p in pairs),
        "deal_mismatches": sum(not p.deal_verified for p in pairs),
    }


def duplicate_report(config: DuplicateConfig, strategy: str, opponent: str) -> dict[str, Any]:
    pairs = run_duplicate_pairs(config, strategy, opponent)
    return _json_safe({
        "duplicate_schema_version": DUPLICATE_SCHEMA_VERSION,
        "report_type": "duplicate_evaluation",
        "configuration": config.as_dict(),
        "strategy": strategy,
        "opponent": opponent,
        "methodology": _methodology(config),
        "metrics": summarize_pairs(pairs, config),
        "raw_pairs": [asdict(pair) for pair in pairs],
    })


def _methodology(config: DuplicateConfig) -> dict[str, Any]:
    return {
        "unit": "duplicate pair: one seeded deal played with the strategy in each seat",
        "stacks": "reset every hand",
        "button": "seat A in both hands; the strategy holds the button cards once and the big-blind cards once",
        "confidence_method": "deterministic percentile bootstrap over pairs",
        "seed_set": config.seed_set,
        "seed_range": [config.seeds()[0], config.seeds()[-1]],
        "holdout_policy": "holdout seeds are reserved for frozen final acceptance runs",
    }


def run_tournament(config: DuplicateConfig, bots: Sequence[str]) -> dict[str, Any]:
    """Round robin: every unordered bot pair played on the same seed schedule."""
    names = list(dict.fromkeys(bots))
    if len(names) < 2:
        raise ValueError("a tournament needs at least two distinct bots")
    for name in names:
        if name not in BOT_TYPES:
            raise ValueError(f"unknown bot: {name}")
    results: dict[tuple[str, str], tuple[DuplicatePair, ...]] = {}
    if config.workers > 1:
        _single_threaded_workers()
    executor = ProcessPoolExecutor(max_workers=config.workers) if config.workers > 1 else None
    try:
        for first, second in combinations(names, 2):
            results[(first, second)] = run_duplicate_pairs(config, first, second, executor)
    finally:
        if executor is not None:
            executor.shutdown()
    return tournament_report(config, names, results)


def _net_vectors(names: Sequence[str], results: dict[tuple[str, str], Sequence[DuplicatePair]]) -> dict[tuple[str, str], list[int]]:
    vectors: dict[tuple[str, str], list[int]] = {}
    for (first, second), pairs in results.items():
        vectors[(first, second)] = [pair.net for pair in pairs]
        vectors[(second, first)] = [-pair.net for pair in pairs]  # zero-sum per pair
    return vectors


def _pool_scores(names, vectors, indices, big_blind, hands_per_pair=2) -> dict[str, float]:
    return {
        name: statistics.fmean(_bb100([vectors[(name, other)][i] for i in indices], big_blind, hands_per_pair) for other in names if other != name)
        for name in names
    }


def tournament_report(config: DuplicateConfig, names: Sequence[str], results: dict[tuple[str, str], Sequence[DuplicatePair]]) -> dict[str, Any]:
    vectors = _net_vectors(names, results)
    n = config.pairs
    all_indices = list(range(n))
    rows = []
    for stream, (first, second) in enumerate(combinations(names, 2), start=1):
        metrics = summarize_pairs(results[(first, second)], config, stream)
        rows.append({"strategy": first, "opponent": second, **metrics})
    pool = _pool_scores(names, vectors, all_indices, config.big_blind, 2 * config.session_hands)
    rng = random.Random(config.statistics_seed + 50_000)
    samples = []
    for _ in range(config.bootstrap_resamples):
        indices = [rng.randrange(n) for _ in all_indices]
        samples.append(_pool_scores(names, vectors, indices, config.big_blind, 2 * config.session_hands))
    ranking = sorted(names, key=lambda name: pool[name], reverse=True)
    standings = [
        {
            "rank": position + 1, "bot": name, "pool_bb_per_100": pool[name],
            "confidence_interval": _percentile_interval([sample[name] for sample in samples], config.confidence_level),
        }
        for position, name in enumerate(ranking)
    ]
    matrix = {name: {other: (_bb100(vectors[(name, other)], config.big_blind, 2 * config.session_hands) if other != name else None) for other in names} for name in names}
    return _json_safe({
        "duplicate_schema_version": DUPLICATE_SCHEMA_VERSION,
        "report_type": "duplicate_tournament",
        "configuration": config.as_dict(),
        "bots": list(names),
        "methodology": {**_methodology(config), "pool_score": "unweighted mean of head-to-head bb/100 against every other bot; bootstrap resamples seeds jointly across all pairings"},
        "rows": rows,
        "matrix_bb_per_100": matrix,
        "standings": standings,
        "bootstrap_pool_samples": samples,
        "totals": {
            "hands": sum(row["hands"] for row in rows),
            "illegal_actions": sum(row["illegal_actions"] for row in rows),
            "fallback_actions": sum(row["fallback_actions"] for row in rows),
            "deal_mismatches": sum(row["deal_mismatches"] for row in rows),
        },
    })


def win_rate_gate(report: dict[str, Any], candidate: str) -> dict[str, Any]:
    """Phase 5 acceptance gate for ``candidate`` inside a tournament report.

    Passes only when every head-to-head interval is above zero and the
    candidate's pool score beats the best other bot with the paired bootstrap
    interval of that difference above zero.
    """
    names = report["bots"]
    if candidate not in names:
        raise ValueError(f"{candidate} is not in the tournament")
    head_to_head = []
    for row in report["rows"]:
        if candidate not in (row["strategy"], row["opponent"]):
            continue
        flipped = row["opponent"] == candidate
        estimate = -row["bb_per_100"] if flipped else row["bb_per_100"]
        lower = -row["confidence_interval"]["upper"] if flipped else row["confidence_interval"]["lower"]
        upper = -row["confidence_interval"]["lower"] if flipped else row["confidence_interval"]["upper"]
        head_to_head.append({"opponent": row["strategy"] if flipped else row["opponent"], "bb_per_100": estimate, "lower": lower, "upper": upper, "passed": lower > 0})
    others = [name for name in names if name != candidate]
    pool = {entry["bot"]: entry["pool_bb_per_100"] for entry in report["standings"]}
    best_other = max(others, key=lambda name: pool[name])
    differences = [sample[candidate] - max(sample[name] for name in others) for sample in report["bootstrap_pool_samples"]]
    interval = _percentile_interval(differences, report["configuration"]["confidence_level"])
    clean = report["totals"]["illegal_actions"] == 0 and report["totals"]["deal_mismatches"] == 0
    passed = all(item["passed"] for item in head_to_head) and interval["lower"] > 0 and clean
    return _json_safe({
        "candidate": candidate,
        "seed_set": report["configuration"]["seed_set"],
        "head_to_head": head_to_head,
        "pool": {"candidate_bb_per_100": pool[candidate], "best_other": best_other, "best_other_bb_per_100": pool[best_other], "difference_interval": interval},
        "clean_play": clean,
        "passed": passed,
        "acceptance_eligible": passed and report["configuration"]["seed_set"] == "holdout",
    })
