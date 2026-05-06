"""Embedding generation for feature similarity search (T1.2).

Uses ``sentence-transformers/all-MiniLM-L6-v2`` (384-dim, CPU-friendly,
multilingual-light, good general-purpose retrieval). The model is loaded
lazily on first call so importing this module costs nothing if no embedding
is ever generated.

If ``sentence-transformers`` isn't installed (it's an optional ``[embeddings]``
extra — torch is heavy), every public function raises a clear ``RuntimeError``
naming the install command. Callers that want graceful degradation should
guard with ``embeddings_available()``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from ..db.embedding_type import Embedding
from ..db.models import EMBEDDING_DIM

# Bound-parameter spec for the embedding column. ``text()`` doesn't infer
# column types so the TypeDecorator's bind processor (which JSON-encodes on
# sqlite, passes through on postgres) wouldn't fire without this declaration.
_EMBED_PARAM = bindparam("vec", type_=Embedding(EMBEDDING_DIM))

if TYPE_CHECKING:
    from ..catalog.models import Feature

log = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Module-level cache for the loaded model; ``None`` until first use, or when
# sentence-transformers isn't installed.
_model: Any = None
_model_load_failed: bool = False


def embeddings_available() -> bool:
    """Return True if sentence-transformers is importable.

    Use this to gate features that need embeddings; if False, fall back to
    the existing TF-IDF similarity path. Doesn't trigger model download —
    only checks the import.
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model() -> Any:
    """Lazy-load the embedding model. First call may take 5–30s + ~100MB
    download. Subsequent calls return the cached instance."""
    global _model, _model_load_failed
    if _model is not None:
        return _model
    if _model_load_failed:
        raise RuntimeError("Embedding model previously failed to load — see prior log entries")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install with: "
            "uv pip install -e '.[embeddings]' (or 'pip install featcat[embeddings]')."
        ) from exc
    log.info("Loading embedding model: %s", MODEL_NAME)
    try:
        _model = SentenceTransformer(MODEL_NAME)
    except Exception as exc:
        _model_load_failed = True
        raise RuntimeError(f"Failed to load embedding model: {exc}") from exc
    return _model


def embed_text(text_: str) -> list[float]:
    """Embed a single string. Returns a 384-length list of floats."""
    return embed_batch([text_])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings. More efficient than calling embed_text in a loop."""
    if not texts:
        return []
    model = _get_model()
    arr = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return [list(row) for row in arr]


def feature_embed_text(feature: Feature, doc: dict | None = None) -> str:
    """Build the text representation of a feature used for embedding.

    Source: ``{name} {tags joined} {short_description} {long_description}``.
    Doc fields are pulled from the optional ``doc`` argument (caller supplies
    via ``db.get_feature_doc(feature.id)``); skipping the doc lookup when the
    caller already has it batched avoids N+1 queries during ``--all`` runs.
    """
    parts = [feature.name]
    if feature.tags:
        parts.append(" ".join(feature.tags))
    if doc:
        short = doc.get("short_description")
        if short:
            parts.append(str(short))
        long_ = doc.get("long_description")
        if long_:
            parts.append(str(long_))
    return " ".join(parts).strip()


def update_feature_embedding(db: Any, feature: Feature) -> None:
    """Compute and persist a single feature's embedding."""
    doc = db.get_feature_doc(feature.id)
    embed_text_ = feature_embed_text(feature, doc=doc)
    vec = embed_text(embed_text_)
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(f"Embedding dimension mismatch: model returned {len(vec)}, expected {EMBEDDING_DIM}")
    stmt = text("UPDATE features SET embedding = :vec, embedding_updated_at = :now WHERE id = :id").bindparams(
        _EMBED_PARAM
    )
    with db.session() as s:
        s.execute(stmt, {"vec": vec, "now": datetime.now(timezone.utc), "id": feature.id})
        s.commit()


def update_missing_embeddings(db: Any, batch_size: int = 32) -> dict[str, int]:
    """Embed every feature with NULL embedding OR stale (updated_at > embedding_updated_at).

    Returns ``{embedded, skipped, failed}`` counts.
    """
    # Build the candidate list. Use the SA session so postgres' NULL handling
    # plays nice with the embedding column's vector type.
    with db.session() as s:
        rows = (
            s.execute(
                text(
                    "SELECT id, name, data_source_id, column_name, dtype, description, "
                    "       tags, owner, stats, definition, definition_type, "
                    "       definition_updated_at, generation_hints, "
                    "       created_at, updated_at "
                    "FROM features "
                    "WHERE embedding IS NULL "
                    "   OR embedding_updated_at IS NULL "
                    "   OR updated_at > embedding_updated_at"
                )
            )
            .mappings()
            .all()
        )
    if not rows:
        return {"embedded": 0, "skipped": 0, "failed": 0}

    # Resolve features (use _row_to_feature for tag/stats JSON parsing).
    from ..catalog.local import _row_to_feature

    features = [_row_to_feature(r) for r in rows]

    # Batched encode for speed, then per-row UPDATE so a single failure
    # doesn't lose the whole batch.
    embedded = 0
    failed = 0
    docs_map = db.get_all_feature_docs()
    for i in range(0, len(features), batch_size):
        batch = features[i : i + batch_size]
        texts = [feature_embed_text(f, doc=docs_map.get(f.id)) for f in batch]
        try:
            vectors = embed_batch(texts)
        except Exception as exc:
            log.warning("Batch embed failed (%d features): %s", len(batch), exc)
            failed += len(batch)
            continue
        with db.session() as s:
            now = datetime.now(timezone.utc)
            stmt = text("UPDATE features SET embedding = :vec, embedding_updated_at = :now WHERE id = :id").bindparams(
                _EMBED_PARAM
            )
            for f, vec in zip(batch, vectors, strict=True):
                if len(vec) != EMBEDDING_DIM:
                    failed += 1
                    continue
                s.execute(stmt, {"vec": vec, "now": now, "id": f.id})
                embedded += 1
            s.commit()
    return {"embedded": embedded, "skipped": 0, "failed": failed}


__all__ = [
    "EMBEDDING_DIM",
    "MODEL_NAME",
    "embed_batch",
    "embed_text",
    "embeddings_available",
    "feature_embed_text",
    "update_feature_embedding",
    "update_missing_embeddings",
]
