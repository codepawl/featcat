"""Pytest configuration for the opt-in perf suite.

Performance benches are double-gated:

1. ``@pytest.mark.perf`` — registered marker; required on every bench.
2. ``--bench`` CLI flag — custom flag declared here. Without it, perf tests
   are deselected even if the user runs ``pytest tests/perf -m perf``.

Why two gates? The marker alone would let a stray ``pytest`` invocation in
``tests/perf/`` collect and run the suite, which can take many minutes and
needs a live Postgres. Requiring an explicit ``--bench`` makes it
impossible to trigger the suite by accident from CI or pre-commit.

Bench functions are named ``bench_*`` (not the default ``test_*``) because
the prefix doubles as their result-recorder category. The
``python_functions`` ini override below teaches pytest to collect them in
this directory only.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--bench",
        action="store_true",
        default=False,
        help="Run the opt-in performance benches in tests/perf/.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "perf: mark a test as part of the opt-in performance bench suite (requires --bench to actually run).",
    )
    # Scope ``bench_*`` collection to this directory. The global pyproject
    # config keeps ``test_*`` for the rest of the suite; here we union both.
    # Using ``inicfg`` would persist beyond this session — we only want it
    # for collection inside tests/perf/, which is what setting it on the
    # config object during pytest_configure achieves.
    cfg = config.getini("python_functions")
    if "bench_*" not in cfg:
        cfg.append("bench_*")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip perf-marked tests when --bench is not passed.

    Using a dynamic skip (rather than ``--deselect``) keeps reported test
    counts honest: pytest still shows the bench tests as ``skipped``,
    making it obvious when an operator forgot the flag.
    """
    if config.getoption("--bench"):
        return
    skip_marker = pytest.mark.skip(reason="perf bench requires --bench flag")
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip_marker)
