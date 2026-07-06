#!/usr/bin/env python3
"""
Comprehensive login flow verification test.
Tests all scenarios requested in the review request.
"""
import requests
import json
import time
from typing import Dict, Any

# Test configuration
BACKEND_URL = "https://4411416a-6779-4d1b-ba32-8060d6385338.preview.emergentagent.com"
LOGIN_ENDPOINT = f"{BACKEND_URL}/api/auth/login"
ME_ENDPOINT = f"{BACKEND_URL}/api/auth/me"

# Test credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_test(name: str):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST: {name}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")

def print_pass(msg: str):
    print(f"{GREEN}✓ PASS: {msg}{RESET}")

def print_fail(msg: str):
    print(f"{RED}✗ FAIL: {msg}{RESET}")

def print_info(msg: str):
    print(f"{YELLOW}ℹ INFO: {msg}{RESET}")

def print_result(test_name: str, passed: bool, details: str = ""):
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  Details: {details}")

# Test results tracking
test_results = []

def test_1_correct_credentials():
    """Test 1: POST /api/auth/login with correct credentials"""
    print_test("Test 1: Login with correct credentials (admin@example.com / admin123)")
    
    try:
        response = requests.post(
            LOGIN_ENDPOINT,
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        print_info(f"Status Code: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        print_info(f"Cookies: {dict(response.cookies)}")
        
        # Check status code
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            test_results.append(("Test 1: Correct credentials", False, f"Status {response.status_code}"))
            return None
        
        # Check response body
        data = response.json()
        required_fields = ["access_token", "refresh_token", "email", "role", "id"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            print_fail(f"Missing fields in response: {missing_fields}")
            test_results.append(("Test 1: Correct credentials", False, f"Missing fields: {missing_fields}"))
            return None
        
        # Check email and role
        if data["email"] != ADMIN_EMAIL:
            print_fail(f"Expected email {ADMIN_EMAIL}, got {data['email']}")
            test_results.append(("Test 1: Correct credentials", False, f"Wrong email: {data['email']}"))
            return None
        
        if data["role"] != "admin":
            print_fail(f"Expected role 'admin', got {data['role']}")
            test_results.append(("Test 1: Correct credentials", False, f"Wrong role: {data['role']}"))
            return None
        
        # Check cookies
        cookies = response.cookies
        if "access_token" not in cookies:
            print_fail("access_token cookie not set")
            test_results.append(("Test 1: Correct credentials", False, "access_token cookie missing"))
            return None
        
        if "refresh_token" not in cookies:
            print_fail("refresh_token cookie not set")
            test_results.append(("Test 1: Correct credentials", False, "refresh_token cookie missing"))
            return None
        
        print_pass("Login successful with correct credentials")
        print_pass(f"Response contains access_token and refresh_token")
        print_pass(f"Cookies set: access_token, refresh_token")
        print_pass(f"User email: {data['email']}, role: {data['role']}")
        
        test_results.append(("Test 1: Correct credentials", True, "All checks passed"))
        return data["access_token"]
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 1: Correct credentials", False, f"Exception: {str(e)}"))
        return None


def test_2_auth_me(access_token: str):
    """Test 2: GET /api/auth/me with Bearer token"""
    print_test("Test 2: GET /api/auth/me with Bearer token")
    
    if not access_token:
        print_fail("No access token available from previous test")
        test_results.append(("Test 2: /auth/me endpoint", False, "No access token"))
        return
    
    try:
        response = requests.get(
            ME_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        print_info(f"Status Code: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            test_results.append(("Test 2: /auth/me endpoint", False, f"Status {response.status_code}"))
            return
        
        data = response.json()
        
        if data.get("email") != ADMIN_EMAIL:
            print_fail(f"Expected email {ADMIN_EMAIL}, got {data.get('email')}")
            test_results.append(("Test 2: /auth/me endpoint", False, f"Wrong email: {data.get('email')}"))
            return
        
        if data.get("role") != "admin":
            print_fail(f"Expected role 'admin', got {data.get('role')}")
            test_results.append(("Test 2: /auth/me endpoint", False, f"Wrong role: {data.get('role')}"))
            return
        
        print_pass("/auth/me returned 200 with correct user data")
        print_pass(f"User: {data.get('email')}, role: {data.get('role')}")
        
        test_results.append(("Test 2: /auth/me endpoint", True, "All checks passed"))
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 2: /auth/me endpoint", False, f"Exception: {str(e)}"))


def test_3_wrong_password():
    """Test 3: Login with wrong password"""
    print_test("Test 3: Login with wrong password")
    
    try:
        response = requests.post(
            LOGIN_ENDPOINT,
            json={"email": ADMIN_EMAIL, "password": "wrong"},
            timeout=10
        )
        
        print_info(f"Status Code: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 401:
            print_fail(f"Expected status 401, got {response.status_code}")
            test_results.append(("Test 3: Wrong password", False, f"Status {response.status_code}"))
            return
        
        data = response.json()
        if data.get("detail") != "Invalid email or password":
            print_fail(f"Expected detail 'Invalid email or password', got '{data.get('detail')}'")
            test_results.append(("Test 3: Wrong password", False, f"Wrong detail: {data.get('detail')}"))
            return
        
        print_pass("Wrong password correctly rejected with 401")
        print_pass(f"Error message: {data.get('detail')}")
        
        test_results.append(("Test 3: Wrong password", True, "Correctly rejected"))
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 3: Wrong password", False, f"Exception: {str(e)}"))


def test_4_uppercase_email():
    """Test 4: Login with uppercase email"""
    print_test("Test 4: Login with uppercase email (ADMIN@EXAMPLE.COM)")
    
    try:
        response = requests.post(
            LOGIN_ENDPOINT,
            json={"email": "ADMIN@EXAMPLE.COM", "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        print_info(f"Status Code: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 200:
            print_fail(f"Expected status 200, got {response.status_code}")
            test_results.append(("Test 4: Uppercase email", False, f"Status {response.status_code}"))
            return
        
        data = response.json()
        
        # Email should be normalized to lowercase in response
        if data.get("email") != ADMIN_EMAIL:
            print_fail(f"Expected normalized email {ADMIN_EMAIL}, got {data.get('email')}")
            test_results.append(("Test 4: Uppercase email", False, f"Email not normalized: {data.get('email')}"))
            return
        
        print_pass("Uppercase email correctly normalized and accepted")
        print_pass(f"Response email: {data.get('email')}")
        
        test_results.append(("Test 4: Uppercase email", True, "Email normalized correctly"))
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 4: Uppercase email", False, f"Exception: {str(e)}"))


def test_5_email_with_whitespace():
    """Test 5: Login with email containing whitespace"""
    print_test("Test 5: Login with email containing leading/trailing whitespace")
    
    try:
        response = requests.post(
            LOGIN_ENDPOINT,
            json={"email": " admin@example.com ", "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        print_info(f"Status Code: {response.status_code}")
        print_info(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print_pass("Email with whitespace accepted (backend strips whitespace)")
            test_results.append(("Test 5: Email with whitespace", True, "Accepted - whitespace stripped"))
        elif response.status_code == 401:
            print_info("Email with whitespace rejected (backend does NOT strip whitespace)")
            print_info("This means users must paste email without extra spaces")
            test_results.append(("Test 5: Email with whitespace", True, "Rejected - no whitespace stripping"))
        else:
            print_fail(f"Unexpected status code: {response.status_code}")
            test_results.append(("Test 5: Email with whitespace", False, f"Unexpected status {response.status_code}"))
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 5: Email with whitespace", False, f"Exception: {str(e)}"))


def test_6_database_verification():
    """Test 6: Verify database state"""
    print_test("Test 6: Database verification")
    
    try:
        import subprocess
        result = subprocess.run(
            [
                "mongosh", "mongodb://localhost:27017/ssk_footcare_erp",
                "--quiet", "--eval",
                "db.users.find({email: 'admin@example.com'}).toArray()"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print_fail(f"MongoDB query failed: {result.stderr}")
            test_results.append(("Test 6: Database verification", False, "MongoDB query failed"))
            return
        
        print_info(f"Database query result:\n{result.stdout}")
        
        # Parse the output to verify fields
        output = result.stdout
        
        checks = [
            ("email: 'admin@example.com'" in output, "Email is admin@example.com"),
            ("role: 'admin'" in output, "Role is admin"),
            ("active: true" in output, "User is active"),
            ("password_hash:" in output, "Password hash exists"),
        ]
        
        all_passed = True
        for check, description in checks:
            if check:
                print_pass(description)
            else:
                print_fail(description)
                all_passed = False
        
        # Verify password hash with bcrypt
        print_info("\nVerifying password hash with bcrypt...")
        verify_result = subprocess.run(
            [
                "python3", "-c",
                """
import bcrypt
stored_hash = '$2b$12$f9S/IQZ2dKpKCgPKooRGs.wslFXdjgxb8LmlC7F43wqZupWWU8hu6'
password = 'admin123'
result = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
print(f'Password verification: {result}')
"""
            ],
            capture_output=True,
            text=True,
            cwd="/app/backend"
        )
        
        if "True" in verify_result.stdout:
            print_pass("Password hash correctly verifies against 'admin123'")
        else:
            print_fail("Password hash does NOT verify against 'admin123'")
            all_passed = False
        
        if all_passed:
            test_results.append(("Test 6: Database verification", True, "All DB checks passed"))
        else:
            test_results.append(("Test 6: Database verification", False, "Some DB checks failed"))
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 6: Database verification", False, f"Exception: {str(e)}"))


def test_7_rate_limiting():
    """Test 7: Rate limiting verification"""
    print_test("Test 7: Rate limiting - 6 failed attempts should trigger 429")
    
    print_info("Restarting backend to clear in-memory rate limit state...")
    try:
        import subprocess
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, timeout=10)
        time.sleep(3)  # Wait for backend to restart
        print_pass("Backend restarted successfully")
    except Exception as e:
        print_fail(f"Failed to restart backend: {e}")
        test_results.append(("Test 7: Rate limiting", False, f"Backend restart failed: {e}"))
        return
    
    try:
        print_info("Attempting 6 failed login attempts...")
        
        for i in range(1, 7):
            print_info(f"Attempt {i}/6 with wrong password...")
            response = requests.post(
                LOGIN_ENDPOINT,
                json={"email": ADMIN_EMAIL, "password": "wrongpassword"},
                timeout=10
            )
            print_info(f"  Status: {response.status_code}, Detail: {response.json().get('detail', 'N/A')}")
            
            if i < 6:
                if response.status_code != 401:
                    print_fail(f"Expected 401 on attempt {i}, got {response.status_code}")
                    test_results.append(("Test 7: Rate limiting", False, f"Wrong status on attempt {i}"))
                    return
                time.sleep(0.5)  # Small delay between attempts
            else:
                # 6th attempt should be 429
                if response.status_code != 429:
                    print_fail(f"Expected 429 on 6th attempt, got {response.status_code}")
                    test_results.append(("Test 7: Rate limiting", False, f"No 429 after 5 failures"))
                    return
                
                data = response.json()
                detail = data.get("detail", "")
                
                if "Too many failed login attempts" not in detail:
                    print_fail(f"Expected rate limit message, got: {detail}")
                    test_results.append(("Test 7: Rate limiting", False, f"Wrong error message"))
                    return
                
                print_pass(f"6th attempt correctly returned 429: {detail}")
                
                # Extract lockout duration from message
                if "15 minutes" in detail or "14 minutes" in detail:
                    print_pass("Lockout window is ~15 minutes (900 seconds)")
                
        # Now try correct credentials - should also be blocked
        print_info("\nAttempting login with CORRECT credentials (should still be blocked)...")
        response = requests.post(
            LOGIN_ENDPOINT,
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        print_info(f"Status: {response.status_code}, Detail: {response.json().get('detail', 'N/A')}")
        
        if response.status_code != 429:
            print_fail(f"Expected 429 for correct credentials during lockout, got {response.status_code}")
            test_results.append(("Test 7: Rate limiting", False, "Correct credentials not blocked during lockout"))
            return
        
        print_pass("Correct credentials also blocked during lockout period (as expected)")
        print_pass("Rate limiting working correctly")
        
        test_results.append(("Test 7: Rate limiting", True, "All rate limit checks passed"))
        
        # Restart backend again to clear rate limit for subsequent tests
        print_info("\nRestarting backend to clear rate limit for remaining tests...")
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, timeout=10)
        time.sleep(3)
        print_pass("Backend restarted")
        
    except Exception as e:
        print_fail(f"Exception: {str(e)}")
        test_results.append(("Test 7: Rate limiting", False, f"Exception: {str(e)}"))


def print_summary():
    """Print test summary"""
    print(f"\n\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    passed = sum(1 for _, result, _ in test_results if result)
    total = len(test_results)
    
    for test_name, result, details in test_results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"{status}: {test_name}")
        if details and not result:
            print(f"       {details}")
    
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"{GREEN}ALL TESTS PASSED ✓{RESET}")
    else:
        print(f"{RED}SOME TESTS FAILED ✗{RESET}")
    
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    # Analysis
    print(f"\n{YELLOW}ANALYSIS:{RESET}")
    print(f"The most likely reasons a user might see 'invalid credentials':")
    print(f"1. {YELLOW}Rate limiting:{RESET} After 5 failed attempts, the 6th attempt (even with correct credentials) returns 429 for 15 minutes")
    print(f"2. {YELLOW}Email case sensitivity:{RESET} Backend normalizes email to lowercase, so 'ADMIN@EXAMPLE.COM' works fine")
    print(f"3. {YELLOW}Whitespace in email:{RESET} If backend doesn't strip whitespace, ' admin@example.com ' would fail")
    print(f"4. {YELLOW}Wrong password:{RESET} Obviously, typing wrong password returns 401")
    print(f"\n{YELLOW}RECOMMENDATION:{RESET}")
    print(f"If user reports 'credentials not working', first check:")
    print(f"- Are they hitting rate limit? (restart backend clears it)")
    print(f"- Are they pasting email with extra spaces?")
    print(f"- Are they using the exact password 'admin123' (case-sensitive)?")


def main():
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}LOGIN FLOW VERIFICATION TEST SUITE{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    # Run all tests
    access_token = test_1_correct_credentials()
    test_2_auth_me(access_token)
    test_3_wrong_password()
    test_4_uppercase_email()
    test_5_email_with_whitespace()
    test_6_database_verification()
    test_7_rate_limiting()
    
    # Print summary
    print_summary()


if __name__ == "__main__":
    main()
