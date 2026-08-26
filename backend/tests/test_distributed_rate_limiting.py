"""Test distributed login rate limiting (Redis and in-memory fallback)."""
import pytest
import os
import time
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException, Response
import server
import routes.auth as auth_routes
from server import (
    oid,
    login,
    LoginInput,
    check_rate_limit,
    record_login_failure,
    clear_login_failures,
    hash_password,
)


class DummyRequest:
    """Mock Request for unit testing login endpoint."""
    def __init__(self, client_ip="192.168.1.50"):
        self.headers = {"x-test-rate-limit-client-ip": client_ip}
        self.client = type("Client", (), {"host": client_ip})()


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    monkeypatch.setattr(server, "client", c)
    monkeypatch.setattr(server, "db", d)
    server._login_failures.clear()
    yield d
    server._login_failures.clear()
    c.close()


@pytest.mark.anyio
async def test_in_memory_rate_limiting_lockout_and_clear(fresh_db, monkeypatch):
    """Verify single-instance rate limiting works correctly with 5-attempt limit and clear-on-success."""
    monkeypatch.setattr(server, "redis_client", None)
    monkeypatch.setattr(auth_routes, "redis_client", None)
    server._login_failures.clear()

    test_ip = "10.0.0.1"
    req = DummyRequest(client_ip=test_ip)
    res = Response()

    # Seed test user
    email = "ratelimit_user@sskfootcare.com"
    pwd = "CorrectPassword123!"
    await server.db.users.delete_many({"email": email})
    await server.db.users.insert_one({
        "email": email,
        "name": "Rate Limit User",
        "role": "admin",
        "active": True,
        "password_hash": hash_password(pwd),
    })

    try:
        # 1. First 5 failed attempts should raise 401
        for i in range(5):
            with pytest.raises(HTTPException) as exc_info:
                await login(LoginInput(email=email, password="WrongPassword!"), req, res)
            assert exc_info.value.status_code == 401

        # 2. 6th attempt should trigger 429 Too Many Requests
        with pytest.raises(HTTPException) as exc_info:
            await login(LoginInput(email=email, password=pwd), req, res)
        assert exc_info.value.status_code == 429
        assert "Too many failed login attempts" in exc_info.value.detail

        # 3. Clear failures for IP
        await clear_login_failures(test_ip)

        # 4. Attempt with correct password should now succeed
        success_res = await login(LoginInput(email=email, password=pwd), req, res)
        assert success_res["email"] == email
        assert "access_token" in success_res

    finally:
        await server.db.users.delete_many({"email": email})
        await clear_login_failures(test_ip)


class MockRedisStore:
    """Mock Redis client simulating shared Redis across multiple backend worker instances."""
    def __init__(self):
        self.store = {}

    async def zremrangebyscore(self, key, min_score, max_score):
        if key not in self.store:
            return 0
        original = len(self.store[key])
        self.store[key] = [(val, score) for val, score in self.store[key] if score > float(max_score)]
        return original - len(self.store[key])

    async def zcard(self, key):
        return len(self.store.get(key, []))

    async def zrange(self, key, start, stop, withscores=False):
        items = sorted(self.store.get(key, []), key=lambda x: x[1])
        if stop == -1:
            slice_items = items[start:]
        else:
            slice_items = items[start:stop + 1]
        if withscores:
            return [(v, s) for v, s in slice_items]
        return [v for v, s in slice_items]

    async def zadd(self, key, mapping):
        if key not in self.store:
            self.store[key] = []
        for val, score in mapping.items():
            self.store[key].append((val, float(score)))
        return len(mapping)

    async def expire(self, key, seconds):
        return True

    async def delete(self, key):
        if key in self.store:
            del self.store[key]
            return 1
        return 0


@pytest.mark.anyio
async def test_distributed_multi_instance_rate_limiting(fresh_db, monkeypatch):
    """Simulate two backend instances (Instance A and Instance B) sharing the same Redis store."""
    shared_redis = MockRedisStore()
    monkeypatch.setattr(server, "redis_client", shared_redis)
    monkeypatch.setattr(auth_routes, "redis_client", shared_redis)

    test_ip = "10.0.0.99"
    req = DummyRequest(client_ip=test_ip)
    res = Response()

    email = "multi_instance_user@sskfootcare.com"
    pwd = "SecretPassword123!"
    await server.db.users.delete_many({"email": email})
    await server.db.users.insert_one({
        "email": email,
        "name": "Multi Instance User",
        "role": "admin",
        "active": True,
        "password_hash": hash_password(pwd),
    })

    try:
        # Instance A receives 3 failed attempts
        for _ in range(3):
            with pytest.raises(HTTPException) as exc_info:
                await login(LoginInput(email=email, password="BadPassword"), req, res)
            assert exc_info.value.status_code == 401

        # Instance B receives 2 failed attempts
        for _ in range(2):
            with pytest.raises(HTTPException) as exc_info:
                await login(LoginInput(email=email, password="BadPassword"), req, res)
            assert exc_info.value.status_code == 401

        # Instance A (or B) receives the 6th attempt -> should be blocked by shared 429
        with pytest.raises(HTTPException) as exc_info:
            await login(LoginInput(email=email, password=pwd), req, res)
        assert exc_info.value.status_code == 429

        # Verify attempts are tracked in shared Redis
        card = await shared_redis.zcard(f"login_failures:{test_ip}")
        assert card == 5

        # Successful reset
        await clear_login_failures(test_ip)
        card_after = await shared_redis.zcard(f"login_failures:{test_ip}")
        assert card_after == 0

        # Login now succeeds
        success_res = await login(LoginInput(email=email, password=pwd), req, res)
        assert success_res["email"] == email

    finally:
        await server.db.users.delete_many({"email": email})
        await shared_redis.delete(f"login_failures:{test_ip}")
