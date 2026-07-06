#!/usr/bin/env python3
"""
Backend test suite for Phase 2 bulk stock-entry endpoints.

Tests:
1. POST /api/fg-inventory/bulk-movements — happy path
2. POST /api/fg-inventory/bulk-movements — partial-success (mix of valid + invalid)
3. POST /api/fg-inventory/bulk-movements — batch too large (2001 movements)
4. POST /api/fg-inventory/bulk-movements — empty list
5. GET /api/fg-inventory/csv-template
6. POST /api/fg-inventory/import-csv?dry_run=true — happy path + errors
7. POST /api/fg-inventory/import-csv?dry_run=false — commit
8. CSV missing required column
9. CSV import — adjustment_field enforcement
10. Regression smoke: previously-passing endpoints still work
"""

import requests
import json
import sys
import io

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
# SETUP: Login and get access token
# ============================================================================
def login():
    print_test("SETUP: Login to get access token")
    
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    resp = requests.post(url, json=payload)
    
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"Login failed with {resp.status_code}: {resp.text[:500]}")
        return None
    
    data = resp.json()
    access_token = data.get("access_token")
    
    if not access_token:
        print_fail("No access_token in response")
        return None
    
    print_pass(f"Login successful, got access token")
    return access_token

# ============================================================================
# SETUP: Get or create a style to use for testing
# ============================================================================
def get_or_create_style(headers):
    print_test("SETUP: Get or create a style for testing")
    
    # Try to get existing styles
    resp = requests.get(f"{BASE_URL}/styles", headers=headers)
    
    if resp.status_code == 200:
        styles = resp.json()
        if styles:
            style = styles[0]
            print_pass(f"Using existing style: {style['id']} (code: {style.get('code', 'N/A')})")
            return style['id'], style.get('code', 'TEST-STYLE')
    
    # Create a new style
    print_info("No existing styles found, creating a new one...")
    
    payload = {
        "code": "TEST-BULK-001",
        "name": "Test Style for Bulk Operations",
        "category": "Footwear",
        "brand": "Test Brand"
    }
    
    resp = requests.post(f"{BASE_URL}/styles", json=payload, headers=headers)
    
    if resp.status_code not in [200, 201]:
        print_fail(f"Failed to create style: {resp.status_code} - {resp.text[:500]}")
        return None, None
    
    data = resp.json()
    style_id = data.get("id")
    style_code = data.get("code", "TEST-BULK-001")
    
    print_pass(f"Created new style: {style_id} (code: {style_code})")
    return style_id, style_code

# ============================================================================
# TEST 1: POST /api/fg-inventory/bulk-movements — happy path
# ============================================================================
def test_bulk_movements_happy_path(headers, style_id):
    print_test("TEST 1: POST /api/fg-inventory/bulk-movements — happy path")
    
    payload = {
        "movements": [
            {
                "style_id": style_id,
                "color": "BULK-A",
                "size": "41",
                "movement_type": "production_in",
                "quantity": 5,
                "reference_type": "manual"
            },
            {
                "style_id": style_id,
                "color": "BULK-A",
                "size": "42",
                "movement_type": "production_in",
                "quantity": 7,
                "reference_type": "manual"
            },
            {
                "style_id": style_id,
                "color": "BULK-B",
                "size": "41",
                "movement_type": "production_in",
                "quantity": 3,
                "reference_type": "manual"
            }
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/bulk-movements", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check response structure
    if data.get("total") != 3:
        print_fail(f"Expected total=3, got {data.get('total')}")
        return False
    
    if data.get("success") != 3:
        print_fail(f"Expected success=3, got {data.get('success')}")
        return False
    
    if data.get("failed") != 0:
        print_fail(f"Expected failed=0, got {data.get('failed')}")
        return False
    
    results = data.get("results", [])
    if len(results) != 3:
        print_fail(f"Expected 3 results, got {len(results)}")
        return False
    
    # Check all results have ok=True
    for i, result in enumerate(results):
        if not result.get("ok"):
            print_fail(f"Result {i} has ok=False: {result}")
            return False
        if "delta" not in result:
            print_fail(f"Result {i} missing 'delta' field")
            return False
    
    print_pass("Bulk movements happy path successful: 3/3 movements applied")
    
    # Verify inventory rows were created
    print_info("Verifying inventory rows...")
    resp = requests.get(f"{BASE_URL}/fg-inventory/by-style/{style_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Failed to fetch inventory by style: {resp.status_code}")
        return False
    
    inv_data = resp.json()
    rows = inv_data.get("rows", [])
    
    # Check for the three (color, size) combinations
    expected = [
        ("BULK-A", "41", 5),
        ("BULK-A", "42", 7),
        ("BULK-B", "41", 3)
    ]
    
    for color, size, qty in expected:
        found = False
        for row in rows:
            if row.get("color") == color and row.get("size") == size:
                found = True
                if row.get("ready_stock_qty") != qty:
                    print_fail(f"Expected ready_stock_qty={qty} for {color}/{size}, got {row.get('ready_stock_qty')}")
                    return False
                break
        
        if not found:
            print_fail(f"Inventory row not found for {color}/{size}")
            return False
    
    print_pass("All 3 inventory rows verified with correct quantities")
    return True

# ============================================================================
# TEST 2: POST /api/fg-inventory/bulk-movements — partial-success
# ============================================================================
def test_bulk_movements_partial_success(headers, style_id):
    print_test("TEST 2: POST /api/fg-inventory/bulk-movements — partial-success")
    
    payload = {
        "movements": [
            # Valid: production_in of 4
            {
                "style_id": style_id,
                "color": "PARTIAL-TEST",
                "size": "40",
                "movement_type": "production_in",
                "quantity": 4,
                "reference_type": "manual"
            },
            # Invalid: dispatched on a (color,size) with 0 stock → should fail
            {
                "style_id": style_id,
                "color": "NONEXISTENT-COLOR",
                "size": "99",
                "movement_type": "dispatched",
                "quantity": 10,
                "reference_type": "manual"
            },
            # Invalid: unresolvable style_id
            {
                "style_id": "000000000000000000000000",
                "color": "ANY",
                "size": "50",
                "movement_type": "production_in",
                "quantity": 5,
                "reference_type": "manual"
            }
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/bulk-movements", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check response structure
    if data.get("total") != 3:
        print_fail(f"Expected total=3, got {data.get('total')}")
        return False
    
    if data.get("success") != 1:
        print_fail(f"Expected success=1, got {data.get('success')}")
        return False
    
    if data.get("failed") != 2:
        print_fail(f"Expected failed=2, got {data.get('failed')}")
        return False
    
    results = data.get("results", [])
    if len(results) != 3:
        print_fail(f"Expected 3 results, got {len(results)}")
        return False
    
    # Check result 0 is ok=True
    if not results[0].get("ok"):
        print_fail(f"Result 0 should be ok=True, got: {results[0]}")
        return False
    
    # Check results 1 and 2 are ok=False with error messages
    if results[1].get("ok"):
        print_fail(f"Result 1 should be ok=False, got: {results[1]}")
        return False
    
    if not results[1].get("error"):
        print_fail(f"Result 1 should have 'error' field")
        return False
    
    if results[2].get("ok"):
        print_fail(f"Result 2 should be ok=False, got: {results[2]}")
        return False
    
    if not results[2].get("error"):
        print_fail(f"Result 2 should have 'error' field")
        return False
    
    print_pass("Partial-success test passed: 1 valid movement applied, 2 failed with errors")
    
    # Verify the valid movement was applied
    print_info("Verifying the valid movement was applied...")
    resp = requests.get(f"{BASE_URL}/fg-inventory/by-style/{style_id}", headers=headers)
    
    if resp.status_code != 200:
        print_fail(f"Failed to fetch inventory by style: {resp.status_code}")
        return False
    
    inv_data = resp.json()
    rows = inv_data.get("rows", [])
    
    found = False
    for row in rows:
        if row.get("color") == "PARTIAL-TEST" and row.get("size") == "40":
            found = True
            if row.get("ready_stock_qty") != 4:
                print_fail(f"Expected ready_stock_qty=4, got {row.get('ready_stock_qty')}")
                return False
            break
    
    if not found:
        print_fail("Valid movement was not applied to inventory")
        return False
    
    print_pass("Valid movement verified in inventory")
    return True

# ============================================================================
# TEST 3: POST /api/fg-inventory/bulk-movements — batch too large
# ============================================================================
def test_bulk_movements_too_large(headers, style_id):
    print_test("TEST 3: POST /api/fg-inventory/bulk-movements — batch too large")
    
    # Create 2001 movements
    movements = []
    for i in range(2001):
        movements.append({
            "style_id": style_id,
            "color": f"COLOR-{i}",
            "size": "40",
            "movement_type": "production_in",
            "quantity": 1,
            "reference_type": "manual"
        })
    
    payload = {"movements": movements}
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/bulk-movements", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 400:
        print_fail(f"Expected 400, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "max 2000" not in detail.lower():
        print_fail(f"Expected error message mentioning 'max 2000', got: {detail}")
        return False
    
    print_pass("Batch too large correctly rejected with 400 and appropriate error message")
    return True

# ============================================================================
# TEST 4: POST /api/fg-inventory/bulk-movements — empty list
# ============================================================================
def test_bulk_movements_empty_list(headers):
    print_test("TEST 4: POST /api/fg-inventory/bulk-movements — empty list")
    
    payload = {"movements": []}
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/bulk-movements", json=payload, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:500]}")
    
    if resp.status_code != 400:
        print_fail(f"Expected 400, got {resp.status_code}")
        return False
    
    data = resp.json()
    detail = data.get("detail", "")
    
    if "non-empty" not in detail.lower():
        print_fail(f"Expected error message mentioning 'non-empty', got: {detail}")
        return False
    
    print_pass("Empty list correctly rejected with 400")
    return True

# ============================================================================
# TEST 5: GET /api/fg-inventory/csv-template
# ============================================================================
def test_csv_template(headers):
    print_test("TEST 5: GET /api/fg-inventory/csv-template")
    
    resp = requests.get(f"{BASE_URL}/fg-inventory/csv-template", headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Content-Type: {resp.headers.get('Content-Type')}")
    print_info(f"Content-Disposition: {resp.headers.get('Content-Disposition')}")
    print_info(f"Response (first 500 chars): {resp.text[:500]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    content_type = resp.headers.get("Content-Type", "")
    if "text/csv" not in content_type:
        print_fail(f"Expected Content-Type 'text/csv', got: {content_type}")
        return False
    
    content_disp = resp.headers.get("Content-Disposition", "")
    if "fg_stock_template.csv" not in content_disp:
        print_fail(f"Expected Content-Disposition to contain 'fg_stock_template.csv', got: {content_disp}")
        return False
    
    # Check header line
    lines = resp.text.split('\n')
    if not lines:
        print_fail("CSV template is empty")
        return False
    
    header = lines[0]
    required_cols = ["style_code", "color", "size", "movement_type", "quantity"]
    
    for col in required_cols:
        if col not in header:
            print_fail(f"Header missing required column '{col}': {header}")
            return False
    
    print_pass("CSV template downloaded successfully with correct headers")
    return True

# ============================================================================
# TEST 6: POST /api/fg-inventory/import-csv?dry_run=true — happy path + errors
# ============================================================================
def test_csv_import_dry_run(headers, style_code):
    print_test("TEST 6: POST /api/fg-inventory/import-csv?dry_run=true — happy path + errors")
    
    # Create CSV with UTF-8 BOM, 5 rows:
    # - 2 valid production_in
    # - 1 valid adjustment
    # - 1 with bogus style_code
    # - 1 with quantity=0 (should be silently skipped)
    
    csv_content = (
        "\ufeff"  # UTF-8 BOM
        "style_code,color,size,movement_type,quantity,reference_type,adjustment_field,notes\n"
        f"{style_code},CSV-COLOR-1,36,production_in,10,manual,,Test row 1\n"
        f"{style_code},CSV-COLOR-2,37,production_in,15,manual,,Test row 2\n"
        f"{style_code},CSV-COLOR-3,38,adjustment,5,manual,ready_stock_qty,Test adjustment\n"
        "DOES-NOT-EXIST,CSV-COLOR-4,39,production_in,20,manual,,Bad style code\n"
        f"{style_code},CSV-COLOR-5,40,production_in,0,manual,,Should be skipped\n"
    )
    
    # Get inventory count before
    resp_before = requests.get(f"{BASE_URL}/fg-inventory", headers=headers)
    count_before = len(resp_before.json()) if resp_before.status_code == 200 else 0
    
    # Upload CSV
    files = {"file": ("test.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/fg-inventory/import-csv?dry_run=true", files=files, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:2000]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check dry_run flag
    if not data.get("dry_run"):
        print_fail("Expected dry_run=true in response")
        return False
    
    # Check parsed rows (should be 3: 2 production_in + 1 adjustment, NOT the qty=0 row)
    parsed = data.get("parsed", [])
    if len(parsed) != 3:
        print_fail(f"Expected 3 parsed rows (qty=0 should be skipped), got {len(parsed)}")
        return False
    
    # Check errors (should be 1: the bogus style_code)
    errors = data.get("errors", [])
    if len(errors) != 1:
        print_fail(f"Expected 1 error (bogus style_code), got {len(errors)}")
        return False
    
    error_msg = errors[0].get("error", "")
    if "Unknown style_code" not in error_msg:
        print_fail(f"Expected error mentioning 'Unknown style_code', got: {error_msg}")
        return False
    
    # Check summary
    summary = data.get("summary", {})
    if summary.get("valid") != 3:
        print_fail(f"Expected summary.valid=3, got {summary.get('valid')}")
        return False
    
    if summary.get("invalid") != 1:
        print_fail(f"Expected summary.invalid=1, got {summary.get('invalid')}")
        return False
    
    print_pass("CSV dry_run successful: 3 valid rows parsed, 1 error, qty=0 row skipped")
    
    # Verify NO new inventory rows were created
    resp_after = requests.get(f"{BASE_URL}/fg-inventory", headers=headers)
    count_after = len(resp_after.json()) if resp_after.status_code == 200 else 0
    
    if count_after != count_before:
        print_fail(f"Inventory count changed during dry_run: before={count_before}, after={count_after}")
        return False
    
    print_pass("Verified: No inventory rows created during dry_run")
    return True

# ============================================================================
# TEST 7: POST /api/fg-inventory/import-csv?dry_run=false — commit
# ============================================================================
def test_csv_import_commit(headers, style_code, style_id):
    print_test("TEST 7: POST /api/fg-inventory/import-csv?dry_run=false — commit")
    
    # Create CSV with only valid rows
    csv_content = (
        "style_code,color,size,movement_type,quantity,reference_type,notes\n"
        f"{style_code},CSV-COMMIT-1,36,production_in,12,manual,Commit test 1\n"
        f"{style_code},CSV-COMMIT-2,37,production_in,18,manual,Commit test 2\n"
    )
    
    # Get movements count before
    resp_before = requests.get(f"{BASE_URL}/fg-inventory/movements?style_id={style_id}", headers=headers)
    movements_before = len(resp_before.json()) if resp_before.status_code == 200 else 0
    
    # Upload CSV
    files = {"file": ("test_commit.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/fg-inventory/import-csv?dry_run=false", files=files, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:2000]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check committed flag
    if not data.get("committed"):
        print_fail("Expected committed=true in response")
        return False
    
    # Check results
    results = data.get("results", [])
    if len(results) != 2:
        print_fail(f"Expected 2 results, got {len(results)}")
        return False
    
    # All results should have ok=True
    for i, result in enumerate(results):
        if not result.get("ok"):
            print_fail(f"Result {i} has ok=False: {result}")
            return False
    
    print_pass("CSV commit successful: 2 rows applied")
    
    # Verify ledger rows were created
    resp_after = requests.get(f"{BASE_URL}/fg-inventory/movements?style_id={style_id}", headers=headers)
    movements_after = len(resp_after.json()) if resp_after.status_code == 200 else 0
    
    if movements_after <= movements_before:
        print_fail(f"No new movements created: before={movements_before}, after={movements_after}")
        return False
    
    print_pass(f"Verified: {movements_after - movements_before} new movement(s) in ledger")
    
    # Verify inventory rows were updated
    resp_inv = requests.get(f"{BASE_URL}/fg-inventory/by-style/{style_id}", headers=headers)
    
    if resp_inv.status_code != 200:
        print_fail(f"Failed to fetch inventory: {resp_inv.status_code}")
        return False
    
    inv_data = resp_inv.json()
    rows = inv_data.get("rows", [])
    
    # Check for the two (color, size) combinations
    expected = [
        ("CSV-COMMIT-1", "36", 12),
        ("CSV-COMMIT-2", "37", 18)
    ]
    
    for color, size, qty in expected:
        found = False
        for row in rows:
            if row.get("color") == color and row.get("size") == size:
                found = True
                if row.get("ready_stock_qty") != qty:
                    print_fail(f"Expected ready_stock_qty={qty} for {color}/{size}, got {row.get('ready_stock_qty')}")
                    return False
                break
        
        if not found:
            print_fail(f"Inventory row not found for {color}/{size}")
            return False
    
    print_pass("Verified: Inventory rows updated with correct quantities")
    return True

# ============================================================================
# TEST 8: CSV missing required column
# ============================================================================
def test_csv_missing_column(headers, style_code):
    print_test("TEST 8: CSV missing required column")
    
    # CSV missing "color" column
    csv_content = (
        "style_code,size,quantity\n"
        f"{style_code},40,10\n"
        f"{style_code},41,15\n"
    )
    
    files = {"file": ("test_missing_col.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/fg-inventory/import-csv?dry_run=true", files=files, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200 (per-line errors), got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check errors
    errors = data.get("errors", [])
    if len(errors) != 2:
        print_fail(f"Expected 2 errors (one per row), got {len(errors)}")
        return False
    
    # Both errors should mention "Missing color"
    for error in errors:
        error_msg = error.get("error", "")
        if "Missing color" not in error_msg:
            print_fail(f"Expected error mentioning 'Missing color', got: {error_msg}")
            return False
    
    print_pass("CSV with missing column correctly produces per-line errors")
    return True

# ============================================================================
# TEST 9: CSV import — adjustment_field enforcement
# ============================================================================
def test_csv_adjustment_field_enforcement(headers, style_code):
    print_test("TEST 9: CSV import — adjustment_field enforcement")
    
    # CSV with movement_type=adjustment but NO adjustment_field
    csv_content = (
        "style_code,color,size,movement_type,quantity,reference_type\n"
        f"{style_code},ADJ-TEST,40,adjustment,5,manual\n"
    )
    
    files = {"file": ("test_adj.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/fg-inventory/import-csv?dry_run=true", files=files, headers=headers)
    
    print_info(f"Status: {resp.status_code}")
    print_info(f"Response: {resp.text[:1000]}")
    
    if resp.status_code != 200:
        print_fail(f"Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check errors
    errors = data.get("errors", [])
    if len(errors) != 1:
        print_fail(f"Expected 1 error, got {len(errors)}")
        return False
    
    error_msg = errors[0].get("error", "")
    if "adjustment_field is required" not in error_msg:
        print_fail(f"Expected error mentioning 'adjustment_field is required', got: {error_msg}")
        return False
    
    print_pass("CSV adjustment without adjustment_field correctly produces error")
    return True

# ============================================================================
# TEST 10: Regression smoke — previously-passing endpoints still work
# ============================================================================
def test_regression_smoke(headers, style_id):
    print_test("TEST 10: Regression smoke — previously-passing endpoints")
    
    # Test 1: POST /api/fg-inventory/movements (single movement)
    print_info("Testing POST /api/fg-inventory/movements (single)")
    
    movement_payload = {
        "style_id": style_id,
        "color": "REGRESSION-TEST",
        "size": "42",
        "movement_type": "production_in",
        "quantity": 8,
        "reference_type": "manual",
        "notes": "Regression smoke test"
    }
    
    resp = requests.post(f"{BASE_URL}/fg-inventory/movements", json=movement_payload, headers=headers)
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code not in [200, 201]:
        print_fail(f"POST /api/fg-inventory/movements failed with {resp.status_code}: {resp.text[:200]}")
        return False
    
    print_pass("POST /api/fg-inventory/movements works")
    
    # Test 2: GET /api/fg-inventory
    print_info("Testing GET /api/fg-inventory")
    
    resp = requests.get(f"{BASE_URL}/fg-inventory", headers=headers)
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"GET /api/fg-inventory failed with {resp.status_code}")
        return False
    
    data = resp.json()
    if not isinstance(data, list):
        print_fail(f"Expected list response, got: {type(data)}")
        return False
    
    print_pass("GET /api/fg-inventory works")
    
    # Test 3: GET /api/fg-inventory/by-style/{style_id}
    print_info("Testing GET /api/fg-inventory/by-style/{style_id}")
    
    resp = requests.get(f"{BASE_URL}/fg-inventory/by-style/{style_id}", headers=headers)
    print_info(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print_fail(f"GET /api/fg-inventory/by-style failed with {resp.status_code}")
        return False
    
    data = resp.json()
    if "rows" not in data:
        print_fail(f"Expected 'rows' in response, got: {data.keys()}")
        return False
    
    print_pass("GET /api/fg-inventory/by-style works")
    
    print_pass("All regression smoke tests passed")
    return True

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print("\n" + "="*80)
    print("BACKEND BULK STOCK-ENTRY ENDPOINTS TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("="*80)
    
    # Login
    access_token = login()
    if not access_token:
        print("\n❌ CRITICAL: Login failed, cannot continue")
        sys.exit(1)
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Get or create a style
    style_id, style_code = get_or_create_style(headers)
    if not style_id:
        print("\n❌ CRITICAL: Failed to get/create style, cannot continue")
        sys.exit(1)
    
    # Run tests
    results = {}
    
    results["test_1_bulk_happy_path"] = test_bulk_movements_happy_path(headers, style_id)
    results["test_2_bulk_partial_success"] = test_bulk_movements_partial_success(headers, style_id)
    results["test_3_bulk_too_large"] = test_bulk_movements_too_large(headers, style_id)
    results["test_4_bulk_empty_list"] = test_bulk_movements_empty_list(headers)
    results["test_5_csv_template"] = test_csv_template(headers)
    results["test_6_csv_dry_run"] = test_csv_import_dry_run(headers, style_code)
    results["test_7_csv_commit"] = test_csv_import_commit(headers, style_code, style_id)
    results["test_8_csv_missing_column"] = test_csv_missing_column(headers, style_code)
    results["test_9_csv_adjustment_field"] = test_csv_adjustment_field_enforcement(headers, style_code)
    results["test_10_regression_smoke"] = test_regression_smoke(headers, style_id)
    
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
