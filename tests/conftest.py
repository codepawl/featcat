"""Shared test fixtures."""

from __future__ import annotations

import io
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.db import CatalogDB

if TYPE_CHECKING:
    from collections.abc import Iterator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_parquet(tmp_path: Path) -> Path:
    """Create a small sample Parquet file for testing."""
    table = pa.table(
        {
            "user_id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "age": pa.array([25, 30, None, 22, 45], type=pa.int64()),
            "revenue": pa.array([100.5, 200.0, 150.3, None, 300.0], type=pa.float64()),
            "city": pa.array(["HCM", "HN", "DN", "HCM", None], type=pa.string()),
        }
    )
    path = tmp_path / "sample.parquet"
    pq.write_table(table, path)
    return path


@pytest.fixture()
def sample_parquet_dir(tmp_path: Path) -> Path:
    """Create a directory with multiple Parquet files for bulk scan testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # File 1
    t1 = pa.table({"user_id": pa.array([1, 2, 3]), "score": pa.array([0.5, 0.8, 0.3])})
    pq.write_table(t1, data_dir / "users.parquet")
    # File 2
    t2 = pa.table({"item_id": pa.array([10, 20]), "price": pa.array([9.99, 19.99])})
    pq.write_table(t2, data_dir / "items.parquet")
    # Nested file
    sub = data_dir / "sub"
    sub.mkdir()
    t3 = pa.table({"event": pa.array(["click", "view"]), "ts": pa.array([1000, 2000])})
    pq.write_table(t3, sub / "events.parquet")
    return data_dir


@pytest.fixture()
def db(tmp_path: Path) -> CatalogDB:
    """Create a temporary catalog database."""
    db_path = str(tmp_path / "test_catalog.db")
    catalog = CatalogDB(db_path)
    catalog.init_db()
    yield catalog
    catalog.close()


# ---------------------------------------------------------------------------
# MinIO testcontainer fixtures (Phase 2 of S3 implementation)
#
# Architecture: three layered fixtures so tests get full isolation while
# paying the container startup cost only once per session.
#
#   _minio_container (session)    -> one MinIO container, ephemeral host port
#   minio_backend    (function)   -> unique uuid-suffixed bucket per test
#   minio_env        (function)   -> FEATCAT_S3_* env vars via monkeypatch
#
# Tests gated on `@pytest.mark.s3` are skipped cleanly when Docker is absent.
# ---------------------------------------------------------------------------


@dataclass
class MinioBackend:
    """Per-test handle to MinIO: shared container, isolated bucket."""

    endpoint_url: str  # dynamic ephemeral host port, e.g. "http://127.0.0.1:32768"
    access_key: str
    secret_key: str
    bucket: str  # uuid-suffixed, unique per test
    client: Any  # boto3 S3 client bound to this endpoint

    def upload_parquet(self, key: str, table: pa.Table) -> str:
        """Upload an in-memory parquet to ``{self.bucket}/{key}``; return s3:// URI."""
        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=buf.read())
        return f"s3://{self.bucket}/{key}"


def _docker_available() -> bool:
    """True iff a docker daemon is reachable."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


@pytest.fixture(scope="session")
def _minio_container() -> Iterator[dict[str, str]]:
    """Session-wide MinIO container. Uses testcontainers' dynamic port mapping
    so the container's :9000 binds to an ephemeral host port — no conflict
    with a featcat compose stack listening on :9000 on the same host.

    Skipped cleanly when Docker is unavailable so the rest of the suite
    still runs in environments without a Docker daemon (CI without DinD).
    """
    if not _docker_available():
        pytest.skip("Docker not available; S3 tests skipped")

    from testcontainers.minio import MinioContainer

    with MinioContainer() as mc:
        host = mc.get_container_host_ip()
        port = mc.get_exposed_port(9000)
        yield {
            "endpoint_url": f"http://{host}:{port}",
            "access_key": mc.access_key,
            "secret_key": mc.secret_key,
        }


@pytest.fixture()
def minio_backend(_minio_container: dict[str, str]) -> Iterator[MinioBackend]:
    """Per-test isolated bucket against the session MinIO. Created at start,
    emptied + deleted at end so tests never share bucket state."""
    import boto3

    bucket = f"featcat-test-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=_minio_container["endpoint_url"],
        aws_access_key_id=_minio_container["access_key"],
        aws_secret_access_key=_minio_container["secret_key"],
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    try:
        yield MinioBackend(
            endpoint_url=_minio_container["endpoint_url"],
            access_key=_minio_container["access_key"],
            secret_key=_minio_container["secret_key"],
            bucket=bucket,
            client=client,
        )
    finally:
        # Per-test cleanup: boto3 won't delete a non-empty bucket.
        try:
            objs = client.list_objects_v2(Bucket=bucket).get("Contents", [])
            if objs:
                client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objs]},
                )
            client.delete_bucket(Bucket=bucket)
        except Exception:
            # Container is dropped at session end anyway; best-effort cleanup.
            pass


@pytest.fixture()
def minio_env(minio_backend: MinioBackend, monkeypatch: pytest.MonkeyPatch) -> Iterator[MinioBackend]:
    """FEATCAT_S3_* env vars pointed at the per-test MinIO bucket.

    Uses monkeypatch (project convention: never touch os.environ directly in
    tests) so env state is guaranteed clean at teardown.
    """
    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", minio_backend.endpoint_url)
    monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", minio_backend.access_key)
    monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", minio_backend.secret_key)
    monkeypatch.setenv("FEATCAT_S3_REGION", "us-east-1")
    yield minio_backend


# ---------------------------------------------------------------------------
# Real-endpoint S3 fixtures (Phase 6 — opt-in integration suite)
#
# Used by ``tests/test_s3_real.py`` for tests gated on ``@pytest.mark.s3_real``.
# These fixtures point at a real S3 / MinIO backend the operator configures
# out-of-band via env vars; if any of the four are missing, every dependent
# test is skipped cleanly with a clear message naming what's missing.
# ---------------------------------------------------------------------------


@dataclass
class RealS3Backend:
    """Read-only view of a real S3 / MinIO endpoint for integration tests."""

    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str


@pytest.fixture(scope="session")
def real_s3_backend() -> Iterator[RealS3Backend]:
    """Real-endpoint S3 backend, configured via ``FEATCAT_S3_TEST_*`` env vars.

    Skips the entire dependent suite when any required env var is missing,
    so operators only opt in by setting all four together.

    Required env vars:
        FEATCAT_S3_TEST_ENDPOINT     — e.g. http://minio.lab.fpt.internal:9000
        FEATCAT_S3_TEST_ACCESS_KEY
        FEATCAT_S3_TEST_SECRET_KEY
        FEATCAT_S3_TEST_BUCKET       — must already exist; tests don't create it.
                                       See admin-guide for fixture setup.
    """
    import os

    required = {
        "endpoint_url": "FEATCAT_S3_TEST_ENDPOINT",
        "access_key": "FEATCAT_S3_TEST_ACCESS_KEY",
        "secret_key": "FEATCAT_S3_TEST_SECRET_KEY",
        "bucket": "FEATCAT_S3_TEST_BUCKET",
    }
    resolved = {field: os.environ.get(env_var) for field, env_var in required.items()}
    missing = [env_var for field, env_var in required.items() if not resolved[field]]
    if missing:
        pytest.skip(f"Real S3 not configured; missing: {', '.join(missing)}")
    # type: ignore[arg-type] — resolved values are guaranteed non-None after the
    # missing check above, but the type checker can't see that.
    yield RealS3Backend(**resolved)  # type: ignore[arg-type]


@pytest.fixture()
def real_s3_env(
    real_s3_backend: RealS3Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[RealS3Backend]:
    """FEATCAT_S3_* env vars pointed at the real backend (via monkeypatch).

    Strips any previously-set MinIO-testcontainer env state so the two
    suites can coexist in one pytest session without env leakage.
    """
    # Clear any prior MinIO testcontainer state first.
    monkeypatch.delenv("FEATCAT_S3_SESSION_TOKEN", raising=False)
    # Then set the real-endpoint state.
    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", real_s3_backend.endpoint_url)
    monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", real_s3_backend.access_key)
    monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", real_s3_backend.secret_key)
    monkeypatch.setenv("FEATCAT_S3_REGION", "us-east-1")
    yield real_s3_backend
