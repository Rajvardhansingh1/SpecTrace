from fastapi.testclient import TestClient

from app.api.ratelimit import SlidingWindowLimiter
from app.config import Settings
from app.main import create_app


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def client(**overrides) -> TestClient:
    return TestClient(
        create_app(Settings(_env_file=None, **overrides)),
        headers={"X-Owner-Token": "test-owner-token-0123456789"},
    )


def test_limiter_blocks_after_limit_and_reports_retry_after():
    clock = FakeClock()
    lim = SlidingWindowLimiter(limit=2, window=60, clock=clock)
    assert lim.check("a") == (True, 0)
    clock.now += 10
    assert lim.check("a") == (True, 0)
    allowed, retry = lim.check("a")
    assert not allowed and 1 <= retry <= 51


def test_limiter_window_slides_and_keys_are_independent():
    clock = FakeClock()
    lim = SlidingWindowLimiter(limit=1, window=60, clock=clock)
    assert lim.check("a")[0] and not lim.check("a")[0]
    assert lim.check("b")[0]
    clock.now += 61
    assert lim.check("a")[0]


def test_limiter_memory_is_bounded():
    lim = SlidingWindowLimiter(limit=5, max_keys=100)
    for i in range(1000):
        assert lim.check(f"ip-{i}")[0]
    assert len(lim._hits) <= 100


def test_heavy_bucket_returns_429_envelope_with_retry_after(v1, v2):
    c = client(rate_limit_heavy_per_minute=2)
    body = {"files_a": v1, "files_b": v2}
    assert c.post("/v1/runs", json=body).status_code == 201
    assert c.post("/v1/runs", json=body).status_code == 201
    r = c.post("/v1/runs", json=body)
    assert r.status_code == 429
    assert r.json() == {"error": {"code": "rate_limited", "message": "too many requests"}}
    assert int(r.headers["retry-after"]) >= 1


def test_reads_use_the_general_bucket_not_the_heavy_one(v1, v2):
    c = client(rate_limit_heavy_per_minute=1, rate_limit_per_minute=5)
    assert c.post("/v1/runs", json={"files_a": v1, "files_b": v2}).status_code == 201
    assert all(c.get("/v1/runs").status_code == 200 for _ in range(5))
    assert c.get("/v1/runs").status_code == 429


def test_health_is_never_limited():
    c = client(rate_limit_per_minute=1)
    assert all(c.get("/health").status_code == 200 for _ in range(10))


def test_limited_response_keeps_cors_header_for_allowed_origin():
    c = client(rate_limit_per_minute=1, cors_origins=["http://localhost:3000"])
    headers = {"Origin": "http://localhost:3000"}
    c.get("/v1/runs", headers=headers)
    r = c.get("/v1/runs", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_forwarded_header_is_ignored_unless_proxy_is_trusted():
    spoof = lambda i: {"X-Forwarded-For": f"10.0.0.{i}"}  # noqa: E731
    untrusted = client(rate_limit_per_minute=2)
    codes = [untrusted.get("/v1/runs", headers=spoof(i)).status_code for i in range(3)]
    assert codes == [200, 200, 429]

    trusted = client(rate_limit_per_minute=2, trust_proxy_headers=True)
    codes = [trusted.get("/v1/runs", headers=spoof(i)).status_code for i in range(3)]
    assert codes == [200, 200, 200]


def test_browsers_may_read_retry_after_and_request_id_across_origins():
    c = client(rate_limit_per_minute=1, cors_origins=["http://localhost:3000"])
    headers = {"Origin": "http://localhost:3000"}
    c.get("/v1/runs", headers=headers)
    limited = c.get("/v1/runs", headers=headers)
    assert limited.status_code == 429
    exposed = limited.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed and "x-request-id" in exposed
