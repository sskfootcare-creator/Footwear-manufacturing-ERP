import pytest
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock
from models.workers import AdvanceIn


class MockCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.idx = 0

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs)

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx < len(self.docs):
            doc = self.docs[self.idx]
            self.idx += 1
            return doc
        raise StopAsyncIteration


@pytest.fixture
def mock_payroll_env():
    class PayrollEnv:
        def __init__(self):
            self.workers_store = {}
            self.advances_store = {}
            self.cash_ledger_store = {}
            self.bank_accounts_store = {}
            self.expenses_store = {}
            self.jobs_store = {}
            self.wage_payments_store = {}

            self.workers = MagicMock()
            self.workers.find_one = AsyncMock(side_effect=self._find_one_worker)
            self.workers.find = MagicMock(side_effect=self._find_workers)

            self.advances = MagicMock()
            self.advances.find_one = AsyncMock(side_effect=self._find_one_advance)
            self.advances.find = MagicMock(side_effect=self._find_advances)
            self.advances.insert_one = AsyncMock(side_effect=self._insert_advance)
            self.advances.delete_one = AsyncMock(side_effect=self._delete_advance)
            self.advances.update_one = AsyncMock(side_effect=self._update_advance)
            self.advances.count_documents = AsyncMock(side_effect=self._count_advances)

            self.cash_ledger = MagicMock()
            self.cash_ledger.find_one = AsyncMock(side_effect=self._find_one_cash)
            self.cash_ledger.find = MagicMock(side_effect=self._find_cash)
            self.cash_ledger.update_one = AsyncMock(side_effect=self._update_cash)
            self.cash_ledger.delete_one = AsyncMock(side_effect=self._delete_cash)

            self.bank_accounts = MagicMock()
            self.bank_accounts.find_one = AsyncMock(side_effect=self._find_one_bank)
            self.bank_accounts.find = MagicMock(side_effect=self._find_banks)

            self.expenses = MagicMock()
            self.expenses.insert_one = AsyncMock(side_effect=self._insert_expense)
            self.expenses.delete_one = AsyncMock(side_effect=self._delete_expense)
            self.expenses.find_one = AsyncMock(side_effect=self._find_one_expense)
            self.expenses.find = MagicMock(side_effect=self._find_expenses)
            self.expenses.count_documents = AsyncMock(return_value=0)

            self.production_jobs = MagicMock()
            self.production_jobs.find = MagicMock(return_value=MockCursor([]))

            self.wage_payments = MagicMock()
            self.wage_payments.find = MagicMock(return_value=MockCursor([]))
            self.wage_payments.count_documents = AsyncMock(return_value=0)

            self.activity_logs = MagicMock()
            self.activity_logs.insert_one = AsyncMock()

        def _find_one_worker(self, q):
            oid_val = q.get("_id")
            return self.workers_store.get(str(oid_val))

        def _find_workers(self, q=None):
            return MockCursor(list(self.workers_store.values()))

        def _find_one_advance(self, q):
            oid_val = q.get("_id")
            return self.advances_store.get(str(oid_val))

        def _find_advances(self, q=None):
            docs = list(self.advances_store.values())
            if q and "worker_id" in q:
                docs = [d for d in docs if str(d.get("worker_id")) == str(q["worker_id"])]
            if q and "cash_ledger_id" in q:
                c_filter = q["cash_ledger_id"]
                if isinstance(c_filter, dict) and "$in" in c_filter:
                    docs = [d for d in docs if str(d.get("cash_ledger_id")) in c_filter["$in"]]
            return MockCursor(docs)

        def _insert_advance(self, doc):
            new_id = doc.get("_id") or ObjectId()
            doc["_id"] = new_id
            self.advances_store[str(new_id)] = doc
            res = MagicMock()
            res.inserted_id = new_id
            return res

        def _delete_advance(self, q):
            oid_val = str(q.get("_id"))
            if oid_val in self.advances_store:
                del self.advances_store[oid_val]
            return MagicMock(deleted_count=1)

        def _update_advance(self, q, u):
            oid_val = str(q.get("_id"))
            if oid_val in self.advances_store:
                if "$set" in u:
                    self.advances_store[oid_val].update(u["$set"])
            return MagicMock(modified_count=1)

        def _count_advances(self, q=None):
            docs = list(self.advances_store.values())
            if q and "cash_ledger_id" in q:
                docs = [d for d in docs if str(d.get("cash_ledger_id")) == str(q["cash_ledger_id"])]
            return len(docs)

        def _find_one_cash(self, q):
            oid_val = str(q.get("_id"))
            return self.cash_ledger_store.get(oid_val)

        def _find_cash(self, q=None):
            docs = list(self.cash_ledger_store.values())
            return MockCursor(docs)

        def _update_cash(self, q, update):
            oid_val = str(q.get("_id"))
            if oid_val not in self.cash_ledger_store:
                return MagicMock(modified_count=0)
            doc = self.cash_ledger_store[oid_val]
            if "remaining_balance" in q:
                gte = q["remaining_balance"].get("$gte", 0)
                if doc.get("remaining_balance", 0) < gte:
                    return MagicMock(modified_count=0)
            if "$inc" in update:
                inc_val = update["$inc"].get("remaining_balance", 0)
                doc["remaining_balance"] = round(doc.get("remaining_balance", 0) + inc_val, 2)
            return MagicMock(modified_count=1)

        def _delete_cash(self, q):
            oid_val = str(q.get("_id"))
            if oid_val in self.cash_ledger_store:
                del self.cash_ledger_store[oid_val]
            return MagicMock(deleted_count=1)

        def _find_one_bank(self, q):
            oid_val = str(q.get("_id"))
            return self.bank_accounts_store.get(oid_val)

        def _find_banks(self, q=None):
            return MockCursor(list(self.bank_accounts_store.values()))

        def _insert_expense(self, doc):
            new_id = doc.get("_id") or ObjectId()
            doc["_id"] = new_id
            self.expenses_store[str(new_id)] = doc
            res = MagicMock()
            res.inserted_id = new_id
            return res

        def _delete_expense(self, q):
            oid_val = str(q.get("_id"))
            if oid_val in self.expenses_store:
                del self.expenses_store[oid_val]
            return MagicMock(deleted_count=1)

        def _find_one_expense(self, q):
            oid_val = str(q.get("_id"))
            return self.expenses_store.get(oid_val)

        def _find_expenses(self, q=None):
            return MockCursor(list(self.expenses_store.values()))

    return PayrollEnv()


@pytest.fixture
def client(mock_payroll_env, monkeypatch):
    from fastapi.testclient import TestClient
    import server

    monkeypatch.setattr(server, "db", mock_payroll_env)
    async def _dummy_user(req):
        return {"id": "test_admin", "email": "admin@example.com", "role": "admin"}
    monkeypatch.setattr("routes.workers._get_user", _dummy_user)
    monkeypatch.setattr("routes.expenses._get_user", _dummy_user)
    monkeypatch.setattr("routes.banking._get_user", _dummy_user)
    monkeypatch.setattr("routes.banking._get_db", lambda r: mock_payroll_env)
    monkeypatch.setattr("routes.banking._check_period_locked", AsyncMock())

    return TestClient(server.app)


def test_advance_cash_drawdown_success(client, mock_payroll_env):
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {"_id": ObjectId(wid), "name": "Mohan Karigar", "skill": "stitching"}

    cid = str(ObjectId())
    mock_payroll_env.cash_ledger_store[cid] = {
        "_id": ObjectId(cid),
        "amount": 5000.0,
        "remaining_balance": 5000.0,
        "date": "2026-09-01",
        "notes": "ATM Withdrawal HDFC"
    }

    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 1500.0,
        "date": "2026-09-05",
        "notes": "Advance for medical emergency",
        "txn_type": "advance",
        "paid_via": "cash",
        "cash_ledger_id": cid,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["amount"] == 1500.0
    assert data["paid_via"] == "cash"
    assert data["cash_ledger_id"] == cid
    # Cash pool balance should now be 3500.0
    assert mock_payroll_env.cash_ledger_store[cid]["remaining_balance"] == 3500.0


def test_advance_cash_overdraft_fails(client, mock_payroll_env):
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {"_id": ObjectId(wid), "name": "Sohan Karigar"}

    cid = str(ObjectId())
    mock_payroll_env.cash_ledger_store[cid] = {
        "_id": ObjectId(cid),
        "amount": 1000.0,
        "remaining_balance": 500.0,
        "date": "2026-09-01",
    }

    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 800.0,
        "txn_type": "advance",
        "paid_via": "cash",
        "cash_ledger_id": cid,
    })
    assert res.status_code == 400
    assert "Insufficient cash in ledger entry" in res.json()["detail"]
    assert mock_payroll_env.cash_ledger_store[cid]["remaining_balance"] == 500.0


def test_advance_bank_transfer_creates_erp_expense(client, mock_payroll_env):
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {"_id": ObjectId(wid), "name": "Ramesh Karigar"}

    bid = str(ObjectId())
    mock_payroll_env.bank_accounts_store[bid] = {
        "_id": ObjectId(bid),
        "name": "HDFC Current",
        "bank_name": "HDFC Bank",
    }

    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 2500.0,
        "date": "2026-09-05",
        "notes": "Weekly wage payment",
        "txn_type": "payment",
        "paid_via": "bank_transfer",
        "bank_account_id": bid,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["paid_via"] == "bank_transfer"
    assert data["bank_account_id"] == bid
    assert data.get("linked_expense_id") is not None

    exp_id = data["linked_expense_id"]
    exp_doc = mock_payroll_env.expenses_store.get(str(exp_id))
    assert exp_doc is not None
    assert exp_doc["category"] == "wages"
    assert exp_doc["amount"] == 2500.0
    assert exp_doc["bank_account_id"] == bid
    assert exp_doc["payee"] == "Ramesh Karigar"
    assert "Wage Payment to Ramesh Karigar" in exp_doc["notes"]


def test_advance_upi_payment_creates_expense_with_ref(client, mock_payroll_env):
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {"_id": ObjectId(wid), "name": "Deepak Karigar"}

    bid = str(ObjectId())
    mock_payroll_env.bank_accounts_store[bid] = {
        "_id": ObjectId(bid),
        "name": "SBI Current",
        "bank_name": "State Bank of India",
    }

    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 3200.0,
        "date": "2026-09-05",
        "notes": "Festival advance",
        "txn_type": "advance",
        "paid_via": "upi",
        "bank_account_id": bid,
        "upi_reference": "UPI/429182390192/ADV",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["paid_via"] == "upi"
    assert data["upi_reference"] == "UPI/429182390192/ADV"
    assert data.get("linked_expense_id") is not None

    exp_id = data["linked_expense_id"]
    exp_doc = mock_payroll_env.expenses_store.get(str(exp_id))
    assert exp_doc is not None
    assert "UPI/429182390192/ADV" in exp_doc["notes"]


def test_delete_advance_reverses_cash_and_expense(client, mock_payroll_env):
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {"_id": ObjectId(wid), "name": "Mohan Karigar"}

    cid = str(ObjectId())
    mock_payroll_env.cash_ledger_store[cid] = {
        "_id": ObjectId(cid),
        "amount": 5000.0,
        "remaining_balance": 5000.0,
    }

    # Create cash advance
    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 1000.0,
        "paid_via": "cash",
        "cash_ledger_id": cid,
    })
    aid = res.json()["id"]
    assert mock_payroll_env.cash_ledger_store[cid]["remaining_balance"] == 4000.0

    # Delete advance -> should restore remaining_balance to 5000.0
    del_res = client.delete(f"/api/advances/{aid}")
    assert del_res.status_code == 200
    assert mock_payroll_env.cash_ledger_store[cid]["remaining_balance"] == 5000.0
