"""Cross-dialect embedding column type.

PostgreSQL gets a real ``vector(N)`` column via pgvector — supports HNSW
indexes and the ``<=>`` cosine-distance operator. SQLite has no native vector
type, so we fall back to a JSON-encoded ``TEXT`` column. Similarity *queries*
are postgres-only (the existing TF-IDF path covers sqlite); the column itself
exists on both so embedding generation works in either mode.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text, TypeDecorator


class Embedding(TypeDecorator[list]):
    """``vector(N)`` on postgres, JSON-encoded ``TEXT`` on sqlite.

    Constructor takes the embedding dimension (matched against the model in
    ``featcat/ai/embeddings.py``). The dimension is used for postgres DDL and
    is otherwise informational on sqlite.
    """

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 384) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            # Imported lazily so sqlite-only test runs don't pay the import cost.
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: list[float] | None, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector.sqlalchemy.Vector handles list serialization itself.
            return value
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector returns a numpy array — cast to plain list for parity.
            return list(value)
        if isinstance(value, str):
            return json.loads(value)
        return list(value)
