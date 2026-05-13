"""sqlglot-based lineage auto-detection (T1.1b).

Parses SQL transformation files into proposed ``(child, parent, transform)``
edges that the user can confirm en masse via ``featcat lineage detect
--apply``. The parser is intentionally conservative: when it can't find a
clear output target it skips the statement with a warning rather than
emitting noisy edges.

Public API:

* :class:`ProposedEdge` — dataclass that the CLI / scheduler consumes.
* :func:`detect_lineage_from_sql` — parse a single SQL string.
* :func:`detect_lineage_from_file` — convenience wrapper that reads a path
  and propagates ``source_file`` onto each edge.

The optional ``[lineage-sql]`` extra (``uv pip install
'featcat[lineage-sql]'``) provides ``sqlglot``. We import it lazily so the
default install works fine until someone actually calls the detector.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    # ``Expr`` is sqlglot's root AST class — what ``parse_one`` actually
    # returns. ``Expression`` is a subclass; using ``Expr`` keeps the
    # signatures permissive enough to accept any AST node we walk.
    # Importing under TYPE_CHECKING keeps the optional-extra contract
    # intact (default install never imports sqlglot at all).
    from sqlglot.expressions import Expr

logger = logging.getLogger(__name__)

# AST node types we recognize as having an output target. Anything else
# (plain SELECT, DDL without a body, etc.) is skipped with a warning.
_TARGETED_NODES = ("Create", "Insert")


@dataclass(frozen=True)
class ProposedEdge:
    """A single lineage edge proposed by the SQL parser.

    Attributes:
        child: ``"<output_table>.<column>"`` — the derived feature name.
        parent: ``"<input_table>.<column>"`` — the upstream column. Plain
            column references with no table qualifier are emitted as
            ``"<column>"`` (no dot prefix); the CLI's apply step will look
            them up by feature name first, then source name.
        transform: SQL fragment that produced the child column (e.g.
            ``"a + b"`` or ``"count(distinct session_id)"``).
        source_file: Path of the .sql file the edge came from (set by
            :func:`detect_lineage_from_file`; ``None`` from the string-only
            entry point).
        source_line: 1-indexed line in ``source_file`` where the output
            alias appears. Best-effort — sqlglot's AST doesn't carry line
            numbers post-parse, so we re-scan the raw text. ``None`` when we
            can't locate it.
    """

    child: str
    parent: str
    transform: str
    source_file: str | None = None
    source_line: int | None = field(default=None)


def detect_lineage_from_sql(
    sql_text: str,
    dialect: str = "postgres",
    *,
    source_file: str | None = None,
) -> list[ProposedEdge]:
    """Parse ``sql_text`` and return proposed lineage edges.

    Multiple-parent is supported — a single ``c = a + b`` produces two
    edges. Aliases on FROM tables are resolved (``FROM bar t`` → parents
    use ``bar``, not ``t``).

    Args:
        sql_text: Raw SQL. Single statement; multi-statement scripts should
            be split by the caller (the CLI loops file-by-file).
        dialect: sqlglot dialect name. Defaults to ``"postgres"`` because
            it's the closest fit to the analytics-warehouse dialects most
            DS teams use; pass ``"snowflake"``, ``"bigquery"``, etc. when
            needed.
        source_file: Optional path attached to every emitted edge for the
            ``--apply`` summary. The string-only callers leave it ``None``;
            :func:`detect_lineage_from_file` fills it in.

    Returns:
        List of :class:`ProposedEdge`. Empty when the SQL has no clear
        output target (a warning is also emitted in that case).
    """
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as e:
        raise ImportError(
            "sqlglot is required for lineage auto-detection. Install with: uv pip install 'featcat[lineage-sql]'"
        ) from e

    try:
        tree = sqlglot.parse_one(sql_text, dialect=dialect)
    except Exception as e:
        warnings.warn(
            f"sqlglot failed to parse SQL ({source_file or 'inline'}): {e}",
            stacklevel=2,
        )
        return []

    if tree is None:
        return []

    target = _find_target(tree)
    if target is None:
        warnings.warn(
            f"Skipping SQL without a clear output target ({source_file or 'inline'}): {type(tree).__name__}",
            stacklevel=2,
        )
        return []

    target_name, body = target
    # body is the SELECT (or wrapped query) that produces rows.
    select = _unwrap_select(body)
    if select is None:
        warnings.warn(
            f"Skipping {target_name}: no SELECT body found ({source_file or 'inline'})",
            stacklevel=2,
        )
        return []

    alias_map = _build_alias_map(select)
    edges: list[ProposedEdge] = []
    for proj in select.expressions:
        column_alias, body_node = _extract_alias_and_body(proj)
        if column_alias is None:
            # No alias and not a bare column — skip (we don't know what
            # to call the output column).
            continue
        child = f"{target_name}.{column_alias}"
        transform_sql = body_node.sql(dialect=dialect)
        line = _find_alias_line(sql_text, column_alias) if source_file else None
        for col in body_node.find_all(exp.Column):
            parent = _format_parent(col, alias_map)
            edges.append(
                ProposedEdge(
                    child=child,
                    parent=parent,
                    transform=transform_sql,
                    source_file=source_file,
                    source_line=line,
                )
            )
    return edges


def detect_lineage_from_file(path: str | Path, dialect: str = "postgres") -> list[ProposedEdge]:
    """Read ``path`` and parse lineage edges from its contents.

    Convenience wrapper — the CLI uses this for each ``--from`` glob match.
    """
    p = Path(path)
    sql_text = p.read_text(encoding="utf-8")
    return detect_lineage_from_sql(sql_text, dialect=dialect, source_file=str(p))


# --------------------------------------------------------------------------- #
# Internals                                                                   #
# --------------------------------------------------------------------------- #


def _find_target(tree: Expr) -> tuple[str, Expr] | None:
    """Return ``(target_table_name, body_expression)`` if the root has a
    clear output, else ``None``.

    Handles ``CREATE TABLE/VIEW ... AS SELECT ...`` and ``INSERT INTO ...
    SELECT ...``. ``CREATE TABLE foo (col int)`` (DDL only, no AS SELECT
    body) returns ``None``.
    """
    cls = type(tree).__name__
    if cls not in _TARGETED_NODES:
        return None
    table = tree.this
    if table is None:
        return None
    # tree.this for Create is a Table or Schema (Schema wraps a Table when
    # there's a column list). For Insert it's always a Table.
    name = _table_name(table)
    if not name:
        return None
    body = tree.expression  # SELECT / Union / etc., None for plain DDL
    if body is None:
        return None
    return name, body


def _table_name(node: Expr) -> str:
    """Return the unqualified table name, ignoring any schema/db prefix.

    ``schema.foo`` → ``"foo"``. Lineage edges live in a flat
    ``feature_name`` namespace, so we drop schemas to maximize the chance
    that a downstream feature-by-name lookup finds a match.
    """
    try:
        from sqlglot import exp
    except ImportError:  # pragma: no cover - guarded at entry point
        return ""
    if isinstance(node, exp.Schema):
        node = node.this
    if isinstance(node, exp.Table):
        return node.name or ""
    # Fallback: last component of dotted SQL.
    raw = node.sql() if hasattr(node, "sql") else str(node)
    return raw.split(".")[-1].strip('"')


def _unwrap_select(node: Expr) -> Expr | None:
    """Pull a SELECT out of a body that might be wrapped in a Subquery /
    With / Union. Returns ``None`` if no SELECT is found.
    """
    try:
        from sqlglot import exp
    except ImportError:  # pragma: no cover - guarded at entry point
        return None
    if isinstance(node, exp.Select):
        return node
    # Common wrappers: With (CTE), Subquery, Union — pick the first SELECT.
    inner = node.find(exp.Select)
    return inner


def _build_alias_map(select: Expr) -> dict[str, str]:
    """Map FROM-table aliases to their real table names.

    ``FROM bar t JOIN sup s`` → ``{"t": "bar", "bar": "bar", "s": "sup",
    "sup": "sup"}``. Real names are mapped to themselves so a parent
    column with no alias (``bar.a``) round-trips cleanly.
    """
    try:
        from sqlglot import exp
    except ImportError:  # pragma: no cover - guarded at entry point
        return {}
    out: dict[str, str] = {}
    for tbl in select.find_all(exp.Table):
        # Avoid grabbing tables nested inside subqueries that shadow outer
        # scope — for simple cases this is fine; nested CTEs are rare in
        # the typical "feature definition" SQL we're parsing.
        name = tbl.name
        if not name:
            continue
        alias = tbl.alias or ""
        if alias:
            out[alias] = name
        out.setdefault(name, name)
    return out


def _extract_alias_and_body(proj: Expr) -> tuple[str | None, Expr]:
    """Return ``(alias_name, body_node)`` for a SELECT projection.

    ``a + b AS c`` → ``("c", <a+b>)``. Bare ``foo`` → ``("foo", <foo>)``.
    ``*`` and unaliased expressions return ``(None, proj)`` so the caller
    skips them.
    """
    try:
        from sqlglot import exp
    except ImportError:  # pragma: no cover - guarded at entry point
        return None, proj
    if isinstance(proj, exp.Alias):
        return proj.alias, proj.this
    if isinstance(proj, exp.Column):
        return proj.name, proj
    return None, proj


def _format_parent(col: Expr, alias_map: dict[str, str]) -> str:
    """Render a parent column reference as ``table.column`` (or just
    ``column`` if there's no table qualifier and the alias map is empty)."""
    name = getattr(col, "name", "") or ""
    raw_table = getattr(col, "table", "") or ""
    table = alias_map.get(raw_table, raw_table)
    if not table and len(alias_map) == 1:
        # Single-table query, column unqualified — attribute it to the
        # only table in scope.
        table = next(iter(alias_map.values()))
    return f"{table}.{name}" if table else name


def _find_alias_line(sql_text: str, alias: str) -> int | None:
    """Best-effort: 1-indexed line where ``alias`` first appears as a
    whole-word identifier. Used only for the ``--apply`` summary so users
    can jump to the right line in their editor; ``None`` is acceptable.
    """
    if not alias:
        return None
    import re

    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", re.IGNORECASE)
    for i, line in enumerate(sql_text.splitlines(), start=1):
        if pattern.search(line):
            return i
    return None
