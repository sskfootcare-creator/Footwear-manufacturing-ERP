import os
import pytest
import requests
import time

API_URL = "http://localhost:8000/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "Admin@123")

def test_login_rate_limiting():
    # We will use a unique dummy IP for this test to avoid interfering with other runs or tests
    import random
    dummy_ip = f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    headers = {"X-Test-Rate-Limit-Client-IP": dummy_ip}

    # 1. First 5 failed login attempts should return 401 (Unauthorized)
    for i in range(5):
        r = requests.post(
            f"{API_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WrongPassword"},
            headers=headers,
            timeout=10
        )
        assert r.status_code == 401, f"Attempt {i+1} failed with status {r.status_code}: {r.text}"
        assert "Invalid email or password" in r.json().get("detail", "")

    # 2. The 6th attempt (even with correct credentials) should be blocked with 429 (Too Many Requests)
    r = requests.post(
        f"{API_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers=headers,
        timeout=10
    )
    assert r.status_code == 429, f"6th attempt should be blocked, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "Too many failed login attempts" in detail
    assert "Retry-After" in r.headers
    
    # 3. A request from a different IP should not be blocked
    other_headers = {"X-Test-Rate-Limit-Client-IP": f"11.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"}
    r = requests.post(
        f"{API_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers=other_headers,
        timeout=10
    )
    assert r.status_code == 200, f"Other IP should be able to login successfully, got {r.status_code}"


def test_rate_limiting_reset_on_success():
    import random
    dummy_ip = f"12.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    headers = {"X-Test-Rate-Limit-Client-IP": dummy_ip}

    # 1. Perform 3 failed attempts
    for i in range(3):
        r = requests.post(
            f"{API_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WrongPassword"},
            headers=headers,
            timeout=10
        )
        assert r.status_code == 401

    # 2. Perform 1 successful login
    r = requests.post(
        f"{API_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        headers=headers,
        timeout=10
    )
    assert r.status_code == 200

    # 3. Perform 3 more failed attempts (should succeed as failures count was reset)
    for i in range(3):
        r = requests.post(
            f"{API_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "WrongPassword"},
            headers=headers,
            timeout=10
        )
        assert r.status_code == 401, f"Should return 401 after reset, got {r.status_code}"


def test_file_upload_rate_limiting():
    import random
    dummy_ip = f"13.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    headers = {
        "X-Test-Rate-Limit-Client-IP": dummy_ip,
        "X-Test-Rate-Limit-Window": "300"
    }
    files = {"file": ("test.pdf", b"dummy pdf content", "application/pdf")}

    # 1. First 20 requests to an upload endpoint (e.g. /pos/extract) should return non-429
    for i in range(20):
        r = requests.post(
            f"{API_URL}/pos/extract",
            headers=headers,
            files=files,
            timeout=10
        )
        assert r.status_code != 429, f"Attempt {i+1} was rate limited prematurely: {r.status_code}"

    # 2. The 21st request must be rate limited with 429
    r = requests.post(
        f"{API_URL}/pos/extract",
        headers=headers,
        files=files,
        timeout=10
    )
    assert r.status_code == 429, f"21st attempt should be blocked, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "Too many file upload requests" in detail
    assert "Retry-After" in r.headers


def test_pdf_generation_rate_limiting():
    import random
    dummy_ip = f"14.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    headers = {
        "X-Test-Rate-Limit-Client-IP": dummy_ip,
        "X-Test-Rate-Limit-Window": "300"
    }
    json_data = {"job_ids": []}

    # 1. First 30 requests to a PDF generation endpoint (e.g. /production/card.pdf) should return non-429
    for i in range(30):
        r = requests.post(
            f"{API_URL}/production/card.pdf",
            headers=headers,
            json=json_data,
            timeout=10
        )
        assert r.status_code != 429, f"Attempt {i+1} was rate limited prematurely: {r.status_code}"

    # 2. The 31st request must be rate limited with 429
    r = requests.post(
        f"{API_URL}/production/card.pdf",
        headers=headers,
        json=json_data,
        timeout=10
    )
    assert r.status_code == 429, f"31st attempt should be blocked, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "Too many PDF generation requests" in detail
    assert "Retry-After" in r.headers


