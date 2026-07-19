"""Unit tests for environment-gated admin seeding in auth.py."""

import os
import asyncio
import pytest
from unittest.mock import MagicMock
from auth import seed_admin


class MockUserCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, filter_dict):
        email = filter_dict.get("email")
        for doc in self.docs:
            if doc["email"] == email:
                return doc
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="mock_id")

    async def update_one(self, filter_dict, update_dict):
        email = filter_dict.get("email")
        for doc in self.docs:
            if doc["email"] == email:
                if "$set" in update_dict:
                    doc.update(update_dict["$set"])
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)


class MockDB:
    def __init__(self):
        self.users = MockUserCollection()


def test_seed_admin_production_missing_password_fails():
    """Verify that in production mode, missing ADMIN_PASSWORD causes startup to fail with RuntimeError."""
    os.environ["ENVIRONMENT"] = "production"
    if "ADMIN_PASSWORD" in os.environ:
        del os.environ["ADMIN_PASSWORD"]

    db = MockDB()
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD environment variable is not set"):
        asyncio.run(seed_admin(db))


def test_seed_admin_production_seeds_only_env_admin():
    """Verify that in production mode, only env admin is seeded and hardcoded accounts are skipped."""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["ADMIN_EMAIL"] = "prodadmin@sskfootcare.com"
    os.environ["ADMIN_PASSWORD"] = "ProdSecret123!"

    db = MockDB()
    asyncio.run(seed_admin(db))

    seeded_emails = [u["email"] for u in db.users.docs]
    assert "prodadmin@sskfootcare.com" in seeded_emails
    assert "admin@sskfootcare.com" not in seeded_emails
    assert "admin@example.com" not in seeded_emails
    assert len(seeded_emails) == 1


def test_seed_admin_test_seeds_env_and_ssk_admin():
    """Verify that in test mode, env admin + admin@sskfootcare.com are seeded, and example admin is skipped."""
    os.environ["ENVIRONMENT"] = "test"
    os.environ["ADMIN_EMAIL"] = "testenvadmin@sskfootcare.com"
    os.environ["ADMIN_PASSWORD"] = "TestSecret123!"

    db = MockDB()
    asyncio.run(seed_admin(db))

    seeded_emails = [u["email"] for u in db.users.docs]
    assert "testenvadmin@sskfootcare.com" in seeded_emails
    assert "admin@sskfootcare.com" in seeded_emails
    assert "admin@example.com" not in seeded_emails
    assert len(seeded_emails) == 2


def test_seed_admin_development_seeds_all_three():
    """Verify that in development mode, all three admins are seeded."""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["ADMIN_EMAIL"] = "devadmin@sskfootcare.com"
    os.environ["ADMIN_PASSWORD"] = "DevSecret123!"

    db = MockDB()
    asyncio.run(seed_admin(db))

    seeded_emails = [u["email"] for u in db.users.docs]
    assert "devadmin@sskfootcare.com" in seeded_emails
    assert "admin@sskfootcare.com" in seeded_emails
    assert "admin@example.com" in seeded_emails
    assert len(seeded_emails) == 3
