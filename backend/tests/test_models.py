import pytest
from pydantic import ValidationError

from app.core.limits import Limits
from app.core.models import Entity, EntityKind, Location


def test_location_requires_positive_lines():
    with pytest.raises(ValidationError):
        Location(file="a.md", line_start=0, line_end=1)


def test_entity_is_frozen():
    e = Entity(
        key="schema:Pet",
        kind=EntityKind.SCHEMA,
        name="Pet",
        location=Location(file="a.yaml", line_start=1, line_end=2),
        content_hash="h",
        text="t",
    )
    with pytest.raises(ValidationError):
        e.key = "x"


def test_limits_defaults_are_bounded():
    limits = Limits()
    assert limits.max_file_bytes <= limits.max_total_bytes
    assert limits.max_yaml_depth > 0
