"""Thin Python SDK for registering and querying catalog metadata."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from .catalog.factory import get_backend
from .catalog.models import BusinessMetric, DataSource, Entity, EntityRelationship, Feature, FeatureSet, FeatureView


class FeatcatSDK(AbstractContextManager["FeatcatSDK"]):
    """Convenience wrapper over the catalog backend.

    The SDK intentionally stays thin: it mirrors the registry objects and
    delegates storage/query behavior to the configured backend, so callers
    can use the same API in local or remote mode.
    """

    def __init__(self) -> None:
        self._db = get_backend()

    def __enter__(self) -> FeatcatSDK:
        self._db.init_db()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, D401
        self._db.close()
        return None

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _coerce(model_cls: type[Any], value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value
        return model_cls.model_validate(value)

    # --- Data sources ---

    def register_data_source(self, source: DataSource | dict[str, Any]) -> DataSource:
        return self._db.add_source(self._coerce(DataSource, source))

    def list_data_sources(self) -> list[DataSource]:
        return self._db.list_sources()

    def get_data_source(self, name: str) -> DataSource | None:
        return self._db.get_source_by_name(name)

    # --- Entities ---

    def register_entity(self, entity: Entity | dict[str, Any]) -> Entity:
        return self._db.upsert_entity(self._coerce(Entity, entity))

    def list_entities(self) -> list[Entity]:
        return self._db.list_entities()

    def get_entity(self, name: str) -> Entity | None:
        return self._db.get_entity_by_name(name)

    # --- Relationships ---

    def register_relationship(self, relationship: EntityRelationship | dict[str, Any]) -> EntityRelationship:
        return self._db.upsert_entity_relationship(self._coerce(EntityRelationship, relationship))

    def list_relationships(
        self,
        *,
        left_entity: str | None = None,
        right_entity: str | None = None,
        relation_type: str | None = None,
    ) -> list[EntityRelationship]:
        return self._db.list_entity_relationships(
            left_entity=left_entity,
            right_entity=right_entity,
            relation_type=relation_type,
        )

    def get_relationship(self, name: str) -> EntityRelationship | None:
        return self._db.get_entity_relationship_by_name(name)

    # --- Feature views / sets ---

    def register_feature_view(self, feature_view: FeatureView | dict[str, Any]) -> FeatureView:
        return self._db.upsert_feature_view(self._coerce(FeatureView, feature_view))

    def list_feature_views(self, *, entity: str | None = None, owner: str | None = None) -> list[FeatureView]:
        return self._db.list_feature_views(entity=entity, owner=owner)

    def get_feature_view(self, name: str) -> FeatureView | None:
        return self._db.get_feature_view_by_name(name)

    def register_feature_set(self, feature_set: FeatureSet | dict[str, Any]) -> FeatureSet:
        return self._db.upsert_feature_set(self._coerce(FeatureSet, feature_set))

    def list_feature_sets(self, *, target_entity: str | None = None, owner: str | None = None) -> list[FeatureSet]:
        return self._db.list_feature_sets(target_entity=target_entity, owner=owner)

    def get_feature_set(self, name: str) -> FeatureSet | None:
        return self._db.get_feature_set_by_name(name)

    # --- Business metrics ---

    def register_business_metric(self, metric: BusinessMetric | dict[str, Any]) -> BusinessMetric:
        return self._db.upsert_business_metric(self._coerce(BusinessMetric, metric))

    def list_business_metrics(
        self,
        *,
        metric_domain: str | None = None,
        lifecycle_stage: str | None = None,
        metric_level: str | None = None,
        owner: str | None = None,
    ) -> list[BusinessMetric]:
        return self._db.list_business_metrics(
            metric_domain=metric_domain,
            lifecycle_stage=lifecycle_stage,
            metric_level=metric_level,
            owner=owner,
        )

    def get_business_metric(self, name: str) -> BusinessMetric | None:
        return self._db.get_business_metric_by_name(name)

    # --- Features ---

    def register_feature(self, feature: Feature | dict[str, Any]) -> Feature:
        return self._db.upsert_feature(self._coerce(Feature, feature))

    def list_features(self, **kwargs: Any) -> list[Feature]:
        return self._db.list_features(**kwargs)

    def get_feature(self, name: str) -> Feature | None:
        return self._db.get_feature_by_name(name)
