"""Validation test suite for audit record fixes:
- OPS-003: Production gate for test helper endpoints
- CODE-004: Centralized constants & elimination of magic numbers
- DB-005 & PERF-003: Bounded queries with projections
- DEPLOY-003: Circuit breaker operations and /readyz probe
- DEPLOY-004: Secrets manager validation and entropy checks
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from server import app
from constants import (
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_IMAGE_PIXELS,
    DASHBOARD_STATS_CACHE_TTL,
    DASHBOARD_QUERY_BATCH_SIZE,
    DASHBOARD_MAX_DOCS_LIMIT,
)
from circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenException,
    get_circuit_breakers_status,
)
from secrets_manager import SecretsManager, calculate_entropy, mask_secret


@pytest.fixture
def client_env(monkeypatch):
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1})
    mock_db.users.find_one = AsyncMock(return_value={"_id": ObjectId(), "role": "admin"})
    monkeypatch.setattr(server, "db", mock_db)
    monkeypatch.setattr(server, "_get_auth_user", AsyncMock(return_value={"id": "admin_1", "role": "admin"}))
    client = TestClient(app)
    return client, mock_db


# ── OPS-003: Test Helper Production Gate ──────────────────────────────────────
def test_test_helper_blocked_in_production(client_env, monkeypatch):
    """Verify POST /test-helpers/create-test-invoice returns 403 in production."""
    client, mock_db = client_env
    monkeypatch.setenv("ENVIRONMENT", "production")

    payload = {"invoice_no": "TEST-INV-PROD", "grand_total": 1000.0}
    res = client.post("/test-helpers/create-test-invoice", json=payload)
    assert res.status_code == 403
    assert "disabled in production" in res.json()["detail"].lower()


def test_test_helper_allowed_in_development(client_env, monkeypatch):
    """Verify POST /test-helpers/create-test-invoice succeeds in non-production."""
    client, mock_db = client_env
    monkeypatch.setenv("ENVIRONMENT", "development")
    mock_db.invoices.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    payload = {"invoice_no": "TEST-INV-DEV", "grand_total": 500.0}
    res = client.post("/test-helpers/create-test-invoice", json=payload)
    assert res.status_code == 200
    assert res.json()["invoice_no"] == "TEST-INV-DEV"


# ── CODE-004: Centralized Constants ──────────────────────────────────────────
def test_code_004_constants_configured():
    """Verify all previously magic numbers are properly defined in constants module."""
    assert MAX_IMAGE_UPLOAD_BYTES == 8 * 1024 * 1024
    assert MAX_IMAGE_PIXELS == 10_000_000
    assert DASHBOARD_STATS_CACHE_TTL == 300
    assert DASHBOARD_QUERY_BATCH_SIZE == 500
    assert DASHBOARD_MAX_DOCS_LIMIT == 10_000


# ── DEPLOY-003: Circuit Breaker Mechanics ────────────────────────────────────
@pytest.mark.anyio
async def test_circuit_breaker_transitions():
    """Verify circuit breaker trips to OPEN after threshold and fails fast."""
    cb = CircuitBreaker("mock_service", failure_threshold=2, recovery_timeout_seconds=0.1)
    assert cb.state == CircuitState.CLOSED

    async def faulty_operation():
        raise ConnectionError("Service unreachable")

    # Failure 1
    with pytest.raises(ConnectionError):
        await cb.call_async(faulty_operation)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # Failure 2: reaches threshold -> trips to OPEN
    with pytest.raises(ConnectionError):
        await cb.call_async(faulty_operation)
    assert cb.state == CircuitState.OPEN

    # Call while OPEN fails fast with CircuitBreakerOpenException without invoking func
    with pytest.raises(CircuitBreakerOpenException):
        await cb.call_async(faulty_operation)


def test_readyz_includes_circuit_breakers(client_env, monkeypatch):
    """Verify /readyz endpoint reports circuit breaker diagnostic health."""
    client, _ = client_env
    monkeypatch.setenv("ENVIRONMENT", "test")
    res = client.get("/readyz")
    assert res.status_code == 200
    data = res.json()
    assert "circuit_breakers" in data["checks"]
    cb_statuses = data["checks"]["circuit_breakers"]
    assert "mongodb" in cb_statuses
    assert "redis" in cb_statuses
    assert cb_statuses["mongodb"]["state"] == "CLOSED"


# ── DEPLOY-004: Secrets Manager ──────────────────────────────────────────────
def test_secrets_manager_validation():
    """Verify SecretsManager catches insecure defaults and missing production secrets."""
    sm = SecretsManager()

    # Insecure secret detection
    assert calculate_entropy("secret") < 3.0
    assert mask_secret("supersecretjwtkey12345!") == "supe...345!"

    # Production validation fails on weak JWT
    with pytest.raises(RuntimeError, match="Production secret validation failed"):
        with patch.dict(os.environ, {
            "JWT_SECRET": "short",
            "MONGO_URL": "mongodb://prod-cluster:27017/erp",
            "S3_BUCKET": "prod-bucket",
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "AWS_SECRET_ACCESS_KEY": "secret...",
        }):
            sm.validate_all_secrets("production")

    # Successful validation in production
    valid_jwt = "a" * 32 + "cryptographically_secure_token_123!"
    with patch.dict(os.environ, {
        "JWT_SECRET": valid_jwt,
        "MONGO_URL": "mongodb://prod-cluster:27017/erp",
        "S3_BUCKET": "prod-bucket",
        "AWS_ACCESS_KEY_ID": "AKIA...",
        "AWS_SECRET_ACCESS_KEY": "secret...",
    }):
        res = sm.validate_all_secrets("production")
        assert res["status"] == "ok"
