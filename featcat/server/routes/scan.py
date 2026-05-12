"""Bulk scan endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ...catalog.models import DataSource, Feature
from ...catalog.scanner import discover_parquet_files, scan_source
from ...catalog.storage import validate_path_input
from ..deps import get_db

router = APIRouter()


class BulkScanRequest(BaseModel):
    path: str
    recursive: bool = False
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = False


class FileDetail(BaseModel):
    file: str
    status: str  # "registered" | "skipped" | "error"
    feature_count: int = 0
    error: str = ""


class BulkScanResponse(BaseModel):
    found: int
    registered_sources: int
    registered_features: int
    skipped: int
    details: list[FileDetail]


@router.post("", response_model=BulkScanResponse)
async def bulk_scan(body: BulkScanRequest, db=Depends(get_db)):  # noqa: B008
    """Scan a directory or S3 prefix for Parquet files and register them as sources + features."""
    try:
        validated_path = validate_path_input(body.path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    def _scan():
        files = discover_parquet_files(validated_path, recursive=body.recursive)
        registered_sources = 0
        registered_features = 0
        skipped = 0
        details: list[dict] = []

        for f in files:
            # ``f`` is a string in both branches: absolute local path or s3:// URI.
            abs_path = f
            source_name = Path(f).stem

            existing = db.get_source_by_path(abs_path)
            if existing:
                skipped += 1
                details.append({"file": f, "status": "skipped", "feature_count": 0})
                continue

            if body.dry_run:
                try:
                    columns = scan_source(abs_path)
                    details.append({"file": f, "status": "would_register", "feature_count": len(columns)})
                except Exception as e:  # noqa: BLE001
                    details.append({"file": f, "status": "error", "feature_count": 0, "error": str(e)})
                continue

            # Handle name collision
            final_name = source_name
            suffix = 1
            while db.get_source_by_name(final_name) is not None:
                final_name = f"{source_name}_{suffix}"
                suffix += 1

            started = datetime.now(timezone.utc)
            perf_start = time.perf_counter()
            source: DataSource | None = None
            try:
                source = DataSource(name=final_name, path=abs_path)
                db.add_source(source)
                registered_sources += 1

                columns = scan_source(abs_path)
                for col in columns:
                    feature = Feature(
                        name=f"{final_name}.{col.column_name}",
                        data_source_id=source.id,
                        column_name=col.column_name,
                        dtype=col.dtype,
                        stats=col.stats,
                        owner=body.owner,
                        tags=list(body.tags),
                    )
                    db.upsert_feature(feature)
                    registered_features += 1

                # One scan-log row per registered source. Newly-registered
                # sources start empty, so every column counts as `added`.
                finished = datetime.now(timezone.utc)
                db.record_scan_log(
                    source.id,
                    started_at=started,
                    finished_at=finished,
                    duration_seconds=time.perf_counter() - perf_start,
                    status="success",
                    files_scanned=1,
                    features_added=len(columns),
                    triggered_by="api",
                )

                details.append({"file": f, "status": "registered", "feature_count": len(columns)})
            except Exception as e:  # noqa: BLE001
                # Only audit when the source row was created — pre-add failures
                # have no source_id to log against.
                if source is not None and db.get_source_by_name(source.name) is not None:
                    finished = datetime.now(timezone.utc)
                    db.record_scan_log(
                        source.id,
                        started_at=started,
                        finished_at=finished,
                        duration_seconds=time.perf_counter() - perf_start,
                        status="failed",
                        files_scanned=0,
                        error_message=str(e),
                        triggered_by="api",
                    )
                details.append({"file": f, "status": "error", "feature_count": 0, "error": str(e)})

        return {
            "found": len(files),
            "registered_sources": registered_sources,
            "registered_features": registered_features,
            "skipped": skipped,
            "details": details,
        }

    return await run_in_threadpool(_scan)
