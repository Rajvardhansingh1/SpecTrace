import os

import pytest
from fastapi.testclient import TestClient

from app.adapters.store import RunStore, make_engine
from app.config import Settings
from app.main import create_app

URL = os.environ.get("SPECTRACE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="SPECTRACE_TEST_DATABASE_URL not set")


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url=URL)))


@pytest.fixture(autouse=True)
def remove_rows_created_by_the_test():
    """The target may be the hosted project, so every row a test adds is deleted afterwards."""
    store = RunStore(make_engine(URL))
    before = {r.id for r in store.list(limit=1000)}
    yield
    for row in store.list(limit=1000):
        if row.id not in before:
            store.delete(row.id)


def test_run_round_trip_and_survives_a_new_app_instance(v1, v2):
    body = {"files_a": v1, "files_b": v2}
    run = make_client().post("/v1/runs", json=body).json()
    # A fresh app has a fresh engine, standing in for a process restart.
    got = make_client().get(f"/v1/runs/{run['id']}").json()
    assert got["status"] == "done"
    assert got["result"]["changes"][0]["key"] == "schema:Pet"


def test_failed_run_is_persisted_with_error_code(v1):
    c = make_client()
    r = c.post("/v1/runs", json={"files_a": {"../x.md": "# a"}, "files_b": v1})
    assert r.status_code == 415
    assert c.get("/v1/runs").json()["runs"][0]["error_code"] == "unsupported_input"
