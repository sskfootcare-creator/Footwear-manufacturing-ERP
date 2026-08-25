"""Test CORS security policy and rejection of arbitrary *.vercel.app and *.onrender.com subdomains."""
import pytest
import httpx
import server
from server import app


@pytest.mark.anyio
async def test_cors_allows_legitimate_production_origin():
    """Verify that official production origin receives valid CORS headers."""
    valid_origin = "https://ssk-footcare-manufacturing-erp.vercel.app"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/dashboard/stats",
            headers={
                "Origin": valid_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == valid_origin
        assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.anyio
async def test_cors_allows_localhost_origins():
    """Verify that local development origins are permitted."""
    valid_origin = "http://localhost:3000"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/dashboard/stats",
            headers={
                "Origin": valid_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == valid_origin


@pytest.mark.anyio
async def test_cors_rejects_arbitrary_vercel_and_onrender_subdomains(monkeypatch):
    """Verify: an attacker deploying a phishing page on arbitrary *.vercel.app or *.onrender.com
    is rejected and does NOT receive CORS access headers.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    malicious_origins = [
        "https://evil-ssk.vercel.app",
        "https://phishing-footwear.vercel.app",
        "https://attacker.onrender.com",
        "https://random-app.onrender.com",
        "https://malicious-domain.com",
    ]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for evil_origin in malicious_origins:
            # Preflight OPTIONS request
            options_res = await client.options(
                "/api/dashboard/stats",
                headers={
                    "Origin": evil_origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            # Should not grant access-control-allow-origin to the evil origin
            assert options_res.headers.get("access-control-allow-origin") is None, f"Expected {evil_origin} to be rejected"


