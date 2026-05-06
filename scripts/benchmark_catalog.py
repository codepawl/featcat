#!/usr/bin/env python
"""Benchmark featcat API endpoints. Pairs with ``generate_synthetic_features.py``.

Hits each endpoint ``--iters`` times against a running server and reports
``p50 / p95 / p99 / max`` in milliseconds.

Endpoints exercised:
- ``GET /api/features``                                — full list (legacy mode)
- ``GET /api/features?limit=50``                       — paginated mode
- ``GET /api/features?limit=50&search=col_0042``       — paginated + search
- ``GET /api/features/by-name?name=...``               — single feature detail
- ``GET /api/sources``                                 — cached list
- ``GET /api/stats``                                   — cached dashboard

Usage:
    python scripts/benchmark_catalog.py --base-url http://localhost:8000 --iters 100
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--timeout", type=float, default=30.0)
    return p.parse_args()


def time_request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> float:
    """Return latency in milliseconds. Raises on non-2xx so a broken endpoint
    fails fast instead of silently skewing the distribution."""
    start = time.perf_counter()
    resp = client.request(method, path, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    return elapsed_ms


def summarize(samples: list[float]) -> dict[str, float]:
    samples = sorted(samples)
    return {
        "n": len(samples),
        "p50": statistics.median(samples),
        "p95": samples[int(len(samples) * 0.95) - 1] if samples else 0.0,
        "p99": samples[int(len(samples) * 0.99) - 1] if samples else 0.0,
        "max": max(samples) if samples else 0.0,
    }


def fmt_row(name: str, stats: dict[str, float]) -> str:
    return (
        f"{name:<48} n={stats['n']:>4}  "
        f"p50={stats['p50']:>7.1f}ms  p95={stats['p95']:>7.1f}ms  "
        f"p99={stats['p99']:>7.1f}ms  max={stats['max']:>7.1f}ms"
    )


def main() -> int:
    args = parse_args()
    client = httpx.Client(base_url=args.base_url, timeout=args.timeout)

    # First grab a real feature name for the detail benchmark.
    first = client.get("/api/features", params={"limit": 1}).json()
    items = first.get("items", []) if isinstance(first, dict) else first
    if not items:
        print("No features in catalog. Run scripts/generate_synthetic_features.py first.", file=sys.stderr)
        return 1
    sample_name = items[0]["name"]

    bench: dict[str, list[float]] = {
        "GET /api/features (full list)": [],
        "GET /api/features?limit=50": [],
        "GET /api/features?limit=50&search=col_0042": [],
        f"GET /api/features/by-name?name={sample_name}": [],
        "GET /api/sources (cached)": [],
        "GET /api/stats (cached)": [],
    }

    for _ in range(args.iters):
        bench["GET /api/features (full list)"].append(time_request(client, "GET", "/api/features"))
        bench["GET /api/features?limit=50"].append(time_request(client, "GET", "/api/features", params={"limit": 50}))
        bench["GET /api/features?limit=50&search=col_0042"].append(
            time_request(client, "GET", "/api/features", params={"limit": 50, "search": "col_0042"})
        )
        bench[f"GET /api/features/by-name?name={sample_name}"].append(
            time_request(client, "GET", "/api/features/by-name", params={"name": sample_name})
        )
        bench["GET /api/sources (cached)"].append(time_request(client, "GET", "/api/sources"))
        bench["GET /api/stats (cached)"].append(time_request(client, "GET", "/api/stats"))

    print(f"Base URL: {args.base_url}")
    print(f"Iterations: {args.iters}")
    print()
    for name, samples in bench.items():
        print(fmt_row(name, summarize(samples)))
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
