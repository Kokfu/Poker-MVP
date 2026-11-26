"""Check two confirmed Coach clients with and without concurrent speculation."""

import argparse
import asyncio
from collections import defaultdict
import json
import math
from pathlib import Path
from random import Random
from statistics import median
import sys
from time import perf_counter

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from coach.reference_spots import REFERENCE, fingerprint


async def measure(competition):
    fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
    rng = Random(20261127)
    timings = defaultdict(list)
    base = "http://127.0.0.1:5178"
    path = "/api/coach/advise"

    async with (
        httpx.AsyncClient(base_url=base, timeout=40, trust_env=False) as first,
        httpx.AsyncClient(base_url=base, timeout=40, trust_env=False) as second,
        httpx.AsyncClient(base_url=base, timeout=40, trust_env=False) as speculative,
    ):
        (await first.get("/api/health")).raise_for_status()

        async def confirm(client, spot):
            start = perf_counter()
            response = await client.post(path, json=spot["request"])
            elapsed = (perf_counter() - start) * 1_000
            response.raise_for_status()
            if fingerprint(response.json()) != spot["expected"]:
                raise ValueError(f"confirmed advice changed at {spot['id']}")
            return elapsed

        for street in ("flop", "turn", "river"):
            eligible = [spot for spot in fixture["spots"]
                        if spot["id"].startswith(street + "-") and not spot["request"]["opponent"]]
            selected = rng.sample(eligible, 12)
            for offset in range(0, len(selected), 3):
                left, right, other = selected[offset:offset + 3]
                pending = None
                if competition:
                    pending = asyncio.create_task(speculative.post(
                        path, json=other["request"], headers={"X-Coach-Speculative": "1"},
                    ))
                    await asyncio.sleep(0.05)
                try:
                    times = await asyncio.gather(confirm(first, left), confirm(second, right))
                finally:
                    if pending is not None:
                        response = await pending
                        if response.status_code != 204:
                            raise ValueError(f"speculative request unexpectedly returned {response.status_code}")
                timings[street].extend(times)
                timings["postflop"].extend(times)

    return {
        street: {
            "confirmed": len(times), "median_ms": round(median(times), 2),
            "p95_ms": round(sorted(times)[math.ceil(.95 * len(times)) - 1], 2),
        } for street, times in timings.items()
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-speculation", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(measure(args.with_speculation)), indent=2))
