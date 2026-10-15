from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityKind(StrEnum):
    ENDPOINT = "endpoint"
    SCHEMA = "schema"
    SECTION = "section"
    REQUIREMENT = "requirement"
    EXAMPLE = "example"


class Label(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class Classification(StrEnum):
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


class RawRefKind(StrEnum):
    ENDPOINT = "endpoint"
    ANCHOR = "anchor"
    REQUIREMENT = "requirement"
    IDENTIFIER = "identifier"
    JSON_KEYS = "json_keys"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Location(_Frozen):
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class Entity(_Frozen):
    key: str
    kind: EntityKind
    name: str
    location: Location
    content_hash: str
    text: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class Edge(_Frozen):
    """`source_key` depends on `target_key`."""

    source_key: str
    target_key: str
    relation: str
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Location
    reason: str


class RawRef(_Frozen):
    source_key: str
    kind: RawRefKind
    value: str
    location: Location


class ParseResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    raw_refs: list[RawRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Change(_Frozen):
    key: str
    kind: EntityKind
    change_type: ChangeType
    classification: Classification
    reasons: list[str]
    source_diff: str
    before: Location | None = None
    after: Location | None = None


class Impact(_Frozen):
    change_key: str
    impacted_key: str
    certainty: Label
    confidence: float
    path: list[Edge]
    confirmed_breaking: bool
    summary: str
