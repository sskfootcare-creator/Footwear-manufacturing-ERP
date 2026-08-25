"""Test refresh token rotation on /auth/refresh."""
import pytest
import os
import jwt
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import Response
from starlette.requests import Request
import server
from server import (
    oid,
    refresh_token_route,
    create_refresh_token,
    get_jwt_secret,
    JWT_ALGORITHM,
)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    monkeypatch.setattr(server, "client", c)
    monkeypatch.setattr(server, "db", d)
    yield d
    c.close()


@pytest.mark.anyio
async def test_refresh_token_rotates_on_every_use(fresh_db):
    """Verify: call refresh, confirm a new refresh_token cookie is set alongside the new
    access_token; confirm the response/cookie actually differs from the previous
    refresh token value each time.
    """
    # 1. Setup a test user
    user_res = await server.db.users.insert_one({
        "email": "refreshtest@sskfootcare.com",
        "name": "Refresh Test User",
        "role": "admin",
        "active": True,
        "password_hash": "dummyhash",
    })
    user_id = str(user_res.inserted_id)

    try:
        # Initial refresh token
        initial_refresh_token = create_refresh_token(user_id)

        # 2. First refresh call (via JSON body)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/refresh",
            "headers": [(b"content-type", b"application/json")],
        }
        async def receive_body_1():
            import json
            return {"type": "http.request", "body": json.dumps({"refresh_token": initial_refresh_token}).encode("utf-8")}

        req_1 = Request(scope, receive_body_1)
        res_1 = Response()

        out_1 = await refresh_token_route(req_1, res_1)

        assert out_1["ok"] is True
        assert "access_token" in out_1
        assert "refresh_token" in out_1
        new_refresh_token_1 = out_1["refresh_token"]

        # Confirm new refresh token differs from initial
        assert new_refresh_token_1 != initial_refresh_token

        # Verify decoded payload has type 'refresh' and sub matching user_id
        decoded_1 = jwt.decode(new_refresh_token_1, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        assert decoded_1["sub"] == user_id
        assert decoded_1["type"] == "refresh"
        assert "jti" in decoded_1

        # Confirm response set cookie for refresh_token
        set_cookie_headers_1 = res_1.headers.getlist("set-cookie")
        assert any("refresh_token=" in h for h in set_cookie_headers_1)
        assert any("access_token=" in h for h in set_cookie_headers_1)
        # Verify the cookie contains the new token value
        assert any(new_refresh_token_1 in h for h in set_cookie_headers_1)

        # 3. Second refresh call using the newly rotated token (via cookie)
        scope_2 = {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/refresh",
            "headers": [
                (b"cookie", f"refresh_token={new_refresh_token_1}".encode("utf-8")),
            ],
        }
        async def receive_body_2():
            return {"type": "http.request", "body": b""}

        req_2 = Request(scope_2, receive_body_2)
        res_2 = Response()

        out_2 = await refresh_token_route(req_2, res_2)

        assert out_2["ok"] is True
        assert "access_token" in out_2
        assert "refresh_token" in out_2
        new_refresh_token_2 = out_2["refresh_token"]

        # Confirm second new refresh token differs from the first rotated token
        assert new_refresh_token_2 != new_refresh_token_1
        assert new_refresh_token_2 != initial_refresh_token

        # Confirm response set cookie contains the second rotated token
        set_cookie_headers_2 = res_2.headers.getlist("set-cookie")
        assert any(new_refresh_token_2 in h for h in set_cookie_headers_2)

    finally:
        await server.db.users.delete_one({"_id": oid(user_id)})
