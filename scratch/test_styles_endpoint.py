import requests

res = requests.post("http://localhost:8000/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
token = res.json().get("access_token")
print("Token:", token[:20] if token else "No token")

headers = {"Authorization": f"Bearer {token}"}
styles_res = requests.get("http://localhost:8000/api/styles", headers=headers)
print("Styles status:", styles_res.status_code)
try:
    print("Styles count:", len(styles_res.json()))
except Exception as e:
    print("Styles error:", styles_res.text[:500])
