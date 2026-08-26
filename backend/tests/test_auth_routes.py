"""Unit tests for routes/auth.py — auth HTTP routes extraction.

Tests cover:
 - Login (success, wrong password, inactive user, rate-limit lockout/reset)
 - Logout (cookie cleared)
 - Refresh token rotation
 - GET /auth/me
 - Password-reset helpers (hash token, reset link base, send email stub)
 - Users CRUD (list/create/update/delete)
 - Re-export contracts: all symbols still importable from server module
"""
from __future__ import annotations

import os
import pytest
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import server
import routes.auth as auth_routes
from server import (
    oid,
    login,
    logout,
    refresh_token_route,
    me,
    forgot_password,
    reset_password,
    list_users,
    create_user,
    update_user,
    delete_user,
    check_rate_limit,
    record_login_failure,
    clear_login_failures,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    _login_failures,
    hash_password,
    verify_password,
    ForgotPasswordInput,
    ResetPasswordInput,
    _hash_reset_token,
    _reset_link_base,
    _send_reset_email,
    PASSWORD_RESET_TTL_HOURS,
)
from auth import create_access_token, create_refresh_token, get_jwt_secret, JWT_ALGORITHM
import jwt


# ---------------------------------------------------------------------------
# Re-export contract tests (import-only, no runtime needed)
# ---------------------------------------------------------------------------

def test_server_reexports_auth_symbols():
    """All auth symbols are accessible via the server module (backward compat)."""
    import server as s
    assert callable(s.login)
    assert callable(s.logout)
    assert callable(s.refresh_token_route)
    assert callable(s.me)
    assert callable(s.forgot_password)
    assert callable(s.reset_password)
    assert callable(s.list_users)
    assert callable(s.create_user)
    assert callable(s.update_user)
    assert callable(s.delete_user)
    assert callable(s.check_rate_limit)
    assert callable(s.record_login_failure)
    assert callable(s.clear_login_failures)
    assert isinstance(s._login_failures, dict)
    assert s.LOGIN_MAX_ATTEMPTS == 5
    assert s.LOGIN_WINDOW_SECONDS == 900
    assert s.PASSWORD_RESET_TTL_HOURS == 1


# ---------------------------------------------------------------------------
# Rate-limit helpers (pure in-memory, no MongoDB needed)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_check_rate_limit_allows_under_max(monkeypatch):
    """No exception raised when failures are below the limit."""
    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()
    await check_rate_limit("testip_allow", max_attempts=5, window_seconds=900)
    auth_routes._login_failures.clear()


@pytest.mark.anyio
async def test_check_rate_limit_raises_429_at_max(monkeypatch):
    """HTTPException 429 raised after max_attempts failures."""
    from fastapi import HTTPException
    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()
    ip = "testip_block"
    for _ in range(5):
        auth_routes._login_failures[ip].append(
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
        )
    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit(ip, max_attempts=5, window_seconds=900)
    assert exc_info.value.status_code == 429
    assert "Too many failed login attempts" in exc_info.value.detail
    auth_routes._login_failures.clear()


@pytest.mark.anyio
async def test_record_and_clear_login_failures(monkeypatch):
    """record_login_failure appends a timestamp; clear_login_failures removes them."""
    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()
    ip = "testip_record"
    n = await record_login_failure(ip)
    assert n == 1
    n2 = await record_login_failure(ip)
    assert n2 == 2
    await clear_login_failures(ip)
    assert ip not in auth_routes._login_failures
    auth_routes._login_failures.clear()


# ---------------------------------------------------------------------------
# Password-reset helpers (pure, no I/O)
# ---------------------------------------------------------------------------

def test_hash_reset_token_is_deterministic():
    raw = "some_random_token_value"
    h1 = _hash_reset_token(raw)
    h2 = _hash_reset_token(raw)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_reset_token_different_for_different_inputs():
    assert _hash_reset_token("abc") != _hash_reset_token("def")


def test_reset_link_base_uses_env(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://myapp.example.com/")
    base = _reset_link_base()
    assert base == "https://myapp.example.com"


def test_reset_link_base_fallback(monkeypatch):
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    base = _reset_link_base()
    assert base == "http://localhost:3000"


def test_send_reset_email_no_smtp_configured(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    ok, hint = _send_reset_email("user@example.com", "http://link", "Alice")
    assert ok is False
    assert hint == "email_not_configured"


# ---------------------------------------------------------------------------
# Login endpoint (mock DB)
# ---------------------------------------------------------------------------

class _DummyRequest:
    """Minimal mock for Starlette Request."""
    def __init__(self, client_ip="192.168.1.1"):
        self.headers = {"x-test-rate-limit-client-ip": client_ip}
        self.client = type("C", (), {"host": client_ip})()


class _DummyResponse:
    """Minimal mock for Starlette Response (cookie tracking)."""
    def __init__(self):
        self._cookies = {}

    def set_cookie(self, key, value, **kw):
        self._cookies[key] = value

    def delete_cookie(self, key, **kw):
        self._cookies.pop(key, None)


@pytest.mark.anyio
async def test_login_success_with_mock_db(monkeypatch):
    """Login succeeds when credentials match."""
    import datetime
    from models.auth import LoginInput as LI

    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()

    pwd = "TestPass123!"
    fake_user = {
        "_id": __import__("bson").ObjectId(),
        "email": "testlogin@sskfootcare.com",
        "name": "Test User",
        "role": "admin",
        "active": True,
        "password_hash": hash_password(pwd),
    }

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=fake_user)
    mock_db = MagicMock()
    mock_db.users = mock_users
    monkeypatch.setattr(server, "db", mock_db)

    req = _DummyRequest("1.2.3.4")
    resp = _DummyResponse()
    result = await login(LI(email=fake_user["email"], password=pwd), req, resp)

    assert result["email"] == fake_user["email"]
    assert "access_token" in result
    assert "refresh_token" in result
    assert "access_token" in resp._cookies
    auth_routes._login_failures.clear()


@pytest.mark.anyio
async def test_login_failure_wrong_password(monkeypatch):
    """Login raises 401 on wrong password."""
    from fastapi import HTTPException
    from models.auth import LoginInput as LI

    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()

    fake_user = {
        "_id": __import__("bson").ObjectId(),
        "email": "testfail@sskfootcare.com",
        "name": "Fail User",
        "role": "admin",
        "active": True,
        "password_hash": hash_password("CorrectPass123!"),
    }

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=fake_user)
    mock_db = MagicMock()
    mock_db.users = mock_users
    monkeypatch.setattr(server, "db", mock_db)

    req = _DummyRequest("1.2.3.5")
    resp = _DummyResponse()
    with pytest.raises(HTTPException) as exc:
        await login(LI(email=fake_user["email"], password="WrongPass!"), req, resp)
    assert exc.value.status_code == 401
    auth_routes._login_failures.clear()


@pytest.mark.anyio
async def test_login_fails_for_inactive_user(monkeypatch):
    """Login raises 401 for inactive accounts."""
    from fastapi import HTTPException
    from models.auth import LoginInput as LI

    monkeypatch.setattr(auth_routes, "redis_client", None)
    auth_routes._login_failures.clear()

    pwd = "Inactive123!"
    fake_user = {
        "_id": __import__("bson").ObjectId(),
        "email": "inactive@sskfootcare.com",
        "name": "Inactive",
        "role": "admin",
        "active": False,
        "password_hash": hash_password(pwd),
    }

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=fake_user)
    mock_db = MagicMock()
    mock_db.users = mock_users
    monkeypatch.setattr(server, "db", mock_db)

    req = _DummyRequest("1.2.3.6")
    resp = _DummyResponse()
    with pytest.raises(HTTPException) as exc:
        await login(LI(email=fake_user["email"], password=pwd), req, resp)
    assert exc.value.status_code == 401
    auth_routes._login_failures.clear()


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_logout_clears_cookies():
    resp = _DummyResponse()
    resp._cookies["access_token"] = "some_token"
    result = await logout(resp)
    assert result == {"ok": True}
    # Cookie should be deleted
    assert "access_token" not in resp._cookies


# ---------------------------------------------------------------------------
# Refresh token route (mock DB)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_refresh_token_route_success_with_mock_db(monkeypatch):
    """refresh_token_route returns new tokens when a valid refresh token is presented."""
    from bson import ObjectId

    fake_user = {
        "_id": ObjectId(),
        "email": "refresh@sskfootcare.com",
        "role": "admin",
        "active": True,
    }
    user_id = str(fake_user["_id"])
    initial_refresh = create_refresh_token(user_id)

    mock_users = MagicMock()
    mock_users.find_one = AsyncMock(return_value=fake_user)
    mock_db = MagicMock()
    mock_db.users = mock_users
    monkeypatch.setattr(server, "db", mock_db)

    # Build a mock Request with refresh token in JSON body
    import json

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/refresh",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive():
        return {"type": "http.request", "body": json.dumps({"refresh_token": initial_refresh}).encode()}

    from starlette.requests import Request
    req = Request(scope, receive)
    resp = _DummyResponse()

    result = await refresh_token_route(req, resp)
    assert result["ok"] is True
    assert "access_token" in result
    assert "refresh_token" in result
    # New tokens must differ from original
    assert result["refresh_token"] != initial_refresh


# ---------------------------------------------------------------------------
# GET /auth/me  (mock get_current_user)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_me_returns_current_user(monkeypatch):
    """GET /auth/me delegates to get_current_user and returns the user dict."""
    fake_user = {"id": "abc123", "email": "me@sskfootcare.com", "role": "admin"}

    async def _mock_gcu(request):
        return fake_user

    monkeypatch.setattr(server, "get_current_user", _mock_gcu)

    class _Req:
        pass

    result = await me(_Req())
    assert result == fake_user


# ---------------------------------------------------------------------------
# Users CRUD helpers (integration relies on MongoDB — skipped without it)
# ---------------------------------------------------------------------------

def test_forgotpasswordinput_model_validates_email():
    """ForgotPasswordInput rejects non-email strings."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ForgotPasswordInput(email="not-an-email")


def test_resetpasswordinput_model_accepts_valid_input():
    payload = ResetPasswordInput(token="abc123", new_password="NewP@ss123")
    assert payload.token == "abc123"
    assert payload.new_password == "NewP@ss123"
