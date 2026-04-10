# Feature Versioning Design

**Date**: 2026-04-10
**Phase**: 7.1 (Feature Store-Inspired Improvements)
**Status**: Approved

## Context

featcat tracks feature metadata (description, tags, owner, dtype) but has no history of changes. When metadata is updated, the previous state is lost. This makes it impossible to audit who changed what, when, or to recover from accidental overwrites.

Feature versioning adds a snapshot-before-overwrite mechanism: every metadata change creates a version record with the previous state, a human-readable diff summary, and a timestamp. Users can view history, compare versions, and rollback to any previous state.

## Scope

**In scope**: Versioning metadata changes (description, tags, owner, dtype, column_name, data_source_id). History viewing, diffing, and rollback. Backend, CLI, API, and RemoteBackend.

**Out of scope**: Versioning stats refreshes from scanner (too noisy). Web UI for version history (future phase). TUI integration (future phase).

## Schema

New table in `SCHEMA_SQL` (`featcat/catalog/local.py`):

```sql
CREATE TABLE IF NOT EXISTS feature_versions (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    changed_by TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL,
    UNIQUE(feature_id, version)
);
```

- `id`: UUID (same `_new_id()` pattern as other tables)
- `version`: Auto-incremented per feature, starts at 1
- `snapshot`: JSON string of full feature row at the time of the change (before the update)
- `change_summary`: Human-readable diff, e.g. `"tags: [a,b] -> [a,b,c]; owner: '' -> 'ds-team'"`
- `changed_by`: From owner field or config; empty string if unknown

Table created in `init_db()` via the existing `CREATE TABLE IF NOT EXISTS` pattern.

## CatalogBackend Interface

Three new abstract methods in `featcat/catalog/backend.py`:

```python
@abstractmethod
def list_feature_versions(self, feature_id: str) -> list[dict]:
    """Return all versions for a feature, ordered by version descending."""

@abstractmethod
def get_feature_version(self, feature_id: str, version: int) -> dict | None:
    """Return a specific version snapshot, or None if not found."""

@abstractmethod
def rollback_feature(self, feature_id: str, version: int) -> dict:
    """Restore feature metadata from a version snapshot. Creates a new version record."""
```

## LocalBackend Implementation

File: `featcat/catalog/local.py`

### Private helper: `_snapshot_feature()`

```python
def _snapshot_feature(self, feature_id: str, changes: dict[str, tuple], changed_by: str = "") -> None:
    """Save a version snapshot before applying changes.

    Args:
        feature_id: The feature being modified
        changes: Dict of {field: (old_value, new_value)} for changed fields
        changed_by: Who made the change
    """
```

Logic:
1. Read current feature row as dict (the "before" state)
2. Compute next version: `SELECT COALESCE(MAX(version), 0) + 1 FROM feature_versions WHERE feature_id = ?`
3. Build `change_summary` from the `changes` dict: `"field: old -> new"` for each changed field
4. Insert into `feature_versions` with the current row as JSON snapshot

### Versioned fields

Only these fields trigger versioning: `description`, `tags`, `owner`, `dtype`, `column_name`, `data_source_id`.

Stats-only updates from the scanner (`upsert_feature` on conflict) do NOT create versions.

### Hook points

1. **`update_feature_tags(feature_id, tags)`**: Before writing new tags, diff old vs new. If different, call `_snapshot_feature()`.

2. **New `update_feature_metadata(feature_id, **kwargs)`**: General method for updating any combination of: description, owner, tags. Diffs each field, snapshots if any changed, then applies the update. The PATCH endpoint will call this instead of `update_feature_tags` directly.

3. **`update_feature_tags`** remains for backward compatibility but delegates to `update_feature_metadata`.

### `list_feature_versions(feature_id)`

```sql
SELECT * FROM feature_versions WHERE feature_id = ? ORDER BY version DESC
```

Returns list of dicts with: version, change_summary, changed_by, created_at, snapshot (parsed JSON).

### `get_feature_version(feature_id, version)`

```sql
SELECT * FROM feature_versions WHERE feature_id = ? AND version = ?
```

Returns dict or None.

### `rollback_feature(feature_id, version)`

1. Fetch the target version's snapshot
2. Extract versioned fields from snapshot
3. Call `update_feature_metadata()` with those values (which creates a new version with summary "rollback to v{N}")
4. Return the updated feature

## RemoteBackend Implementation

File: `featcat/catalog/remote.py`

```python
def list_feature_versions(self, feature_id: str) -> list[dict]:
    # Need feature name for API call — look up or accept name
    resp = self._request("GET", f"/features/by-name/versions", params={"name": name})
    return resp.json()

def get_feature_version(self, feature_id: str, version: int) -> dict | None:
    resp = self._request("GET", f"/features/by-name/versions/{version}", params={"name": name})
    return resp.json()

def rollback_feature(self, feature_id: str, version: int) -> dict:
    resp = self._request("POST", f"/features/by-name/rollback", params={"name": name}, json={"version": version})
    return resp.json()
```

**ID-to-name resolution**: RemoteBackend methods receive `feature_id` from the abstract interface but need the feature name for the API. Since RemoteBackend has no local DB, and iterating all features to find a name by ID is expensive, the practical approach is: callers (CLI, routes) always have the feature name available already (they look up by name first). RemoteBackend will cache the last-used feature name→id mapping in a simple dict attribute, populated by `get_feature_by_name()`. If the ID isn't in the cache, it falls back to iterating `list_features()`. This is acceptable because version operations always follow a name lookup.

## API Endpoints

File: `featcat/server/routes/features.py`

All use query params for feature name (consistent with existing `by-name` pattern for dotted names).

### GET /api/features/by-name/versions

```python
@router.get("/by-name/versions")
def list_versions(name: str = Query(...), db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(404, f"Feature not found: {name}")
    versions = db.list_feature_versions(feature.id)
    return versions
```

### GET /api/features/by-name/versions/{version}

```python
@router.get("/by-name/versions/{version}")
def get_version(version: int, name: str = Query(...), db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(404, f"Feature not found: {name}")
    v = db.get_feature_version(feature.id, version)
    if v is None:
        raise HTTPException(404, f"Version {version} not found")
    return v
```

### POST /api/features/by-name/rollback

```python
class RollbackRequest(BaseModel):
    version: int

@router.post("/by-name/rollback")
def rollback(name: str = Query(...), body: RollbackRequest = ..., db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(404, f"Feature not found: {name}")
    result = db.rollback_feature(feature.id, body.version)
    return result
```

### PATCH endpoint enhancement

Expand the existing `update_feature_by_name` to process all `FeatureUpdate` fields:

```python
@router.patch("/by-name")
def update_feature_by_name(name: str = Query(...), body: FeatureUpdate = ..., db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(404, f"Feature not found: {name}")
    updates = body.model_dump(exclude_none=True)
    if updates:
        db.update_feature_metadata(feature.id, **updates)
    return {"updated": name}
```

## CLI Commands

File: `featcat/cli.py`, under the existing `feature_app` typer group.

### featcat feature history \<name\>

```
$ featcat feature history device_performance.cpu_usage
Version  Changed            Summary                          By
───────  ─────────────────  ───────────────────────────────  ──────
  3      2026-04-10 14:30   tags: [compute] -> [compute,ml]  dev
  2      2026-04-09 10:15   owner: '' -> 'ds-team'           admin
  1      2026-04-08 09:00   tags: [] -> [compute]            dev
```

### featcat feature diff \<name\> [--v1 N --v2 M]

Default: latest vs previous. Shows field-by-field comparison.

```
$ featcat feature diff device_performance.cpu_usage
Comparing v3 vs v2:
  tags:  [compute] -> [compute, ml]

$ featcat feature diff device_performance.cpu_usage --v1 1 --v2 3
Comparing v3 vs v1:
  tags:   [] -> [compute, ml]
  owner:  '' -> 'ds-team'
```

### featcat feature rollback \<name\> --version N

```
$ featcat feature rollback device_performance.cpu_usage --version 2
Rollback device_performance.cpu_usage to version 2?
  tags:  [compute, ml] -> [compute]
  owner: ds-team (unchanged)
Confirm? [y/N]: y
Rolled back. New version 4 created.
```

## Testing

File: `tests/test_versioning.py`

Test cases:
1. **Version on tag update**: Update tags, verify version record created with correct snapshot and summary
2. **Version on metadata update**: Update owner + description, verify single version with both changes
3. **No version on stats upsert**: Call `upsert_feature` with only stats changes, verify no version created
4. **Sequential numbering**: Multiple updates produce versions 1, 2, 3... per feature
5. **Independent per feature**: Versions for feature A don't affect feature B's numbering
6. **Rollback restores state**: Rollback to v1, verify feature metadata matches v1 snapshot
7. **Rollback creates version**: After rollback, a new version exists with "rollback to vN" summary
8. **Rollback to nonexistent version**: Returns error / raises exception
9. **List versions**: Returns correct order (newest first)
10. **Get specific version**: Returns correct snapshot data

## File Changes Summary

| File | Change |
|------|--------|
| `featcat/catalog/backend.py` | +3 abstract methods |
| `featcat/catalog/local.py` | +table schema, +_snapshot_feature, +update_feature_metadata, +3 interface methods, modify update_feature_tags |
| `featcat/catalog/remote.py` | +3 interface methods |
| `featcat/catalog/models.py` | No changes needed |
| `featcat/server/routes/features.py` | +3 endpoints, enhance PATCH |
| `featcat/cli.py` | +3 subcommands (history, diff, rollback) |
| `tests/test_versioning.py` | New file, ~10 test cases |
