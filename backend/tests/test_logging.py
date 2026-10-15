import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_config import redact
from app.main import create_app


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="spectrace")
    return caplog


def client(**overrides) -> TestClient:
    return TestClient(
        create_app(Settings(_env_file=None, **overrides)), raise_server_exceptions=False
    )


def test_request_line_has_id_route_template_status_and_duration(logs):
    c = client()
    r = c.get("/v1/runs/not-a-real-id")
    line = next(m for m in logs.messages if m.startswith("request "))
    assert f"id={r.headers['x-request-id']}" in line
    assert "path=/v1/runs/{run_id}" in line and "not-a-real-id" not in line
    assert "status=404" in line and "ms=" in line


def test_submitted_content_never_reaches_the_log(logs):
    c = client()
    c.post("/v1/runs", json={"files_a": "SECRET-VALUE-1"})
    c.post("/v1/runs", json={"files_a": {"../SECRET-NAME-2.md": "SECRET-BODY-3"}, "files_b": {}})
    c.get("/v1/runs/SECRET-PATH-4")
    for secret in ("SECRET-VALUE-1", "SECRET-NAME-2", "SECRET-BODY-3", "SECRET-PATH-4"):
        assert secret not in logs.text


def test_rejection_logs_the_error_code_only(logs):
    client().post("/v1/runs", json={"files_a": {"../x.md": "# a"}, "files_b": {}})
    assert any("code=unsupported_input" in m for m in logs.messages)
    assert "unsafe file path" not in logs.text


def test_unhandled_error_returns_generic_500_and_logs_class_only(logs, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("password=hunter2 INSERT ... VALUES ('SECRET-DOC')")

    monkeypatch.setattr("app.api.v1.runs.analyze", boom)
    r = client().post("/v1/runs", json={"files_a": {}, "files_b": {}})
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "internal error"}}
    assert "x-request-id" in r.headers
    assert "error=RuntimeError" in logs.text
    assert "hunter2" not in logs.text and "SECRET-DOC" not in logs.text
    assert "hunter2" not in r.text


def test_redact_masks_url_credentials_and_secret_pairs():
    url = "connect postgresql+psycopg://postgres.abc:p%40ss@host:5432/db failed"
    assert redact(url) == "connect postgresql+psycopg://***@host:5432/db failed"
    assert redact("token=abc123 and Authorization: Bearer") == "token=*** and Authorization: ***"
    assert "p%40ss" not in redact(url)


def test_redact_neutralizes_forged_log_lines():
    assert "\n" not in redact("a\nERROR forged\r\nline")


def test_filter_redacts_even_if_a_secret_is_logged_by_mistake(logs):
    logging.getLogger("spectrace").info("dsn %s", "postgresql://u:topsecret@h/db")
    assert "topsecret" not in logs.text
