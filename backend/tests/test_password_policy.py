import pytest
import requests

API_URL = "http://localhost:8000/api"
ADMIN_EMAIL = "admin@sskfootcare.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    assert r.status_code == 200, f"Login failed: {r.status_code} - {r.text}"
    return s


def test_create_user_password_validation(admin_session):
    # 1. Try creating a user with a short password
    payload = {
        "email": "testshortpwd@sskfootcare.com",
        "name": "Test Short Pwd",
        "role": "production",
        "password": "123"
    }
    r = admin_session.post(f"{API_URL}/users", json=payload, timeout=10)
    assert r.status_code == 422, f"Expected 422 validation error, got {r.status_code}: {r.text}"
    err_json = r.json()
    assert "detail" in err_json
    # Pydantic validation error structure is a list of errors
    detail = err_json["detail"]
    assert isinstance(detail, list)
    assert len(detail) > 0
    assert "Password must be at least 8 characters long." in [err.get("msg") for err in detail]

    # 2. Try creating a user with an empty password
    payload["password"] = ""
    r = admin_session.post(f"{API_URL}/users", json=payload, timeout=10)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "Password must be at least 8 characters long." in [err.get("msg") for err in detail]


def test_update_user_password_validation(admin_session):
    # First, create a valid user
    payload = {
        "email": "testupdatepwd@sskfootcare.com",
        "name": "Test Update Pwd",
        "role": "production",
        "password": "ValidPassword123"
    }
    # Clean up user if it already exists from a previous run
    r = admin_session.post(f"{API_URL}/users", json=payload, timeout=10)
    if r.status_code == 409: # Conflict, already exists
        r_list = admin_session.get(f"{API_URL}/users", timeout=10)
        user_id = next(u["id"] for u in r_list.json() if u["email"] == payload["email"])
    else:
        assert r.status_code == 200, f"Failed to create test user: {r.text}"
        user_id = r.json()["id"]

    # 1. Try updating the password with a short password
    update_payload = {"password": "short"}
    r_up = admin_session.patch(f"{API_URL}/users/{user_id}", json=update_payload, timeout=10)
    assert r_up.status_code == 422, f"Expected 422 validation error, got {r_up.status_code}: {r_up.text}"
    detail = r_up.json()["detail"]
    assert "Password must be at least 8 characters long." in [err.get("msg") for err in detail]

    # 2. Try updating the password with an empty password
    update_payload = {"password": ""}
    r_up = admin_session.patch(f"{API_URL}/users/{user_id}", json=update_payload, timeout=10)
    assert r_up.status_code == 422
    detail = r_up.json()["detail"]
    assert "Password must be at least 8 characters long." in [err.get("msg") for err in detail]

    # 3. Try updating with a valid password
    update_payload = {"password": "ValidNewPassword456"}
    r_up = admin_session.patch(f"{API_URL}/users/{user_id}", json=update_payload, timeout=10)
    assert r_up.status_code == 200, f"Expected successful update, got {r_up.status_code}: {r_up.text}"

    # 4. Try updating without a password field (should succeed)
    update_payload = {"name": "Test Update Pwd Renamed"}
    r_up = admin_session.patch(f"{API_URL}/users/{user_id}", json=update_payload, timeout=10)
    assert r_up.status_code == 200
    assert r_up.json()["name"] == "Test Update Pwd Renamed"

    # Clean up (deactivate the user)
    r_del = admin_session.delete(f"{API_URL}/users/{user_id}", timeout=10)
    assert r_del.status_code == 200
