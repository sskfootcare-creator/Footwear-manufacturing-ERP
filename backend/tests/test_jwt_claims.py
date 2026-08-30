"""Unit tests for JWT iss (issuer) and aud (audience) claims validation."""

import os
import pytest
import jwt
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient

from auth import (
    create_access_token,
    create_refresh_token,
    get_jwt_secret,
    get_current_user_factory,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_AUDIENCE,
)


def test_token_creation_includes_iss_and_aud():
    """Verify create_access_token and create_refresh_token embed iss and aud claims."""
    uid = str(ObjectId())
    token = create_access_token(uid, "test@sskfootcare.com", "admin")
    
    # Decode raw payload
    payload = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )
    assert payload["iss"] == "ssk-footcare-erp"
    assert payload["aud"] == "ssk-footcare-erp-api"
    assert payload["sub"] == uid
    assert payload["type"] == "access"

    # Refresh token
    refresh_token = create_refresh_token(uid)
    ref_payload = jwt.decode(
        refresh_token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )
    assert ref_payload["iss"] == "ssk-footcare-erp"
    assert ref_payload["aud"] == "ssk-footcare-erp-api"
    assert ref_payload["sub"] == uid
    assert ref_payload["type"] == "refresh"


@pytest.mark.anyio
async def test_get_current_user_validates_iss_and_aud_success():
    """Verify valid token with matching iss and aud authenticates successfully."""
    uid = str(ObjectId())
    mock_user = {
        "_id": ObjectId(uid),
        "email": "user@sskfootcare.com",
        "name": "Test User",
        "role": "manager",
        "active": True,
    }

    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=mock_user)

    get_current_user = await get_current_user_factory(mock_db)

    token = create_access_token(uid, "user@sskfootcare.com", "manager")

    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"Authorization": f"Bearer {token}"}
    mock_req.cookies = {}

    user = await get_current_user(mock_req)
    assert user["email"] == "user@sskfootcare.com"
    assert user["role"] == "manager"


@pytest.mark.anyio
async def test_get_current_user_rejects_missing_aud():
    """Verify token missing aud claim is rejected with 401."""
    uid = str(ObjectId())
    mock_db = MagicMock()
    get_current_user = await get_current_user_factory(mock_db)

    # Manually forge token without aud claim
    bad_payload = {
        "sub": uid,
        "email": "user@sskfootcare.com",
        "role": "admin",
        "iss": JWT_ISSUER,
        # "aud" omitted
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "access",
    }
    bad_token = jwt.encode(bad_payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"Authorization": f"Bearer {bad_token}"}
    mock_req.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_req)
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.anyio
async def test_get_current_user_rejects_mismatched_aud():
    """Verify token with incorrect aud claim is rejected with 401."""
    uid = str(ObjectId())
    mock_db = MagicMock()
    get_current_user = await get_current_user_factory(mock_db)

    # Token with malicious/different audience
    bad_payload = {
        "sub": uid,
        "email": "user@sskfootcare.com",
        "role": "admin",
        "iss": JWT_ISSUER,
        "aud": "attacker-fake-api",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "access",
    }
    bad_token = jwt.encode(bad_payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"Authorization": f"Bearer {bad_token}"}
    mock_req.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_req)
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.anyio
async def test_get_current_user_rejects_mismatched_iss():
    """Verify token with incorrect issuer is rejected with 401."""
    uid = str(ObjectId())
    mock_db = MagicMock()
    get_current_user = await get_current_user_factory(mock_db)

    # Token with wrong issuer
    bad_payload = {
        "sub": uid,
        "email": "user@sskfootcare.com",
        "role": "admin",
        "iss": "rogue-auth-server",
        "aud": JWT_AUDIENCE,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "access",
    }
    bad_token = jwt.encode(bad_payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"Authorization": f"Bearer {bad_token}"}
    mock_req.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_req)
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail
