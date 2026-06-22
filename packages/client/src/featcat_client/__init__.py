"""featcat-client — Python SDK for the featcat feature catalog server.

Quickstart:

    from featcat_client import FeatCatClient

    client = FeatCatClient(base_url="http://localhost:8000")
    feat = client.get_feature("user_behavior.session_count_30d")
    df = client.read_feature("user_behavior.session_count_30d")

See README for full API.
"""

from __future__ import annotations

# Version is defined first (before sub-module imports) so client.py can import
# it via ``from . import __version__`` without triggering a circular import.
__version__ = "0.1.0"

from .client import FeatCatClient
from .exceptions import (
    BusinessMetricNotFound,
    ConnectionError,
    EntityNotFound,
    EntityRelationshipNotFound,
    FeatCatError,
    FeatureNotFound,
    FeatureSetNotFound,
    FeatureViewNotFound,
    GroupNotFound,
    ServerError,
    SourceNotFound,
)
from .models import (
    BulkScanRequest,
    BulkScanResult,
    BusinessMetric,
    BusinessMetricCreateRequest,
    BusinessMetricCsvImportError,
    BusinessMetricCsvImportResult,
    DataSource,
    DataSourceCreateRequest,
    DataSourceUpdateRequest,
    Entity,
    EntityCreateRequest,
    EntityRelationship,
    EntityRelationshipCreateRequest,
    Feature,
    FeatureGroup,
    FeatureGroupDetail,
    FeatureSet,
    FeatureSetCreateRequest,
    FeatureUsage,
    FeatureView,
    FeatureViewCreateRequest,
    FlowResult,
    MaterializationAudit,
    MaterializationIssue,
    MaterializationResult,
    MaterializationSchedule,
    MaterializationScheduleCreateRequest,
    MaterializationScheduleRunResult,
    MaterializationScheduleUpdateRequest,
    OnlineFeatureReadMetadata,
    OnlineFeatureReadResult,
    OnlineFeatureReadRow,
    OnlineFeatureWrite,
    OnlineFeatureWriteError,
    OnlineFeatureWriteResult,
    SourceScanResult,
    TrainingDatasetBuildAudit,
    TrainingDatasetBuildResult,
    TrainingDatasetIssue,
)

__all__ = [
    "ConnectionError",
    "BusinessMetric",
    "BusinessMetricCsvImportError",
    "BusinessMetricCsvImportResult",
    "BusinessMetricCreateRequest",
    "BusinessMetricNotFound",
    "DataSource",
    "DataSourceCreateRequest",
    "DataSourceUpdateRequest",
    "FeatCatClient",
    "FeatCatError",
    "Entity",
    "EntityCreateRequest",
    "EntityNotFound",
    "EntityRelationship",
    "EntityRelationshipCreateRequest",
    "EntityRelationshipNotFound",
    "FeatureSet",
    "FeatureSetCreateRequest",
    "FeatureSetNotFound",
    "FeatureView",
    "FeatureViewCreateRequest",
    "FeatureViewNotFound",
    "Feature",
    "FlowResult",
    "SourceNotFound",
    "FeatureGroup",
    "FeatureGroupDetail",
    "FeatureNotFound",
    "BulkScanRequest",
    "BulkScanResult",
    "SourceScanResult",
    "FeatureUsage",
    "GroupNotFound",
    "MaterializationIssue",
    "MaterializationAudit",
    "MaterializationResult",
    "MaterializationSchedule",
    "MaterializationScheduleCreateRequest",
    "MaterializationScheduleRunResult",
    "MaterializationScheduleUpdateRequest",
    "OnlineFeatureReadMetadata",
    "OnlineFeatureReadResult",
    "OnlineFeatureReadRow",
    "OnlineFeatureWrite",
    "OnlineFeatureWriteError",
    "OnlineFeatureWriteResult",
    "ServerError",
    "TrainingDatasetBuildAudit",
    "TrainingDatasetBuildResult",
    "TrainingDatasetIssue",
    "__version__",
]
