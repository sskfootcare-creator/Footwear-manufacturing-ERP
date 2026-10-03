import pytest
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock
from routes.pos import compute_payroll


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
            self.styles_store = {}
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
            self.advances.count_documents = AsyncMock(return_value=0)

            self.cash_ledger = MagicMock()
            self.bank_accounts = MagicMock()
            self.bank_accounts.find_one = AsyncMock(side_effect=self._find_one_bank)
            self.bank_accounts.find = MagicMock(side_effect=self._find_banks)

            self.expenses = MagicMock()
            self.expenses.insert_one = AsyncMock(side_effect=self._insert_expense)
            self.expenses.find_one = AsyncMock(side_effect=self._find_one_expense)
            self.expenses.find = MagicMock(side_effect=self._find_expenses)

            self.production_jobs = MagicMock()
            self.production_jobs.find = MagicMock(side_effect=self._find_jobs)

            self.styles = MagicMock()
            self.styles.find = MagicMock(side_effect=self._find_styles)

            self.wage_payments = MagicMock()
            self.wage_payments.find = MagicMock(return_value=MockCursor([]))
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
            return MagicMock(modified_count=1)

        def _find_one_bank(self, q):
            oid_val = q.get("_id")
            return self.bank_accounts_store.get(str(oid_val))

        def _find_banks(self, q=None):
            return MockCursor(list(self.bank_accounts_store.values()))

        def _insert_expense(self, doc):
            new_id = doc.get("_id") or ObjectId()
            doc["_id"] = new_id
            self.expenses_store[str(new_id)] = doc
            res = MagicMock()
            res.inserted_id = new_id
            return res

        def _find_one_expense(self, q):
            oid_val = str(q.get("_id"))
            return self.expenses_store.get(oid_val)

        def _find_expenses(self, q=None):
            return MockCursor(list(self.expenses_store.values()))

        def _find_jobs(self, q=None):
            return MockCursor(list(self.jobs_store.values()))

        def _find_styles(self, q=None):
            return MockCursor(list(self.styles_store.values()))

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
    monkeypatch.setattr("routes.pos._get_user", _dummy_user)
    monkeypatch.setattr("routes.banking._get_db", lambda r: mock_payroll_env)
    monkeypatch.setattr("routes.banking._check_period_locked", AsyncMock())

    return TestClient(server.app)


@pytest.mark.anyio
async def test_contract_labour_earnings_in_payroll_and_bank_reconciliation(client, mock_payroll_env):
    # 1. Register a Karigar / Contractor in the workers master
    wid = str(ObjectId())
    mock_payroll_env.workers_store[wid] = {
        "_id": ObjectId(wid),
        "name": "Kailash Contractor",
        "skill": "upper",
        "rate_per_pair": 8.0,
        "active": True,
    }

    # 2. Register a Bank Account in the bank accounts master
    bid = str(ObjectId())
    mock_payroll_env.bank_accounts_store[bid] = {
        "_id": ObjectId(bid),
        "name": "Kotak Business Current",
        "bank_name": "Kotak Mahindra Bank",
    }

    # 3. Create a production job with Contract / Outside Labour assigned to this Karigar
    jid = str(ObjectId())
    mock_payroll_env.jobs_store[jid] = {
        "_id": ObjectId(jid),
        "po_number": "PO-2026-OUTSIDE-01",
        "style_code": "SSK_00999",
        "color": "BLACK",
        "size": "7",
        "quantity": 250,
        "completed_qty": 250,
        "stage": "lasting",
        "components": {
            "upper_done": True,
            "bottom_done": True,
            "sole_done": False,
        },
        "outside_labour": [
            {
                "name": "Embossing & Foil",
                "component": "upper",
                "worker_id": wid,
                "worker_name": "Kailash Contractor",
                "vendor": "Kailash Contractor",
                "rate": 7.5,
                "is_outside": True,
            }
        ],
    }

    # 4. Compute Payroll - Kailash Contractor must have piece-rate earnings from Contract Labour:
    # 250 pairs * ₹7.5 = ₹1,875.00
    payroll_data = await compute_payroll(db=mock_payroll_env)
    kailash_row = next((r for r in payroll_data["rows"] if r["worker_id"] == wid), None)
    assert kailash_row is not None, "Kailash Contractor should be present in Payroll"
    assert kailash_row["total_pairs"] == 250
    assert kailash_row["total_earning"] == 1875.0
    assert kailash_row["net_payable"] == 1875.0
    assert "Contract: Embossing & Foil" in kailash_row["by_role"]

    # 5. Pay Kailash Contractor from Kotak Bank Account via /api/advances
    res = client.post("/api/advances", json={
        "worker_id": wid,
        "amount": 1875.0,
        "date": "2026-09-30",
        "notes": "Full settlement for Embossing & Foil contract labour",
        "txn_type": "payment",
        "paid_via": "bank_transfer",
        "bank_account_id": bid,
    })
    assert res.status_code == 200, res.text
    adv_data = res.json()
    assert adv_data["paid_via"] == "bank_transfer"
    assert adv_data["bank_account_id"] == bid
    assert adv_data.get("linked_expense_id") is not None

    # 6. Verify that an ERP Expense linked to Kotak Bank Account was created in db.expenses
    exp_id = adv_data["linked_expense_id"]
    exp_doc = mock_payroll_env.expenses_store.get(str(exp_id))
    assert exp_doc is not None, "ERP Expense document must be created"
    assert exp_doc["category"] == "wages"
    assert exp_doc["amount"] == 1875.0
    assert exp_doc["bank_account_id"] == bid
    assert exp_doc["payee"] == "Kailash Contractor"
    assert "Wage Payment to Kailash Contractor" in exp_doc["notes"]

    # 7. Verify that after payment, Karigar remaining balance owed is 0.00
    payroll_data_after = await compute_payroll(db=mock_payroll_env)
    kailash_row_after = next((r for r in payroll_data_after["rows"] if r["worker_id"] == wid), None)
    assert kailash_row_after is not None
    assert kailash_row_after["payments_paid"] == 1875.0
    assert kailash_row_after["net_payable"] == 0.0
