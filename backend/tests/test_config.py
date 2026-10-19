import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('["https://a.vercel.app"]', ["https://a.vercel.app"]),
        ("https://a.vercel.app", ["https://a.vercel.app"]),
        ("https://a.vercel.app/", ["https://a.vercel.app"]),
        ("https://a.app, http://localhost:3000", ["https://a.app", "http://localhost:3000"]),
        ('"https://a.app"', ["https://a.app"]),
        ("[https://a.app]", ["https://a.app"]),
        ("", ["http://localhost:3000"]),
    ],
)
def test_cors_origins_accept_json_or_plain_text(monkeypatch, raw, expected):
    monkeypatch.setenv("SPECTRACE_CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origins == expected


def test_cors_origins_default_without_setting(monkeypatch):
    monkeypatch.delenv("SPECTRACE_CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ["http://localhost:3000"]
