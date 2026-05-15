# Catalog Schema Reference

Authoritative reference for every table in the featcat catalog database. Derived
from the live Alembic migration tree — not from design docs.

## Source of truth

- Audit SHA: `84041cd7264d705c82f5a150618d2e4b37e2c547`
- Migration directory: `featcat/db/migrations/versions/`
- Migrations applied in order:
  1. `affaec86825b_initial_schema.py` — initial schema (T0)
  2. `b4de1aac246b_t1_1_lineage_source_column_parents.py` — lineage source-column parents
  3. `d6e943d39311_t1_2_features_embedding_column.py` — `features.embedding` (pgvector)
  4. `f871e02d23fb_t1_4a_indexes_features_dtype_features_.py` — extra indexes on `features`
  5. `25c2acba0f39_merge_t1_1_lineage_and_t1_4a_indexes_.py` — merge (no schema change)
  6. `fc06fb939993_t2_1_in_app_notifications_table.py` — `notifications` table
  7. `489ac96fd407_t2_2_features_search_vector_tsvector_.py` — `features.search_vector` (Postgres-only)
  8. `842a42f73f0f_merge_t2_1_notifications_and_t2_2a_fts_.py` — merge (no schema change)
  9. `48172b100cdf_t3_1_features_status_columns.py` — `features.status` lifecycle columns
- Engine resolution: `featcat/db/connection.py` selects SQLite or PostgreSQL via
  the `FEATCAT_DB_BACKEND` env var. The schema below is the union; columns
  flagged **Postgres-only** are skipped on SQLite by their migration.

No table created in the initial schema has been dropped. All 13 tables in
this document exist in the final schema.

---

## Sources & features (core catalog)

### `data_sources`

External data sources scanned for feature columns.

| Column          | Type                       | Nullable | Default     | Notes |
|-----------------|----------------------------|----------|-------------|-------|
| `id`            | TEXT                       | NOT NULL | —           | PK |
| `name`          | TEXT                       | NOT NULL | —           | UNIQUE |
| `path`          | TEXT                       | NOT NULL | —           | filesystem path or S3 URI |
| `storage_type`  | TEXT                       | NOT NULL | `'local'`   | `local` \| `s3` |
| `format`        | TEXT                       | NOT NULL | `'parquet'` | |
| `description`   | TEXT                       | NOT NULL | `''`        | |
| `created_at`    | TIMESTAMP WITH TIME ZONE   | NOT NULL | —           | |
| `updated_at`    | TIMESTAMP WITH TIME ZONE   | NOT NULL | —           | |
| `auto_refresh`  | INTEGER                    | NOT NULL | `0`         | boolean-as-int (SQLite) |

- Primary key: `id`
- Unique: `name`
- No additional indexes
- No outgoing FKs

### `features`

The catalog's central table — one row per registered feature.

| Column                  | Type                        | Nullable | Default    | Notes |
|-------------------------|-----------------------------|----------|------------|-------|
| `id`                    | TEXT                        | NOT NULL | —          | PK |
| `name`                  | TEXT                        | NOT NULL | —          | dotted: `<source>.<column>` |
| `data_source_id`        | TEXT                        | NOT NULL | —          | FK → `data_sources.id` |
| `column_name`           | TEXT                        | NOT NULL | —          | |
| `dtype`                 | TEXT                        | NOT NULL | `''`       | pandas dtype string |
| `description`           | TEXT                        | NOT NULL | `''`       | |
| `tags`                  | TEXT                        | NOT NULL | `'[]'`     | JSON-encoded list |
| `owner`                 | TEXT                        | NOT NULL | `''`       | |
| `stats`                 | TEXT                        | NOT NULL | `'{}'`     | JSON-encoded stats blob |
| `created_at`            | TIMESTAMP WITH TIME ZONE    | NOT NULL | —          | |
| `updated_at`            | TIMESTAMP WITH TIME ZONE    | NOT NULL | —          | |
| `definition`            | TEXT                        | NULL     | —          | SQL / Python source |
| `definition_type`       | TEXT                        | NULL     | —          | `sql` \| `python` \| `manual` |
| `definition_updated_at` | TIMESTAMP WITH TIME ZONE    | NULL     | —          | |
| `generation_hints`      | TEXT                        | NULL     | —          | JSON hint dict for autodoc |
| `embedding`             | `vector(384)` / TEXT(JSON)  | NULL     | —          | pgvector on Postgres, JSON-as-TEXT on SQLite (migration `d6e943d39311`) |
| `embedding_updated_at`  | TIMESTAMP WITH TIME ZONE    | NULL     | —          | (migration `d6e943d39311`) |
| `search_vector`         | `tsvector`                  | NULL     | computed   | **Postgres-only** stored generated column (migration `489ac96fd407`) |
| `status`                | TEXT                        | NOT NULL | `'draft'`  | lifecycle: `draft`/`reviewed`/`certified`/`deprecated` (migration `48172b100cdf`) |
| `status_changed_at`     | TIMESTAMP WITH TIME ZONE    | NULL     | —          | (migration `48172b100cdf`) |
| `status_notes`          | TEXT                        | NULL     | —          | (migration `48172b100cdf`) |

- Primary key: `id`
- Unique: `uq_features_source_column` over `(data_source_id, column_name)`
- Foreign keys: `data_source_id` → `data_sources.id`
- Indexes:
  - `idx_features_created_at` (`created_at`)
  - `idx_features_name` (`name`)
  - `idx_features_source` (`data_source_id`)
  - `idx_features_dtype` (`dtype`) — added in `f871e02d23fb`
  - `idx_features_updated_at` (`updated_at`) — added in `f871e02d23fb`
  - `idx_features_status` (`status`) — added in `48172b100cdf`
  - `idx_features_embedding` HNSW over `embedding vector_cosine_ops` — **Postgres-only**, added in `d6e943d39311`
  - `idx_features_search_vector` GIN over `search_vector` — **Postgres-only**, added in `489ac96fd407`

`search_vector` is computed as
`setweight(to_tsvector('simple', name), 'A') || setweight(to_tsvector('simple', tags), 'B') || setweight(to_tsvector('simple', description), 'C')`,
stored, with the `simple` config to support mixed English + Vietnamese
(`featcat/db/migrations/versions/489ac96fd407_t2_2_features_search_vector_tsvector_.py:37-45`).

### `feature_docs`

AI-generated documentation for a feature (1:1).

| Column               | Type                       | Nullable | Default | Notes |
|----------------------|----------------------------|----------|---------|-------|
| `feature_id`         | TEXT                       | NOT NULL | —       | PK; FK → `features.id` |
| `short_description`  | TEXT                       | NOT NULL | `''`    | |
| `long_description`   | TEXT                       | NOT NULL | `''`    | |
| `expected_range`     | TEXT                       | NOT NULL | `''`    | |
| `potential_issues`   | TEXT                       | NOT NULL | `''`    | |
| `generated_at`       | TIMESTAMP WITH TIME ZONE   | NULL     | —       | |
| `model_used`         | TEXT                       | NOT NULL | `''`    | |
| `hints_used`         | TEXT                       | NULL     | —       | JSON snapshot of hints applied |
| `context_features`   | TEXT                       | NULL     | —       | JSON list of sibling features used as context |

- Primary key: `feature_id`
- Foreign keys: `feature_id` → `features.id` (no cascade)

### `feature_versions`

Version history snapshots for a feature.

| Column            | Type                       | Nullable | Default      | Notes |
|-------------------|----------------------------|----------|--------------|-------|
| `id`              | TEXT                       | NOT NULL | —            | PK |
| `feature_id`      | TEXT                       | NOT NULL | —            | FK → `features.id` (CASCADE) |
| `version`         | INTEGER                    | NOT NULL | —            | monotonic per feature |
| `snapshot`        | TEXT                       | NOT NULL | —            | JSON snapshot of metadata |
| `change_summary`  | TEXT                       | NOT NULL | `''`         | |
| `changed_by`      | TEXT                       | NOT NULL | `''`         | |
| `created_at`      | TIMESTAMP WITH TIME ZONE   | NOT NULL | —            | |
| `change_type`     | TEXT                       | NOT NULL | `'metadata'` | |
| `previous_value`  | TEXT                       | NULL     | —            | |
| `new_value`       | TEXT                       | NULL     | —            | |

- Primary key: `id`
- Unique: `(feature_id, version)`
- Foreign keys: `feature_id` → `features.id` ON DELETE CASCADE

---

## Groups

### `feature_groups`

Logical collections of features.

| Column         | Type                       | Nullable | Default | Notes |
|----------------|----------------------------|----------|---------|-------|
| `id`           | TEXT                       | NOT NULL | —       | PK |
| `name`         | TEXT                       | NOT NULL | —       | UNIQUE |
| `description`  | TEXT                       | NOT NULL | `''`    | |
| `project`      | TEXT                       | NOT NULL | `''`    | |
| `owner`        | TEXT                       | NOT NULL | `''`    | |
| `created_at`   | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |
| `updated_at`   | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |

- Primary key: `id`
- Unique: `name`

### `feature_group_members`

Many-to-many between groups and features.

| Column         | Type                       | Nullable | Default | Notes |
|----------------|----------------------------|----------|---------|-------|
| `group_id`     | TEXT                       | NOT NULL | —       | composite PK; FK → `feature_groups.id` CASCADE |
| `feature_id`   | TEXT                       | NOT NULL | —       | composite PK; FK → `features.id` CASCADE |
| `added_at`     | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |

- Primary key: `(group_id, feature_id)`
- Index: `idx_group_members_group_feature` (`group_id, feature_id`)
- Foreign keys: `group_id` → `feature_groups.id` CASCADE; `feature_id` → `features.id` CASCADE

---

## Lineage

### `feature_lineage`

Parent/child edges between features, and source-column → feature edges.

| Column                | Type                       | Nullable | Default     | Notes |
|-----------------------|----------------------------|----------|-------------|-------|
| `id`                  | TEXT                       | NOT NULL | —           | PK |
| `child_feature_id`    | TEXT                       | NOT NULL | —           | FK → `features.id` CASCADE |
| `parent_feature_id`   | TEXT                       | NULL     | —           | FK → `features.id` CASCADE (made nullable in `b4de1aac246b`) |
| `parent_type`         | TEXT                       | NOT NULL | `'feature'` | `feature` \| `source_column` (added in `b4de1aac246b`) |
| `parent_source_id`    | TEXT                       | NULL     | —           | FK → `data_sources.id` SET NULL (added in `b4de1aac246b`) |
| `parent_column`       | TEXT                       | NULL     | —           | (added in `b4de1aac246b`) |
| `transform`           | TEXT                       | NOT NULL | `''`        | free-form transform description |
| `detected_method`     | TEXT                       | NOT NULL | `'manual'`  | `manual` \| `sql_parse` \| `imported` \| `demo` (added in `b4de1aac246b`) |
| `created_at`          | TIMESTAMP WITH TIME ZONE   | NOT NULL | —           | |

- Primary key: `id`
- Unique: `(child_feature_id, parent_type, parent_feature_id, parent_source_id, parent_column)` — expanded from the original `(child_feature_id, parent_feature_id)` in `b4de1aac246b` to allow source-column parents
- Indexes:
  - `idx_lineage_child` (`child_feature_id`)
  - `idx_lineage_parent` (`parent_feature_id`)
  - `idx_lineage_parent_source` (`parent_source_id`) — added in `b4de1aac246b`
- Foreign keys: `child_feature_id` → `features.id` CASCADE; `parent_feature_id` → `features.id` CASCADE; `parent_source_id` → `data_sources.id` SET NULL

---

## Monitoring & quality

### `monitoring_baselines`

One baseline-stats blob per monitored feature.

| Column           | Type                       | Nullable | Default | Notes |
|------------------|----------------------------|----------|---------|-------|
| `feature_id`     | TEXT                       | NOT NULL | —       | PK; FK → `features.id` |
| `baseline_stats` | TEXT                       | NOT NULL | `'{}'`  | JSON |
| `computed_at`    | TIMESTAMP WITH TIME ZONE   | NULL     | —       | |

- Primary key: `feature_id`
- Foreign keys: `feature_id` → `features.id`

### `monitoring_checks`

History of quality / drift checks.

| Column              | Type                       | Nullable | Default | Notes |
|---------------------|----------------------------|----------|---------|-------|
| `id`                | TEXT                       | NOT NULL | —       | PK |
| `feature_id`        | TEXT                       | NOT NULL | —       | FK → `features.id` |
| `feature_name`      | TEXT                       | NOT NULL | —       | denormalized for fast filtering |
| `psi`               | FLOAT                      | NULL     | —       | population stability index |
| `severity`          | TEXT                       | NOT NULL | —       | `ok` \| `warning` \| `critical` |
| `checked_at`        | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |
| `llm_analysis_json` | TEXT                       | NULL     | —       | optional LLM commentary |

- Primary key: `id`
- Indexes:
  - `idx_monitoring_checks_date` (`checked_at`)
  - `idx_monitoring_checks_feature` (`feature_name`)
- Foreign keys: `feature_id` → `features.id`

---

## Action items, usage, notifications

### `action_items`

Recommendations surfaced for a feature (autodoc fixes, drift remediation, etc.).

| Column            | Type                       | Nullable | Default     | Notes |
|-------------------|----------------------------|----------|-------------|-------|
| `id`              | TEXT                       | NOT NULL | —           | PK |
| `feature_id`      | TEXT                       | NOT NULL | —           | FK → `features.id` CASCADE |
| `source`          | TEXT                       | NOT NULL | —           | producer (`autodoc`, `drift`, `chat`, …) |
| `title`           | TEXT                       | NOT NULL | —           | |
| `recommendation`  | TEXT                       | NOT NULL | —           | |
| `status`          | TEXT                       | NOT NULL | `'pending'` | `pending` \| `applied` \| `dismissed` \| `snoozed` |
| `created_by`      | TEXT                       | NOT NULL | `''`        | |
| `applied_by`      | TEXT                       | NOT NULL | `''`        | |
| `applied_at`      | TIMESTAMP WITH TIME ZONE   | NULL     | —           | |
| `change_summary`  | TEXT                       | NOT NULL | `''`        | |
| `context_json`    | TEXT                       | NOT NULL | `'{}'`      | JSON context blob |
| `created_at`      | TIMESTAMP WITH TIME ZONE   | NOT NULL | —           | |
| `updated_at`      | TIMESTAMP WITH TIME ZONE   | NOT NULL | —           | |

- Primary key: `id`
- Indexes:
  - `idx_action_items_feature` (`feature_id, status`)
  - `idx_action_items_status` (`status, created_at`)
- Foreign keys: `feature_id` → `features.id` ON DELETE CASCADE

### `usage_log`

Audit trail of feature accesses.

| Column        | Type                       | Nullable | Default | Notes |
|---------------|----------------------------|----------|---------|-------|
| `id`          | TEXT                       | NOT NULL | —       | PK |
| `feature_id`  | TEXT                       | NOT NULL | —       | FK → `features.id` |
| `action`      | TEXT                       | NOT NULL | —       | `view`, `query`, `export`, … |
| `user`        | TEXT                       | NOT NULL | `''`    | |
| `context`     | TEXT                       | NOT NULL | `''`    | |
| `created_at`  | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |

- Primary key: `id`
- Indexes:
  - `idx_usage_log_created` (`created_at`)
  - `idx_usage_log_feature` (`feature_id`)
- Foreign keys: `feature_id` → `features.id`

### `notifications`

In-app notification feed (added in migration `fc06fb939993`).

| Column        | Type                       | Nullable | Default  | Notes |
|---------------|----------------------------|----------|----------|-------|
| `id`          | TEXT                       | NOT NULL | —        | PK |
| `kind`        | TEXT                       | NOT NULL | —        | event family |
| `title`       | TEXT                       | NOT NULL | —        | |
| `body`        | TEXT                       | NOT NULL | `''`     | |
| `severity`    | TEXT                       | NOT NULL | `'info'` | `info` \| `warning` \| `critical` |
| `feature_id`  | TEXT                       | NULL     | —        | FK → `features.id` SET NULL |
| `link`        | TEXT                       | NULL     | —        | deep link target |
| `created_at`  | TIMESTAMP WITH TIME ZONE   | NOT NULL | —        | |
| `read_at`     | TIMESTAMP WITH TIME ZONE   | NULL     | —        | unread iff NULL |

- Primary key: `id`
- Indexes:
  - `idx_notifications_feature` (`feature_id`)
  - `idx_notifications_unread` (`read_at, created_at`)
- Foreign keys: `feature_id` → `features.id` ON DELETE SET NULL

---

## Scheduling

### `job_schedules`

Cron-style schedule definitions for background jobs.

| Column                    | Type                       | Nullable | Default | Notes |
|---------------------------|----------------------------|----------|---------|-------|
| `job_name`                | TEXT                       | NOT NULL | —       | PK |
| `cron_expression`         | TEXT                       | NOT NULL | —       | |
| `enabled`                 | INTEGER                    | NOT NULL | `1`     | boolean-as-int |
| `last_run_at`             | TIMESTAMP WITH TIME ZONE   | NULL     | —       | |
| `next_run_at`             | TIMESTAMP WITH TIME ZONE   | NULL     | —       | |
| `description`             | TEXT                       | NOT NULL | `''`    | |
| `max_log_retention_days`  | INTEGER                    | NOT NULL | `30`    | |

- Primary key: `job_name`

### `job_logs`

Per-execution audit trail.

| Column              | Type                       | Nullable | Default | Notes |
|---------------------|----------------------------|----------|---------|-------|
| `id`                | TEXT                       | NOT NULL | —       | PK |
| `job_name`          | TEXT                       | NOT NULL | —       | |
| `status`            | TEXT                       | NOT NULL | —       | `success` \| `error` \| `running` |
| `started_at`        | TIMESTAMP WITH TIME ZONE   | NOT NULL | —       | |
| `finished_at`       | TIMESTAMP WITH TIME ZONE   | NULL     | —       | |
| `duration_seconds`  | FLOAT                      | NULL     | —       | |
| `result_summary`    | TEXT                       | NOT NULL | `'{}'`  | JSON |
| `error_message`     | TEXT                       | NULL     | —       | |
| `triggered_by`      | TEXT                       | NOT NULL | —       | `schedule` \| `manual` \| user id |

- Primary key: `id`
- No additional indexes
- Not foreign-keyed to `job_schedules` — logs survive schedule deletion

---

## Postgres-specific notes

- `features.embedding` uses the `pgvector` `vector(384)` type with an HNSW
  index over `vector_cosine_ops`. On SQLite the same column stores a
  JSON-encoded float array as `TEXT` and there is no index — the runtime
  falls back to TF-IDF in `LocalBackend`.
- `features.search_vector` is a `STORED GENERATED` `tsvector` with a GIN
  index. The migration is a no-op on SQLite; full-text search falls back to
  the FTS5 virtual table created in `LocalBackend.init_db` (see
  `featcat/catalog/local.py`).

## Tables seen in older migrations but not in the final schema

None. All tables introduced in the initial schema persist through the
current head revision.
