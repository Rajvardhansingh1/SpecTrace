from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(**overrides) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, **overrides)))


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
