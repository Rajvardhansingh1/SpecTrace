from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ParseError
from app.main import create_app


def make_client(**overrides):
    # _env_file=None: a developer's local .env must not change test outcomes.
    app = create_app(Settings(_env_file=None, **overrides))

    @app.get("/boom")
    def boom():
        raise ParseError("bad input")

    return TestClient(app)


def test_health_ok():
    r = make_client().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_spectrace_error_uses_stable_envelope():
    r = make_client().get("/boom")
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "parse_error", "message": "bad input"}}


def test_cors_allows_configured_origin_only():
    client = make_client(cors_origins=["http://localhost:3000"])
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_plain_postgres_urls_use_the_psycopg3_driver():
    for plain in ("postgresql://u:p@h:5432/db", "postgres://u:p@h:5432/db"):
        url = Settings(_env_file=None, database_url=plain).database_url
        assert url == "postgresql+psycopg://u:p@h:5432/db"
    explicit = "postgresql+psycopg://u:p@h/db"
    assert Settings(_env_file=None, database_url=explicit).database_url == explicit


def test_plain_postgres_urls_use_the_psycopg3_driver():
    for plain in ("postgresql://u:p@h:5432/db", "postgres://u:p@h:5432/db"):
        url = Settings(_env_file=None, database_url=plain).database_url
        assert url == "postgresql+psycopg://u:p@h:5432/db"
    explicit = "postgresql+psycopg://u:p@h/db"
    assert Settings(_env_file=None, database_url=explicit).database_url == explicit
