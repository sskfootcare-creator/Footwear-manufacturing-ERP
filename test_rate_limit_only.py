#!/usr/bin/env python3
"""Test rate limiting in isolation after backend restart."""

import requests
import time

BASE_URL = "https://4411416a-6779-4d1b-ba32-8060d6385338.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@example.com"

print("Testing rate limit after backend restart...")
print("Attempting 6 failed logins in quick succession...")

url = f"{BASE_URL}/auth/login"

for i in range(1, 7):
    payload = {"email": ADMIN_EMAIL, "password": f"wrongpass{i}"}
    resp = requests.post(url, json=payload)
    print(f"Attempt {i}: Status {resp.status_code}, Detail: {resp.json().get('detail', 'N/A')}")
    time.sleep(0.5)  # Small delay to ensure same session

print("\nAttempting with correct credentials (should also be blocked)...")
payload = {"email": ADMIN_EMAIL, "password": "admin123"}
resp = requests.post(url, json=payload)
print(f"Correct credentials: Status {resp.status_code}, Detail: {resp.json().get('detail', 'N/A')}")
