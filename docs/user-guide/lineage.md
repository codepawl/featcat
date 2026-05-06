# Lineage

Lineage answers the question "if I change X, what breaks?" featcat tracks two kinds of relationships: feature-to-feature (`derived_from`) and source-to-source (`upstream_source`).

## When to use it

- **Before changing a feature's definition** — get the impact list to know who to notify.
- **During incident response** — "feature X looks broken; what feeds it, and what consumes it?"
- **For documentation** — show stakeholders the dependency tree of a model's inputs.
- **For deprecation** — find every feature that depends on the one you're about to retire.

## Recording lineage

Today, lineage is **manual** — you record relationships explicitly. T1.1b adds sqlglot-based auto-detection from SQL transformation files, but that's not landed yet.

CLI:

```bash
# "X is derived from A and B"
featcat lineage set user_behavior.session_count_30d \
    --derived-from user_events.session_id \
    --derived-from user_events.timestamp \
    --transform "count(distinct session_id) over 30-day window"
```

API:

```bash
curl -X POST http://localhost:8000/api/lineage \
    -H 'Content-Type: application/json' \
    -d '{
          "feature": "user_behavior.session_count_30d",
          "derived_from": ["user_events.session_id", "user_events.timestamp"],
          "transform": "count(distinct session_id) over 30-day window"
        }'
```

The relationship is stored on a `feature_lineage` table with `(child_feature, parent_feature, transform_description)` tuples. Multi-parent is supported (most aggregations have several inputs).

## Querying impact

`GET /api/lineage/impact?feature=user_events.session_id` returns the transitive *downstream* set:

```json
{
  "feature": "user_events.session_id",
  "downstream": [
    "user_behavior.session_count_30d",
    "user_behavior.session_count_7d",
    "churn_features.is_active_user"
  ],
  "depth": 2,
  "graph": [
    {"from": "user_events.session_id", "to": "user_behavior.session_count_30d", "transform": "..."},
    ...
  ]
}
```

CLI:

```bash
featcat lineage impact user_events.session_id
# 3 downstream features depend on user_events.session_id (depth 2)
#   ├── user_behavior.session_count_30d
#   ├── user_behavior.session_count_7d
#   └── churn_features.is_active_user (via user_behavior.session_count_30d)
```

## Querying ancestors

The opposite direction — given a feature, what does it depend on?

```bash
featcat lineage ancestors user_behavior.session_count_30d
# user_behavior.session_count_30d depends on:
#   ├── user_events.session_id
#   └── user_events.timestamp
```

API: `GET /api/lineage/ancestors?feature=user_behavior.session_count_30d`

## Visualizing the graph

The web UI's **Lineage** tab on the feature detail panel shows a small ego-graph: the feature in the middle, parents above, children below. Click a node to navigate. Edge labels show the transform description.

A bigger graph view is on the roadmap (T1.1c) — D3-based, full-catalog flowchart, filterable by source / project. Until then, the API + your favorite graph viz tool work fine:

```python
import httpx, networkx as nx
graph = httpx.get("http://localhost:8000/api/lineage/full").json()
G = nx.DiGraph()
for edge in graph["edges"]:
    G.add_edge(edge["from"], edge["to"], label=edge["transform"])
```

## Auto-detection (preview)

T1.1b will scan SQL transformation files and propose lineage automatically using `sqlglot`. Sketch:

```bash
featcat lineage detect --from sql/transforms/*.sql
# Proposed 47 lineage edges:
#   user_behavior.session_count_30d ← user_events.session_id (sql/transforms/sessions.sql:12)
#   ...
# Apply with --confirm.
```

For now, recording lineage by hand at definition time is the only path. Conventional pattern: pair every `featcat docs generate` with a `featcat lineage set` call in the same script that built the feature.

## Limitations

- **No event-time lineage.** featcat tracks logical dependency, not run-time provenance ("which Spark job populated this row?"). For that, integrate with your data platform's metadata store and import into featcat.
- **No column-level lineage within a single source.** If `user_events` has 50 columns and `user_behavior.session_count_30d` derives from 3 of them, you record those 3 explicitly.
- **No SQL parsing today.** Coming with T1.1b.

## Related

- **[Catalog browser](catalog.md)** — features list shows lineage in the detail panel
- **[Bulk operations](bulk.md)** — for setting lineage on many features at once (use the bulk tag endpoint with structured JSON)
- **[Architecture › Data Layer](../architecture/data.md)** *(coming soon)* — `feature_lineage` schema
