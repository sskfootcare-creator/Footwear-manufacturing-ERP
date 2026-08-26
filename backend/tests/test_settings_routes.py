import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server
from routes.settings import settings_router
from models.settings import DEFAULT_STAGE_HOURS, StageDurationsIn


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction):
        return self

    async def to_list(self, limit):
        return self.docs


class MockSettingsDB:
    def __init__(self):
        self.settings_store = {}
        self.audit_logs_store = []
        self.collections = {
            "users": [{"_id": "u1", "email": "admin@sskfootcare.com"}],
            "materials": [],
            "styles": [],
            "pos": [],
            "production_jobs": [],
            "workers": [],
            "defects": [],
            "packing_templates": [],
            "invoices": [],
            "grns": [],
            "payments": [],
            "settings": [],
            "inventory_movements": [],
            "audit_logs": [],
        }

        self.settings = MagicMock()
        self.settings.find_one = AsyncMock(side_effect=self._find_one_setting)
        self.settings.update_one = AsyncMock(side_effect=self._update_one_setting)

        self.audit_logs = MagicMock()
        self.audit_logs.find = MagicMock(side_effect=self._find_audit_logs)
        self.audit_logs.insert_one = AsyncMock(side_effect=self._insert_audit_log)

    async def _find_one_setting(self, query):
        sid = query.get("_id")
        if sid in self.settings_store:
            return dict(self.settings_store[sid])
        return None

    async def _update_one_setting(self, query, update, upsert=False):
        sid = query.get("_id")
        set_fields = update.get("$set", {})
        if sid not in self.settings_store:
            self.settings_store[sid] = {"_id": sid}
        self.settings_store[sid].update(set_fields)
        return MagicMock(acknowledged=True)

    def _find_audit_logs(self, query):
        return MockCursor(self.audit_logs_store)

    async def _insert_audit_log(self, doc):
        self.audit_logs_store.append(dict(doc))
        return MagicMock(inserted_id="mock_audit_id")

    def __getitem__(self, name):
        mock_col = MagicMock()
        mock_col.find = MagicMock(return_value=MockCursor(self.collections.get(name, [])))
        return mock_col


@pytest.fixture
def mock_settings_env(monkeypatch):
    mock_db = MockSettingsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_settings_env):
    test_app = FastAPI()
    test_app.include_router(settings_router)
    test_app.mongodb = mock_settings_env
    return TestClient(test_app)


def test_get_and_put_stage_durations(client, mock_settings_env):
    # 1. GET defaults
    res = client.get("/api/settings/stage-durations")
    assert res.status_code == 200
    data = res.json()
    assert "hours" in data
    assert "defaults" in data
    assert data["hours"]["procurement"] == 24
    assert data["defaults"] == DEFAULT_STAGE_HOURS

    # 2. PUT updated hours
    new_hours = {"procurement": 30.0, "stitching": 40.0}
    put_res = client.put("/api/settings/stage-durations", json={"hours": new_hours})
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["ok"] is True
    assert put_data["hours"]["procurement"] == 30.0
    assert put_data["hours"]["stitching"] == 40.0

    # 3. GET persists
    res2 = client.get("/api/settings/stage-durations")
    assert res2.status_code == 200
    assert res2.json()["hours"]["procurement"] == 30.0


def test_get_and_put_company_profile(client, mock_settings_env):
    # 1. GET default company
    res = client.get("/api/settings/company")
    assert res.status_code == 200
    assert "name" in res.json() or "company_name" in res.json() or isinstance(res.json(), dict)

    # 2. PUT custom profile
    payload = {"company_name": "SSK Footcare Global", "city": "Agra", "gstin": "09AAAAA0000A1Z5"}
    put_res = client.put("/api/settings/company", json=payload)
    assert put_res.status_code == 200
    assert put_res.json()["ok"] is True

    # 3. GET custom profile
    res2 = client.get("/api/settings/company")
    assert res2.status_code == 200
    assert res2.json()["company_name"] == "SSK Footcare Global"
    assert res2.json()["city"] == "Agra"


def test_get_audit_logs(client, mock_settings_env):
    mock_settings_env.audit_logs_store.append({
        "_id": "audit_1",
        "action": "test_action",
        "category": "settings",
        "details": "Test audit entry",
        "by": "admin@sskfootcare.com",
        "created_at": "2026-08-26T11:00:00Z"
    })

    res = client.get("/api/settings/audit-logs")
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "test_action"
    assert logs[0]["id"] == "audit_1"


def test_get_export_backup(client, mock_settings_env):
    res = client.get("/api/settings/export-backup")
    assert res.status_code == 200
    data = res.json()
    assert "users" in data
    assert "materials" in data
    assert "styles" in data
    assert len(data["users"]) == 1
    assert data["users"][0]["id"] == "u1"
