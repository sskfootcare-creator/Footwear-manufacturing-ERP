#!/usr/bin/env python3
"""
Phase 2 Backend Testing — Finished Goods Inventory + Reservation Engine
Tests the movement engine, ledger, reservations, and low_stock semantics.
"""
import requests
import json
import sys
from typing import Optional

# Backend URL from environment
BASE_URL = "https://4411416a-6779-4d1b-ba32-8060d6385338.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

# Global session with cookies
session = requests.Session()

def login():
    """Login as admin and store cookies."""
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    print(f"✅ Logged in as {ADMIN_EMAIL}")
    return resp.json()

def create_style(code: str, name: str) -> dict:
    """Create a test style."""
    payload = {
        "code": code,
        "name": name,
        "category": "Footwear",
        "base_size": "8",
        "bom": [],
        "labor": [],
        "overhead_pct": 10,
        "packing_cost": 15,
        "margin_pct": 25,
        "gst_pct": 5,
        "status": "active"
    }
    resp = session.post(f"{BASE_URL}/styles", json=payload)
    if resp.status_code in [200, 201]:
        print(f"✅ Created style {code}")
        return resp.json()
    elif resp.status_code == 409:
        # Already exists, fetch it
        resp = session.get(f"{BASE_URL}/styles")
        styles = resp.json()
        for s in styles:
            if s["code"] == code:
                print(f"✅ Style {code} already exists")
                return s
    print(f"❌ Failed to create style {code}: {resp.status_code} {resp.text}")
    sys.exit(1)

def post_movement(style_id: str, color: str, size: str, movement_type: str, 
                  quantity: int, online_order_id: Optional[str] = None,
                  adjustment_field: Optional[str] = None) -> dict:
    """POST /api/fg-inventory/movements"""
    payload = {
        "style_id": style_id,
        "color": color,
        "size": size,
        "movement_type": movement_type,
        "quantity": quantity,
        "reference_type": "manual",
        "reference_id": "",
        "notes": f"Test {movement_type}"
    }
    if online_order_id:
        payload["online_order_id"] = online_order_id
    if adjustment_field:
        payload["adjustment_field"] = adjustment_field
    
    resp = session.post(f"{BASE_URL}/fg-inventory/movements", json=payload)
    return resp

def get_movements(style_id: Optional[str] = None, movement_type: Optional[str] = None) -> list:
    """GET /api/fg-inventory/movements"""
    params = {}
    if style_id:
        params["style_id"] = style_id
    if movement_type:
        params["movement_type"] = movement_type
    resp = session.get(f"{BASE_URL}/fg-inventory/movements", params=params)
    if resp.status_code == 200:
        return resp.json()
    return []

def get_by_style(style_id: str) -> dict:
    """GET /api/fg-inventory/by-style/{style_id}"""
    resp = session.get(f"{BASE_URL}/fg-inventory/by-style/{style_id}")
    if resp.status_code == 200:
        return resp.json()
    return {}

def get_reservations(online_order_id: Optional[str] = None, status: Optional[str] = None) -> list:
    """GET /api/inventory-reservations"""
    params = {}
    if online_order_id:
        params["online_order_id"] = online_order_id
    if status:
        params["status"] = status
    resp = session.get(f"{BASE_URL}/inventory-reservations", params=params)
    if resp.status_code == 200:
        return resp.json()
    return []

def patch_inventory(inv_id: str, min_stock_level: int) -> dict:
    """PATCH /api/fg-inventory/{id}"""
    resp = session.patch(f"{BASE_URL}/fg-inventory/{inv_id}", json={
        "min_stock_level": min_stock_level
    })
    return resp

def test_movement_engine():
    """Test 1: Movement engine — POST /api/fg-inventory/movements"""
    print("\n" + "="*80)
    print("TEST 1: Movement Engine — POST /api/fg-inventory/movements")
    print("="*80)
    
    # Create a test style
    import time
    unique_suffix = str(int(time.time()))[-6:]
    style = create_style(f"TEST-P2-{unique_suffix}", f"Phase 2 Test Style {unique_suffix}")
    style_id = style["id"]
    color = f"Tan-{unique_suffix}"
    size = f"8-{unique_suffix}"
    
    # 1. production_in with qty=50
    print("\n1️⃣  Testing production_in qty=50...")
    resp = post_movement(style_id, color, size, "production_in", 50)
    if resp.status_code != 200:
        print(f"❌ production_in failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["ready_stock_qty"] != 50:
        print(f"❌ Expected ready_stock_qty=50, got {inv['ready_stock_qty']}")
        return False
    if inv["available_qty"] != 50:
        print(f"❌ Expected available_qty=50, got {inv['available_qty']}")
        return False
    if inv["is_low_stock"] != False:
        print(f"❌ Expected is_low_stock=False, got {inv['is_low_stock']}")
        return False
    print(f"✅ production_in: ready_stock_qty={inv['ready_stock_qty']}, available_qty={inv['available_qty']}, is_low_stock={inv['is_low_stock']}")
    
    inv_id = inv["id"]
    
    # 2. reserved with qty=10, online_order_id="ORD-TEST-1"
    print("\n2️⃣  Testing reserved qty=10 with online_order_id=ORD-TEST-1...")
    resp = post_movement(style_id, color, size, "reserved", 10, online_order_id="ORD-TEST-1")
    if resp.status_code != 200:
        print(f"❌ reserved failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["reserved_qty"] != 10:
        print(f"❌ Expected reserved_qty=10, got {inv['reserved_qty']}")
        return False
    if inv["available_qty"] != 40:
        print(f"❌ Expected available_qty=40, got {inv['available_qty']}")
        return False
    print(f"✅ reserved: reserved_qty={inv['reserved_qty']}, available_qty={inv['available_qty']}")
    
    # Check reservation row
    reservations = get_reservations(online_order_id="ORD-TEST-1")
    if len(reservations) != 1:
        print(f"❌ Expected 1 reservation for ORD-TEST-1, got {len(reservations)}")
        return False
    res = reservations[0]
    if res["status"] != "active" or res["qty"] != 10:
        print(f"❌ Reservation status={res['status']}, qty={res['qty']}")
        return False
    print(f"✅ Reservation created: status={res['status']}, qty={res['qty']}")
    
    # 3. dispatched with qty=10, online_order_id="ORD-TEST-1"
    print("\n3️⃣  Testing dispatched qty=10 with online_order_id=ORD-TEST-1...")
    resp = post_movement(style_id, color, size, "dispatched", 10, online_order_id="ORD-TEST-1")
    if resp.status_code != 200:
        print(f"❌ dispatched failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["ready_stock_qty"] != 40:
        print(f"❌ Expected ready_stock_qty=40, got {inv['ready_stock_qty']}")
        return False
    if inv["reserved_qty"] != 0:
        print(f"❌ Expected reserved_qty=0, got {inv['reserved_qty']}")
        return False
    print(f"✅ dispatched: ready_stock_qty={inv['ready_stock_qty']}, reserved_qty={inv['reserved_qty']}")
    
    # Check reservation status changed to fulfilled
    reservations = get_reservations(online_order_id="ORD-TEST-1")
    if len(reservations) != 1:
        print(f"❌ Expected 1 reservation for ORD-TEST-1, got {len(reservations)}")
        return False
    res = reservations[0]
    if res["status"] != "fulfilled":
        print(f"❌ Expected reservation status=fulfilled, got {res['status']}")
        return False
    print(f"✅ Reservation status changed to fulfilled")
    
    # 4. unreserved without any active reservation → should return 400
    print("\n4️⃣  Testing unreserved without active reservation (should fail)...")
    resp = post_movement(style_id, color, size, "unreserved", 5, online_order_id="ORD-TEST-1")
    if resp.status_code == 400:
        print(f"✅ unreserved correctly blocked (no active reservation)")
    else:
        print(f"❌ unreserved should have failed with 400, got {resp.status_code}")
        return False
    
    # 5. Post another reserved qty=5 with online_order_id="ORD-TEST-2"
    print("\n5️⃣  Testing reserved qty=5 with online_order_id=ORD-TEST-2...")
    resp = post_movement(style_id, color, size, "reserved", 5, online_order_id="ORD-TEST-2")
    if resp.status_code != 200:
        print(f"❌ reserved failed: {resp.status_code} {resp.text}")
        return False
    print(f"✅ reserved qty=5 for ORD-TEST-2")
    
    # 6. unreserved qty=5 with same online_order_id → reservation row transitions to status="released"
    print("\n6️⃣  Testing unreserved qty=5 with online_order_id=ORD-TEST-2...")
    resp = post_movement(style_id, color, size, "unreserved", 5, online_order_id="ORD-TEST-2")
    if resp.status_code != 200:
        print(f"❌ unreserved failed: {resp.status_code} {resp.text}")
        return False
    print(f"✅ unreserved qty=5 for ORD-TEST-2")
    
    # Check reservation status changed to released
    reservations = get_reservations(online_order_id="ORD-TEST-2")
    if len(reservations) != 1:
        print(f"❌ Expected 1 reservation for ORD-TEST-2, got {len(reservations)}")
        return False
    res = reservations[0]
    if res["status"] != "released":
        print(f"❌ Expected reservation status=released, got {res['status']}")
        return False
    if not res.get("released_at"):
        print(f"❌ Expected released_at to be populated")
        return False
    print(f"✅ Reservation status changed to released, released_at populated")
    
    # 7. return_in qty=3
    print("\n7️⃣  Testing return_in qty=3...")
    resp = post_movement(style_id, color, size, "return_in", 3)
    if resp.status_code != 200:
        print(f"❌ return_in failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["return_qty"] != 3:
        print(f"❌ Expected return_qty=3, got {inv['return_qty']}")
        return False
    print(f"✅ return_in: return_qty={inv['return_qty']}")
    
    # 8. return_damaged qty=2
    print("\n8️⃣  Testing return_damaged qty=2...")
    resp = post_movement(style_id, color, size, "return_damaged", 2)
    if resp.status_code != 200:
        print(f"❌ return_damaged failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["return_qty"] != 1:
        print(f"❌ Expected return_qty=1, got {inv['return_qty']}")
        return False
    if inv["damaged_qty"] != 2:
        print(f"❌ Expected damaged_qty=2, got {inv['damaged_qty']}")
        return False
    print(f"✅ return_damaged: return_qty={inv['return_qty']}, damaged_qty={inv['damaged_qty']}")
    
    # 9. return_restocked qty=1
    print("\n9️⃣  Testing return_restocked qty=1...")
    resp = post_movement(style_id, color, size, "return_restocked", 1)
    if resp.status_code != 200:
        print(f"❌ return_restocked failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["return_qty"] != 0:
        print(f"❌ Expected return_qty=0, got {inv['return_qty']}")
        return False
    if inv["ready_stock_qty"] != 41:
        print(f"❌ Expected ready_stock_qty=41, got {inv['ready_stock_qty']}")
        return False
    print(f"✅ return_restocked: return_qty={inv['return_qty']}, ready_stock_qty={inv['ready_stock_qty']}")
    
    # 10. liquidation_out qty=5
    print("\n🔟 Testing liquidation_out qty=5...")
    resp = post_movement(style_id, color, size, "liquidation_out", 5)
    if resp.status_code != 200:
        print(f"❌ liquidation_out failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["ready_stock_qty"] != 36:
        print(f"❌ Expected ready_stock_qty=36, got {inv['ready_stock_qty']}")
        return False
    if inv["liquidation_qty"] != 5:
        print(f"❌ Expected liquidation_qty=5, got {inv['liquidation_qty']}")
        return False
    print(f"✅ liquidation_out: ready_stock_qty={inv['ready_stock_qty']}, liquidation_qty={inv['liquidation_qty']}")
    
    # 11. adjustment with adjustment_field="ready_stock_qty" and quantity=-2
    print("\n1️⃣1️⃣  Testing adjustment with adjustment_field=ready_stock_qty, quantity=-2...")
    resp = post_movement(style_id, color, size, "adjustment", -2, adjustment_field="ready_stock_qty")
    if resp.status_code != 200:
        print(f"❌ adjustment failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    inv = data["inventory"]
    if inv["ready_stock_qty"] != 34:
        print(f"❌ Expected ready_stock_qty=34, got {inv['ready_stock_qty']}")
        return False
    print(f"✅ adjustment: ready_stock_qty={inv['ready_stock_qty']}")
    
    # 12. adjustment without adjustment_field → 400
    print("\n1️⃣2️⃣  Testing adjustment without adjustment_field (should fail)...")
    resp = post_movement(style_id, color, size, "adjustment", 5)
    if resp.status_code == 400:
        print(f"✅ adjustment correctly blocked (no adjustment_field)")
    else:
        print(f"❌ adjustment should have failed with 400, got {resp.status_code}")
        return False
    
    # 13. Attempting movement_type "production_in" with quantity=0 → 400
    print("\n1️⃣3️⃣  Testing production_in with quantity=0 (should fail)...")
    resp = post_movement(style_id, color, size, "production_in", 0)
    if resp.status_code == 400:
        print(f"✅ production_in correctly blocked (quantity=0)")
    else:
        print(f"❌ production_in should have failed with 400, got {resp.status_code}")
        return False
    
    # 14. Attempting movement_type "production_in" with negative quantity → 400
    print("\n1️⃣4️⃣  Testing production_in with quantity=-5 (should fail)...")
    resp = post_movement(style_id, color, size, "production_in", -5)
    if resp.status_code == 400:
        print(f"✅ production_in correctly blocked (negative quantity)")
    else:
        print(f"❌ production_in should have failed with 400, got {resp.status_code}")
        return False
    
    print("\n✅ TEST 1 PASSED: Movement engine working correctly")
    return True, style_id, inv_id

def test_ledger_view(style_id: str):
    """Test 2: GET /api/fg-inventory/movements (ledger view)"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/fg-inventory/movements (ledger view)")
    print("="*80)
    
    # No filter: returns list, ordered newest first
    print("\n1️⃣  Testing GET /api/fg-inventory/movements (no filter)...")
    movements = get_movements()
    if not movements:
        print(f"❌ Expected movements, got empty list")
        return False
    print(f"✅ Got {len(movements)} movements")
    
    # Filter by style_id
    print("\n2️⃣  Testing GET /api/fg-inventory/movements?style_id={style_id}...")
    movements = get_movements(style_id=style_id)
    if not movements:
        print(f"❌ Expected movements for style_id={style_id}, got empty list")
        return False
    print(f"✅ Got {len(movements)} movements for style_id={style_id}")
    
    # Filter by movement_type=production_in
    print("\n3️⃣  Testing GET /api/fg-inventory/movements?movement_type=production_in...")
    movements = get_movements(movement_type="production_in")
    if not movements:
        print(f"❌ Expected production_in movements, got empty list")
        return False
    for m in movements:
        if m["movement_type"] != "production_in":
            print(f"❌ Expected movement_type=production_in, got {m['movement_type']}")
            return False
    print(f"✅ Got {len(movements)} production_in movements")
    
    print("\n✅ TEST 2 PASSED: Ledger view working correctly")
    return True

def test_by_style(style_id: str):
    """Test 3: GET /api/fg-inventory/by-style/{style_id}"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/fg-inventory/by-style/{style_id}")
    print("="*80)
    
    data = get_by_style(style_id)
    if not data:
        print(f"❌ Expected data for style_id={style_id}, got empty")
        return False
    
    # Check structure
    if "style" not in data:
        print(f"❌ Expected 'style' in response")
        return False
    if "rows" not in data:
        print(f"❌ Expected 'rows' in response")
        return False
    if "colors" not in data:
        print(f"❌ Expected 'colors' in response")
        return False
    if "sizes" not in data:
        print(f"❌ Expected 'sizes' in response")
        return False
    if "active_reservations" not in data:
        print(f"❌ Expected 'active_reservations' in response")
        return False
    
    print(f"✅ Response structure correct")
    
    # Check rows have computed fields
    for row in data["rows"]:
        if "available_qty" not in row:
            print(f"❌ Expected 'available_qty' in row")
            return False
        if "is_low_stock" not in row:
            print(f"❌ Expected 'is_low_stock' in row")
            return False
    
    print(f"✅ Rows have computed available_qty and is_low_stock")
    
    # Check active_reservations shows only status=="active" rows
    # (We don't have any active reservations at this point, so should be empty)
    if len(data["active_reservations"]) != 0:
        print(f"❌ Expected 0 active reservations, got {len(data['active_reservations'])}")
        return False
    
    print(f"✅ active_reservations correct (0 active)")
    
    print("\n✅ TEST 3 PASSED: GET /api/fg-inventory/by-style/{style_id} working correctly")
    return True

def test_reservations():
    """Test 4: GET /api/inventory-reservations"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/inventory-reservations")
    print("="*80)
    
    # Get all reservations
    print("\n1️⃣  Testing GET /api/inventory-reservations (no filter)...")
    reservations = get_reservations()
    if len(reservations) < 2:
        print(f"❌ Expected at least 2 reservations, got {len(reservations)}")
        return False
    print(f"✅ Got {len(reservations)} reservations")
    
    # Filter by status="fulfilled"
    print("\n2️⃣  Testing GET /api/inventory-reservations?status=fulfilled...")
    reservations = get_reservations(status="fulfilled")
    if len(reservations) < 1:
        print(f"❌ Expected at least 1 fulfilled reservation, got {len(reservations)}")
        return False
    for r in reservations:
        if r["status"] != "fulfilled":
            print(f"❌ Expected status=fulfilled, got {r['status']}")
            return False
    print(f"✅ Got {len(reservations)} fulfilled reservations")
    
    # Filter by online_order_id="ORD-TEST-1"
    print("\n3️⃣  Testing GET /api/inventory-reservations?online_order_id=ORD-TEST-1...")
    reservations = get_reservations(online_order_id="ORD-TEST-1")
    if len(reservations) != 1:
        print(f"❌ Expected 1 reservation for ORD-TEST-1, got {len(reservations)}")
        return False
    print(f"✅ Got 1 reservation for ORD-TEST-1")
    
    print("\n✅ TEST 4 PASSED: GET /api/inventory-reservations working correctly")
    return True

def test_patch_ledger_only(inv_id: str):
    """Test 5: PATCH /api/fg-inventory/{id} — ledger-only writes"""
    print("\n" + "="*80)
    print("TEST 5: PATCH /api/fg-inventory/{id} — ledger-only writes")
    print("="*80)
    
    # PATCH with ready_stock_qty → 400
    print("\n1️⃣  Testing PATCH with ready_stock_qty=999 (should fail)...")
    resp = patch_inventory(inv_id, 999)
    # Actually, we're patching min_stock_level, not ready_stock_qty
    # Let me fix this test
    resp = session.patch(f"{BASE_URL}/fg-inventory/{inv_id}", json={
        "ready_stock_qty": 999
    })
    if resp.status_code == 400:
        if "/api/fg-inventory/movements" in resp.text and "adjustment_field" in resp.text:
            print(f"✅ PATCH correctly blocked (must go via /movements)")
        else:
            print(f"❌ Error message doesn't mention /movements or adjustment_field: {resp.text}")
            return False
    else:
        print(f"❌ PATCH should have failed with 400, got {resp.status_code}")
        return False
    
    # PATCH with min_stock_level → 200 OK
    print("\n2️⃣  Testing PATCH with min_stock_level=30 (should succeed)...")
    resp = patch_inventory(inv_id, 30)
    if resp.status_code != 200:
        print(f"❌ PATCH failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    if data["min_stock_level"] != 30:
        print(f"❌ Expected min_stock_level=30, got {data['min_stock_level']}")
        return False
    print(f"✅ PATCH succeeded: min_stock_level={data['min_stock_level']}")
    
    print("\n✅ TEST 5 PASSED: PATCH /api/fg-inventory/{id} working correctly")
    return True

def test_legacy_reserve_release(style_id: str):
    """Test 6: Legacy POST /api/fg-inventory/reserve and /release"""
    print("\n" + "="*80)
    print("TEST 6: Legacy POST /api/fg-inventory/reserve and /release")
    print("="*80)
    
    import time
    unique_suffix = str(int(time.time()))[-6:]
    color = f"Blue-{unique_suffix}"
    size = f"9-{unique_suffix}"
    
    # First, add some stock via production_in
    print("\n1️⃣  Adding stock via production_in...")
    resp = post_movement(style_id, color, size, "production_in", 20)
    if resp.status_code != 200:
        print(f"❌ production_in failed: {resp.status_code} {resp.text}")
        return False
    print(f"✅ Added 20 pairs of stock")
    
    # /reserve with valid stock
    print("\n2️⃣  Testing POST /api/fg-inventory/reserve...")
    resp = session.post(f"{BASE_URL}/fg-inventory/reserve", json={
        "style_id": style_id,
        "color": color,
        "size": size,
        "quantity": 5
    })
    if resp.status_code != 200:
        print(f"❌ /reserve failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    if not data.get("success"):
        print(f"❌ Expected success=true, got {data}")
        return False
    print(f"✅ /reserve succeeded: {data['message']}")
    
    # Check movement row of type "reserved" is present
    movements = get_movements(style_id=style_id, movement_type="reserved")
    found = False
    for m in movements:
        if m["color"] == color and m["size"] == size:
            found = True
            break
    if not found:
        print(f"❌ Expected movement row of type 'reserved' for {color}/{size}")
        return False
    print(f"✅ Movement row of type 'reserved' found in ledger")
    
    # /release with release_type="ship"
    print("\n3️⃣  Testing POST /api/fg-inventory/release with release_type=ship...")
    resp = session.post(f"{BASE_URL}/fg-inventory/release", json={
        "style_id": style_id,
        "color": color,
        "size": size,
        "quantity": 5,
        "release_type": "ship"
    })
    if resp.status_code != 200:
        print(f"❌ /release failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    if not data.get("success"):
        print(f"❌ Expected success=true, got {data}")
        return False
    print(f"✅ /release succeeded: {data['message']}")
    
    # Check movement row of type "dispatched" is present
    movements = get_movements(style_id=style_id, movement_type="dispatched")
    found = False
    for m in movements:
        if m["color"] == color and m["size"] == size:
            found = True
            break
    if not found:
        print(f"❌ Expected movement row of type 'dispatched' for {color}/{size}")
        return False
    print(f"✅ Movement row of type 'dispatched' found in ledger")
    
    # Reserve again and release with release_type="cancel"
    print("\n4️⃣  Testing /reserve and /release with release_type=cancel...")
    resp = session.post(f"{BASE_URL}/fg-inventory/reserve", json={
        "style_id": style_id,
        "color": color,
        "size": size,
        "quantity": 3
    })
    if resp.status_code != 200:
        print(f"❌ /reserve failed: {resp.status_code} {resp.text}")
        return False
    
    resp = session.post(f"{BASE_URL}/fg-inventory/release", json={
        "style_id": style_id,
        "color": color,
        "size": size,
        "quantity": 3,
        "release_type": "cancel"
    })
    if resp.status_code != 200:
        print(f"❌ /release failed: {resp.status_code} {resp.text}")
        return False
    print(f"✅ /release with cancel succeeded")
    
    # Check movement row of type "unreserved" is present
    movements = get_movements(style_id=style_id, movement_type="unreserved")
    found = False
    for m in movements:
        if m["color"] == color and m["size"] == size:
            found = True
            break
    if not found:
        print(f"❌ Expected movement row of type 'unreserved' for {color}/{size}")
        return False
    print(f"✅ Movement row of type 'unreserved' found in ledger")
    
    print("\n✅ TEST 6 PASSED: Legacy /reserve and /release working correctly")
    return True

def test_low_stock_filter(style_id: str, inv_id: str):
    """Test 7: low_stock filter semantics"""
    print("\n" + "="*80)
    print("TEST 7: low_stock filter semantics")
    print("="*80)
    
    # Get current inventory
    resp = session.get(f"{BASE_URL}/fg-inventory/{inv_id}")
    if resp.status_code != 200:
        print(f"❌ Failed to get inventory: {resp.status_code}")
        return False
    inv = resp.json()
    current_ready = inv["ready_stock_qty"]
    
    # Set min_stock_level to a value greater than current ready_stock_qty
    new_min = current_ready + 10
    print(f"\n1️⃣  Setting min_stock_level={new_min} (current ready_stock_qty={current_ready})...")
    resp = patch_inventory(inv_id, new_min)
    if resp.status_code != 200:
        print(f"❌ PATCH failed: {resp.status_code} {resp.text}")
        return False
    print(f"✅ min_stock_level set to {new_min}")
    
    # GET /api/fg-inventory?low_stock=true should include this row
    print("\n2️⃣  Testing GET /api/fg-inventory?low_stock=true...")
    resp = session.get(f"{BASE_URL}/fg-inventory", params={"low_stock": "true"})
    if resp.status_code != 200:
        print(f"❌ GET failed: {resp.status_code}")
        return False
    rows = resp.json()
    found = False
    for r in rows:
        if r["id"] == inv_id:
            found = True
            if not r.get("is_low_stock"):
                print(f"❌ Expected is_low_stock=true, got {r.get('is_low_stock')}")
                return False
            break
    if not found:
        print(f"❌ Expected to find inventory row {inv_id} in low_stock=true results")
        return False
    print(f"✅ Row found in low_stock=true results")
    
    # GET /api/fg-inventory?low_stock=false should exclude this row
    print("\n3️⃣  Testing GET /api/fg-inventory?low_stock=false...")
    resp = session.get(f"{BASE_URL}/fg-inventory", params={"low_stock": "false"})
    if resp.status_code != 200:
        print(f"❌ GET failed: {resp.status_code}")
        return False
    rows = resp.json()
    for r in rows:
        if r["id"] == inv_id:
            print(f"❌ Row should not be in low_stock=false results")
            return False
    print(f"✅ Row correctly excluded from low_stock=false results")
    
    print("\n✅ TEST 7 PASSED: low_stock filter semantics working correctly")
    return True

def main():
    """Run all Phase 2 tests."""
    print("="*80)
    print("PHASE 2 BACKEND TESTING — Finished Goods Inventory + Reservation Engine")
    print("="*80)
    
    # Login
    login()
    
    # Test 1: Movement engine
    result = test_movement_engine()
    if not result:
        print("\n❌ TEST 1 FAILED")
        sys.exit(1)
    success, style_id, inv_id = result
    
    # Test 2: Ledger view
    if not test_ledger_view(style_id):
        print("\n❌ TEST 2 FAILED")
        sys.exit(1)
    
    # Test 3: GET /api/fg-inventory/by-style/{style_id}
    if not test_by_style(style_id):
        print("\n❌ TEST 3 FAILED")
        sys.exit(1)
    
    # Test 4: GET /api/inventory-reservations
    if not test_reservations():
        print("\n❌ TEST 4 FAILED")
        sys.exit(1)
    
    # Test 5: PATCH /api/fg-inventory/{id}
    if not test_patch_ledger_only(inv_id):
        print("\n❌ TEST 5 FAILED")
        sys.exit(1)
    
    # Test 6: Legacy /reserve and /release
    if not test_legacy_reserve_release(style_id):
        print("\n❌ TEST 6 FAILED")
        sys.exit(1)
    
    # Test 7: low_stock filter semantics
    if not test_low_stock_filter(style_id, inv_id):
        print("\n❌ TEST 7 FAILED")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("✅ ALL PHASE 2 TESTS PASSED")
    print("="*80)

if __name__ == "__main__":
    main()
