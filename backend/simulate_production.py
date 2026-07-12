import requests
import json

BASE_URL = "http://localhost:8000/api"

def main():
    session = requests.Session()
    
    # 1. Login
    print("Logging in...")
    login_resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@ssk.com",
        "password": "admin1234"
    })
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.status_code} - {login_resp.text}")
        return
        
    print("Logged in successfully!")
    
    # Get styles to find their actual database IDs dynamically
    styles_resp = session.get(f"{BASE_URL}/styles")
    styles = styles_resp.json()
    style_ids = {s["code"]: s["id"] for s in styles}
    print(f"Fetched Style IDs: {style_ids}")
    
    # 2. Simulate Exact Production
    # SSK_00002, Black, Size 8. Pending: 10. Produce: 10.
    print("\n1. Simulating Exact Production (10/10) for SSK_00002 Black Size 8...")
    resp1 = session.post(f"{BASE_URL}/production/produce-cell", json={
        "style_id": style_ids["SSK_00002"],
        "color": "Black",
        "size": "8",
        "produced_qty": 10,
        "use_components": True,
        "force_negative_stock": True
    })
    print(f"Response: {resp1.status_code}")
    print(json.dumps(resp1.json(), indent=2))
    
    # 3. Simulate Short Production (Short dispatch)
    # SSK_00001, Brown, Size 9. Pending: 6. Produce: 4.
    print("\n2. Simulating Short Production (4/6) for SSK_00001 Brown Size 9...")
    resp2 = session.post(f"{BASE_URL}/production/produce-cell", json={
        "style_id": style_ids["SSK_00001"],
        "color": "Brown",
        "size": "9",
        "produced_qty": 4,
        "reason": "Stitching machine alignment issue",
        "use_components": True,
        "force_negative_stock": True
    })
    print(f"Response: {resp2.status_code}")
    print(json.dumps(resp2.json(), indent=2))
    
    # 4. Simulate Excess Production (Over-production)
    # SSK_00002, Black, Size 9. Pending: 4. Produce: 6.
    print("\n3. Simulating Excess Production (6/4) for SSK_00002 Black Size 9...")
    resp3 = session.post(f"{BASE_URL}/production/produce-cell", json={
        "style_id": style_ids["SSK_00002"],
        "color": "Black",
        "size": "9",
        "produced_qty": 6,
        "use_components": True,
        "force_negative_stock": True
    })
    print(f"Response: {resp3.status_code}")
    print(json.dumps(resp3.json(), indent=2))

if __name__ == "__main__":
    main()
