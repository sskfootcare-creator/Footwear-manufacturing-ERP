import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient

from rate_limiter import RateLimiter, rate_limit_dependency, _is_test_mode
from routes.auth import auth_router
from routes.workers import workers_router


def test_is_test_mode_logic(monkeypatch):
    # 1. In production, _is_test_mode is always False regardless of TESTING or RATE_LIMIT_DISABLED
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    assert _is_test_mode() is False

    # 2. Case insensitive production
    monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
    assert _is_test_mode() is False

    # 3. In test environment
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("TESTING", raising=False)
    assert _is_test_mode() is True

    # 4. In development environment
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert _is_test_mode() is True

    # 5. When TESTING=1 is set
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("TESTING", "1")
    assert _is_test_mode() is True


def test_production_ignores_test_ip_header(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    app = FastAPI()

    @app.get("/test-endpoint")
    async def endpoint(request: Request):
        limiter.check(request)
        return {"ok": True}

    client = TestClient(app)

    # 1st request with spoofed test IP "1.1.1.1"
    r1 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "1.1.1.1"})
    assert r1.status_code == 200

    # 2nd request with different spoofed test IP "2.2.2.2" from same client (testclient default host)
    r2 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "2.2.2.2"})
    assert r2.status_code == 200

    # 3rd request with another spoofed test IP "3.3.3.3" -> In production, it MUST be rate limited (429)
    # because real client IP (testclient host) exceeded 2 requests!
    r3 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "3.3.3.3"})
    assert r3.status_code == 429
    assert "Too many request requests" in r3.json()["detail"]


def test_test_mode_honors_test_ip_header(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TESTING", "1")
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    app = FastAPI()

    @app.get("/test-endpoint")
    async def endpoint(request: Request):
        limiter.check(request)
        return {"ok": True}

    client = TestClient(app)

    # In test mode, different test IPs get separate buckets
    for i in range(5):
        r = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": f"10.0.0.{i}"})
        assert r.status_code == 200

    # But exceeding 2 requests on the same test IP still blocks
    r_same1 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "10.0.0.99"})
    assert r_same1.status_code == 200
    r_same2 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "10.0.0.99"})
    assert r_same2.status_code == 200
    r_same3 = client.get("/test-endpoint", headers={"x-test-rate-limit-client-ip": "10.0.0.99"})
    assert r_same3.status_code == 429


def test_production_ignores_test_window_header(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    app = FastAPI()

    @app.get("/test-endpoint")
    async def endpoint(request: Request):
        limiter.check(request)
        return {"ok": True}

    client = TestClient(app)

    # Try to spoof a 1-second window in production
    r1 = client.get("/test-endpoint", headers={"x-test-rate-limit-window": "1"})
    assert r1.status_code == 200
    r2 = client.get("/test-endpoint", headers={"x-test-rate-limit-window": "1"})
    assert r2.status_code == 200
    r3 = client.get("/test-endpoint", headers={"x-test-rate-limit-window": "1"})
    assert r3.status_code == 429
    # Retry-After should be relative to 60s, not 1s
    retry_after = int(r3.headers.get("Retry-After", "0"))
    assert retry_after > 10


def test_login_rate_limiting_production_ignores_test_ip(monkeypatch):
    """Confirm /auth/login ignores x-test-rate-limit-client-ip when ENVIRONMENT=production."""
    from unittest.mock import AsyncMock
    import server

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TESTING", raising=False)
    server._login_failures.clear()

    mock_db = MagicMock()
    mock_db.users = MagicMock()
    # Mock find_one returning None (invalid user/password)
    mock_db.users.find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(server, "db", mock_db)
    monkeypatch.setattr(server, "redis_client", None)

    app = FastAPI()
    app.include_router(auth_router)
    client = TestClient(app)

    # In production, each failed login increments failures for the real client IP (testclient host),
    # even if each request rotates the spoofed x-test-rate-limit-client-ip header.
    for i in range(5):
        r = client.post(
            "/api/auth/login",
            json={"email": "victim@sskfootcare.com", "password": "WrongPassword"},
            headers={"x-test-rate-limit-client-ip": f"10.0.0.{i}"},
        )
        assert r.status_code == 401, f"Attempt {i+1} got {r.status_code}"

    # 6th attempt with another new test IP must be 429 because real client IP is blocked!
    r6 = client.post(
        "/api/auth/login",
        json={"email": "victim@sskfootcare.com", "password": "WrongPassword"},
        headers={"x-test-rate-limit-client-ip": "10.0.0.99"},
    )
    assert r6.status_code == 429
    assert "Too many failed login attempts" in r6.json()["detail"]

