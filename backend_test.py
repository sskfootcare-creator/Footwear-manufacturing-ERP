#!/usr/bin/env python3
"""
Backend test suite for auth bug fix verification.

Tests the CORS/withCredentials fix where:
- Backend /api/auth/refresh now accepts refresh_token from either cookie OR JSON body
- Frontend no longer uses withCredentials: true
- Login stores refresh_token in localStorage
- Refresh interceptor sends refresh_token in body
"""

import requests
import json
import sys

# Backend URL from frontend/.env
BASE_URL = "https://4411416a-6779-4d1b-ba32-8060d6385338.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

def print_test(name):
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)

def print_pass(msg):
    print(f"✅ PASS: {msg}")

def print_fail(msg):
    print(f"❌ FAIL: {msg}")

def print_info(msg):
    print(f"ℹ️  INFO: {msg}")

# ============================================================================
# TEST 1: POST /api/auth/login with correct credentials
# ============================================================================
def test_login_success():
    print_test("POST /api/auth/login with correct credentials")
    
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return None, None
    
    data = resp.json()
    
    # Check response body contains access_token and refresh_token
    if "access_token" not in data:
        print_fail("Response missing 'access_token' in body")
        return None, None
    
    if "refresh_token" not in data:
        print_fail("Response missing 'refresh_token' in body")
        return None, None
    
    print_pass(f"Login successful with access_token and refresh_token in response body")
    print_info(f"User: {data.get('email')} (role: {data.get('role')})")
    
    return data["access_token"], data["refresh_token"]

# ============================================================================
# TEST 2: POST /api/auth/login with wrong password
# ============================================================================
def test_login_wrong_password():
    print_test("POST /api/auth/login with wrong password")
    
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": "wrongpassword123"}
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 401:
        print_fail(f"Expected 401, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "Invalid email or password" not in detail:
        print_fail(f"Expected 'Invalid email or password', got: {detail}")
        return False
    
    print_pass(f"Wrong password correctly rejected with 401 and detail: '{detail}'")
    return True

# ============================================================================
# TEST 3: POST /api/auth/refresh with body flow (new)
# ============================================================================
def test_refresh_body_flow(refresh_token):
    print_test("POST /api/auth/refresh with body flow (new)")
    
    url = f"{BASE_URL}/auth/refresh"
    payload = {"refresh_token": refresh_token}
    
    # NO cookies, only body
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return None
    
    data = resp.json()
    
    if "access_token" not in data:
        print_fail("Response missing 'access_token'")
        return None
    
    print_pass(f"Refresh via body flow successful, new access_token received")
    return data["access_token"]

# ============================================================================
# TEST 4: POST /api/auth/refresh with cookie flow (legacy)
# ============================================================================
def test_refresh_cookie_flow(refresh_token):
    print_test("POST /api/auth/refresh with cookie flow (legacy)")
    
    url = f"{BASE_URL}/auth/refresh"
    
    # Send refresh_token as cookie, empty body
    cookies = {"refresh_token": refresh_token}
    resp = requests.post(url, json={}, cookies=cookies)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return None
    
    data = resp.json()
    
    if "access_token" not in data:
        print_fail("Response missing 'access_token'")
        return None
    
    print_pass(f"Refresh via cookie flow (legacy) successful, new access_token received")
    return data["access_token"]

# ============================================================================
# TEST 5: POST /api/auth/refresh with no cookie and no body
# ============================================================================
def test_refresh_missing_token():
    print_test("POST /api/auth/refresh with no cookie and no body")
    
    url = f"{BASE_URL}/auth/refresh"
    
    # No cookies, empty body
    resp = requests.post(url, json={})
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 401:
        print_fail(f"Expected 401, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "Missing refresh token" not in detail:
        print_fail(f"Expected 'Missing refresh token', got: {detail}")
        return False
    
    print_pass(f"Missing token correctly rejected with 401 and detail: '{detail}'")
    return True

# ============================================================================
# TEST 6: POST /api/auth/refresh with invalid refresh token in body
# ============================================================================
def test_refresh_invalid_token():
    print_test("POST /api/auth/refresh with invalid refresh token in body")
    
    url = f"{BASE_URL}/auth/refresh"
    payload = {"refresh_token": "not-a-jwt-token"}
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 401:
        print_fail(f"Expected 401, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "Invalid refresh token" not in detail:
        print_fail(f"Expected 'Invalid refresh token', got: {detail}")
        return False
    
    print_pass(f"Invalid token correctly rejected with 401 and detail: '{detail}'")
    return True

# ============================================================================
# TEST 7: POST /api/auth/refresh with wrong token type (access token instead of refresh)
# ============================================================================
def test_refresh_wrong_token_type(access_token):
    print_test("POST /api/auth/refresh with wrong token type (access token instead of refresh)")
    
    url = f"{BASE_URL}/auth/refresh"
    payload = {"refresh_token": access_token}  # Send access token instead of refresh
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 401:
        print_fail(f"Expected 401, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "Invalid token type" not in detail:
        print_fail(f"Expected 'Invalid token type', got: {detail}")
        return False
    
    print_pass(f"Wrong token type correctly rejected with 401 and detail: '{detail}'")
    return True

# ============================================================================
# TEST 8: GET /api/auth/me with Bearer token (no cookies)
# ============================================================================
def test_auth_me(access_token):
    print_test("GET /api/auth/me with Bearer token (no cookies)")
    
    url = f"{BASE_URL}/auth/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    resp = requests.get(url, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    if data.get("email") != ADMIN_EMAIL:
        print_fail(f"Expected email '{ADMIN_EMAIL}', got: {data.get('email')}")
        return False
    
    if data.get("role") != "admin":
        print_fail(f"Expected role 'admin', got: {data.get('role')}")
        return False
    
    print_pass(f"Auth /me successful with Bearer token only (no cookies)")
    print_info(f"User: {data.get('email')} (role: {data.get('role')})")
    return True

# ============================================================================
# TEST 9: Regression check - Phase 2 endpoints still work with Bearer token only
# ============================================================================
def test_phase2_regression(access_token):
    print_test("Regression check - Phase 2 endpoints with Bearer token only")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Test 1: GET /api/fg-inventory
    print_info("Testing GET /api/fg-inventory")
    resp = requests.get(f"{BASE_URL}/fg-inventory", headers=headers)
    print_info(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print_fail(f"GET /api/fg-inventory failed with {resp.status_code}")
        return False
    print_pass("GET /api/fg-inventory works")
    
    # Test 2: GET /api/fg-inventory/movements
    print_info("Testing GET /api/fg-inventory/movements")
    resp = requests.get(f"{BASE_URL}/fg-inventory/movements", headers=headers)
    print_info(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print_fail(f"GET /api/fg-inventory/movements failed with {resp.status_code}")
        return False
    print_pass("GET /api/fg-inventory/movements works")
    
    # Test 3: POST /api/fg-inventory/movements (smoke test with production_in)
    print_info("Testing POST /api/fg-inventory/movements")
    
    # First, get a style_id to use
    styles_resp = requests.get(f"{BASE_URL}/styles", headers=headers)
    if styles_resp.status_code != 200:
        print_info("No styles available, skipping POST movement test")
        return True
    
    styles = styles_resp.json()
    if not styles:
        print_info("No styles available, skipping POST movement test")
        return True
    
    style_id = styles[0]["id"]
    
    movement_payload = {
        "style_id": style_id,
        "color": "TestColor",
        "size": "8",
        "movement_type": "production_in",
        "quantity": 10,
        "reference_type": "manual",
        "notes": "Regression test movement"
    }
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/movements", json=movement_payload, headers=headers)
    print_info(f"Status: {resp.status_code}")
    if resp.status_code not in [200, 201]:
        print_fail(f"POST /api/fg-inventory/movements failed with {resp.status_code}: {resp.text[:200]}")
        return False
    print_pass("POST /api/fg-inventory/movements works")
    
    print_pass("All Phase 2 regression checks passed")
    return True

# ============================================================================
# TEST 10: Rate limit check - 5 wrong-password attempts → 429
# ============================================================================
def test_rate_limit():
    print_test("Rate limit check - 5 wrong-password attempts → 429")
    
    url = f"{BASE_URL}/auth/login"
    
    print_info("Attempting 5 failed logins to trigger rate limit...")
    
    for i in range(1, 6):
        payload = {"email": ADMIN_EMAIL, "password": f"wrongpass{i}"}
        resp = requests.post(url, json=payload)
        print_info(f"Attempt {i}: Status {resp.status_code}")
        
        if resp.status_code != 401:
            print_fail(f"Expected 401 on attempt {i}, got {resp.status_code}")
            return False
    
    # 6th attempt should be rate-limited
    print_info("Attempting 6th failed login (should be rate-limited)...")
    payload = {"email": ADMIN_EMAIL, "password": "wrongpass6"}
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 429:
        print_fail(f"Expected 429 (rate limited), got {resp.status_code}")
        print_info("NOTE: Rate limiting is per-backend-pod (in-memory). On load-balanced environments, it may take more attempts.")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "Too many failed login attempts" not in detail:
        print_fail(f"Expected 'Too many failed login attempts', got: {detail}")
        return False
    
    print_pass(f"Rate limit correctly triggered after 5 failed attempts with 429 and detail: '{detail}'")
    
    # Test that correct credentials are also blocked during lockout
    print_info("Testing that correct credentials are also blocked during lockout...")
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 429:
        print_fail(f"Expected 429 (rate limited) even with correct credentials, got {resp.status_code}")
        return False
    
    print_pass("Correct credentials also blocked during lockout (as expected)")
    return True

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print("\n" + "="*80)
    print("BACKEND AUTH BUG FIX VERIFICATION TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("="*80)
    
    results = {}
    
    # Test 1: Login with correct credentials
    access_token, refresh_token = test_login_success()
    results["login_success"] = (access_token is not None and refresh_token is not None)
    
    if not results["login_success"]:
        print("\n❌ CRITICAL: Login failed, cannot continue with other tests")
        sys.exit(1)
    
    # Test 2: Login with wrong password
    results["login_wrong_password"] = test_login_wrong_password()
    
    # Test 3: Refresh with body flow (new)
    new_access_token = test_refresh_body_flow(refresh_token)
    results["refresh_body_flow"] = (new_access_token is not None)
    
    # Test 4: Refresh with cookie flow (legacy)
    cookie_access_token = test_refresh_cookie_flow(refresh_token)
    results["refresh_cookie_flow"] = (cookie_access_token is not None)
    
    # Test 5: Refresh with missing token
    results["refresh_missing_token"] = test_refresh_missing_token()
    
    # Test 6: Refresh with invalid token
    results["refresh_invalid_token"] = test_refresh_invalid_token()
    
    # Test 7: Refresh with wrong token type
    results["refresh_wrong_token_type"] = test_refresh_wrong_token_type(access_token)
    
    # Test 8: Auth /me with Bearer token
    results["auth_me"] = test_auth_me(access_token)
    
    # Test 9: Phase 2 regression check
    results["phase2_regression"] = test_phase2_regression(access_token)
    
    # Test 10: Rate limit check
    results["rate_limit"] = test_rate_limit()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
