from helpers import graph_of

from app.core.diff import diff_graphs
from app.core.impact import find_impacts
from app.core.models import Label


def impacts_for(a_files, b_files, key, **kw):
    ga, gb = graph_of(a_files), graph_of(b_files)
    change = next(c for c in diff_graphs(ga, gb) if c.key == key)
    return find_impacts(change, ga.edges, gb.edges, **kw)


def by_label(impacts, label):
    return {i.impacted_key for i in impacts if i.certainty is label}


def test_pet_change_impact_sets(v1, v2):
    impacts = impacts_for(v1, v2, "schema:Pet")
    assert by_label(impacts, Label.CONFIRMED) == {
        "endpoint:GET /pets",
        "endpoint:POST /pets",
        "endpoint:GET /pets/{petId}",
        "section:docs/guide.md#listing-pets",
        "section:docs/guide.md#fetching-a-pet",
    }
    assert by_label(impacts, Label.INFERRED) == {
        "requirement:REQ-001",
        "example:docs/guide.md#fetching-a-pet:1",
    }


def test_unrelated_entities_are_not_reported(v1, v2):
    impacted = {i.impacted_key for i in impacts_for(v1, v2, "schema:Pet")}
    assert impacted.isdisjoint(
        {"endpoint:GET /owners", "schema:Owner", "schema:NewPet", "section:docs/guide.md#owners"}
    )


def test_confirmed_path_carries_line_evidence(v1, v2):
    imp = next(
        i
        for i in impacts_for(v1, v2, "schema:Pet")
        if i.impacted_key == "section:docs/guide.md#listing-pets"
    )
    assert [e.target_key for e in imp.path] == ["schema:Pet", "endpoint:GET /pets"]
    assert all(e.label is Label.CONFIRMED for e in imp.path)
    assert all(e.evidence.line_start >= 1 for e in imp.path)
    assert imp.confidence == 1.0


def test_confirmed_breaking_requires_deterministic_rule_and_confirmed_path(v1, v2):
    for imp in impacts_for(v1, v2, "schema:Pet"):
        assert imp.confirmed_breaking == (imp.certainty is Label.CONFIRMED)
        if imp.certainty is Label.INFERRED:
            assert imp.confirmed_breaking is False


def test_inferred_confidence_is_edge_product(v1, v2):
    by_key = {i.impacted_key: i for i in impacts_for(v1, v2, "schema:Pet")}
    assert by_key["requirement:REQ-001"].confidence == 0.8
    assert by_key["example:docs/guide.md#fetching-a-pet:1"].confidence == 0.6


def test_depth_limit_downgrades_to_inferred_direct_edge(v1, v2):
    imp = next(
        i
        for i in impacts_for(v1, v2, "schema:Pet", max_depth=1)
        if i.impacted_key == "section:docs/guide.md#listing-pets"
    )
    assert imp.certainty is Label.INFERRED


def test_removed_endpoint_impacts_use_edges_from_old_version(v1):
    lines = v1["openapi.yaml"].splitlines()
    start = lines.index("  /pets/{petId}:")
    end = lines.index("  /owners:")
    v2 = dict(v1)
    v2["openapi.yaml"] = "\n".join(lines[:start] + lines[end:]) + "\n"
    impacts = impacts_for(v1, v2, "endpoint:GET /pets/{petId}")
    assert "section:docs/guide.md#fetching-a-pet" in by_label(impacts, Label.CONFIRMED)
