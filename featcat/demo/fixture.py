"""Pydantic schemas for the demo-catalog.json fixture format."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from pathlib import Path


class DemoSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    path: str
    description: str | None = None


class DemoFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    column_name: str
    dtype: str
    description: str | None = None
    owner: str | None = None
    extra_tags: list[str] = Field(default_factory=list)


class DemoDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_name: str
    short_description: str
    long_description: str
    expected_range: str
    potential_issues: str
    suggested_tags: list[str] = Field(default_factory=list)


class DemoGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None
    feature_names: list[str] = Field(default_factory=list)


class DemoLineageEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child: str
    parent: str
    transformation: str = ""


class DemoFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    version: str
    sources: Annotated[list[DemoSource], Field(min_length=1)]
    features: list[DemoFeature]
    docs: list[DemoDoc] = Field(default_factory=list)
    groups: list[DemoGroup] = Field(default_factory=list)
    lineage_edges: list[DemoLineageEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_feature_sources_known(self) -> DemoFixture:
        known = {s.name for s in self.sources}
        for f in self.features:
            if "." not in f.name:
                raise ValueError(f"Feature name must be 'source.column': {f.name!r}")
            src = f.name.split(".", 1)[0]
            if src not in known:
                raise ValueError(
                    f"Feature {f.name!r} references unknown source {src!r}; add it to `sources` or fix the prefix."
                )
        return self


def load_demo_fixture(path: Path) -> DemoFixture:
    """Read a demo-catalog JSON file and validate it.

    Raises ``ValueError`` on read, parse, or schema failure. The CLI
    translates this into a clear console message + ``typer.Exit(1)``.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"Could not read fixture {path}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    try:
        return DemoFixture.model_validate(data)
    except Exception as e:
        raise ValueError(f"Fixture schema validation failed: {e}") from e
