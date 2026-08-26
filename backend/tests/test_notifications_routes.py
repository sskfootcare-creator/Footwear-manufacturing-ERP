import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.notifications import notifications_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockNotificationsDB:
    def __init__(self):
        self.notifications_store = {}

        self.notifications = MagicMock()
        self.notifications.find = MagicMock(side_effect=self._find_notifs)
        self.notifications.find_one = AsyncMock(side_effect=self._find_one_notif)
        self.notifications.insert_one = AsyncMock(side_effect=self._insert_notif)
        self.notifications.update_one = AsyncMock(side_effect=self._update_notif)

    def _find_notifs(self, query=None):
        docs = list(self.notifications_store.values())
        if query and query.get("read") is False:
            docs = [d for d in docs if not d.get("read")]
        return MockCursor(docs)

    async def _find_one_notif(self, query):
        oid_str = str(query.get("_id"))
        return self.notifications_store.get(oid_str)

    async def _insert_notif(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.notifications_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_notif(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.notifications_store:
            self.notifications_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)


@pytest.fixture
def mock_notifs_env(monkeypatch):
    mock_db = MockNotificationsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "prod_mgr_1",
            "email": "manager@sskfootcare.com",
            "role": "production",
            "name": "Production Manager"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_notifs_env):
    test_app = FastAPI()
    test_app.include_router(notifications_router)
    test_app.mongodb = mock_notifs_env
    return TestClient(test_app)


def test_notifications_flow(client, mock_notifs_env):
    # Setup notifications in DB
    nid1 = str(ObjectId())
    nid2 = str(ObjectId())

    mock_notifs_env.notifications_store[nid1] = {
        "_id": ObjectId(nid1),
        "type": "pickup_ready",
        "job_id": "job_101",
        "style_code": "SSK-BOOT-01",
        "stage": "stitching",
        "worker_name": "Ramesh",
        "completed_qty": 60,
        "read": False,
        "at": "2026-08-26T10:00:00Z"
    }

    mock_notifs_env.notifications_store[nid2] = {
        "_id": ObjectId(nid2),
        "type": "pickup_ready",
        "job_id": "job_102",
        "style_code": "SSK-BOOT-02",
        "stage": "lasting",
        "worker_name": "Suresh",
        "completed_qty": 120,
        "read": True,
        "at": "2026-08-26T09:00:00Z"
    }

    # 1. GET unread notifications (default)
    res = client.get("/api/notifications")
    assert res.status_code == 200
    notifs = res.json()
    assert len(notifs) == 1
    assert notifs[0]["id"] == nid1
    assert notifs[0]["job_id"] == "job_101"

    # 2. GET all notifications (unread_only=false)
    res = client.get("/api/notifications?unread_only=false")
    assert res.status_code == 200
    all_notifs = res.json()
    assert len(all_notifs) == 2

    # 3. Mark notification as read
    res = client.patch(f"/api/notifications/{nid1}/read")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert mock_notifs_env.notifications_store[nid1]["read"] is True

    # 4. 404 for non-existent notification
    fake_id = str(ObjectId())
    res = client.patch(f"/api/notifications/{fake_id}/read")
    assert res.status_code == 404
