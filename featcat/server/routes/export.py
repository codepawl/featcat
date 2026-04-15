"""Feature data export endpoints."""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter()

# Track exports for cleanup
_exports: dict[str, str] = {}  # export_id -> file_path
_lock = threading.Lock()

CLEANUP_SECONDS = 3600  # 1 hour


class ExportRequest(BaseModel):
    feature_specs: list[str] | None = None
    group_name: str | None = None
    join_on: str | None = None
    format: str = "parquet"


@router.post("")
def create_export(body: ExportRequest, db=Depends(get_db)):
    """Create a feature data export."""
    from ...catalog.exporter import export_features

    if not body.feature_specs and not body.group_name:
        raise HTTPException(
            status_code=400,
            detail="Provide either feature_specs or group_name.",
        )

    # Resolve feature specs from group if needed
    specs = body.feature_specs or []
    if body.group_name:
        group = db.get_group_by_name(body.group_name)
        if group is None:
            raise HTTPException(status_code=404, detail=f"Group not found: {body.group_name}")
        members = db.list_group_members(group.id)
        specs = [m.name for m in members]

    if not specs:
        raise HTTPException(status_code=400, detail="No features to export.")

    if body.format not in ("parquet", "csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {body.format}")

    try:
        result = export_features(
            feature_specs=specs,
            db=db,
            join_on=body.join_on,
            fmt=body.format,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Track for cleanup
    with _lock:
        _exports[result.export_id] = result.output_path

    # Schedule cleanup
    _schedule_cleanup(result.export_id, result.output_path)

    return {
        "export_id": result.export_id,
        "download_url": f"/api/export/{result.export_id}/download",
        "feature_count": result.feature_count,
        "row_count": result.row_count,
        "sources_used": result.sources_used,
        "join_column": result.join_column,
        "code_snippet": result.code_snippet,
        "warnings": result.warnings,
        "file_size": result.file_size,
    }


@router.get("/{export_id}/download")
def download_export(export_id: str):
    """Download an exported file."""
    with _lock:
        file_path = _exports.get(export_id)

    if file_path is None or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Export not found or expired.")

    ext = Path(file_path).suffix.lstrip(".")
    media_type = "text/csv" if ext == "csv" else "application/octet-stream"
    filename = f"featcat_export.{ext}"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


def _schedule_cleanup(export_id: str, file_path: str) -> None:
    """Schedule file cleanup after CLEANUP_SECONDS."""

    def _cleanup():
        with _lock:
            _exports.pop(export_id, None)
        with contextlib.suppress(OSError):
            os.remove(file_path)

    timer = threading.Timer(CLEANUP_SECONDS, _cleanup)
    timer.daemon = True
    timer.start()
