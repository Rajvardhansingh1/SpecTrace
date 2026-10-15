from app.core.limits import Limits
from app.core.models import EntityKind, RawRefKind
from app.core.parsers.markdown import parse_markdown

LIMITS = Limits()


def parse(v1):
    return parse_markdown("docs/guide.md", v1["docs/guide.md"], LIMITS)


def refs_of(result, key):
    return {(r.kind, r.value) for r in result.raw_refs if r.source_key == key}


def test_extracts_sections_requirement_and_example(v1):
    keys = {e.key for e in parse(v1).entities}
    assert keys == {
        "section:docs/guide.md#petstore-guide",
        "section:docs/guide.md#listing-pets",
        "section:docs/guide.md#fetching-a-pet",
        "section:docs/guide.md#owners",
        "requirement:REQ-001",
        "example:docs/guide.md#fetching-a-pet:1",
    }


def test_locations(v1):
    ents = {e.key: e for e in parse(v1).entities}
    req = ents["requirement:REQ-001"]
    assert (req.location.line_start, req.location.line_end) == (9, 9)
    ex = ents["example:docs/guide.md#fetching-a-pet:1"]
    assert (ex.location.line_start, ex.location.line_end) == (11, 13)
    assert ex.attrs["language"] == "json"


def test_section_text_excludes_requirement_and_example(v1):
    sec = {e.key: e for e in parse(v1).entities}["section:docs/guide.md#fetching-a-pet"]
    assert "REQ-001" not in sec.text
    assert '"id"' not in sec.text
    assert "GET /pets/{petId}" in sec.text


def test_raw_references(v1):
    result = parse(v1)
    assert refs_of(result, "section:docs/guide.md#listing-pets") == {
        (RawRefKind.ENDPOINT, "GET /pets"),
        (RawRefKind.IDENTIFIER, "Pet"),
    }
    assert (RawRefKind.ENDPOINT, "GET /pets/{petId}") in refs_of(
        result, "section:docs/guide.md#fetching-a-pet"
    )
    assert refs_of(result, "requirement:REQ-001") == {(RawRefKind.IDENTIFIER, "Pet")}
    assert refs_of(result, "example:docs/guide.md#fetching-a-pet:1") == {
        (RawRefKind.JSON_KEYS, "id,name,tag")
    }


def test_headings_inside_fences_are_ignored():
    text = "# Title\n\n```\n# not a heading\n```\n"
    keys = {e.key for e in parse_markdown("a.md", text, LIMITS).entities}
    assert keys == {"section:a.md#title", "example:a.md#title:1"}


def test_duplicate_headings_get_unique_slugs():
    text = "## Setup\none\n\n## Setup\ntwo\n"
    keys = {e.key for e in parse_markdown("a.md", text, LIMITS).entities}
    assert keys == {"section:a.md#setup", "section:a.md#setup-1"}


def test_rfc2119_line_without_id_becomes_requirement():
    text = "## Auth\nThe server MUST reject unsigned tokens.\n"
    ents = parse_markdown("a.md", text, LIMITS).entities
    req = next(e for e in ents if e.kind is EntityKind.REQUIREMENT)
    assert req.key == "requirement:a.md#auth:1"


def test_anchor_and_requirement_mentions():
    text = "## A\nSee [b](#b) and REQ-002.\n\n## B\nbody\n"
    result = parse_markdown("a.md", text, LIMITS)
    assert refs_of(result, "section:a.md#a") == {
        (RawRefKind.ANCHOR, "b"),
        (RawRefKind.REQUIREMENT, "REQ-002"),
    }


def test_whitespace_only_change_keeps_hash():
    a = parse_markdown("a.md", "## A\nhello   world\n", LIMITS).entities[0].content_hash
    b = parse_markdown("a.md", "## A\nhello world\n", LIMITS).entities[0].content_hash
    assert a == b
