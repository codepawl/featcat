# Feature groups

A *group* is a named bundle of features that belong together — typically the inputs to a single model, the outputs of a single pipeline, or a feature set being reviewed as a unit.

## When to use them

- **Model inputs**: bundle the 30+ features that feed `churn_v2` so a notebook can pull them all in one frame.
- **Cross-team handoff**: data team certifies a group; ML team consumes it as a stable contract.
- **Sprint scope**: assemble candidate features for an experiment, then promote the winners and deprecate the rest in one move.
- **Health snapshots**: get a single drift/doc-coverage view across a logical bundle, not one feature at a time.

## Creating a group

=== "Web UI"

    1. Open `http://localhost:8000` → **Groups**
    2. Click **+ New group**
    3. Pick a name (slug — `churn_v2`, not `Churn v2`), description, optional project tag
    4. **Add features** — opens the [shared FeatureSelector](../architecture/overview.md#where-to-look-in-the-code) with search, source-filter, shift-click range, and AI suggest

=== "CLI"

    ```bash
    featcat groups create churn_v2 \
        --description "Inputs for the v2 churn model" \
        --project ml-platform

    featcat groups add-members churn_v2 \
        user_behavior.session_count_30d \
        user_behavior.event_count_30d \
        device_performance.crash_count_7d
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/groups \
        -H 'Content-Type: application/json' \
        -d '{"name": "churn_v2", "description": "...", "project": "ml-platform"}'

    curl -X POST http://localhost:8000/api/groups/churn_v2/members \
        -H 'Content-Type: application/json' \
        -d '{"feature_names": ["user_behavior.session_count_30d", ...]}'
    ```

Group names are unique per project. Member features can belong to many groups (it's many-to-many).

## Pulling a group as a DataFrame

The most useful thing about a group from a notebook: one method gives you every member parquet, joined on the entity key.

```python
from featcat_client import FeatCatClient

client = FeatCatClient("http://localhost:8000")
detail = client.get_group("churn_v2")
df = detail.to_polars(entity_key="user_id")
df.head()
```

The SDK reads each member's parquet once (cached), then runs a polars left-join on `entity_key`. If you don't pass `entity_key`, the SDK auto-detects: it intersects the non-feature columns across all member parquets and prefers `user_id`, `session_id`, `id`, `entity_id`, `device_id`. If the candidate set is ambiguous, it raises with the choices so you can pick.

`detail.to_pandas(...)` returns the same thing as a pandas DataFrame, when you've installed the `[pandas]` extra.

## Group health

Each group exposes an aggregated health view:

```bash
curl http://localhost:8000/api/groups/churn_v2/health
```

Returns:

- `doc_coverage`: fraction of members with auto-generated docs
- `baseline_coverage`: fraction with monitoring baselines
- `cert_distribution`: count by status (`draft` / `reviewed` / `certified` / `deprecated`)
- `latest_drift_summary`: count by severity (`none` / `warning` / `critical`)
- `total_members`: how many features

In the web UI, the group detail page surfaces this as a top banner with one-click filters into the catalog scoped to the group's members.

## Group monitoring

`GET /api/groups/{name}/monitoring` returns the most recent drift check per member. Useful for "is the whole input contract for `churn_v2` healthy this morning?" without clicking through 30 features. Powers the group page's drift table.

## Regenerating docs for the whole group

When the upstream pipeline changes — say, a column's semantics shift — regenerate all member docs in one call:

```bash
featcat groups regenerate-docs churn_v2 --hint "v2 schema: 30-day window per user, excluding bots"
```

The hint flows into every member's autodoc prompt, so descriptions stay consistent across the bundle.

## Deprecating a group

When a group is replaced (`churn_v2` → `churn_v3`):

```bash
featcat groups deprecate churn_v2 --successor churn_v3
```

Doesn't delete — sets `deprecated=true` and stores the successor name. The web UI hides deprecated groups by default with a toggle to show them; the SDK still returns them but with `deprecated=True` on the model.

## Common patterns

- **Branched experiments**: clone a group via `featcat groups clone churn_v2 churn_v2_experiment`, swap a few members, run an A/B.
- **Subset for ablation**: `detail.to_polars(only=["session_count_30d", "event_count_30d"])` returns a subset frame without redefining the group.
- **Cross-source joins**: members can come from any source. The SDK transparently reads each parquet and joins them. Good for joining `user_behavior` features with `device_performance` features.

## When *not* to use groups

- Don't use a group as a tag substitute. If you want "all churn-relevant features," set a `tag=churn` and filter by it. Groups carry overhead (membership rows, regeneration jobs). Tags are free-form and lightweight.
- Don't use groups for ad-hoc scratch work. They show up in the dashboard. If you'll throw it away tomorrow, just write a notebook.

## Related

- **[Catalog browser](catalog.md)** — find features to add to a group
- **[Documentation](docs.md)** — autodoc behavior is per-feature, but groups give you batch entrypoints
- **[Monitoring](monitoring.md)** — per-feature drift; groups aggregate the view
- **[SDK Quickstart](../sdk/quickstart.md#groups)** — `to_polars` / `to_pandas` reference
