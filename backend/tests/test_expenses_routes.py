import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.expenses import expenses_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        return self

    async def to_list(self, limit):
        return self.docs


class MockExpensesDB:
    def __init__(self):
        self.expenses_store = {}
        self.recurring_store = {}
        self.invoices_store = {}
        self.online_settlements_store = {}
        self.vendor_pos_store = {}
        self.audit_logs_store = []

        self.expenses = MagicMock()
        self.expenses.find = MagicMock(side_effect=self._find_expenses)
        self.expenses.find_one = AsyncMock(side_effect=self._find_one_expense)
        self.expenses.insert_one = AsyncMock(side_effect=self._insert_expense)
        self.expenses.update_one = AsyncMock(side_effect=self._update_expense)
        self.expenses.delete_one = AsyncMock(side_effect=self._delete_expense)

        self.recurring_expenses = MagicMock()
        self.recurring_expenses.find = MagicMock(side_effect=self._find_recurring)
        self.recurring_expenses.find_one = AsyncMock(side_effect=self._find_one_recurring)
        self.recurring_expenses.insert_one = AsyncMock(side_effect=self._insert_recurring)
        self.recurring_expenses.update_one = AsyncMock(side_effect=self._update_recurring)
        self.recurring_expenses.delete_one = AsyncMock(side_effect=self._delete_recurring)

        self.invoices = MagicMock()
        self.invoices.find = MagicMock(return_value=MockCursor(list(self.invoices_store.values())))

        self.online_settlements = MagicMock()
        self.online_settlements.find = MagicMock(return_value=MockCursor(list(self.online_settlements_store.values())))

        self.vendor_pos = MagicMock()
        self.vendor_pos.find = MagicMock(return_value=MockCursor(list(self.vendor_pos_store.values())))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_expenses(self, query=None):
        docs = list(self.expenses_store.values())
        if query and "status" in query and isinstance(query["status"], dict):
            in_list = query["status"].get("$in")
            if in_list:
                docs = [d for d in docs if d.get("status") in in_list]
        return MockCursor(docs)

    async def _find_one_expense(self, query):
        if "_id" in query:
            return self.expenses_store.get(str(query["_id"]))
        if "recurring_expense_id" in query:
            for e in self.expenses_store.values():
                if e.get("recurring_expense_id") == query["recurring_expense_id"]:
                    return e
        return None

    async def _insert_expense(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.expenses_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_expense(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.expenses_store:
            self.expenses_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def _delete_expense(self, query):
        oid_str = str(query.get("_id"))
        self.expenses_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_recurring(self, query=None):
        return MockCursor(list(self.recurring_store.values()))

    async def _find_one_recurring(self, query):
        oid_str = str(query.get("_id"))
        return self.recurring_store.get(oid_str)

    async def _insert_recurring(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.recurring_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_recurring(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.recurring_store:
            self.recurring_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def _delete_recurring(self, query):
        oid_str = str(query.get("_id"))
        self.recurring_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)


@pytest.fixture
def mock_expenses_env(monkeypatch):
    mock_db = MockExpensesDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_expenses_env):
    test_app = FastAPI()
    test_app.include_router(expenses_router)
    test_app.mongodb = mock_expenses_env
    return TestClient(test_app)


def test_expense_crud(client, mock_expenses_env):
    # 1. Create expense
    res = client.post("/api/expenses", json={
        "category": "Rent & Utilities",
        "amount": 45000.0,
        "date": "2026-08-01",
        "payee": "Factory Landlord",
        "notes": "Factory Unit 1 Rent August",
        "status": "confirmed"
    })
    assert res.status_code == 200
    exp = res.json()
    assert exp["category"] == "Rent & Utilities"
    assert exp["amount"] == 45000.0
    eid = exp["id"]

    # 2. Get expense
    res = client.get(f"/api/expenses/{eid}")
    assert res.status_code == 200
    assert res.json()["payee"] == "Factory Landlord"

    # 3. List expenses
    res = client.get("/api/expenses")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 4. Update expense
    res = client.put(f"/api/expenses/{eid}", json={
        "notes": "Factory Unit 1 Rent August (Paid via NEFT)"
    })
    assert res.status_code == 200
    assert "Paid via NEFT" in res.json()["notes"]

    # 5. Delete expense
    res = client.delete(f"/api/expenses/{eid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_recurring_expenses_flow(client, mock_expenses_env):
    # 1. Create recurring expense template
    res = client.post("/api/expenses/recurring", json={
        "category": "Office & Administrative",
        "payee": "Broadband Internet",
        "amount": 2500.0,
        "frequency": "monthly",
        "start_date": "2026-01-01",
        "due_day": 5,
        "active": True,
        "notes": "High speed fiber"
    })
    assert res.status_code == 201
    rec = res.json()
    assert rec["category"] == "Office & Administrative"
    rid = rec["id"]

    # 2. List recurring templates
    res = client.get("/api/expenses/recurring")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Get single recurring template
    res = client.get(f"/api/expenses/recurring/{rid}")
    assert res.status_code == 200
    assert res.json()["amount"] == 2500.0

    # 4. Trigger recurring check
    res = client.post("/api/expenses/check-recurring")
    assert res.status_code == 200
    assert "generated_count" in res.json()

    # 5. Due queue check
    res = client.get("/api/expenses/due-queue")
    assert res.status_code == 200
    queue = res.json()
    assert isinstance(queue, list)
    if queue:
        due_eid = queue[0]["id"]
        # 6. Confirm expense from due queue
        res_conf = client.post(f"/api/expenses/{due_eid}/confirm", json={"amount": 2500.0})
        assert res_conf.status_code == 200
        assert res_conf.json()["status"] == "confirmed"

    # 7. Update recurring template
    res = client.patch(f"/api/expenses/recurring/{rid}", json={"amount": 2800.0})
    assert res.status_code == 200
    assert res.json()["amount"] == 2800.0

    # 8. Delete recurring template
    res = client.delete(f"/api/expenses/recurring/{rid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_pnl_report(client, mock_expenses_env):
    res = client.get("/api/reports/pnl")
    assert res.status_code == 200
    pnl = res.json()
    assert "revenue" in pnl
    assert "material_cost" in pnl
    assert "labor_cost" in pnl
    assert "expenses" in pnl
    assert "gross_profit" in pnl
    assert "net_profit" in pnl
    assert "monthly_breakdown" in pnl
