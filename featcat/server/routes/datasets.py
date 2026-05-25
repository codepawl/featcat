"""Training dataset build endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...catalog.training_dataset import (
    TrainingDatasetBuildResult,
    TrainingDatasetValidationIssue,
    build_training_dataset,
    training_dataset_result_to_dict,
)
from ..deps import get_db

router = APIRouter()


class DatasetBuildRequest(BaseModel):
    entity_df_path: str
    source_path: str | None = None
    source_name: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str]
    output_path: str | None = None


class DatasetBuildIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


class DatasetBuildResponse(BaseModel):
    is_valid: bool
    errors: list[DatasetBuildIssue]
    warnings: list[DatasetBuildIssue]
    entity_df_path: str | None = None
    source_path: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str]
    output_path: str | None = None
    row_count: int
    feature_count: int
    unresolved_row_count: int
    missing_feature_value_count: int


def _response_from_result(result: TrainingDatasetBuildResult) -> DatasetBuildResponse:
    return DatasetBuildResponse.model_validate(training_dataset_result_to_dict(result))


@router.post("/build", response_model=DatasetBuildResponse)
def build_dataset(body: DatasetBuildRequest, db=Depends(get_db)) -> DatasetBuildResponse:
    """Build a local point-in-time training dataset."""
    data_source = None
    if body.source_name:
        data_source = db.get_source_by_name(body.source_name)
        if data_source is None:
            return _response_from_result(
                TrainingDatasetBuildResult(
                    is_valid=False,
                    errors=[
                        TrainingDatasetValidationIssue(
                            code="source_not_found",
                            message=f"DataSource not found: {body.source_name}",
                            field="source_name",
                        )
                    ],
                    entity_df_path=body.entity_df_path,
                    source_path=body.source_path,
                    entity_key=body.entity_key,
                    entity_timestamp_column=body.entity_timestamp_column,
                    source_event_timestamp_column=body.source_event_timestamp_column,
                    feature_columns=body.feature_columns,
                    feature_count=len(body.feature_columns),
                )
            )

    result = build_training_dataset(
        entity_df_path=body.entity_df_path,
        source_path=body.source_path,
        entity_key=body.entity_key,
        entity_timestamp_column=body.entity_timestamp_column,
        source_event_timestamp_column=body.source_event_timestamp_column,
        feature_columns=body.feature_columns,
        output_path=body.output_path,
        data_source=data_source,
    )
    return _response_from_result(result)
