"""Unit and API tests for Modular Role-Based Access Control (RBAC)."""

import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from auth import (
    ERP_MODULES,
    ROLE_DEFAULT_MODULES,
    get_user_modules,
    has_module_access,
    require_module,
    create_access_token,
    JWT_ALGORITHM,
    get_jwt_secret,
)
import jwt


def test_erp_modules_structure():
    """Verify all required ERP modules are registered with keys, names, descriptions, and categories."""
    expected_keys = {
        "production", "inventory", "workers", "orders_sales",
        "procurement", "finance", "online", "reports", "settings_admin"
    }
    assert expected_keys.issubset(set(ERP_MODULES.keys()))
    for key, mod in ERP_MODULES.items():
        assert "name" in mod
        assert "description" in mod
        assert "category" in mod


def test_user_modules_resolution():
    """Verify default vs custom allowed_modules resolution."""
    # Admin gets all modules
    admin_user = {"role": "admin"}
    assert set(get_user_modules(admin_user)) == set(ERP_MODULES.keys())
    assert has_module_access(admin_user, "finance") is True

    # Standard CA role gets finance, orders_sales, procurement, reports
    ca_user = {"role": "ca"}
    assert "finance" in get_user_modules(ca_user)
    assert has_module_access(ca_user, "finance") is True
    assert has_module_access(ca_user, "production") is False

    # Custom allowed_modules override
    custom_user = {
        "role": "production",
        "allowed_modules": ["production", "finance"],
    }
    assert set(get_user_modules(custom_user)) == {"production", "finance"}
    assert has_module_access(custom_user, "finance") is True
    assert has_module_access(custom_user, "online") is False


def test_create_access_token_with_modules():
    """Verify JWT payload contains allowed_modules when provided."""
    token = create_access_token(
        user_id="u123",
        email="test@ssk.com",
        role="custom",
        allowed_modules=["finance", "orders_sales"],
    )
    from auth import JWT_AUDIENCE
    decoded = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE)
    assert decoded["allowed_modules"] == ["finance", "orders_sales"]
    assert decoded["sub"] == "u123"


def test_require_module_enforcement():
    """Verify require_module permits authorized users and raises 403 on unauthorized users."""
    from fastapi import HTTPException

    checker = require_module("finance")

    # Admin passes
    admin = {"role": "admin"}
    assert checker(admin) == admin

    # User with finance passes
    fin_user = {"role": "accountant", "allowed_modules": ["finance"]}
    assert checker(fin_user) == fin_user

    # User without finance fails with 403
    prod_user = {"role": "production", "allowed_modules": ["production"]}
    with pytest.raises(HTTPException) as exc_info:
        checker(prod_user)
    assert exc_info.value.status_code == 403
