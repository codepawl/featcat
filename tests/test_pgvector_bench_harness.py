"""Smoke tests for the pgvector bench harness.

These do NOT exercise Postgres — they only verify the bench module imports
cleanly and its random-embedding helper produces valid 384-d unit vectors.
The point is to catch import-time regressions (e.g. a renamed model field
breaking the bench) even on CI runners that don't have Postgres.
"""

from __future__ import annotations

import math
import os
import random
from importlib import import_module, reload

import pytest


def _import_bench_module() -> object:
    """Import the bench module with a dummy URL so its top-level skip doesn't fire.

    The bench file is gated by ``pytest.skip(..., allow_module_level=True)``
    when ``FEATCAT_BENCH_DB_URL`` is unset. Setting it to a fake URL lets the
    module finish importing — we never connect to it from these tests.
    """
    os.environ.setdefault("FEATCAT_BENCH_DB_URL", "postgresql+psycopg2://noop:noop@localhost:1/none")
    mod = import_module("tests.perf.test_pgvector_bench")
    # Reload to ensure a fresh module state if a previous test mutated env.
    return reload(mod)


def test_bench_module_imports_cleanly() -> None:
    """The bench file must import without raising — guards against API drift."""
    try:
        mod = _import_bench_module()
    except pytest.skip.Exception:
        # If psycopg2 / pgvector aren't installed, the module skips at import
        # time. That's a valid environment-skip — not a harness regression.
        pytest.skip("bench module skipped due to missing live-DB deps")
    assert hasattr(mod, "random_embedding")
    assert hasattr(mod, "bench_insert")
    assert hasattr(mod, "bench_similarity_top_k")


def test_random_embedding_is_unit_normalized() -> None:
    """Generated vectors must be 384-d and roughly unit-length."""
    try:
        mod = _import_bench_module()
    except pytest.skip.Exception:
        pytest.skip("bench module skipped due to missing live-DB deps")
    rng = random.Random(123)
    vec = mod.random_embedding(rng)
    assert isinstance(vec, list)
    assert len(vec) == 384
    norm = math.sqrt(sum(x * x for x in vec))
    # Float arithmetic; allow tiny tolerance.
    assert math.isclose(norm, 1.0, abs_tol=1e-9)
    assert all(isinstance(x, float) for x in vec)


def test_random_embedding_is_seedable() -> None:
    """Same seed → same vector. Critical for run-over-run comparison."""
    try:
        mod = _import_bench_module()
    except pytest.skip.Exception:
        pytest.skip("bench module skipped due to missing live-DB deps")
    a = mod.random_embedding(random.Random(42))
    b = mod.random_embedding(random.Random(42))
    assert a == b
    c = mod.random_embedding(random.Random(43))
    assert a != c
