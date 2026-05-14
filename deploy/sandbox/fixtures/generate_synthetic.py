"""Generate the synthetic sandbox Parquet fixture.

Run this only when the fixture schema changes; the resulting
``synthetic.parquet`` is committed to the repo so the sandbox launcher needs no
Python at runtime.

Schema (50 rows, deterministic seed so commits are reproducible):

    customer_id       string  random 8-char hex (NOT a real subscriber id)
    age_bucket        string  one of {"18-25", "26-35", "36-45", "46-60", "60+"}
    plan_tier         string  one of {"bronze", "silver", "gold", "platinum"}
    arpu_synthetic    float64 random uniform [50_000, 500_000]
    usage_gb          float64 random uniform [0.5, 50.0]
    churn_flag        int64   0/1 with 15 % positive rate
    signup_month      string  YYYY-MM in 2024-2025

No real telecom data. Every value is freshly sampled with a fixed seed. The
fixture is small on purpose: 50 rows keeps the parquet under 5 KB while still
producing a realistic-looking feature surface for scan-bulk and search.

Usage::

    uv pip install polars
    python deploy/sandbox/fixtures/generate_synthetic.py
"""

from __future__ import annotations

import random
import secrets
from pathlib import Path

import polars as pl

_OUT_PATH = Path(__file__).with_name("synthetic.parquet")
_ROW_COUNT = 50
_SEED = 20260514

_AGE_BUCKETS = ("18-25", "26-35", "36-45", "46-60", "60+")
_PLAN_TIERS = ("bronze", "silver", "gold", "platinum")
_SIGNUP_MONTHS = tuple(f"{year}-{month:02d}" for year in (2024, 2025) for month in range(1, 13))


def _build_rows(seed: int, count: int) -> dict[str, list[object]]:
    rng = random.Random(seed)
    # secrets.token_hex isn't seedable; bind RNG output through hex() so the
    # whole fixture stays deterministic across regenerations.
    rows: dict[str, list[object]] = {
        "customer_id": [f"syn-{rng.getrandbits(32):08x}" for _ in range(count)],
        "age_bucket": [rng.choice(_AGE_BUCKETS) for _ in range(count)],
        "plan_tier": [rng.choice(_PLAN_TIERS) for _ in range(count)],
        "arpu_synthetic": [round(rng.uniform(50_000, 500_000), 2) for _ in range(count)],
        "usage_gb": [round(rng.uniform(0.5, 50.0), 3) for _ in range(count)],
        "churn_flag": [1 if rng.random() < 0.15 else 0 for _ in range(count)],
        "signup_month": [rng.choice(_SIGNUP_MONTHS) for _ in range(count)],
    }
    return rows


def main() -> None:
    # `secrets` import kept above so a future maintainer who needs entropy for
    # non-reproducible columns has it ready. Reference the module here so ruff
    # does not flag it as unused on the static-only path.
    _ = secrets.token_hex
    rows = _build_rows(_SEED, _ROW_COUNT)
    df = pl.DataFrame(rows)
    df.write_parquet(_OUT_PATH)
    print(f"wrote {_OUT_PATH} ({_OUT_PATH.stat().st_size} bytes, {len(df)} rows)")


if __name__ == "__main__":
    main()
