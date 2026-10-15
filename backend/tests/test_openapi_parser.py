import pytest

from app.core.limits import Limits
from app.core.models import EntityKind, Label
from app.core.parsers.openapi import parse_openapi
from app.errors import LimitExceeded, ParseError, UnsupportedInput

LIMITS = Limits()


def parse(v1):
    return parse_openapi("openapi.yaml", v1["openapi.yaml"], LIMITS)


def test_extracts_endpoints_and_schemas(v1):
    keys = {e.key for e in parse(v1).entities}
    assert keys == {
        "endpoint:GET /pets",
        "endpoint:POST /pets",
        "endpoint:GET /pets/{petId}",
        "endpoint:GET /owners",
        "schema:Pet",
        "schema:NewPet",
        "schema:Owner",
    }


def test_endpoint_location_points_at_method_line(v1):
    lines = v1["openapi.yaml"].splitlines()
    path_idx = lines.index("  /pets/{petId}:")
    method_line = next(i for i in range(path_idx, len(lines)) if lines[i].strip() == "get:") + 1
    ent = {e.key: e for e in parse(v1).entities}["endpoint:GET /pets/{petId}"]
    assert ent.location.line_start == method_line
    assert ent.text.splitlines()[0].strip() == "get:"


def test_ref_edges_are_confirmed_with_line_evidence(v1):
    result = parse(v1)
    lines = v1["openapi.yaml"].splitlines()
    edge = next(
        e
        for e in result.edges
        if e.source_key == "endpoint:GET /pets" and e.target_key == "schema:Pet"
    )
    assert edge.label is Label.CONFIRMED
    assert edge.confidence == 1.0
    assert "$ref" in lines[edge.evidence.line_start - 1]
    assert "Pet" in lines[edge.evidence.line_start - 1]


def test_endpoint_attrs(v1):
    ent = {e.key: e for e in parse(v1).entities}["endpoint:GET /pets"]
    assert ent.kind is EntityKind.ENDPOINT
    assert ent.attrs["parameters"]["limit:query"] == {
        "name": "limit",
        "in": "query",
        "required": False,
        "type": "integer",
    }
    assert ent.attrs["responses"]["200"] == "array<ref:Pet>"


def test_schema_attrs(v1):
    ent = {e.key: e for e in parse(v1).entities}["schema:Pet"]
    assert ent.attrs["properties"] == {"id": "string", "name": "string", "tag": "string"}
    assert ent.attrs["required"] == ["id", "name"]


def test_hash_ignores_comments_and_formatting(v1):
    changed = v1["openapi.yaml"].replace("summary: Get a pet", "summary: Get a pet   # note")
    a = {e.key: e.content_hash for e in parse(v1).entities}
    b = {e.key: e.content_hash for e in parse_openapi("openapi.yaml", changed, LIMITS).entities}
    assert a == b


def test_rejects_non_openapi_document():
    with pytest.raises(UnsupportedInput):
        parse_openapi("x.yaml", "name: not-openapi\n", LIMITS)


def test_rejects_invalid_yaml():
    with pytest.raises(ParseError):
        parse_openapi("x.yaml", "openapi: [unclosed\n", LIMITS)


def test_rejects_alias_expansion_bomb():
    lines = ["openapi: 3.0.0", "l0: &l0 [" + ", ".join(["x"] * 10) + "]"]
    for i in range(1, 9):
        lines.append(f"l{i}: &l{i} [" + ", ".join([f"*l{i - 1}"] * 10) + "]")
    with pytest.raises(LimitExceeded):
        parse_openapi("bomb.yaml", "\n".join(lines) + "\n", LIMITS)


@pytest.mark.parametrize("depth", [100, 5000])
def test_rejects_deep_nesting(depth):
    text = "openapi: 3.0.0\nx: " + "[" * depth + "]" * depth + "\n"
    with pytest.raises(LimitExceeded):
        parse_openapi("deep.yaml", text, LIMITS)
