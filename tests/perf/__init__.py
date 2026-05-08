"""Opt-in performance tests.

Performance tests are NOT collected by the default ``pytest`` run. They are
gated behind the ``perf`` marker AND the ``--bench`` CLI flag (see
``conftest.py`` in this directory). This keeps slow / infra-dependent
benches out of ``make check`` while still letting operators run them
locally with ``make bench``.
"""
