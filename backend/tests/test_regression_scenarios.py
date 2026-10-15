"""Regression tests for Testing.md section 3, scenarios 1-4.

Scenario 5 (private repositories are not accessed without authorization) belongs to the
GitHub source adapter and is covered in Plan 5.
"""

from app.core.models import Classification, Label
from app.core.pipeline import analyze, answer_question


def test_scenario_1_breaking_change_produces_expected_change_record(v1, v2):
    result = analyze(v1, v2)
    change = result.changes[0]
    assert (change.key, change.classification) == ("schema:Pet", Classification.BREAKING)
    assert change.before.line_start == change.after.line_start
    assert change.source_diff


def test_scenario_2_known_downstream_references_are_cited_correctly(v1, v2):
    result = analyze(v1, v2)
    files = v2
    checked = 0
    for impact in result.impacts["schema:Pet"]:
        for edge in impact.path:
            line = files[edge.evidence.file].splitlines()[edge.evidence.line_start - 1]
            if edge.relation == "uses_schema":
                assert "$ref" in line and edge.target_key.split(":", 1)[1] in line
            elif edge.relation == "mentions_endpoint":
                method, path = edge.target_key.split(":", 1)[1].split(" ", 1)
                assert method in line and path in line
            elif edge.relation == "mentions_name":
                assert f"`{edge.target_key.split(':', 1)[1]}`" in line
            checked += 1
    assert checked >= 7


def test_scenario_3_unrelated_components_are_never_confirmed_impacts(v1, v2):
    confirmed = {
        i.impacted_key
        for i in analyze(v1, v2).impacts["schema:Pet"]
        if i.certainty is Label.CONFIRMED
    }
    assert not confirmed & {"endpoint:GET /owners", "schema:Owner", "section:docs/guide.md#owners"}


def test_scenario_4_ambiguous_or_unsupported_questions_are_uncertain(v1, v2):
    result = analyze(v1, v2)
    assert answer_question(result, "Will the mobile app crash?").status == "uncertain"


def test_speculative_impact_is_never_presented_as_confirmed_breaking(v1, v2):
    for impacts in analyze(v1, v2).impacts.values():
        for imp in impacts:
            if imp.certainty is Label.INFERRED:
                assert not imp.confirmed_breaking
