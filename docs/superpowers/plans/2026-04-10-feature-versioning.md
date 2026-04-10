# Feature Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add snapshot-before-overwrite versioning for feature metadata changes, with history viewing, diffing, and rollback.

**Architecture:** New `feature_versions` table stores JSON snapshots of feature state before each metadata mutation. A private `_snapshot_feature()` helper in LocalBackend handles diffing and snapshot creation. A new `update_feature_metadata()` method becomes the single entry point for all metadata changes (tags, owner, description), replacing direct field updates. Three new backend interface methods expose version history and rollback.

**Tech Stack:** SQLite (JSON text columns), Pydantic, FastAPI, Typer, pytest

---

## File Structure

| File | Role |
|------|------|
| `featcat/catalog/backend.py` | +3 abstract methods (list_feature_versions, get_feature_version, rollback_feature) |
| `featcat/catalog/local.py` | +schema, +_snapshot_feature, +update_feature_metadata, +3 interface methods, refactor update_feature_tags |
| `featcat/catalog/remote.py` | +3 interface methods (HTTP calls), +name-id cache |
| `featcat/server/routes/features.py` | +3 endpoints (versions, version detail, rollback), enhance PATCH |
| `featcat/cli.py` | +3 feature subcommands (history, diff, rollback) |
| `tests/test_versioning.py` | New file: backend versioning tests |
| `tests/test_server.py` | Add API endpoint tests for versioning |

---

### Task 1: Schema and Backend Interface

**Files:**
- Modify: `featcat/catalog/backend.py`
- Modify: `featcat/catalog/local.py`
- Test: `tests/test_versioning.py`

- [ ] **Step 1: Create test file with first failing test**

Create `tests/test_versioning.py`:

```python
"""Feature versioning tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature


@pytest.fixture()
def db_with_feature(tmp_path: Path):
    """Create a DB with one feature for versioning tests."""
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    feature = Feature(
        name="src.col_a",
        data_source_id=source.id,
        column_name="col_a",
        dtype="int64",
        tags=["original"],
        owner="alice",
    )
    db.upsert_feature(feature)
    yield db
    db.close()


class TestVersionSchema:
    def test_feature_versions_table_exists(self, db_with_feature: CatalogDB):
        row = db_with_feature.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feature_versions'"
        ).fetchone()
        assert row is not None

    def test_list_versions_empty(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        versions = db_with_feature.list_feature_versions(feature.id)
        assert versions == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_versioning.py -v`
Expected: FAIL — `list_feature_versions` not defined

- [ ] **Step 3: Add schema and abstract methods**

In `featcat/catalog/local.py`, append to `SCHEMA_SQL` (before the closing `"""`):

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

In `featcat/catalog/backend.py`, add after the `search_features` method (inside the Features section):

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

In `featcat/catalog/local.py`, add these methods to LocalBackend (after `search_features`):

```python
    # --- Feature Versions ---

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feature_versions WHERE feature_id = ? ORDER BY version DESC",
            (feature_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
            result.append(d)
        return result

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM feature_versions WHERE feature_id = ? AND version = ?",
            (feature_id, version),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
        return d

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        v = self.get_feature_version(feature_id, version)
        if v is None:
            msg = f"Version {version} not found for feature {feature_id}"
            raise ValueError(msg)
        snapshot = v["snapshot"]
        versioned_fields = ("description", "tags", "owner", "dtype")
        updates = {k: snapshot[k] for k in versioned_fields if k in snapshot}
        self.update_feature_metadata(feature_id, _rollback_version=version, **updates)
        feature = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
        return dict(feature) if feature else {}
```

- [ ] **Step 4: Add stub for update_feature_metadata**

In `featcat/catalog/local.py`, add `update_feature_metadata` as a stub (before the version methods):

```python
    def update_feature_metadata(self, feature_id: str, _rollback_version: int | None = None, **kwargs) -> None:
        """Update feature metadata fields with versioning. Stub — implemented in Task 2."""
        now = datetime.now(timezone.utc)
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k == "tags":
                sets.append("tags = ?")
                vals.append(json.dumps(v))
            elif k in ("description", "owner", "dtype"):
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            sets.append("updated_at = ?")
            vals.append(now)
            vals.append(feature_id)
            self.conn.execute(f"UPDATE features SET {', '.join(sets)} WHERE id = ?", vals)
            self.conn.commit()
```

Also add stubs to `featcat/catalog/remote.py` (after `save_baseline`):

```python
    # --- Feature Versions ---

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        return []

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        return None

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        return {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_versioning.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add featcat/catalog/backend.py featcat/catalog/local.py featcat/catalog/remote.py tests/test_versioning.py
git commit -m "feat: add feature_versions schema and backend interface stubs"
```

---

### Task 2: Snapshot and Versioned Metadata Updates

**Files:**
- Modify: `featcat/catalog/local.py`
- Test: `tests/test_versioning.py`

- [ ] **Step 1: Write failing tests for versioned updates**

Append to `tests/test_versioning.py`:

```python
class TestVersionCreation:
    def test_tag_update_creates_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["original", "new_tag"])
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 1
        v = versions[0]
        assert v["version"] == 1
        assert "tags" in v["change_summary"]
        assert v["snapshot"]["tags"] == ["original"]

    def test_metadata_update_creates_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_metadata(feature.id, owner="bob", description="updated desc")
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 1
        v = versions[0]
        assert "owner" in v["change_summary"]
        assert "description" in v["change_summary"]
        assert v["snapshot"]["owner"] == "alice"

    def test_no_version_on_identical_update(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["original"])  # same tags
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 0

    def test_no_version_on_stats_upsert(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        feature.stats = {"mean": 42.0}
        db_with_feature.upsert_feature(feature)
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 0

    def test_sequential_version_numbers(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["v1"])
        db_with_feature.update_feature_tags(feature.id, ["v2"])
        db_with_feature.update_feature_tags(feature.id, ["v3"])
        versions = db_with_feature.list_feature_versions(feature.id)
        assert [v["version"] for v in versions] == [3, 2, 1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_versioning.py::TestVersionCreation -v`
Expected: FAIL — snapshot not created (stub has no versioning logic)

- [ ] **Step 3: Implement `_snapshot_feature` and wire into `update_feature_metadata`**

In `featcat/catalog/local.py`, add the `_snapshot_feature` private method and replace the `update_feature_metadata` stub. Add these inside the LocalBackend class, before the version query methods:

```python
    _VERSIONED_FIELDS = frozenset({"description", "tags", "owner", "dtype", "column_name", "data_source_id"})

    def _snapshot_feature(self, feature_id: str, changes: dict[str, tuple], changed_by: str = "") -> None:
        """Save a version snapshot before applying changes."""
        from .models import _new_id

        row = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
        if row is None:
            return
        snapshot = dict(row)
        # Parse JSON fields for clean storage
        snapshot["tags"] = json.loads(snapshot["tags"]) if isinstance(snapshot.get("tags"), str) else (snapshot.get("tags") or [])
        snapshot["stats"] = json.loads(snapshot["stats"]) if isinstance(snapshot.get("stats"), str) else (snapshot.get("stats") or {})
        # Convert datetime objects to ISO strings for JSON serialization
        for k, v in snapshot.items():
            if isinstance(v, datetime):
                snapshot[k] = v.isoformat()

        next_version = (
            self.conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM feature_versions WHERE feature_id = ?",
                (feature_id,),
            ).fetchone()[0]
        )

        parts = []
        for field, (old_val, new_val) in changes.items():
            parts.append(f"{field}: {old_val!r} -> {new_val!r}")
        change_summary = "; ".join(parts)

        now = datetime.now(timezone.utc)
        self.conn.execute(
            """INSERT INTO feature_versions (id, feature_id, version, snapshot, change_summary, changed_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_new_id(), feature_id, next_version, json.dumps(snapshot), change_summary, changed_by, now),
        )

    def update_feature_metadata(self, feature_id: str, _rollback_version: int | None = None, **kwargs) -> None:
        """Update feature metadata fields with versioning."""
        row = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
        if row is None:
            return
        current = dict(row)
        current["tags"] = json.loads(current["tags"]) if isinstance(current.get("tags"), str) else (current.get("tags") or [])

        # Diff versioned fields
        changes: dict[str, tuple] = {}
        for field in self._VERSIONED_FIELDS:
            if field not in kwargs:
                continue
            old_val = current.get(field)
            new_val = kwargs[field]
            if old_val != new_val:
                changes[field] = (old_val, new_val)

        if not changes:
            return

        # Snapshot before update
        changed_by = kwargs.get("owner", current.get("owner", ""))
        summary_prefix = f"rollback to v{_rollback_version}" if _rollback_version else ""
        self._snapshot_feature(feature_id, changes, changed_by=changed_by)
        if summary_prefix:
            # Update the just-inserted version's change_summary to include rollback prefix
            self.conn.execute(
                """UPDATE feature_versions SET change_summary = ? || ': ' || change_summary
                   WHERE feature_id = ? AND version = (SELECT MAX(version) FROM feature_versions WHERE feature_id = ?)""",
                (summary_prefix, feature_id, feature_id),
            )

        # Apply update
        now = datetime.now(timezone.utc)
        sets = []
        vals: list = []
        for k, v in kwargs.items():
            if k.startswith("_"):
                continue
            if k == "tags":
                sets.append("tags = ?")
                vals.append(json.dumps(v))
            elif k in self._VERSIONED_FIELDS:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            sets.append("updated_at = ?")
            vals.append(now)
            vals.append(feature_id)
            self.conn.execute(f"UPDATE features SET {', '.join(sets)} WHERE id = ?", vals)  # noqa: S608
        self.conn.commit()
```

- [ ] **Step 4: Refactor `update_feature_tags` to delegate**

Replace the existing `update_feature_tags` method in LocalBackend:

```python
    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        self.update_feature_metadata(feature_id, tags=tags)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_versioning.py -v`
Expected: 7 PASSED

- [ ] **Step 6: Commit**

```bash
git add featcat/catalog/local.py tests/test_versioning.py
git commit -m "feat: implement versioned metadata updates with snapshot-before-overwrite"
```

---

### Task 3: Rollback

**Files:**
- Modify: `tests/test_versioning.py`
- Verify: `featcat/catalog/local.py` (rollback_feature already implemented in Task 1)

- [ ] **Step 1: Write rollback tests**

Append to `tests/test_versioning.py`:

```python
class TestRollback:
    def test_rollback_restores_state(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["changed"])
        db_with_feature.update_feature_metadata(feature.id, owner="bob")
        # Rollback to v1 (before owner change, after tag change)
        db_with_feature.rollback_feature(feature.id, 1)
        updated = db_with_feature.get_feature_by_name("src.col_a")
        assert updated.tags == ["original"]
        assert updated.owner == "alice"

    def test_rollback_creates_new_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["changed"])
        db_with_feature.rollback_feature(feature.id, 1)
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert "rollback to v1" in versions[0]["change_summary"]

    def test_rollback_nonexistent_version_raises(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        with pytest.raises(ValueError, match="Version 99 not found"):
            db_with_feature.rollback_feature(feature.id, 99)

    def test_get_specific_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["v1_tags"])
        v = db_with_feature.get_feature_version(feature.id, 1)
        assert v is not None
        assert v["version"] == 1
        assert v["snapshot"]["tags"] == ["original"]

    def test_get_nonexistent_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        assert db_with_feature.get_feature_version(feature.id, 999) is None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_versioning.py::TestRollback -v`
Expected: 5 PASSED (rollback_feature was implemented in Task 1 Step 3)

- [ ] **Step 3: Commit**

```bash
git add tests/test_versioning.py
git commit -m "test: add rollback tests for feature versioning"
```

---

### Task 4: API Endpoints

**Files:**
- Modify: `featcat/server/routes/features.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing API tests**

Read `tests/test_server.py` to understand existing patterns, then append versioning API tests. The file uses `fastapi.testclient.TestClient` and a `client` fixture.

Append to `tests/test_server.py`:

```python
class TestFeatureVersionsAPI:
    def test_list_versions_empty(self, client):
        features = client.get("/api/features").json()
        if not features:
            pytest.skip("No features in test DB")
        name = features[0]["name"]
        resp = client.get(f"/api/features/by-name/versions?name={name}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_version_created_on_patch(self, client):
        features = client.get("/api/features").json()
        if not features:
            pytest.skip("No features in test DB")
        name = features[0]["name"]
        client.patch(f"/api/features/by-name?name={name}", json={"tags": ["api_test"]})
        resp = client.get(f"/api/features/by-name/versions?name={name}")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) >= 1
        assert "tags" in versions[0]["change_summary"]

    def test_get_specific_version(self, client):
        features = client.get("/api/features").json()
        if not features:
            pytest.skip("No features in test DB")
        name = features[0]["name"]
        client.patch(f"/api/features/by-name?name={name}", json={"owner": "test_owner"})
        resp = client.get(f"/api/features/by-name/versions/1?name={name}")
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

    def test_rollback(self, client):
        features = client.get("/api/features").json()
        if not features:
            pytest.skip("No features in test DB")
        name = features[0]["name"]
        original = client.get(f"/api/features/by-name?name={name}").json()
        client.patch(f"/api/features/by-name?name={name}", json={"description": "changed"})
        resp = client.post(f"/api/features/by-name/rollback?name={name}", json={"version": 1})
        assert resp.status_code == 200
        restored = client.get(f"/api/features/by-name?name={name}").json()
        assert restored["description"] == original["description"]

    def test_versions_404_for_unknown_feature(self, client):
        resp = client.get("/api/features/by-name/versions?name=nonexistent.feature")
        assert resp.status_code == 404

    def test_rollback_404_for_bad_version(self, client):
        features = client.get("/api/features").json()
        if not features:
            pytest.skip("No features in test DB")
        name = features[0]["name"]
        resp = client.post(f"/api/features/by-name/rollback?name={name}", json={"version": 9999})
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py::TestFeatureVersionsAPI -v`
Expected: FAIL — endpoints don't exist yet

- [ ] **Step 3: Add API endpoints and enhance PATCH**

In `featcat/server/routes/features.py`, add the new endpoints and update the PATCH handler:

```python
class RollbackRequest(BaseModel):
    version: int


@router.get("/by-name/versions")
def list_versions(name: str = Query(...), db=Depends(get_db)):
    """List version history for a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return db.list_feature_versions(feature.id)


@router.get("/by-name/versions/{version}")
def get_version(version: int, name: str = Query(...), db=Depends(get_db)):
    """Get a specific version snapshot."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    v = db.get_feature_version(feature.id, version)
    if v is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return v


@router.post("/by-name/rollback")
def rollback_feature(name: str = Query(...), body: RollbackRequest = ..., db=Depends(get_db)):
    """Rollback feature metadata to a previous version."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    try:
        result = db.rollback_feature(feature.id, body.version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result
```

Replace the existing `update_feature_by_name` PATCH handler:

```python
@router.patch("/by-name")
def update_feature_by_name(name: str = Query(...), body: FeatureUpdate = ..., db=Depends(get_db)):
    """Update feature metadata (tags, owner, description) with versioning."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    updates = body.model_dump(exclude_none=True)
    if updates:
        db.update_feature_metadata(feature.id, **updates)
    return {"updated": name}
```

**Important:** The version endpoints MUST be defined BEFORE the existing `/by-name` GET route in the file, otherwise FastAPI will match `/by-name/versions` as the `by-name` route with `versions` interpreted as part of the query. Reorder the endpoints: version routes first, then existing by-name routes.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_server.py::TestFeatureVersionsAPI -v`
Expected: 6 PASSED

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add featcat/server/routes/features.py tests/test_server.py
git commit -m "feat: add version history, detail, and rollback API endpoints"
```

---

### Task 5: RemoteBackend Implementation

**Files:**
- Modify: `featcat/catalog/remote.py`

- [ ] **Step 1: Implement RemoteBackend version methods**

Replace the stubs added in Task 1 with real implementations in `featcat/catalog/remote.py`:

```python
    # --- Feature Versions ---

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        name = self._resolve_feature_name(feature_id)
        if name is None:
            return []
        return self._request("GET", "/api/features/by-name/versions", params={"name": name})

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        name = self._resolve_feature_name(feature_id)
        if name is None:
            return None
        try:
            return self._request("GET", f"/api/features/by-name/versions/{version}", params={"name": name})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        name = self._resolve_feature_name(feature_id)
        if name is None:
            msg = f"Feature not found: {feature_id}"
            raise ValueError(msg)
        return self._request("POST", "/api/features/by-name/rollback", params={"name": name}, json={"version": version})
```

Add the name resolution helper and update `get_feature_by_name` to cache:

```python
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url.rstrip("/")
        headers = {}
        token = os.environ.get("FEATCAT_SERVER_AUTH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=self.server_url, timeout=30, headers=headers)
        self._id_to_name: dict[str, str] = {}
```

Update `get_feature_by_name` to populate the cache:

```python
    def get_feature_by_name(self, name: str) -> Any | None:
        try:
            result = self._request("GET", "/api/features/by-name", params={"name": name})
            feature = Feature.model_validate(result)
            self._id_to_name[feature.id] = feature.name
            return feature
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
```

Add the resolver:

```python
    def _resolve_feature_name(self, feature_id: str) -> str | None:
        """Resolve a feature ID to a name, using cache or fallback to list."""
        if feature_id in self._id_to_name:
            return self._id_to_name[feature_id]
        # Fallback: iterate features
        for f in self.list_features():
            self._id_to_name[f.id] = f.name
        return self._id_to_name.get(feature_id)
```

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: All checks passed

- [ ] **Step 3: Commit**

```bash
git add featcat/catalog/remote.py
git commit -m "feat: implement RemoteBackend version methods with name-id cache"
```

---

### Task 6: CLI Commands

**Files:**
- Modify: `featcat/cli.py`

- [ ] **Step 1: Add `feature history` command**

In `featcat/cli.py`, add after the existing `feature_search` command:

```python
@feature_app.command("history")
def feature_history(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show version history for a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)

    versions = db.list_feature_versions(feature.id)
    db.close()

    if not versions:
        console.print(f"No version history for [cyan]{name}[/cyan]")
        return

    table = Table(title=f"Version History: {name}")
    table.add_column("Version", style="bold", justify="right")
    table.add_column("Changed", style="dim")
    table.add_column("Summary")
    table.add_column("By", style="dim")

    for v in versions:
        ts = v["created_at"]
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M")
        table.add_row(str(v["version"]), str(ts), v.get("change_summary", ""), v.get("changed_by", ""))
    console.print(table)
```

Add the `Table` import at the top of the file (it should already be imported — verify):

```python
from rich.table import Table
```

- [ ] **Step 2: Add `feature diff` command**

```python
@feature_app.command("diff")
def feature_diff(
    name: str = typer.Argument(help="Feature name"),
    v1: int | None = typer.Option(None, "--v1", help="First version (default: previous)"),
    v2: int | None = typer.Option(None, "--v2", help="Second version (default: latest)"),
) -> None:
    """Diff two versions of a feature's metadata."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)

    versions = db.list_feature_versions(feature.id)
    db.close()

    if not versions:
        console.print(f"No version history for [cyan]{name}[/cyan]")
        return

    # Default: latest vs previous
    if v2 is None:
        v2 = versions[0]["version"]
    if v1 is None:
        v1 = versions[1]["version"] if len(versions) > 1 else versions[0]["version"]

    snap_v1 = next((v["snapshot"] for v in versions if v["version"] == v1), None)
    snap_v2 = next((v["snapshot"] for v in versions if v["version"] == v2), None)

    if snap_v1 is None or snap_v2 is None:
        console.print("[red]Version not found[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Comparing v{v2} vs v{v1}:[/bold]")
    versioned = ("description", "tags", "owner", "dtype", "column_name")
    has_diff = False
    for field in versioned:
        old = snap_v1.get(field)
        new = snap_v2.get(field)
        if old != new:
            console.print(f"  [cyan]{field}:[/cyan]  {old!r} -> {new!r}")
            has_diff = True
    if not has_diff:
        console.print("  (no differences)")
    console.print()
```

- [ ] **Step 3: Add `feature rollback` command**

```python
@feature_app.command("rollback")
def feature_rollback(
    name: str = typer.Argument(help="Feature name"),
    version: int = typer.Option(..., "--version", "-v", help="Version number to rollback to"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Rollback feature metadata to a previous version."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)

    target = db.get_feature_version(feature.id, version)
    if target is None:
        console.print(f"[red]Version {version} not found[/red]")
        db.close()
        raise typer.Exit(1)

    if not yes:
        console.print(f"\nRollback [cyan]{name}[/cyan] to version {version}?")
        snapshot = target["snapshot"]
        for field in ("description", "tags", "owner", "dtype"):
            old = getattr(feature, field, None)
            new = snapshot.get(field)
            if old != new:
                console.print(f"  [cyan]{field}:[/cyan]  {old!r} -> {new!r}")
        if not typer.confirm("Confirm?"):
            db.close()
            raise typer.Exit(0)

    db.rollback_feature(feature.id, version)
    versions = db.list_feature_versions(feature.id)
    new_ver = versions[0]["version"] if versions else "?"
    db.close()
    console.print(f"[green]Rolled back.[/green] New version {new_ver} created.")
```

- [ ] **Step 4: Run lint and type-check**

Run: `make lint`
Expected: All checks passed

- [ ] **Step 5: Commit**

```bash
git add featcat/cli.py
git commit -m "feat: add feature history, diff, and rollback CLI commands"
```

---

### Task 7: Final Integration and Verification

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `make check`
Expected: lint + type-check + all tests pass

- [ ] **Step 2: Manual API verification**

```bash
# Update a feature's tags
curl -s -X PATCH 'http://localhost:8000/api/features/by-name?name=device_performance.cpu_usage' \
  -H 'Content-Type: application/json' -d '{"tags":["compute","performance","test"]}'

# Check version was created
curl -s 'http://localhost:8000/api/features/by-name/versions?name=device_performance.cpu_usage' | python3 -m json.tool

# Get specific version
curl -s 'http://localhost:8000/api/features/by-name/versions/1?name=device_performance.cpu_usage' | python3 -m json.tool

# Rollback
curl -s -X POST 'http://localhost:8000/api/features/by-name/rollback?name=device_performance.cpu_usage' \
  -H 'Content-Type: application/json' -d '{"version":1}'
```

- [ ] **Step 3: Manual CLI verification**

```bash
featcat feature history device_performance.cpu_usage
featcat feature diff device_performance.cpu_usage
featcat feature rollback device_performance.cpu_usage --version 1 --yes
```

- [ ] **Step 4: Commit any fixes**

If any fixes were needed during verification:

```bash
git add -u
git commit -m "fix: address integration issues in feature versioning"
```
