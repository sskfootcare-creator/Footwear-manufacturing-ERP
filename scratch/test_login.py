import requests

try:
    res = requests.post("http://localhost:8000/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    print("STATUS:", res.status_code)
    print("RESPONSE:", res.json())
except Exception as e:
    print("ERROR:", e)
