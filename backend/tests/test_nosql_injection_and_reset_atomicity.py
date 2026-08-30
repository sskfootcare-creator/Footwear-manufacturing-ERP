"""Tests for MongoDB query parameter type coercion, regex escaping, and password reset atomic token validation."""

import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException

from routes.auth import (
    reset_password,
    ResetPasswordInput,
    _hash_reset_token,
)
from routes.styles import list_styles_summary
from routes.wms import wms_list_locations
from routes.expenses import list_expenses
from routes.sku_map import list_marketplace_mappings


@pytest.mark.anyio
async def test_reset_password_atomic_expiry_rejection():
    """Verify expired reset token is rejected at the query level."""
    raw_token = "valid-length-token-123456789012345"
    token_hash = _hash_reset_token(raw_token)
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)

    mock_db = MagicMock()
    # The atomic query searches for used_at: None, expires_at: {"$gt": now} -> returns None
    mock_db.password_resets.find_one = AsyncMock(side_effect=lambda q: None if "$gt" in str(q) else {
        "_id": ObjectId(),
        "user_id": str(ObjectId()),
        "token_hash": token_hash,
        "expires_at": past_time,
        "used_at": None,
    })

    # Monkeypatch _get_db in routes.auth
    import routes.auth
    orig_get_db = routes.auth._get_db
    routes.auth._get_db = lambda: mock_db

    try:
        payload = ResetPasswordInput(token=raw_token, new_password="ValidNewPassword123!")
        with pytest.raises(HTTPException) as exc_info:
            await reset_password(payload)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()
    finally:
        routes.auth._get_db = orig_get_db


@pytest.mark.anyio
async def test_reset_password_atomic_already_used_rejection():
    """Verify already-used reset token is rejected at the query level."""
    raw_token = "valid-length-token-123456789012345"
    token_hash = _hash_reset_token(raw_token)
    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=1)

    mock_db = MagicMock()
    # The atomic query searches for used_at: None -> returns None
    mock_db.password_resets.find_one = AsyncMock(side_effect=lambda q: None if "$gt" in str(q) else {
        "_id": ObjectId(),
        "user_id": str(ObjectId()),
        "token_hash": token_hash,
        "expires_at": future_time,
        "used_at": "2026-08-30T10:00:00Z",
    })

    import routes.auth
    orig_get_db = routes.auth._get_db
    routes.auth._get_db = lambda: mock_db

    try:
        payload = ResetPasswordInput(token=raw_token, new_password="ValidNewPassword123!")
        with pytest.raises(HTTPException) as exc_info:
            await reset_password(payload)
        assert exc_info.value.status_code == 400
        assert "already been used" in exc_info.value.detail.lower()
    finally:
        routes.auth._get_db = orig_get_db


@pytest.mark.anyio
async def test_reset_password_atomic_success():
    """Verify valid unexpired, unused token succeeds and updates password atomically."""
    raw_token = "valid-length-token-123456789012345"
    token_hash = _hash_reset_token(raw_token)
    user_id = str(ObjectId())
    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=1)

    valid_row = {
        "_id": ObjectId(),
        "user_id": user_id,
        "token_hash": token_hash,
        "expires_at": future_time,
        "used_at": None,
    }

    mock_user = {
        "_id": ObjectId(user_id),
        "email": "user@example.com",
        "active": True,
    }

    mock_db = MagicMock()
    mock_db.password_resets.find_one = AsyncMock(return_value=valid_row)
    mock_db.users.find_one = AsyncMock(return_value=mock_user)
    mock_db.users.update_one = AsyncMock(return_value=None)
    mock_db.password_resets.update_one = AsyncMock(return_value=None)
    mock_db.password_resets.update_many = AsyncMock(return_value=None)

    import routes.auth
    orig_get_db = routes.auth._get_db
    routes.auth._get_db = lambda: mock_db

    try:
        payload = ResetPasswordInput(token=raw_token, new_password="ValidNewPassword123!")
        res = await reset_password(payload)
        assert res["ok"] is True
        assert mock_db.users.update_one.called
        assert mock_db.password_resets.update_one.called
    finally:
        routes.auth._get_db = orig_get_db


@pytest.mark.anyio
async def test_regex_search_escaping_styles(monkeypatch):
    """Verify regex characters like '.*' or '^' in search parameters are escaped."""
    import routes.styles
    mock_user = {"role": "admin", "email": "admin@example.com"}
    monkeypatch.setattr(routes.styles, "_get_user", AsyncMock(return_value=mock_user))

    captured_query = {}

    class MockStylesCollection:
        def find(self, query):
            captured_query.update(query)
            mock_cursor = MagicMock()
            mock_cursor.sort = MagicMock(return_value=mock_cursor)
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

    mock_db = MagicMock()
    mock_db.styles = MockStylesCollection()
    mock_db.style_lifecycle.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_db.production_jobs.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    monkeypatch.setattr(routes.styles, "get_db", lambda: mock_db)

    req = MagicMock()
    await list_styles_summary(req, search=".*[test]")
    
    # Check that $regex is escaped: \.\*\[test\]
    assert "$or" in captured_query
    regex_val = captured_query["$or"][0]["code"]["$regex"]
    assert regex_val == r"\.\*\[test\]"
