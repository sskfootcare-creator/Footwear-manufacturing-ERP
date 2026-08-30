"""Unit tests for security headers in vercel.json and FastAPI backend."""

import json
import os
import pytest
from fastapi.testclient import TestClient
from server import app


def test_vercel_json_security_headers_configuration():
    """Verify vercel.json defines required security headers for all routes."""
    vercel_json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vercel.json"))
    assert os.path.exists(vercel_json_path), f"vercel.json not found at {vercel_json_path}"

    with open(vercel_json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    assert "headers" in config, "vercel.json must have a 'headers' configuration"
    assert len(config["headers"]) > 0

    header_block = next((h for h in config["headers"] if h.get("source") in ("/(.*)", "*", "/:path*")), None)
    assert header_block is not None, "vercel.json must have a global headers rule matching /(.*)"

    headers_dict = {item["key"]: item["value"] for item in header_block["headers"]}

    # 1. HSTS
    assert "Strict-Transport-Security" in headers_dict
    assert "max-age=" in headers_dict["Strict-Transport-Security"]

    # 2. X-Frame-Options (SAMEORIGIN required for in-app PDF and document previews)
    assert headers_dict.get("X-Frame-Options") == "SAMEORIGIN"

    # 3. X-Content-Type-Options
    assert headers_dict.get("X-Content-Type-Options") == "nosniff"

    # 4. Referrer-Policy
    assert headers_dict.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # 5. Content-Security-Policy
    csp = headers_dict.get("Content-Security-Policy")
    assert csp is not None, "Content-Security-Policy must be defined"

    # Validate essential CSP directives
    assert "script-src" in csp
    assert "https://assets.emergent.sh" in csp
    assert "'unsafe-inline'" in csp

    assert "style-src" in csp
    assert "https://fonts.googleapis.com" in csp

    assert "font-src" in csp
    assert "https://fonts.gstatic.com" in csp

    assert "img-src" in csp
    assert "blob:" in csp
    assert "data:" in csp
    assert "https:" in csp

    assert "connect-src" in csp
    assert "https:" in csp

    assert "frame-src" in csp
    assert "frame-ancestors 'self'" in csp


def test_fastapi_backend_security_headers_middleware():
    """Verify FastAPI backend middleware attaches security headers to responses."""
    client = TestClient(app)
    response = client.get("/api/health") if hasattr(app, "health") else client.get("/api/")
    # If 404 or any status, headers must still be present from middleware
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Strict-Transport-Security" in response.headers
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
