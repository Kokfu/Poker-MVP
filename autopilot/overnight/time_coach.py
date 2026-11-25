"""Time the Coach API in-process with generated spots and an isolated SQLite database."""
import argparse
from contextlib import ExitStack
import gc
import hashlib
import json
import math
import os
from pathlib import Path
from random import Random
import re
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, sleep

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient
import httpx
from coach.service import spot_to_dict
from coach.store import HandStore
from main import app
from poker_analyzer import FULL_DECK
from test_coach_learning import simulated_spots


def action(actor, kind, amount=None):
    return {"actor": actor, "action": kind, "amount": amount}


def cases():
    preflop = [action("villain", "raise", 250), action("hero", "call")]
    checks = [action("hero", "check"), action("villain", "check")]
    for i, (cards, board) in enumerate([
        (["As", "Kd"], ["7h", "8d", "2c", "Jd", "3h"]),
        (["Jc", "9d"], ["Qh", "7s", "2d", "Tc", "3h"]),
        (["5h", "5d"], ["Ad", "Kc", "4c", "6s", "9d"]),
        (["Ac", "Qc"], ["Jc", "Tc", "2h", "3c", "Kd"]),
    ]):
        base = {"hero_cards": cards, "opponent": "Synthetic" if i % 2 else None}
        yield f"preflop-{i}", base
        yield f"flop-{i}", dict(base, hero_position="big_blind", actions=preflop, board=board[:3])
        yield f"turn-{i}", dict(base, hero_position="big_blind", actions=preflop + checks, board=board[:4])
        yield f"river-{i}", dict(base, hero_position="big_blind", actions=preflop + 2 * checks, board=board)


def scenarios(suit_variants):
    suits = "cdhs"
    for variant in range(suit_variants):
        shifted = suits[variant:] + suits[:variant]
        mapping = str.maketrans(suits, shifted)
        for label, payload in cases():
            if variant:
                label += f"-suits{variant}"
                payload["hero_cards"] = [card.translate(mapping) for card in payload["hero_cards"]]
                if "board" in payload:
                    payload["board"] = [card.translate(mapping) for card in payload["board"]]
            yield label, payload


def representative_scenarios():
    rng = Random(20261126)
    for board_size, street in ((0, "preflop"), (3, "flop"), (4, "turn"), (5, "river")):
        for index in range(12):
            button, blind = ("hero", "villain") if index % 2 == 0 else ("villain", "hero")
            path = index // 2 % 3
            deal = rng.sample(FULL_DECK, 2 + board_size)
            depth = (2_500, 6_000, 10_000, 20_000)[index // 3]
            opponent = (None, "Synthetic", "Aggressive synthetic")[index % 3]
            if not board_size:
                paths = (
                    ([], [action(button, "call"), action(blind, "raise", 300)],
                     [action(button, "raise", 250), action(blind, "raise", 650)])
                    if button == "hero"
                    else ([action(button, "call")], [action(button, "raise", 250)],
                          [action(button, "raise", 450)])
                )
                actions = paths[path]
            else:
                actions = (
                    [action(button, "call"), action(blind, "check")],
                    [action(button, "raise", 250), action(blind, "call")],
                    [action(button, "raise", 250), action(blind, "raise", 650), action(button, "call")],
                )[path]
                for prior in range(board_size - 3):
                    actions += (
                        [action(blind, "check"), action(button, "check")],
                        [action(blind, "bet", 175), action(button, "call")],
                        [action(blind, "check"), action(button, "bet", 250), action(blind, "call")],
                    )[(path + prior) % 3]
                if button == "hero":
                    actions.append(action(blind, "bet", 200) if path == 2 else action(blind, "check"))
                elif path == 2:
                    actions += [action(blind, "check"), action(button, "bet", 200)]
            yield f"{street}-representative-{index}", {
                "hero_cards": deal[:2], "board": deal[2:], "actions": actions,
                "hero_position": "button" if button == "hero" else "big_blind",
                "hero_stack": depth, "villain_stack": depth, "opponent": opponent,
            }


def http_client(stack, scratch):
    server_log = Path(scratch) / "uvicorn.log"
    with server_log.open("w", encoding="utf-8") as output:
        server = subprocess.Popen(
            [sys.executable, "-B", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "0",
             "--no-access-log", "--no-proxy-headers"],
            cwd=BACKEND, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def stop_server():
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

    stack.callback(stop_server)
    deadline = perf_counter() + 30
    while server.poll() is None and perf_counter() < deadline:
        startup = server_log.read_text(encoding="utf-8", errors="replace")
        if address := re.search(r"Uvicorn running on (http://127\.0\.0\.1:\d+)", startup):
            return stack.enter_context(httpx.Client(base_url=address[1], timeout=60, trust_env=False))
        sleep(0.025)
    raise RuntimeError(f"Local Uvicorn did not start: {server_log.read_text(encoding='utf-8', errors='replace')}")


def measure(repeats, suit_variants, wait_for_warmup, representative=False, http=False):
    measurements = []
    with TemporaryDirectory() as scratch, ExitStack() as stack:
        # SQLite connection cycles can retain Windows file handles until GC.
        stack.callback(gc.collect)
        os.environ["COACH_DB_PATH"] = str(Path(scratch) / "timing.sqlite")
        store = HandStore()
        for spot in simulated_spots("tight", 150):
            store.add("Synthetic", spot_to_dict(spot))
        if representative:
            for spot in simulated_spots("aggressive", 150, seed0=2_000):
                store.add("Aggressive synthetic", spot_to_dict(spot))
        startup = perf_counter()
        client = http_client(stack, scratch) if http else stack.enter_context(TestClient(app))
        startup_ms = 1000 * (perf_counter() - startup)
        if wait_for_warmup and (worker := app.state.coach_warmup):
            worker.join()
        ready_ms = 1000 * (perf_counter() - startup)
        workload = representative_scenarios() if representative else scenarios(suit_variants)
        for label, payload in workload:
            for repeat in range(repeats):
                start = perf_counter()
                response = client.post("/api/coach/advise", json=payload)
                ms = 1000 * (perf_counter() - start)
                response.raise_for_status()
                result = response.json()
                assert result["status"] == "hero_to_act", result
                if representative:
                    assert result["state"]["street"] == label.split("-", 1)[0], (label, result)
                explanation = result["explanation"]
                # Runtime metadata may change without any change to the advice.
                explanation.pop("solve_seconds", None)
                explanation.get("instrumentation", {}).pop("cache_hit", None)
                encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
                measurements.append({"spot": label, "repeat": repeat,
                                     "ms": round(ms, 2), "action": result["advice"],
                                     "source": explanation["source"],
                                     "advice_sha256": hashlib.sha256(encoded).hexdigest()})
    summary = {}
    cohorts = ("preflop", "postflop", "flop", "turn", "river") if representative else ("preflop", "postflop")
    for cohort in cohorts:
        for phase in ("all", "first", "repeat"):
            ms = sorted(row["ms"] for row in measurements
                        if (not row["spot"].startswith("preflop-") if cohort == "postflop"
                            else row["spot"].startswith(cohort + "-"))
                        and (phase == "all" or (row["repeat"] == 0) == (phase == "first")))
            if ms:
                summary[f"{cohort}_{phase}"] = {"n": len(ms), "median_ms": median(ms),
                                               "p95_ms": ms[math.ceil(.95 * len(ms)) - 1]}
    return {"startup_ms": round(startup_ms, 2), "measurement_start_ms": round(ready_ms, 2),
            "summary": summary, "measurements": measurements}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--suit-variants", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--representative", action="store_true",
                        help="48 distinct spots with varied boards and action paths")
    parser.add_argument("--expect", type=Path, help="fail if advice differs from this baseline report")
    parser.add_argument("--wait-for-warmup", action="store_true")
    parser.add_argument("--http", action="store_true", help="use a fresh loopback Uvicorn process")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.representative and args.suit_variants != 1:
        parser.error("--representative cannot be combined with multiple suit variants")
    if args.http and args.wait_for_warmup:
        parser.error("--wait-for-warmup requires in-process requests")
    report = measure(args.repeats, args.suit_variants, args.wait_for_warmup, args.representative, args.http)
    if args.expect:
        def hashes(rows):
            return {(row["spot"], row["repeat"]): row["advice_sha256"] for row in rows}

        expected = hashes(json.loads(args.expect.read_text(encoding="utf-8-sig"))["measurements"])
        actual = hashes(report["measurements"])
        different = sorted(key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key))
        if different:
            parser.exit(1, f"Advice mismatch at {different}\n")
        report["matching_responses"] = len(actual)
    print(json.dumps(report, indent=2))
