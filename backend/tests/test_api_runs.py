from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(**overrides) -> TestClient:
    return TestClient(
        create_app(Settings(_env_file=None, **overrides)),
        headers={"X-Owner-Token": "test-owner-token-0123456789"},
    )


def payload(files_a, files_b):
    return {"files_a": files_a, "files_b": files_b, "label_a": "v1", "label_b": "v2"}


def test_create_and_fetch_run(v1, v2):
    c = client()
    r = c.post("/v1/runs", json=payload(v1, v2))
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "done" and run["stats"]["changes"] == 1
    got = c.get(f"/v1/runs/{run['id']}").json()
    assert got["result"]["changes"][0]["key"] == "schema:Pet"
    assert got["result"]["changes"][0]["classification"] == "breaking"
    assert [x["id"] for x in c.get("/v1/runs").json()["runs"]] == [run["id"]]


def test_ask_answers_with_evidence_and_abstains(v1, v2):
    c = client()
    rid = c.post("/v1/runs", json=payload(v1, v2)).json()["id"]
    ok = c.post(f"/v1/runs/{rid}/ask", json={"question": "What breaks if Pet changes?"}).json()
    assert ok["status"] == "answered" and ok["impacts"]
    unsure = c.post(f"/v1/runs/{rid}/ask", json={"question": "What about the moon?"}).json()
    assert unsure["status"] == "uncertain" and unsure["impacts"] == []


def test_unknown_run_is_404_envelope():
    r = client().get("/v1/runs/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_invalid_body_does_not_echo_input():
    r = client().post("/v1/runs", json={"files_a": "SECRET-VALUE"})
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "invalid_request", "message": "request body is invalid"}}


def test_unsafe_path_rejected_and_run_marked_failed(v1):
    c = client()
    r = c.post("/v1/runs", json=payload({"../x.md": "# a"}, v1))
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_input"
    runs = c.get("/v1/runs").json()["runs"]
    assert runs[0]["status"] == "failed" and runs[0]["error_code"] == "unsupported_input"


def test_oversized_request_rejected_before_parsing(v1, v2):
    r = client(max_request_bytes=1000).post("/v1/runs", json=payload(v1, v2))
    assert r.status_code == 413 and r.json()["error"]["code"] == "input_too_large"


def test_oversized_file_is_413(v1):
    r = client().post("/v1/runs", json=payload({"a.md": "x" * 1_000_001}, v1))
    assert r.status_code == 413


def _run_id(c, v1, v2):
    return c.post("/v1/runs", json=payload(v1, v2)).json()["id"]


def test_snippet_returns_cited_line_with_context(v1, v2):
    c = client()
    rid = _run_id(c, v1, v2)
    r = c.get(
        f"/v1/runs/{rid}/snippet", params={"version": "b", "file": "docs/guide.md", "line": 4}
    )
    assert r.status_code == 200
    body = r.json()
    assert [x["n"] for x in body["lines"]] == [2, 3, 4, 5, 6]
    assert "GET /pets" in next(x["text"] for x in body["lines"] if x["n"] == 4)


def test_snippet_clamps_at_file_edges_and_honours_context_zero(v1, v2):
    c = client()
    rid = _run_id(c, v1, v2)
    top = c.get(
        f"/v1/runs/{rid}/snippet", params={"version": "a", "file": "docs/guide.md", "line": 1}
    )
    assert [x["n"] for x in top.json()["lines"]] == [1, 2, 3]
    one = c.get(
        f"/v1/runs/{rid}/snippet",
        params={"version": "a", "file": "docs/guide.md", "line": 4, "context": 0},
    )
    assert [x["n"] for x in one.json()["lines"]] == [4]


def test_snippet_rejects_unknown_file_traversal_and_bad_lines(v1, v2):
    c = client()
    rid = _run_id(c, v1, v2)
    base = f"/v1/runs/{rid}/snippet"
    ok = {"version": "b", "line": 1}
    assert c.get(base, params={**ok, "file": "../../etc/passwd"}).status_code == 404
    assert c.get(base, params={**ok, "file": "missing.md"}).status_code == 404
    assert (
        c.get(base, params={"version": "b", "file": "docs/guide.md", "line": 9999}).status_code
        == 404
    )
    assert (
        c.get(base, params={"version": "b", "file": "docs/guide.md", "line": 0}).status_code == 422
    )
    assert (
        c.get(base, params={"version": "c", "file": "docs/guide.md", "line": 1}).status_code == 422
    )
    assert c.get(base, params={**ok, "file": "docs/guide.md", "context": 99}).status_code == 422
    assert c.get("/v1/runs/nope/snippet", params={**ok, "file": "docs/guide.md"}).status_code == 404


def test_timestamps_carry_a_timezone_so_browsers_do_not_read_them_as_local(v1, v2):
    c = client()
    run = c.post("/v1/runs", json=payload(v1, v2)).json()
    for stamp in (run["created_at"], run["finished_at"]):
        assert stamp.endswith("+00:00")
    listed = c.get("/v1/runs").json()["runs"][0]
    assert listed["created_at"].endswith("+00:00")
