import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server
from routes.settings import settings_router
from routes.invoice_packing import invoice_packing_router
from services.email_service import (
    get_email_config,
    clean_app_password,
    verify_smtp_credentials,
    build_payment_reminder_template,
    send_email,
    send_invoice_payment_reminder,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockAppDB:
    def __init__(self):
        self.settings_store = {}
        self.invoices_store = []
        self.clients_store = []
        self.audit_logs_store = []
        self.payments_store = []
        self.grns_store = []

        self.settings = MagicMock()
        self.settings.find_one = AsyncMock(side_effect=self._find_one_setting)
        self.settings.update_one = AsyncMock(side_effect=self._update_one_setting)

        self.invoices = MagicMock()
        self.invoices.find_one = AsyncMock(side_effect=self._find_one_invoice)
        self.invoices.update_one = AsyncMock(side_effect=self._update_one_invoice)
        self.invoices.find = MagicMock(side_effect=self._find_invoices)

        self.clients = MagicMock()
        self.clients.find_one = AsyncMock(side_effect=self._find_one_client)
        self.clients.find = MagicMock(side_effect=lambda q=None: MockCursor(self.clients_store))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(side_effect=self._insert_audit_log)
        self.audit_logs.find = MagicMock(side_effect=lambda q=None: MockCursor(self.audit_logs_store))

        self.payments = MagicMock()
        self.payments.find = MagicMock(side_effect=lambda q=None: MockCursor(self.payments_store))

        self.grns = MagicMock()
        self.grns.find = MagicMock(side_effect=lambda q=None: MockCursor(self.grns_store))

        self.dispatch_records = MagicMock()
        self.dispatch_records.find_one = AsyncMock(return_value=None)

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

    async def _find_one_invoice(self, query, projection=None):
        target_id = str(query.get("_id"))
        for inv in self.invoices_store:
            if str(inv["_id"]) == target_id:
                return dict(inv)
        return None

    async def _update_one_invoice(self, query, update, upsert=False):
        target_id = str(query.get("_id"))
        for inv in self.invoices_store:
            if str(inv["_id"]) == target_id:
                if "$set" in update:
                    inv.update(update["$set"])
                if "$push" in update:
                    for k, v in update["$push"].items():
                        inv.setdefault(k, []).append(v)
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        inv[k] = inv.get(k, 0) + v
                return MagicMock(acknowledged=True)
        return MagicMock(acknowledged=False)

    def _find_invoices(self, query=None, projection=None):
        return MockCursor(self.invoices_store)

    async def _find_one_client(self, query):
        if not self.clients_store:
            return None
        return dict(self.clients_store[0])

    async def _insert_audit_log(self, doc):
        self.audit_logs_store.append(dict(doc))
        return MagicMock(inserted_id="audit_123")


@pytest.fixture
def mock_env(monkeypatch):
    mock_db = MockAppDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def test_client(mock_env):
    app = FastAPI()
    app.include_router(settings_router)
    app.include_router(invoice_packing_router)
    app.mongodb = mock_env
    return TestClient(app)


def test_clean_app_password():
    assert clean_app_password("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    assert clean_app_password("  abcd   ") == "abcd"
    assert clean_app_password("") == ""
    assert clean_app_password(None) == ""


def test_build_payment_reminder_template():
    invoice = {
        "invoice_no": "SSK26-27-099",
        "invoice_date": "2026-10-15",
        "due_date": "2026-10-20",
        "po_number": "PO-9999",
        "net_amount": 50000.0,
        "received_amount": 10000.0,
        "outstanding": 40000.0,
    }
    client = {
        "company_name": "Bata India Ltd",
        "contact_person": "Mr. Sharma",
        "email": "sharma@bata.com",
    }
    company = {
        "name": "SSK Footcare Manufacturing LLP",
        "bank_name": "HDFC BANK",
        "bank_acc": "50200105184765",
        "bank_ifsc": "HDFC0001452",
    }

    subj, txt, html = build_payment_reminder_template(
        invoice=invoice,
        client=client,
        company=company,
        include_bank_details=True,
    )

    assert "SSK26-27-099" in subj
    assert "₹40,000.00" in subj
    assert "Bata India Ltd" in subj
    assert "Mr. Sharma" in txt
    assert "50200105184765" in txt
    assert "HDFC0001452" in txt
    assert "SSK Footcare ERP" in html
    assert "₹40,000.00" in html


def test_email_settings_endpoints(test_client, mock_env):
    # 1. GET initial email settings (not configured)
    res = test_client.get("/api/settings/email")
    assert res.status_code == 200
    data = res.json()
    assert data["is_configured"] is False
    assert data["has_app_password"] is False

    # 2. PUT email settings without verification
    payload = {
        "gmail_user": "billing@sskfootcare.com",
        "gmail_app_password": "abcd efgh ijkl mnop",
        "from_name": "SSK Accounts Team",
        "default_cc": "audit@sskfootcare.com",
        "verify_now": False,
    }
    res = test_client.put("/api/settings/email", json=payload)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 3. GET email settings again (should show masked password and configured=True)
    res = test_client.get("/api/settings/email")
    assert res.status_code == 200
    data = res.json()
    assert data["is_configured"] is True
    assert data["gmail_user"] == "billing@sskfootcare.com"
    assert data["has_app_password"] is True
    assert "••••" in data["masked_app_password"]
    assert "mnop" in data["masked_app_password"]
    assert data["from_name"] == "SSK Accounts Team"


def test_verify_and_test_email(test_client, mock_env):
    # Mock SMTP for verification
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        # Test verification route
        verify_res = test_client.post("/api/settings/email/verify", json={
            "gmail_user": "billing@sskfootcare.com",
            "gmail_app_password": "abcd efgh ijkl mnop",
        })
        assert verify_res.status_code == 200
        assert verify_res.json()["ok"] is True
        assert mock_instance.login.called

        # Save settings
        mock_env.settings_store["email_config"] = {
            "gmail_user": "billing@sskfootcare.com",
            "gmail_app_password": "abcdefghijklmnop",
            "from_name": "SSK Accounts",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
        }

        # Test sending a test email
        test_res = test_client.post("/api/settings/email/test", json={
            "test_recipient": "director@sskfootcare.com"
        })
        assert test_res.status_code == 200
        assert test_res.json()["ok"] is True
        assert mock_instance.sendmail.called


def test_invoice_payment_reminder_preview_and_send(test_client, mock_env):
    inv_id = ObjectId()
    mock_env.invoices_store.append({
        "_id": inv_id,
        "invoice_no": "INV-26-27-055",
        "client_name": "Metro Brands Ltd",
        "net_amount": 75000.0,
        "grand_total": 75000.0,
        "received_amount": 0.0,
        "outstanding": 75000.0,
        "due_date": "2026-10-18",
        "po_number": "PO-METRO-101",
        "file_b64": "",
    })
    mock_env.clients_store.append({
        "company_name": "Metro Brands Ltd",
        "name": "Metro Brands Ltd",
        "email": "accounts@metrobrands.com",
        "contact_person": "Anita Roy",
    })
    mock_env.settings_store["email_config"] = {
        "gmail_user": "billing@sskfootcare.com",
        "gmail_app_password": "abcdefghijklmnop",
        "from_name": "SSK Accounts",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
    }

    # 1. Preview
    preview_res = test_client.get(f"/api/invoices/{str(inv_id)}/payment-reminder-preview")
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["ok"] is True
    assert pdata["invoice_no"] == "INV-26-27-055"
    assert pdata["client_name"] == "Metro Brands Ltd"
    assert pdata["client_email"] == "accounts@metrobrands.com"
    assert pdata["contact_person"] == "Anita Roy"
    assert pdata["email_configured"] is True
    assert "INV-26-27-055" in pdata["default_subject"]

    # 2. Send reminder
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        send_res = test_client.post(
            f"/api/invoices/{str(inv_id)}/send-payment-reminder",
            json={
                "to_email": "accounts@metrobrands.com",
                "cc_emails": "internal@sskfootcare.com",
                "subject": "Payment Reminder: INV-26-27-055",
                "custom_message": "Kindly release payment today.",
                "attach_pdf": False,
                "include_bank_details": True,
            }
        )
        assert send_res.status_code == 200
        sdata = send_res.json()
        assert sdata["ok"] is True
        assert mock_instance.sendmail.called

        # Verify reminder history was updated in invoice
        inv = [i for i in mock_env.invoices_store if i["_id"] == inv_id][0]
        assert inv["reminder_count"] == 1
        assert len(inv["reminder_history"]) == 1
        assert inv["reminder_history"][0]["sent_to"] == "accounts@metrobrands.com"
        assert inv["last_reminder_sent_to"] == "accounts@metrobrands.com"
