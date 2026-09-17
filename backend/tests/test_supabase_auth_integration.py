"""Integration tests for Supabase Auth service."""

import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.supabase_auth_service import (
    create_or_sync_supabase_user,
    find_supabase_user_by_email,
    authenticate_with_supabase,
    verify_supabase_token,
    delete_supabase_user,
)


def test_supabase_auth_full_lifecycle():
    test_email = "test_lifecycle_user@example.com"
    test_password = "SecretPassword2026!"
    test_name = "Lifecycle Test"
    test_role = "accountant"
    test_modules = ["orders_sales", "procurement"]

    # 1. Create / provision user in Supabase Auth
    user = create_or_sync_supabase_user(
        email=test_email,
        password=test_password,
        name=test_name,
        role=test_role,
        allowed_modules=test_modules,
    )
    assert user is not None
    user_id = str(user.id)
    assert user_id != ""

    try:
        # 2. Verify lookup by email
        found = find_supabase_user_by_email(test_email)
        assert found is not None
        assert str(found.id) == user_id

        # 3. Authenticate with valid password
        auth_res = authenticate_with_supabase(test_email, test_password)
        assert auth_res is not None
        assert auth_res.session is not None
        token = auth_res.session.access_token
        assert token is not None and len(token) > 20

        # 4. Authenticate with invalid password
        invalid_res = authenticate_with_supabase(test_email, "WrongPassword!")
        assert invalid_res is None

        # 5. Verify Supabase JWT token
        verified_user = verify_supabase_token(token)
        assert verified_user is not None
        assert str(verified_user.id) == user_id
        assert verified_user.email == test_email

    finally:
        # Clean up
        deleted = delete_supabase_user(user_id)
        assert deleted is True
