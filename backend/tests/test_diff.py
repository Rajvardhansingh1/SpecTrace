from helpers import graph_of

from app.core.diff import diff_graphs
from app.core.models import ChangeType, Classification

API = """openapi: 3.0.0
paths:
  /things:
    get:
      summary: List things
{params}      responses:
        "200":
          description: ok
components:
  schemas:
    Thing:
      type: object
      required: [id]
      properties:
        id:
          type: string
"""

PARAM = """      parameters:
        - name: {name}
          in: query
          required: {required}
          schema:
            type: string
"""


def api(params: str = "", summary: str = "List things") -> dict[str, str]:
    return {"openapi.yaml": API.format(params=params).replace("List things", summary)}


def only(changes):
    assert len(changes) == 1, changes
    return changes[0]


def test_petstore_v1_to_v2_is_one_breaking_schema_change(v1, v2):
    change = only(diff_graphs(graph_of(v1), graph_of(v2)))
    assert change.key == "schema:Pet"
    assert change.change_type is ChangeType.MODIFIED
    assert change.classification is Classification.BREAKING
    assert any("property id type changed string -> integer" in r for r in change.reasons)
    assert "-          type: string" in change.source_diff
    assert "+          type: integer" in change.source_diff


def test_formatting_only_change_is_not_a_change(v1):
    edited = dict(v1)
    edited["openapi.yaml"] = v1["openapi.yaml"].replace(
        "summary: List pets", "summary: List pets  # x"
    )
    assert diff_graphs(graph_of(v1), graph_of(edited)) == []


def test_required_parameter_added_is_breaking():
    a, b = api(), api(PARAM.format(name="q", required="true"))
    c = only(diff_graphs(graph_of(a), graph_of(b)))
    assert c.classification is Classification.BREAKING
    assert "parameter q (query) added as required" in c.reasons


def test_optional_parameter_added_is_non_breaking():
    a, b = api(), api(PARAM.format(name="q", required="false"))
    assert only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.NON_BREAKING


def test_summary_only_change_is_documentation():
    a, b = api(), api(summary="Browse things")
    assert (
        only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.DOCUMENTATION
    )


def test_removed_endpoint_is_breaking():
    b = {"openapi.yaml": "openapi: 3.0.0\npaths: {}\ncomponents:\n  schemas: {}\n"}
    changes = {c.key: c for c in diff_graphs(graph_of(api()), graph_of(b))}
    assert changes["endpoint:GET /things"].change_type is ChangeType.REMOVED
    assert changes["endpoint:GET /things"].classification is Classification.BREAKING


def test_added_schema_property_required_vs_optional():
    base = api()["openapi.yaml"]
    optional = base.replace(
        "          type: string\n",
        "          type: string\n        note:\n          type: string\n",
        1,
    )
    c = only(diff_graphs(graph_of({"openapi.yaml": base}), graph_of({"openapi.yaml": optional})))
    assert c.classification is Classification.NON_BREAKING


def test_requirement_change_is_unknown_not_breaking():
    a = {"a.md": "## A\nREQ-001: Clients MUST retry.\n"}
    b = {"a.md": "## A\nREQ-001: Clients SHOULD retry.\n"}
    c = only(diff_graphs(graph_of(a), graph_of(b)))
    assert c.key == "requirement:REQ-001"
    assert c.classification is Classification.UNKNOWN


def test_prose_change_is_documentation():
    a = {"a.md": "## A\nhello\n"}
    b = {"a.md": "## A\nhello there\n"}
    assert (
        only(diff_graphs(graph_of(a), graph_of(b))).classification is Classification.DOCUMENTATION
    )
