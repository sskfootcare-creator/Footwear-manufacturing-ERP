"""Unit tests for JWT_SECRET startup validation and environment gating."""

import os
import pytest
import secrets
from auth import validate_jwt_secret, get_jwt_secret, MIN_JWT_SECRET_LENGTH, _INSECURE_JWT_DEFAULTS


def test_production_missing_jwt_secret_fails(monkeypatch):
    """Verify that in production mode, missing/empty JWT_SECRET causes a hard abort."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET environment variable is not set"):
        validate_jwt_secret()


def test_production_known_insecure_default_fails(monkeypatch):
    """Verify that in production mode, known insecure default 'supersecretjwtkey12345!' causes a hard abort."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "supersecretjwtkey12345!")

    with pytest.raises(RuntimeError, match="known insecure default"):
        validate_jwt_secret()


@pytest.mark.parametrize("insecure_secret", sorted(_INSECURE_JWT_DEFAULTS))
def test_production_all_insecure_defaults_fail(monkeypatch, insecure_secret):
    """Verify that in production mode, all known insecure defaults fail with RuntimeError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", insecure_secret)

    with pytest.raises(RuntimeError):
        validate_jwt_secret()


def test_production_short_secret_fails(monkeypatch):
    """Verify that in production mode, JWT_SECRET with < 32 characters causes a hard abort."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "short-custom-secret-12345")  # 25 characters

    with pytest.raises(RuntimeError, match="below the minimum required 32 characters"):
        validate_jwt_secret()


def test_production_valid_secret_succeeds(monkeypatch):
    """Verify that in production mode, a random secret >= 32 characters succeeds."""
    secure_secret = secrets.token_urlsafe(32)  # 43+ chars
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", secure_secret)

    result = validate_jwt_secret()
    assert result == secure_secret
    assert get_jwt_secret() == secure_secret


def test_non_production_missing_jwt_secret_falls_back(monkeypatch):
    """Verify that in development/test, missing JWT_SECRET falls back to default and does not raise."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    result = validate_jwt_secret()
    assert result == "supersecretjwtkey12345!"
    assert get_jwt_secret() == "supersecretjwtkey12345!"


def test_non_production_insecure_default_allowed(monkeypatch):
    """Verify that in development/test, insecure default is allowed (warns but does not block)."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "supersecretjwtkey12345!")

    result = validate_jwt_secret()
    assert result == "supersecretjwtkey12345!"


def test_non_production_short_secret_allowed(monkeypatch):
    """Verify that in development/test, short secret is allowed (warns but does not block)."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET", "short_secret")

    result = validate_jwt_secret()
    assert result == "short_secret"


def test_server_startup_fails_in_production_with_default_jwt_secret(monkeypatch):
    """Verify that server startup hook aborts in production mode with default JWT_SECRET."""
    import asyncio
    from server import on_startup

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "supersecretjwtkey12345!")
    monkeypatch.setenv("ADMIN_PASSWORD", "ProdAdminPassword123!")

    with pytest.raises(RuntimeError, match="known insecure default"):
        asyncio.run(on_startup())

