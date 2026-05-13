# Data layer

featcat persists everything to a single relational store. PostgreSQL is the production target; SQLite is the dev/test fallback. The same SQLAlchemy models run on both; dialect-specific features (pgvector, tsvector) have sqlite fallbacks in code.

## Schema

The catalog has 12 main tables, all defined in `featcat/db/models.py` as SQLAlchemy 2.x `Mapped[]` ORM classes:

| Table | Purpose |
|---|---|
| `data_sources` | Registered Parquet/SQL/etc. sources |
| `features` | One row per column, with stats + status + tags |
| `feature_docs` | Auto-generated short/long descriptions, hints |
| `feature_lineage` | `(child_feature, parent_feature, transform)` edges |
| `feature_groups` | Named bundles |
| `feature_group_members` | Many-to-many between groups and features |
| `monitoring_baselines` | Frozen stats snapshot per feature |
| `monitoring_checks` | One row per drift check run |
| `notifications` | In-app alert queue |
| `job_schedules` | APScheduler cron entries |
| `job_logs` | Scheduler run history |
| `usage_log` | Analytics: who viewed/queried what |

`features.name` includes the source prefix (e.g. `user_behavior.session_count_30d`) and is unique. Dots in names are why feature-by-name routes use query params (`?name=...`) instead of path params — see [Architecture Overview › Where to look](overview.md#where-to-look-in-the-code).

## Migrations

Alembic with `script_location = featcat/db/migrations`. Every schema change ships as a versioned migration:

```
featcat/db/migrations/versions/
├── 001_initial.py
├── 005_add_certification.py
├── 25c2acba0f39_merge_t1_1_t1_4a.py    # alembic merge of two heads
└── 842a42f73f0f_merge_t2_1_t2_2a.py    # alembic merge
```

Two heads are merged with `alembic merge` whenever stacked PRs each add a head. Convention: PR title prefix the migration filename so blame is obvious.

Cross-dialect migration pattern:

```python
from alembic import op

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE features ADD COLUMN embedding vector(384)")
        op.execute(
            "CREATE INDEX features_embedding_hnsw "
            "ON features USING hnsw (embedding vector_cosine_ops)"
        )
    # SQLite: nothing — Embedding TypeDecorator JSON-encodes into TEXT
```

`op.batch_alter_table(...)` is required for any `ALTER COLUMN` on SQLite (rebuilds the table behind the scenes). Use it for type changes and constraint adds even if PostgreSQL alone would tolerate the simpler form.

## Indexes

| Index | On | Used by |
|---|---|---|
| B-tree | `(source_id, name)` | Catalog list pagination |
| B-tree | `features.status` | Status filter / certification dashboard |
| B-tree | `features.owner` | Owner filter / notification routing |
| GIN | `features.search_tsv` (postgres only) | Full-text search |
| HNSW | `features.embedding` (postgres only) | pgvector similarity |
| B-tree | `monitoring_checks.checked_at` | Recent-checks dashboard tile |

The HNSW index uses `vector_cosine_ops` — distance is `<=>` (cosine) at query time. Tuning: default `m=16, ef_construction=64`. Bump `ef_search` per query for higher recall.

## Embeddings

`features.embedding` is `vector(384)` on PostgreSQL, JSON-encoded text on SQLite. The `Embedding` TypeDecorator in `featcat/db/types.py` handles encoding/decoding transparently — code calling `feature.embedding` gets a `list[float]` either way.

When updating embeddings via raw SQL (`text(...)`), declare the bindparam type explicitly so the TypeDecorator's bind processor fires:

```python
from sqlalchemy import bindparam, text
from featcat.db.types import Embedding, EMBEDDING_DIM

stmt = text("UPDATE features SET embedding = :vec WHERE name = :name").bindparams(
    bindparam("vec", type_=Embedding(EMBEDDING_DIM)),
    bindparam("name"),
)
session.execute(stmt, {"vec": [0.1, 0.2, ...], "name": "..."})
```

Without `type_=`, SQLite sees a Python list and crashes; PostgreSQL would also fail because it needs the pgvector text format.

## Full-text search

PostgreSQL: `features.search_tsv` is a `GENERATED ALWAYS AS (...) STORED` `tsvector` over `name || ' ' || coalesce(description, '') || ' ' || coalesce(tags, '')`. Indexed with GIN. Query at runtime:

```sql
SELECT name, ts_rank_cd(search_tsv, q) AS rank
FROM features, plainto_tsquery('english', :term) q
WHERE search_tsv @@ q
ORDER BY rank DESC
LIMIT 50;
```

SQLite: token-scan over the same fields, `LIKE %term%` ANDed across whitespace-split tokens. Slower but functional. Search ranking on SQLite is by row count of token hits, not TF-IDF.

## Connection management

- **PostgreSQL**: `psycopg` (3.x) with `pool_size=10, max_overflow=20`. Each FastAPI worker gets its own pool.
- **SQLite**: single-file with `check_same_thread=False`. WAL mode enabled for concurrent reads while a write is in progress.
- **Multi-worker**: 4 uvicorn workers. Each hits the same DB; SQL-level locking is the contention story.

## Backup story

- **PostgreSQL**: `pg_dump --format=custom` → restore with `pg_restore`. See [Ops › Backup](../ops/backup.md).
- **SQLite**: file copy (or `sqlite3 .backup`) is sufficient. WAL means a stale `.db` snapshot may need the `.db-wal` and `.db-shm` siblings too.

## Choosing a backend

Default to SQLite for development and tests. Switch to PostgreSQL for any deployment that needs:

- Concurrent writers (more than one CLI/server pointing at the catalog)
- pgvector similarity (10× faster than TF-IDF over the same corpus)
- tsvector ranked search
- Stored procedures / advanced SQL

The CatalogBackend abstraction makes the swap painless — set `FEATCAT_DB_URL=postgresql+psycopg://...` and re-run `alembic upgrade head`.

## Related

- **[Architecture Overview](overview.md)** — bird's-eye context
- **[Architecture › AI Layer](ai.md)** — embedding pipeline that populates `features.embedding`
- **[Ops › Deployment](../ops/deployment.md)** — choosing PostgreSQL vs SQLite in prod
- **[Ops › Backup](../ops/backup.md)** — backup strategies per dialect
