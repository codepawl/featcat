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
    ConnectionError,
    FeatCatError,
    FeatureNotFound,
    GroupNotFound,
    ServerError,
)
from .models import (
    DataSource,
    Feature,
    FeatureGroup,
    FeatureGroupDetail,
    FeatureUsage,
    OnlineFeatureReadMetadata,
    OnlineFeatureReadResult,
    OnlineFeatureReadRow,
    OnlineFeatureWrite,
    OnlineFeatureWriteError,
    OnlineFeatureWriteResult,
    TrainingDatasetBuildAudit,
    TrainingDatasetBuildResult,
    TrainingDatasetIssue,
)

__all__ = [
    "ConnectionError",
    "DataSource",
    "FeatCatClient",
    "FeatCatError",
    "Feature",
    "FeatureGroup",
    "FeatureGroupDetail",
    "FeatureNotFound",
    "FeatureUsage",
    "GroupNotFound",
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
