import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.workers import workers_router
from models.workers import WorkerIn, SetPinIn, WorkerLoginIn, AdvanceIn, WagePaymentIn
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
        self.cash_ledger_store = {}
        self.wage_payments_store = {}
        self.bank_accounts_store = {}

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

        self.cash_ledger = MagicMock()
        self.cash_ledger.find_one = AsyncMock(side_effect=self._find_one_cash)
        self.cash_ledger.find = MagicMock(side_effect=self._find_cash)
        self.cash_ledger.update_one = AsyncMock(side_effect=self._update_cash)

        self.wage_payments = MagicMock()
        self.wage_payments.find_one = AsyncMock(side_effect=self._find_one_wage_payment)
        self.wage_payments.find = MagicMock(side_effect=self._find_wage_payments)
        self.wage_payments.insert_one = AsyncMock(side_effect=self._insert_wage_payment)

        self.bank_accounts = MagicMock()
        self.bank_accounts.find_one = AsyncMock(side_effect=self._find_one_bank_account)

        self.expenses_store = {}
        self.expenses = MagicMock()
        self.expenses.find = MagicMock(side_effect=self._find_expenses)
        self.expenses.find_one = AsyncMock(side_effect=self._find_one_expense)
        self.expenses.insert_one = AsyncMock(side_effect=self._insert_expense)
        self.expenses.update_one = AsyncMock(side_effect=self._update_expense)
        self.expenses.delete_one = AsyncMock(side_effect=self._delete_expense)

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock()

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

    async def _find_one_cash(self, query):
        oid_str = str(query.get("_id"))
        return self.cash_ledger_store.get(oid_str)

    def _find_cash(self, query=None):
        return MockCursor(list(self.cash_ledger_store.values()))

    async def _update_cash(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.cash_ledger_store:
            doc = self.cash_ledger_store[oid_str]
            if "remaining_balance" in query and isinstance(query["remaining_balance"], dict):
                gte_val = query["remaining_balance"].get("$gte")
                if gte_val is not None and doc.get("remaining_balance", 0.0) < gte_val:
                    return MagicMock(matched_count=0, modified_count=0)
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    doc[k] = round(doc.get(k, 0.0) + v, 2)
            if "$set" in update:
                doc.update(update["$set"])
            return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def _find_one_wage_payment(self, query):
        oid_str = str(query.get("_id"))
        return self.wage_payments_store.get(oid_str)

    def _find_wage_payments(self, query=None):
        docs = list(self.wage_payments_store.values())
        if query:
            if "worker_id" in query:
                docs = [d for d in docs if str(d.get("worker_id")) == str(query["worker_id"])]
            if "period_from" in query:
                docs = [d for d in docs if d.get("period_from") == query["period_from"]]
            if "period_to" in query:
                docs = [d for d in docs if d.get("period_to") == query["period_to"]]
        return MockCursor(docs)

    async def _insert_wage_payment(self, doc):
        oid = doc.get("_id") or ObjectId()
        doc["_id"] = oid
        self.wage_payments_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _find_one_bank_account(self, query):
        oid_str = str(query.get("_id"))
        return self.bank_accounts_store.get(oid_str)

    def _find_expenses(self, query=None):
        docs = list(self.expenses_store.values())
        if query:
            if "category" in query:
                docs = [d for d in docs if d.get("category") == query["category"]]
            if "bank_account_id" in query:
                docs = [d for d in docs if d.get("bank_account_id") == query["bank_account_id"]]
        return MockCursor(docs)

    async def _find_one_expense(self, query):
        oid_str = str(query.get("_id"))
        return self.expenses_store.get(oid_str)

    async def _insert_expense(self, doc):
        oid = doc.get("_id") or ObjectId()
        doc["_id"] = oid
        self.expenses_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_expense(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.expenses_store:
            doc = self.expenses_store[oid_str]
            if "$set" in update:
                doc.update(update["$set"])
            return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def _delete_expense(self, query):
        oid_str = str(query.get("_id"))
        self.expenses_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)


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


def test_wage_payment_in_model():
    wp = WagePaymentIn(
        worker_id="w123",
        worker_name="Ramesh",
        amount=1500.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="cash",
        cash_ledger_id="cash_1",
        date="2026-08-16",
        notes="First fortnight payout",
        override_reason=None,
    )
    assert wp.amount == 1500.0
    assert wp.paid_via == "cash"
    assert wp.cash_ledger_id == "cash_1"

    wp_upi = WagePaymentIn(
        worker_id="w123",
        worker_name="Ramesh",
        amount=2500.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="upi",
        bank_account_id="bank_acc_1",
        upi_reference="UPI/623456789012/CR",
        linked_expense_id="exp_999",
        date="2026-08-16",
    )
    assert wp_upi.paid_via == "upi"
    assert wp_upi.upi_reference == "UPI/623456789012/CR"
    assert wp_upi.bank_account_id == "bank_acc_1"
    assert wp_upi.linked_expense_id == "exp_999"


@pytest.mark.anyio
async def test_wage_payment_exact_match_success_and_cash_ledger_drawdown(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Manish",
        "rate_per_pair": 20.0,
        "skill": "cutting",
        "active": True,
    }

    # Setup a production job completed by Manish in 2026-08-01 to 2026-08-15
    jid = str(ObjectId())
    mock_workers_env.jobs_store[jid] = {
        "_id": ObjectId(jid),
        "po_number": "PO-100",
        "style_code": "ST-01",
        "color": "Black",
        "size": "7",
        "updated_at": "2026-08-05T10:00:00Z",
        "stage": "cutting",
        "quantity": 100,
        "completed_qty": 100,
        "assignments": {"cutting": {"worker_id": wid, "completed_qty": 100, "rate_per_pair": 20.0}},
        "history": [
            {"event": "stage_update", "stage": "cutting", "role": "cutting", "worker_id": wid, "completed_qty": 100, "rate_per_pair": 20.0, "at": "2026-08-05T10:00:00Z"}
        ],
    }

    # Setup cash ledger entry with 5000 remaining balance
    cash_id = str(ObjectId())
    mock_workers_env.cash_ledger_store[cash_id] = {
        "_id": ObjectId(cash_id),
        "amount": 5000.0,
        "remaining_balance": 5000.0,
        "date": "2026-08-01",
        "notes": "Bank ATM cash withdrawal",
    }

    # 1. Check payroll computed owed (100 pairs * 20 = 2000)
    from routes.pos import compute_payroll
    payroll = await compute_payroll(db=mock_workers_env, from_date="2026-08-01", to_date="2026-08-15")
    row = next(r for r in payroll["rows"] if r["worker_id"] == wid)
    assert row["net_payable"] == 2000.0
    assert row["actual_paid"] == 0.0
    assert row["remaining_owed"] == 2000.0

    # 2. Record wage payment matching exact owed amount (2000)
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "worker_name": "Manish",
        "amount": 2000.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "cash",
        "cash_ledger_id": cash_id,
        "date": "2026-08-16",
        "notes": "Settled in full via cash",
    })
    assert res.status_code == 200
    wp_data = res.json()
    assert wp_data["amount"] == 2000.0
    assert wp_data["paid_via"] == "cash"
    assert wp_data.get("linked_expense_id") is None
    assert len(mock_workers_env.expenses_store) == 0

    # 3. Confirm cash_ledger entry remaining_balance decreased from 5000 to 3000
    assert mock_workers_env.cash_ledger_store[cash_id]["remaining_balance"] == 3000.0

    # 4. Confirm report_payroll now shows actual_paid == 2000, remaining_owed == 0, payment_status == 'paid'
    payroll_after = await compute_payroll(db=mock_workers_env, from_date="2026-08-01", to_date="2026-08-15")
    row_after = next(r for r in payroll_after["rows"] if r["worker_id"] == wid)
    assert row_after["actual_paid"] == 2000.0
    assert row_after["remaining_owed"] == 0.0
    assert row_after["payment_status"] == "paid"
    assert row_after["is_overpaid"] is False


@pytest.mark.anyio
async def test_wage_payment_overpayment_rejected_without_override(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Sunil",
        "rate_per_pair": 10.0,
        "skill": "stitching",
        "active": True,
    }

    # Worker has 1000 computed owed
    jid = str(ObjectId())
    mock_workers_env.jobs_store[jid] = {
        "_id": ObjectId(jid),
        "updated_at": "2026-08-05T10:00:00Z",
        "stage": "stitching",
        "quantity": 100,
        "completed_qty": 100,
        "assignments": {"stitching": {"worker_id": wid, "completed_qty": 100, "rate_per_pair": 10.0}},
        "history": [
            {"event": "stage_update", "stage": "stitching", "role": "stitching", "worker_id": wid, "completed_qty": 100, "rate_per_pair": 10.0, "at": "2026-08-05T10:00:00Z"}
        ],
    }

    cash_id = str(ObjectId())
    mock_workers_env.cash_ledger_store[cash_id] = {
        "_id": ObjectId(cash_id),
        "amount": 10000.0,
        "remaining_balance": 10000.0,
    }

    # Attempt to pay 1500 (> 1000) with no override_reason
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "amount": 1500.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "cash",
        "cash_ledger_id": cash_id,
        "date": "2026-08-16",
        "override_reason": "",
    })
    assert res.status_code == 400
    assert "override_reason is required" in res.json()["detail"]


@pytest.mark.anyio
async def test_wage_payment_overpayment_accepted_with_override_and_visible_in_payroll(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Sunil",
        "rate_per_pair": 10.0,
        "skill": "stitching",
        "active": True,
    }

    jid = str(ObjectId())
    mock_workers_env.jobs_store[jid] = {
        "_id": ObjectId(jid),
        "updated_at": "2026-08-05T10:00:00Z",
        "stage": "stitching",
        "quantity": 100,
        "completed_qty": 100,
        "assignments": {"stitching": {"worker_id": wid, "completed_qty": 100, "rate_per_pair": 10.0}},
        "history": [
            {"event": "stage_update", "stage": "stitching", "role": "stitching", "worker_id": wid, "completed_qty": 100, "rate_per_pair": 10.0, "at": "2026-08-05T10:00:00Z"}
        ],
    }

    cash_id = str(ObjectId())
    mock_workers_env.cash_ledger_store[cash_id] = {
        "_id": ObjectId(cash_id),
        "amount": 10000.0,
        "remaining_balance": 10000.0,
    }

    # Attempt same overpayment with valid override_reason
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "amount": 1500.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "cash",
        "cash_ledger_id": cash_id,
        "date": "2026-08-16",
        "override_reason": "Advance folded into this payment for festival expenses",
    })
    assert res.status_code == 200
    assert res.json()["override_reason"] == "Advance folded into this payment for festival expenses"

    # Confirm payroll reflects overpayment and reason clearly
    from routes.pos import compute_payroll
    payroll = await compute_payroll(db=mock_workers_env, from_date="2026-08-01", to_date="2026-08-15")
    row = next(r for r in payroll["rows"] if r["worker_id"] == wid)
    assert row["computed_owed"] == 1000.0
    assert row["actual_paid"] == 1500.0
    assert row["is_overpaid"] is True
    assert row["payment_status"] == "overpaid"
    assert "Advance folded into this payment" in row["override_reason"]


def test_wage_payment_overdrawing_cash_ledger_rejected(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Kailash",
        "rate_per_pair": 10.0,
        "skill": "lasting",
        "active": True,
    }

    cash_id = str(ObjectId())
    mock_workers_env.cash_ledger_store[cash_id] = {
        "_id": ObjectId(cash_id),
        "amount": 500.0,
        "remaining_balance": 200.0,  # Only 200 left in cash pool
    }

    # Attempt to pay 500 when only 200 left in cash ledger
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "amount": 500.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "cash",
        "cash_ledger_id": cash_id,
        "date": "2026-08-16",
        "override_reason": "Approved",
    })
    assert res.status_code == 400
    assert "Insufficient cash in ledger entry" in res.json()["detail"]


def test_wage_payment_bank_transfer_success(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Kailash",
        "rate_per_pair": 10.0,
        "skill": "lasting",
        "active": True,
    }

    bank_acc_id = str(ObjectId())
    mock_workers_env.bank_accounts_store[bank_acc_id] = {
        "_id": ObjectId(bank_acc_id),
        "name": "HDFC Primary Current A/C",
    }

    # Bank transfer payment with override
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "amount": 1000.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "bank_transfer",
        "bank_account_id": bank_acc_id,
        "date": "2026-08-16",
        "override_reason": "Direct NEFT wage payout",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["paid_via"] == "bank_transfer"
    assert data["bank_account_id"] == bank_acc_id
    assert data.get("linked_expense_id") is not None

    exp_id = data["linked_expense_id"]
    exp_doc = mock_workers_env.expenses_store.get(str(exp_id))
    assert exp_doc is not None
    assert exp_doc["category"] == "wages"
    assert exp_doc["amount"] == 1000.0
    assert exp_doc["paid_via"] == "bank"
    assert exp_doc["bank_account_id"] == bank_acc_id
    assert exp_doc["payee"] == "Kailash"
    assert exp_doc["linked_wage_payment_id"] == data["id"]
    assert "Wage payment to Kailash" in exp_doc["notes"]

    # List payments for worker
    res = client.get(f"/api/workers/{wid}/wage-payments")
    assert res.status_code == 200
    payments = res.json()
    assert len(payments) == 1
    assert payments[0]["linked_expense_id"] == exp_id


def test_wage_payment_upi_success(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Rakesh",
        "rate_per_pair": 12.0,
        "skill": "finishing",
        "active": True,
    }

    bank_acc_id = str(ObjectId())
    mock_workers_env.bank_accounts_store[bank_acc_id] = {
        "_id": ObjectId(bank_acc_id),
        "name": "ICICI Operations A/C",
    }

    # Record wage disbursement via UPI
    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "worker_name": "Rakesh",
        "amount": 1850.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "upi",
        "bank_account_id": bank_acc_id,
        "upi_reference": "UPI/123456789012/PAYMENT",
        "date": "2026-08-16",
        "notes": "UPI wage payout to karigar",
        "override_reason": "Advance settled, paying remainder via UPI",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["paid_via"] == "upi"
    assert data["bank_account_id"] == bank_acc_id
    assert data["upi_reference"] == "UPI/123456789012/PAYMENT"
    assert data["amount"] == 1850.0
    assert data.get("linked_expense_id") is not None

    # Confirm it saves in MongoDB store with upi_reference, paid_via="upi", and linked_expense_id
    payment_id = data["id"]
    saved_doc = mock_workers_env.wage_payments_store.get(str(payment_id))
    assert saved_doc is not None
    assert saved_doc["paid_via"] == "upi"
    assert saved_doc["upi_reference"] == "UPI/123456789012/PAYMENT"
    assert saved_doc["bank_account_id"] == bank_acc_id
    assert saved_doc["linked_expense_id"] == data["linked_expense_id"]

    # Confirm linked expense in expenses_store
    exp_id = saved_doc["linked_expense_id"]
    exp_doc = mock_workers_env.expenses_store.get(str(exp_id))
    assert exp_doc is not None
    assert exp_doc["category"] == "wages"
    assert exp_doc["amount"] == 1850.0
    assert exp_doc["paid_via"] == "bank"
    assert exp_doc["bank_account_id"] == bank_acc_id
    assert exp_doc["payee"] == "Rakesh"
    assert exp_doc["linked_wage_payment_id"] == payment_id
    assert "UPI/123456789012/PAYMENT" in exp_doc["notes"]

    # List payments for worker and verify upi fields and linked_expense_id returned
    res = client.get(f"/api/workers/{wid}/wage-payments")
    assert res.status_code == 200
    payments = res.json()
    assert len(payments) == 1
    assert payments[0]["paid_via"] == "upi"
    assert payments[0]["upi_reference"] == "UPI/123456789012/PAYMENT"
    assert payments[0]["linked_expense_id"] == exp_id


def test_wage_payment_upi_missing_bank_account(client, mock_workers_env):
    wid = str(ObjectId())
    mock_workers_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Rakesh",
        "active": True,
    }

    res = client.post(f"/api/workers/{wid}/wage-payments", json={
        "worker_id": wid,
        "amount": 1000.0,
        "period_from": "2026-08-01",
        "period_to": "2026-08-15",
        "paid_via": "upi",
        "upi_reference": "UPI/123456789012/PAYMENT",
        "date": "2026-08-16",
        "override_reason": "Override",
    })
    assert res.status_code == 400
    assert "bank_account_id is required when paid_via is 'upi'" in res.json()["detail"]


@pytest.mark.anyio
async def test_concurrent_wage_payment_requests_prevent_race_condition(monkeypatch):
    """Verify two concurrent cash wage-payment requests with balance only for one: exactly one succeeds, one rejected, balance >= 0."""
    import asyncio
    from routes.workers import create_wage_payment

    wid = ObjectId()
    cash_id = ObjectId()
    cash_entry = {
        "_id": cash_id,
        "amount": 5000.0,
        "remaining_balance": 5000.0,
        "date": "2026-08-10",
        "notes": "Cash pool",
    }
    wage_payments_store = {}
    db_lock = asyncio.Lock()

    mock_db = MagicMock()

    async def mock_update_cash(q, update):
        async with db_lock:
            gte_val = q.get("remaining_balance", {}).get("$gte", 0.0)
            if cash_entry["remaining_balance"] >= gte_val:
                inc_val = update.get("$inc", {}).get("remaining_balance", 0.0)
                cash_entry["remaining_balance"] += inc_val
                return MagicMock(modified_count=1)
            return MagicMock(modified_count=0)

    async def mock_find_one_cash(q):
        async with db_lock:
            if str(q.get("_id")) == str(cash_id):
                return dict(cash_entry)
            return None

    async def mock_find_one_worker(q):
        return {"_id": wid, "name": "Ramesh", "skill": "cutting"}

    async def mock_find_one_wp(q):
        return wage_payments_store.get(str(q.get("_id")))

    async def mock_insert_wp(doc):
        pid = ObjectId()
        doc["_id"] = pid
        wage_payments_store[str(pid)] = doc
        return MagicMock(inserted_id=pid)

    mock_db.cash_ledger.update_one = AsyncMock(side_effect=mock_update_cash)
    mock_db.cash_ledger.find_one = AsyncMock(side_effect=mock_find_one_cash)
    mock_db.workers.find_one = AsyncMock(side_effect=mock_find_one_worker)
    mock_db.wage_payments.insert_one = AsyncMock(side_effect=mock_insert_wp)
    mock_db.wage_payments.find_one = AsyncMock(side_effect=mock_find_one_wp)
    mock_db.wage_payments.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    req = MagicMock()
    req.app.mongodb = mock_db
    monkeypatch.setattr("routes.workers._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"}))
    monkeypatch.setattr("routes.pos.compute_payroll", AsyncMock(return_value={"rows": [{"worker_id": str(wid), "net_payable": 10000.0}]}))

    payload1 = WagePaymentIn(
        worker_id=str(wid),
        worker_name="Ramesh",
        amount=4000.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="cash",
        cash_ledger_id=str(cash_id),
        date="2026-08-16",
    )
    payload2 = WagePaymentIn(
        worker_id=str(wid),
        worker_name="Ramesh",
        amount=4000.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="cash",
        cash_ledger_id=str(cash_id),
        date="2026-08-16",
    )

    results = await asyncio.gather(
        create_wage_payment(str(wid), payload1, req),
        create_wage_payment(str(wid), payload2, req),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, dict) and r.get("paid_via") == "cash"]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 400
    assert "Insufficient cash in ledger entry" in failures[0].detail

    assert cash_entry["remaining_balance"] == 1000.0
    assert len(wage_payments_store) == 1


@pytest.mark.anyio
async def test_concurrent_wage_payment_overpayment_guard_prevents_timing_bypass(monkeypatch):
    """Verify two concurrent wage-payment requests for same worker/period where combined amount > computed_owed: exactly one succeeds, overpayment guard cannot be bypassed by timing."""
    import asyncio
    from routes.workers import create_wage_payment

    wid = ObjectId()
    cash_id = ObjectId()
    cash_entry = {
        "_id": cash_id,
        "amount": 20000.0,
        "remaining_balance": 20000.0,
        "date": "2026-08-10",
        "notes": "Ample cash pool",
    }
    wage_payments_store = {}
    db_lock = asyncio.Lock()

    mock_db = MagicMock()

    async def mock_update_cash(q, update):
        async with db_lock:
            gte_val = q.get("remaining_balance", {}).get("$gte", 0.0)
            if cash_entry["remaining_balance"] >= gte_val:
                inc_val = update.get("$inc", {}).get("remaining_balance", 0.0)
                cash_entry["remaining_balance"] += inc_val
                return MagicMock(modified_count=1)
            return MagicMock(modified_count=0)

    async def mock_find_one_cash(q):
        async with db_lock:
            if str(q.get("_id")) == str(cash_id):
                return dict(cash_entry)
            return None

    async def mock_find_one_worker(q):
        return {"_id": wid, "name": "Ramesh", "skill": "cutting"}

    async def mock_find_one_wp(q):
        return wage_payments_store.get(str(q.get("_id")))

    async def mock_insert_wp(doc):
        # Simulate slight async delay to expose any timing windows
        await asyncio.sleep(0.01)
        pid = ObjectId()
        doc["_id"] = pid
        wage_payments_store[str(pid)] = doc
        return MagicMock(inserted_id=pid)

    def mock_find_wage_payments(q):
        # Query existing payments from store for this worker/period
        matching = [
            d for d in wage_payments_store.values()
            if str(d.get("worker_id")) == str(q.get("worker_id"))
            and d.get("period_from") == q.get("period_from")
            and d.get("period_to") == q.get("period_to")
        ]
        return MagicMock(to_list=AsyncMock(return_value=matching))

    mock_db.cash_ledger.update_one = AsyncMock(side_effect=mock_update_cash)
    mock_db.cash_ledger.find_one = AsyncMock(side_effect=mock_find_one_cash)
    mock_db.workers.find_one = AsyncMock(side_effect=mock_find_one_worker)
    mock_db.wage_payments.insert_one = AsyncMock(side_effect=mock_insert_wp)
    mock_db.wage_payments.find_one = AsyncMock(side_effect=mock_find_one_wp)
    mock_db.wage_payments.find = MagicMock(side_effect=mock_find_wage_payments)

    req = MagicMock()
    req.app.mongodb = mock_db
    monkeypatch.setattr("routes.workers._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"}))
    # Worker is owed 5000.0 for this period
    monkeypatch.setattr("routes.pos.compute_payroll", AsyncMock(return_value={"rows": [{"worker_id": str(wid), "net_payable": 5000.0}]}))

    # Two concurrent requests for 3500.0 each. Neither exceeds 5000 individually, but combined 7000 > 5000.
    payload1 = WagePaymentIn(
        worker_id=str(wid),
        worker_name="Ramesh",
        amount=3500.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="cash",
        cash_ledger_id=str(cash_id),
        date="2026-08-16",
        override_reason="",
    )
    payload2 = WagePaymentIn(
        worker_id=str(wid),
        worker_name="Ramesh",
        amount=3500.0,
        period_from="2026-08-01",
        period_to="2026-08-15",
        paid_via="cash",
        cash_ledger_id=str(cash_id),
        date="2026-08-16",
        override_reason="",
    )

    results = await asyncio.gather(
        create_wage_payment(str(wid), payload1, req),
        create_wage_payment(str(wid), payload2, req),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, dict) and r.get("amount") == 3500.0]
    failures = [r for r in results if isinstance(r, HTTPException)]

    # Exactly one request must succeed, and the second must be rejected by overpayment guard
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 400
    assert "exceeds owed amount for period" in failures[0].detail

    # Only 1 wage payment recorded in the database
    assert len(wage_payments_store) == 1
    # Cash pool only decremented once: 20000 - 3500 = 16500
    assert cash_entry["remaining_balance"] == 16500.0


@pytest.mark.anyio
async def test_multi_concurrent_wage_payment_requests_high_contention(monkeypatch):
    """Verify 5 simultaneous concurrent wage payment requests for 1000 each against computed owed of 2500. Exactly 2 succeed, 3 rejected."""
    import asyncio
    from routes.workers import create_wage_payment

    wid = ObjectId()
    cash_id = ObjectId()
    cash_entry = {
        "_id": cash_id,
        "amount": 10000.0,
        "remaining_balance": 10000.0,
        "date": "2026-08-10",
    }
    wage_payments_store = {}
    db_lock = asyncio.Lock()

    mock_db = MagicMock()

    async def mock_update_cash(q, update):
        await asyncio.sleep(0.001)
        async with db_lock:
            gte_val = q.get("remaining_balance", {}).get("$gte", 0.0)
            if cash_entry["remaining_balance"] >= gte_val:
                inc_val = update.get("$inc", {}).get("remaining_balance", 0.0)
                cash_entry["remaining_balance"] = round(cash_entry["remaining_balance"] + inc_val, 2)
                return MagicMock(modified_count=1)
            return MagicMock(modified_count=0)

    async def mock_find_one_cash(q):
        async with db_lock:
            if str(q.get("_id")) == str(cash_id):
                return dict(cash_entry)
            return None

    async def mock_find_one_worker(q):
        return {"_id": wid, "name": "Ramesh", "skill": "cutting"}

    async def mock_find_one_wp(q):
        return wage_payments_store.get(str(q.get("_id")))

    async def mock_insert_wp(doc):
        await asyncio.sleep(0.001)
        pid = ObjectId()
        doc["_id"] = pid
        wage_payments_store[str(pid)] = doc
        return MagicMock(inserted_id=pid)

    def mock_find_wage_payments(q):
        matching = [
            d for d in wage_payments_store.values()
            if str(d.get("worker_id")) == str(q.get("worker_id"))
            and d.get("period_from") == q.get("period_from")
            and d.get("period_to") == q.get("period_to")
        ]
        return MagicMock(to_list=AsyncMock(return_value=matching))

    mock_db.cash_ledger.update_one = AsyncMock(side_effect=mock_update_cash)
    mock_db.cash_ledger.find_one = AsyncMock(side_effect=mock_find_one_cash)
    mock_db.workers.find_one = AsyncMock(side_effect=mock_find_one_worker)
    mock_db.wage_payments.insert_one = AsyncMock(side_effect=mock_insert_wp)
    mock_db.wage_payments.find_one = AsyncMock(side_effect=mock_find_one_wp)
    mock_db.wage_payments.find = MagicMock(side_effect=mock_find_wage_payments)

    req = MagicMock()
    req.app.mongodb = mock_db
    monkeypatch.setattr("routes.workers._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"}))
    # Worker is owed 2500.0 for this period
    monkeypatch.setattr("routes.pos.compute_payroll", AsyncMock(return_value={"rows": [{"worker_id": str(wid), "net_payable": 2500.0}]}))

    payloads = [
        WagePaymentIn(
            worker_id=str(wid),
            worker_name="Ramesh",
            amount=1000.0,
            period_from="2026-08-01",
            period_to="2026-08-15",
            paid_via="cash",
            cash_ledger_id=str(cash_id),
            date="2026-08-16",
            override_reason="",
        )
        for _ in range(5)
    ]

    results = await asyncio.gather(
        *(create_wage_payment(str(wid), p, req) for p in payloads),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, dict) and r.get("amount") == 1000.0]
    failures = [r for r in results if isinstance(r, HTTPException)]

    # Exactly 2 succeed (2 * 1000 = 2000 <= 2500), 3 fail (2000 + 1000 = 3000 > 2500)
    assert len(successes) == 2
    assert len(failures) == 3
    for f in failures:
        assert f.status_code == 400
        assert "exceeds owed amount for period" in f.detail

    assert len(wage_payments_store) == 2
    assert cash_entry["remaining_balance"] == 8000.0




