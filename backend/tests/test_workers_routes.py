import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.workers import workers_router
from models.workers import WorkerIn, SetPinIn, WorkerLoginIn, AdvanceIn
from auth import hash_password


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockWorkersDB:
    def __init__(self):
        self.workers_store = {}
        self.advances_store = {}
        self.jobs_store = {}
        self.notifications_store = []
        self.styles_store = {}

        self.workers = MagicMock()
        self.workers.find = MagicMock(side_effect=self._find_workers)
        self.workers.find_one = AsyncMock(side_effect=self._find_one_worker)
        self.workers.insert_one = AsyncMock(side_effect=self._insert_worker)
        self.workers.update_one = AsyncMock(side_effect=self._update_worker)

        self.advances = MagicMock()
        self.advances.find = MagicMock(side_effect=self._find_advances)
        self.advances.find_one = AsyncMock(side_effect=self._find_one_advance)
        self.advances.insert_one = AsyncMock(side_effect=self._insert_advance)
        self.advances.update_one = AsyncMock(side_effect=self._update_advance)
        self.advances.delete_one = AsyncMock(side_effect=self._delete_advance)

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)
        self.production_jobs.find_one = AsyncMock(side_effect=self._find_one_job)
        self.production_jobs.update_one = AsyncMock(side_effect=self._update_job)

        self.notifications = MagicMock()
        self.notifications.insert_one = AsyncMock(side_effect=self._insert_notif)

        self.styles = MagicMock()
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)
        self.styles.find = MagicMock(side_effect=self._find_styles)

    def _find_workers(self, query=None):
        return MockCursor(list(self.workers_store.values()))

    async def _find_one_worker(self, query):
        if "_id" in query:
            return self.workers_store.get(str(query["_id"]))
        if "phone" in query:
            for w in self.workers_store.values():
                if w.get("phone") == query["phone"]:
                    return w
        return None

    async def _insert_worker(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.workers_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_worker(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.workers_store:
            self.workers_store[oid_str].update(update.get("$set", {}))
        return MagicMock(matched_count=1)

    def _find_advances(self, query=None):
        docs = list(self.advances_store.values())
        if query and "worker_id" in query:
            docs = [d for d in docs if d.get("worker_id") == query["worker_id"]]
        return MockCursor(docs)

    async def _find_one_advance(self, query):
        oid_str = str(query.get("_id"))
        return self.advances_store.get(oid_str)

    async def _insert_advance(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.advances_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_advance(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.advances_store:
            self.advances_store[oid_str].update(update.get("$set", {}))
        return MagicMock(matched_count=1)

    async def _delete_advance(self, query):
        oid_str = str(query.get("_id"))
        self.advances_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_jobs(self, query=None):
        return MockCursor(list(self.jobs_store.values()))

    async def _find_one_job(self, query):
        oid_str = str(query.get("_id"))
        return self.jobs_store.get(oid_str)

    async def _update_job(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.jobs_store:
            self.jobs_store[oid_str].update(update.get("$set", {}))
        return MagicMock(matched_count=1)

    async def _insert_notif(self, doc):
        self.notifications_store.append(doc)
        return MagicMock(inserted_id="mock_notif_id")

    async def _find_one_style(self, query):
        return self.styles_store.get(query.get("code"))

    def _find_styles(self, query=None):
        return MockCursor(list(self.styles_store.values()))


@pytest.fixture
def mock_workers_env(monkeypatch):
    mock_db = MockWorkersDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
            "worker_id": "w_test_1"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_workers_env):
    test_app = FastAPI()
    test_app.include_router(workers_router)
    test_app.mongodb = mock_workers_env
    return TestClient(test_app)


def test_worker_crud(client, mock_workers_env):
    # 1. Create worker
    res = client.post("/api/workers", json={
        "name": "Ramesh Kumar",
        "phone": "9876543210",
        "skill": "stitching",
        "rate_per_pair": 18.5,
        "active": True,
        "bonus_pct": 5.0,
        "target_cycle_days": 3.0,
    })
    assert res.status_code == 200
    wdata = res.json()
    assert wdata["name"] == "Ramesh Kumar"
    assert wdata["rate_per_pair"] == 18.5
    wid = wdata["id"]

    # 2. List workers
    res = client.get("/api/workers")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Update worker
    res = client.patch(f"/api/workers/{wid}", json={
        "name": "Ramesh Kumar Updated",
        "phone": "9876543210",
        "skill": "stitching",
        "rate_per_pair": 20.0,
        "active": True,
    })
    assert res.status_code == 200
    assert res.json()["name"] == "Ramesh Kumar Updated"
    assert res.json()["rate_per_pair"] == 20.0

    # 4. Set PIN
    res = client.patch(f"/api/workers/{wid}/set-pin", json={"pin": "1234"})
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 5. Worker Login with PIN
    res = client.post("/api/auth/worker-login", json={"phone": "9876543210", "pin": "1234"})
    assert res.status_code == 200
    login_data = res.json()
    assert login_data["worker_id"] == wid
    assert login_data["role"] == "worker"
    assert "access_token" in login_data

    # 6. Delete worker
    res = client.delete(f"/api/workers/{wid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_advances_and_ledger(client, mock_workers_env):
    # Setup a worker
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Suresh",
        "rate_per_pair": 15.0,
        "skill": "lasting",
        "active": True
    }

    # 1. Create Advance
    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 500.0,
        "notes": "Emergency advance",
        "txn_type": "advance"
    })
    assert res.status_code == 200
    adv = res.json()
    assert adv["amount"] == 500.0
    aid = adv["id"]

    # 2. List Advances
    res = client.get(f"/api/advances?worker_id={wid}")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # 3. Worker Ledger
    res = client.get(f"/api/workers/{wid}/ledger")
    assert res.status_code == 200
    ledger = res.json()
    assert ledger["worker"]["id"] == wid
    assert ledger["total_paid"] == 500.0
    assert ledger["balance"] == -500.0

    # 4. Update & Delete Advance
    res = client.patch(f"/api/advances/{aid}", json={"settled": True})
    assert res.status_code == 200
    assert res.json()["settled"] is True

    res = client.delete(f"/api/advances/{aid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True
