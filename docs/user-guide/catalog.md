# Catalog browser

The catalog is the heart of featcat: a paginated, filterable list of every feature your team has registered, with one click to see the docs, monitoring history, and lineage of any of them.

## When to use it

- **"Has anyone built X yet?"** — search across names, descriptions, and tags before you build a duplicate.
- **"What's drifting right now?"** — filter by drift status to triage before standups.
- **"What does this team own?"** — filter by owner / tag / source.
- **"Which features still need docs?"** — `has_doc=false` filter to find the gaps.

## Browsing

Open the web UI at `http://localhost:8000` and click **Features**. The list paginates 50 at a time. Above the list, a row of filter chips lets you scope by:

| Filter | Notes |
|---|---|
| **Source** | The Parquet/SQL/etc. source the feature came from |
| **Tag** | Free-form labels you set per feature |
| **Owner** | Person or team the feature belongs to |
| **Dtype** | `int64`, `float64`, `string`, `bool`, etc. |
| **Has doc** | `true` / `false` — find documentation gaps |
| **Status** | `draft` / `reviewed` / `certified` / `deprecated` (see [Certification](#certification)) |
| **Drift** | `none` / `warning` / `critical` based on latest PSI check |

Multiple filters combine with AND. The URL updates so you can bookmark or share a filtered view.

## Searching

The search bar at the top of the page hits the [full-text search endpoint](../sdk/quickstart.md#method-tour), which on PostgreSQL uses a `tsvector` GIN index over name + description + tags. On SQLite it falls back to a token-scan.

```
> "user activity 30 days"
→ user_behavior.session_count_30d         (rank 0.42)
→ user_behavior.event_count_30d           (rank 0.38)
→ device_performance.active_minutes_30d   (rank 0.21)
```

Hits are ranked. The same endpoint powers the AI chat's tool-call retrieval, so what you see in the catalog is what the agent sees.

## CLI equivalents

Every catalog operation is available from the CLI. Useful for piping into other tools:

```bash
# List with filters (same params as the web UI)
featcat features list --source user_behavior --has-doc --tag churn

# Get one feature as JSON
featcat features show user_behavior.session_count_30d --json

# Search
featcat features search "user activity 30 days" --limit 10
```

The CLI uses the same backend abstraction as the web UI ([CatalogBackend](../architecture/overview.md#backend-abstraction)), so behavior matches whether you're pointed at SQLite locally or PostgreSQL in production.

## SDK equivalents

For notebook / pipeline use, the [Python SDK](../sdk/quickstart.md) returns Pydantic models:

```python
from featcat_client import FeatCatClient
client = FeatCatClient("http://localhost:8000")
features = client.list_features(source="user_behavior", has_doc=True)
```

## Feature detail panel

Click a row to open the detail panel. Sections:

1. **Header** — name, source, dtype, owner, status badge.
2. **Description** — auto-generated short + long descriptions, plus expected ranges and gotchas. See [Documentation](docs.md).
3. **Stats** — null ratio, mean / std / min / max for numeric, top-K for categorical.
4. **Lineage** — upstream sources and downstream consumers when known. See [Lineage](lineage.md).
5. **Monitoring** — current drift status + PSI history chart. See [Monitoring](monitoring.md).
6. **Versions** — log of every documentation regeneration with timestamp + actor.
7. **Group memberships** — which [groups](groups.md) this feature belongs to.

## Certification

Features have a four-stage status: `draft → reviewed → certified → deprecated`. Promote with:

```bash
featcat status set user_behavior.session_count_30d certified --notes "Q4 sign-off"
```

The certification readiness check (`featcat status check`) flags missing prerequisites: doc, baseline, owner, group membership. Status changes log to `feature_status_history` for an audit trail.

In the web UI, certified features get a green badge in the list and detail panel. You can filter by status and there's a Dashboard tile counting the production-ready set.

## Performance

The catalog page handles 10k+ features without lag. Implementation details:

- **Server-side pagination** — `?limit=50&offset=N`, default sort by name. Always returns an envelope `{items, total, limit, offset}`.
- **Server-side filtering** — every filter is a SQL `WHERE` clause, never client-side post-filter. With pgvector + tsvector + B-tree indexes on `(source_id, name)`, `(status)`, and `(owner)`, queries return in single-digit ms even at 100k features.
- **Virtualization** — `@tanstack/react-virtual` renders only visible rows. Memory stays flat as you scroll.

## Common questions

- **"Why does my feature show 'no description'?"** — The autodoc batch hasn't run yet, or it was skipped. Run `featcat docs generate --feature <name>` to fix.
- **"Why is the dtype `unknown`?"** — The scanner couldn't open the parquet (path moved, permissions). Fix the path on the source and re-scan.
- **"Search returns nothing for an obvious match."** — On PostgreSQL the `tsvector` column is a stored generated column. Run `alembic upgrade head` if you upgraded — older schemas won't have it.

## Related

- **[First Feature](../getting-started/first-feature.md)** — register a source and scan it
- **[Documentation](docs.md)** — generate auto-docs
- **[Monitoring](monitoring.md)** — drift detection
- **[Bulk operations](bulk.md)** — apply tags / groups across many features
- **[SDK Quickstart](../sdk/quickstart.md)** — programmatic access
