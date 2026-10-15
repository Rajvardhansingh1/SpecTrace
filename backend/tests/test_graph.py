from helpers import graph_of

from app.core.graph import build_graph
from app.core.limits import Limits
from app.core.models import Label
from app.core.parsers.markdown import parse_markdown

LIMITS = Limits()


def edge(graph, source, target):
    return next((e for e in graph.edges if e.source_key == source and e.target_key == target), None)


def test_docs_reference_endpoints_with_confirmed_edges(v1):
    g = graph_of(v1)
    e = edge(g, "section:docs/guide.md#listing-pets", "endpoint:GET /pets")
    assert e.label is Label.CONFIRMED and e.confidence == 1.0 and e.relation == "mentions_endpoint"
    assert e.evidence.line_start == 4
    assert edge(g, "section:docs/guide.md#fetching-a-pet", "endpoint:GET /pets/{petId}")


def test_backticked_schema_name_is_inferred(v1):
    g = graph_of(v1)
    e = edge(g, "requirement:REQ-001", "schema:Pet")
    assert e.label is Label.INFERRED and e.confidence == 0.8
    assert edge(g, "section:docs/guide.md#listing-pets", "schema:Pet").label is Label.INFERRED


def test_json_example_matches_only_the_closest_schema(v1):
    g = graph_of(v1)
    key = "example:docs/guide.md#fetching-a-pet:1"
    e = edge(g, key, "schema:Pet")
    assert e.label is Label.INFERRED and e.confidence == 0.6
    assert edge(g, key, "schema:NewPet") is None
    assert edge(g, key, "schema:Owner") is None


def test_unrelated_entities_have_no_edges_to_pet(v1):
    g = graph_of(v1)
    assert edge(g, "section:docs/guide.md#owners", "schema:Pet") is None
    assert edge(g, "endpoint:GET /owners", "schema:Pet") is None


def test_endpoint_mention_ignores_parameter_names():
    api = (
        "openapi: 3.0.0\npaths:\n  /pets/{petId}:\n    get:\n      responses:\n"
        '        "200":\n          description: ok\n'
    )
    md = "## A\nCall `GET /pets/{id}`.\n"
    g = graph_of({"openapi.yaml": api, "a.md": md})
    assert edge(g, "section:a.md#a", "endpoint:GET /pets/{petId}").label is Label.CONFIRMED


def test_unresolved_anchor_warns_without_edge():
    r = parse_markdown("a.md", "## A\nSee [x](#missing).\n", LIMITS)
    g = build_graph([r])
    assert g.edges == []
    assert any("missing" in w for w in g.warnings)


def test_anchor_link_to_existing_section_is_confirmed():
    r = parse_markdown("a.md", "## A\nSee [b](#b).\n\n## B\nbody\n", LIMITS)
    e = edge(build_graph([r]), "section:a.md#a", "section:a.md#b")
    assert e.label is Label.CONFIRMED and e.relation == "links_to"
