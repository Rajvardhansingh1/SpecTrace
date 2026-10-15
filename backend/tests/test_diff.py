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


def _edit(text: str, old: str, new: str) -> dict[str, str]:
    assert old in text
    return {"openapi.yaml": text.replace(old, new, 1)}


def _classify(a: dict[str, str], b: dict[str, str]):
    return only(diff_graphs(graph_of(a), graph_of(b)))


def test_parameter_type_change_is_breaking():
    a = api(PARAM.format(name="q", required="false"))
    b = _edit(a["openapi.yaml"], "            type: string\n", "            type: integer\n")
    c = _classify(a, b)
    assert c.classification is Classification.BREAKING
    assert "parameter q type changed string -> integer" in c.reasons


def test_parameter_becoming_required_is_breaking():
    a = api(PARAM.format(name="q", required="false"))
    b = _edit(a["openapi.yaml"], "required: false", "required: true")
    c = _classify(a, b)
    assert c.classification is Classification.BREAKING
    assert "parameter q became required" in c.reasons


def test_parameter_removed_is_unknown():
    a, b = api(PARAM.format(name="q", required="false")), api()
    c = _classify(a, b)
    assert c.classification is Classification.UNKNOWN
    assert "parameter q (query) removed" in c.reasons


BODY = """      requestBody:
        required: {required}
        content:
          application/json:
            schema:
              {schema}
"""


def _with_body(required: str, schema: str) -> dict[str, str]:
    base = api()["openapi.yaml"]
    return _edit(
        base,
        "      responses:\n",
        BODY.format(required=required, schema=schema) + "      responses:\n",
    )


def test_request_body_becoming_required_is_breaking():
    a = _with_body("false", "type: string")
    b = _edit(a["openapi.yaml"], "required: false", "required: true")
    c = _classify(a, b)
    assert c.classification is Classification.BREAKING
    assert "request body became required" in c.reasons


def test_request_body_added_as_required_is_breaking():
    c = _classify(api(), _with_body("true", "type: string"))
    assert c.classification is Classification.BREAKING


def test_request_body_schema_change_is_breaking():
    a = _with_body("false", "type: string")
    b = _edit(a["openapi.yaml"], "              type: string\n", "              type: integer\n")
    c = _classify(a, b)
    assert c.classification is Classification.BREAKING
    assert "request body schema changed string -> integer" in c.reasons


def test_request_body_removed_is_unknown():
    c = _classify(_with_body("false", "type: string"), api())
    assert c.classification is Classification.UNKNOWN
    assert "request body removed" in c.reasons


def test_2xx_response_removed_is_breaking_other_is_unknown():
    two = api()["openapi.yaml"].replace(
        '        "200":\n          description: ok\n',
        '        "200":\n          description: ok\n        "404":\n          description: nope\n',
    )
    only200 = api()
    assert _classify({"openapi.yaml": two}, only200).classification is Classification.UNKNOWN
    gone = _edit(
        only200["openapi.yaml"],
        '        "200":\n          description: ok\n',
        '        "204":\n          description: ok\n',
    )
    c = _classify(only200, gone)
    assert c.classification is Classification.BREAKING
    assert "response 200 removed" in c.reasons


def test_response_added_is_non_breaking():
    b = _edit(
        api()["openapi.yaml"],
        '        "200":\n          description: ok\n',
        '        "200":\n          description: ok\n        "404":\n          description: nope\n',
    )
    assert _classify(api(), b).classification is Classification.NON_BREAKING


def test_response_schema_change_is_breaking():
    with_schema = api()["openapi.yaml"].replace(
        "          description: ok\n",
        "          description: ok\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        "                type: string\n",
        1,
    )
    a = {"openapi.yaml": with_schema}
    b = _edit(with_schema, "                type: string\n", "                type: integer\n")
    c = _classify(a, b)
    assert c.classification is Classification.BREAKING
    assert "response 200 schema changed string -> integer" in c.reasons


def test_schema_property_removed_and_required_changes():
    base = api()["openapi.yaml"]
    removed = _edit(
        base,
        "      required: [id]\n      properties:\n        id:\n          type: string\n",
        "      required: []\n      properties: {}\n",
    )
    c = _classify({"openapi.yaml": base}, removed)
    assert c.classification is Classification.BREAKING
    assert "property id removed" in c.reasons


def test_schema_required_added_property_is_breaking():
    base = api()["openapi.yaml"]
    b = _edit(base, "      required: [id]\n", "      required: [id, note]\n").copy()
    b["openapi.yaml"] = b["openapi.yaml"].replace(
        "        id:\n          type: string\n",
        "        id:\n          type: string\n        note:\n          type: string\n",
    )
    c = _classify({"openapi.yaml": base}, b)
    assert c.classification is Classification.BREAKING
    assert "property note added as required" in c.reasons


def test_schema_type_change_and_requiredness_relaxed():
    base = api()["openapi.yaml"]
    t = _edit(base, "      type: object\n", "      type: array\n")
    assert "schema type changed object -> array" in _classify({"openapi.yaml": base}, t).reasons
    relaxed = _edit(base, "      required: [id]\n", "      required: []\n")
    c = _classify({"openapi.yaml": base}, relaxed)
    assert c.classification is Classification.NON_BREAKING
    assert "property id no longer required" in c.reasons


def test_added_and_removed_requirement_are_unknown_and_example_is_documentation():
    a = {"a.md": "## A\ntext\n"}
    b = {"a.md": "## A\ntext\nREQ-001: Clients MUST retry.\n\n```json\n{}\n```\n"}
    changes = {c.key: c for c in diff_graphs(graph_of(a), graph_of(b))}
    assert changes["requirement:REQ-001"].classification is Classification.UNKNOWN
    assert changes["example:a.md#a:1"].classification is Classification.DOCUMENTATION
    back = {c.key: c for c in diff_graphs(graph_of(b), graph_of(a))}
    assert back["requirement:REQ-001"].change_type is ChangeType.REMOVED
