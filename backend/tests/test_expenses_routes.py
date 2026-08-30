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
        "bank_account_id": "bank_acc_123",
        "status": "confirmed"
    })
    assert res.status_code == 200
    exp = res.json()
    assert exp["category"] == "Rent & Utilities"
    assert exp["amount"] == 45000.0
    assert exp["bank_account_id"] == "bank_acc_123"
    eid = exp["id"]

    # 2. Get expense
    res = client.get(f"/api/expenses/{eid}")
    assert res.status_code == 200
    assert res.json()["payee"] == "Factory Landlord"
    assert res.json()["bank_account_id"] == "bank_acc_123"

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


def test_expense_with_bank_account(client, mock_expenses_env):
    payload = {
        "category": "Raw Materials",
        "amount": 12500.0,
        "date": "2026-08-15",
        "payee": "Leather Supplier Co",
        "notes": "Direct bank payment for sole materials",
        "bank_account_id": "bank_acc_xyz_789",
        "status": "confirmed"
    }
    # 1. Create expense with bank_account_id and verify it is returned on create
    res = client.post("/api/expenses", json=payload)
    assert res.status_code == 200
    created = res.json()
    assert created.get("bank_account_id") == "bank_acc_xyz_789"
    assert "id" in created
    eid = created["id"]

    # 2. Verify getting expense by ID returns the bank_account_id correctly
    get_res = client.get(f"/api/expenses/{eid}")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched.get("id") == eid
    assert fetched.get("bank_account_id") == "bank_acc_xyz_789"
    assert fetched.get("payee") == "Leather Supplier Co"
    assert fetched.get("amount") == 12500.0

    # 3. Verify getting expenses list includes the expense with bank_account_id
    list_res = client.get("/api/expenses")
    assert list_res.status_code == 200
    all_expenses = list_res.json()
    matched = next((item for item in all_expenses if item.get("id") == eid), None)
    assert matched is not None
    assert matched.get("bank_account_id") == "bank_acc_xyz_789"


def test_recurring_expenses_flow(client, mock_expenses_env):
    # 1. Create recurring expense template
    res = client.post("/api/expenses/recurring", json={
        "category": "Office & Administrative",
        "payee": "Broadband Internet",
        "amount": 2500.0,
        "frequency": "monthly",
        "start_date": "2026-01-01",
        "due_day": 5,
        "bank_account_id": "bank_acc_recurring_99",
        "active": True,
        "notes": "High speed fiber"
    })
    assert res.status_code == 201
    rec = res.json()
    assert rec["category"] == "Office & Administrative"
    assert rec.get("bank_account_id") == "bank_acc_recurring_99"
    rid = rec["id"]

    # 2. List recurring templates
    res = client.get("/api/expenses/recurring")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Get single recurring template
    res = client.get(f"/api/expenses/recurring/{rid}")
    assert res.status_code == 200
    assert res.json()["amount"] == 2500.0
    assert res.json().get("bank_account_id") == "bank_acc_recurring_99"

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
        assert queue[0].get("bank_account_id") == "bank_acc_recurring_99"
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


def test_recurring_expense_bank_account_inheritance(client, mock_expenses_env):
    # 1. Create a recurring expense template with a bank_account_id set
    res = client.post("/api/expenses/recurring", json={
        "category": "Rent & Utilities",
        "payee": "Warehouse Property Ltd",
        "amount": 35000.0,
        "frequency": "monthly",
        "start_date": "2026-01-01",
        "due_day": 1,
        "bank_account_id": "bank_acc_hdfc_5544",
        "active": True,
        "notes": "Warehouse monthly lease"
    })
    assert res.status_code == 201
    rec_tmpl = res.json()
    assert rec_tmpl.get("bank_account_id") == "bank_acc_hdfc_5544"
    tmpl_id = rec_tmpl["id"]

    # 2. Trigger the recurring expense check via POST /api/expenses/check-recurring
    check_res = client.post("/api/expenses/check-recurring")
    assert check_res.status_code == 200

    # 3. Check the due queue via GET /api/expenses/due-queue
    queue_res = client.get("/api/expenses/due-queue")
    assert queue_res.status_code == 200
    queue = queue_res.json()
    assert isinstance(queue, list)

    # 4. Verify that the auto-generated expense has inherited the same bank_account_id from the template
    gen_expense = next((item for item in queue if item.get("recurring_expense_id") == tmpl_id), None)
    assert gen_expense is not None, "Generated expense not found in due queue"
    assert gen_expense.get("bank_account_id") == "bank_acc_hdfc_5544"
    assert gen_expense.get("payee") == "Warehouse Property Ltd"
    assert gen_expense.get("amount") == 35000.0


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
