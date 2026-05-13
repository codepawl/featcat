"""Lineage helpers (T1.1b).

The catalog stores lineage edges in the ``feature_lineage`` table; this
package contains the *non-storage* helpers: SQL parsing, edge proposal, and
future provenance import paths.

The optional ``[lineage-sql]`` extra pulls in ``sqlglot``. The detector
imports it lazily so importing :mod:`featcat.lineage` itself stays cheap and
doesn't break when the extra isn't installed — callers (CLI, scheduler)
hit a clear ImportError only when they actually invoke the detector.
"""

from __future__ import annotations

from .sql_detect import ProposedEdge, detect_lineage_from_file, detect_lineage_from_sql

__all__ = ["ProposedEdge", "detect_lineage_from_file", "detect_lineage_from_sql"]
