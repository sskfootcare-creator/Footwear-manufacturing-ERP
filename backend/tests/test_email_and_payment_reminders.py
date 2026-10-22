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
    build_multi_invoice_reminder_template,
    send_email,
    send_invoice_payment_reminder,
    send_multi_invoice_payment_reminder,
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
        self.invoices.update_many = AsyncMock(side_effect=self._update_many_invoices)
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

    async def _update_many_invoices(self, query, update, upsert=False):
        target_ids = []
        if "_id" in query and isinstance(query["_id"], dict) and "$in" in query["_id"]:
            target_ids = [str(x) for x in query["_id"]["$in"]]
        modified = 0
        for inv in self.invoices_store:
            if not target_ids or str(inv["_id"]) in target_ids:
                if "$set" in update:
                    inv.update(update["$set"])
                if "$push" in update:
                    for k, v in update["$push"].items():
                        inv.setdefault(k, []).append(v)
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        inv[k] = inv.get(k, 0) + v
                modified += 1
        return MagicMock(acknowledged=True, modified_count=modified)

    def _find_invoices(self, query=None, projection=None):
        return MockCursor(self.invoices_store)

    async def _find_one_client(self, query):
        if not self.clients_store:
            return None
        if not query:
            return dict(self.clients_store[0])
        or_clauses = query.get("$or", [])
        if or_clauses:
            for c in self.clients_store:
                c_name = (c.get("company_name") or c.get("name") or "").lower()
                for clause in or_clauses:
                    for k in ("company_name", "name"):
                        if k in clause:
                            pat = clause[k].get("$regex") if isinstance(clause[k], dict) else clause[k]
                            if pat and pat.strip("^$").lower() == c_name:
                                return dict(c)
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
        "grn_date": "2026-10-18",
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
    assert "GRN Date" in html
    assert "18-Oct-2026" in html
    assert "15-Oct-2026" in html
    assert "Invoice #" in html
    assert "GRN Date" in txt


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


def test_build_multi_invoice_reminder_template():
    invoices = [
        {
            "invoice_no": "SSK26-27-001",
            "invoice_date": "2026-09-01",
            "grn_date": "2026-09-06",
            "due_date": "2026-10-01",
            "po_number": "PO-100",
            "net_amount": 60000.0,
            "received_amount": 10000.0,
            "outstanding": 50000.0,
            "days_to_due": -21,
        },
        {
            "invoice_no": "SSK26-27-002",
            "invoice_date": "2026-09-15",
            "due_date": "2026-10-15",
            "po_number": "PO-200",
            "net_amount": 80000.0,
            "received_amount": 0.0,
            "outstanding": 80000.0,
            "days_to_due": -7,
        },
    ]
    client = {
        "company_name": "Relaxo Footwears",
        "contact_person": "Rajesh Kumar",
        "email": "rajesh@relaxo.com",
    }
    company = {
        "name": "SSK Footcare Manufacturing LLP",
        "bank_name": "HDFC BANK",
        "bank_acc": "50200105184765",
        "bank_ifsc": "HDFC0001452",
    }

    subj, txt, html = build_multi_invoice_reminder_template(
        invoices=invoices,
        client=client,
        company=company,
        include_bank_details=True,
    )

    # 1. Subject checks
    assert "OVERDUE STATEMENT" in subj
    assert "2 Overdue Invoices" in subj
    assert "Relaxo Footwears" in subj
    assert "₹1,30,000.00" in subj

    # 2. Text breakdown checks
    assert "Rajesh Kumar" in txt
    assert "SSK26-27-001" in txt
    assert "SSK26-27-002" in txt
    assert "PO-100" in txt
    assert "PO-200" in txt
    assert "TOTAL OVERDUE BALANCE : ₹1,30,000.00" in txt
    assert "50200105184765" in txt
    assert "GRN: 06-Sep-2026" in txt

    # 3. HTML table checks
    assert "SSK26-27-001" in html
    assert "SSK26-27-002" in html
    assert "HDFC0001452" in html
    assert "₹1,30,000.00" in html
    assert "GRN Date" in html
    assert "06-Sep-2026" in html
    assert "01-Sep-2026" in html
    assert "Overdue Period" in html


def test_multi_invoice_consolidated_reminder_send(test_client, mock_env):
    inv1_id = ObjectId()
    inv2_id = ObjectId()

    mock_env.invoices_store.extend([
        {
            "_id": inv1_id,
            "invoice_no": "SSK-OVERDUE-01",
            "client_name": "Woodland Footwear",
            "net_amount": 50000.0,
            "grand_total": 50000.0,
            "received_amount": 0.0,
            "outstanding": 50000.0,
            "due_date": "2026-09-01",
            "status": "overdue",
            "is_direct_invoice": True,
        },
        {
            "_id": inv2_id,
            "invoice_no": "SSK-OVERDUE-02",
            "client_name": "Woodland Footwear",
            "net_amount": 75000.0,
            "grand_total": 75000.0,
            "received_amount": 0.0,
            "outstanding": 75000.0,
            "due_date": "2026-09-15",
            "status": "overdue",
            "is_direct_invoice": True,
        },
    ])

    mock_env.clients_store.append({
        "company_name": "Woodland Footwear",
        "name": "Woodland Footwear",
        "email": "finance@woodland.com",
        "contact_person": "Vikas Singh",
    })

    mock_env.settings_store["email_config"] = {
        "gmail_user": "billing@sskfootcare.com",
        "gmail_app_password": "abcdefghijklmnop",
        "from_name": "SSK Accounts",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
    }

    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        # Send consolidated reminder for both invoices
        send_res = test_client.post(
            f"/api/invoices/{str(inv1_id)}/send-payment-reminder",
            json={
                "invoice_ids": [str(inv1_id), str(inv2_id)],
                "to_email": "finance@woodland.com",
                "subject": "OVERDUE STATEMENT: 2 Overdue Invoices (Woodland)",
                "attach_pdf": False,
                "include_bank_details": True,
            }
        )
        assert send_res.status_code == 200
        data = send_res.json()
        assert data["ok"] is True
        assert data["invoices_count"] == 2
        assert data["total_outstanding"] == 125000.0
        assert mock_instance.sendmail.called

        # Verify BOTH invoices got reminder recorded
        for target_id in (inv1_id, inv2_id):
            inv = [i for i in mock_env.invoices_store if i["_id"] == target_id][0]
            assert inv["reminder_count"] == 1
            assert len(inv["reminder_history"]) == 1
            assert inv["reminder_history"][0]["sent_to"] == "finance@woodland.com"
            assert inv["last_reminder_sent_to"] == "finance@woodland.com"


def test_overdue_reminders_summary_and_batch_dispatch(test_client, mock_env):
    inv_a = ObjectId()
    inv_b = ObjectId()
    inv_paid = ObjectId()

    mock_env.invoices_store = [
        {
            "_id": inv_a,
            "invoice_no": "SSK-OD-10",
            "client_name": "Campus Shoes",
            "net_amount": 40000.0,
            "grand_total": 40000.0,
            "received_amount": 0.0,
            "outstanding": 40000.0,
            "due_date": "2026-08-01",
            "status": "overdue",
            "is_direct_invoice": True,
        },
        {
            "_id": inv_b,
            "invoice_no": "SSK-OD-11",
            "client_name": "Campus Shoes",
            "net_amount": 60000.0,
            "grand_total": 60000.0,
            "received_amount": 0.0,
            "outstanding": 60000.0,
            "due_date": "2026-08-15",
            "status": "overdue",
            "is_direct_invoice": True,
        },
        {
            "_id": inv_paid,
            "invoice_no": "SSK-PAID-01",
            "client_name": "Campus Shoes",
            "net_amount": 50000.0,
            "grand_total": 50000.0,
            "received_amount": 50000.0,
            "outstanding": 0.0,
            "due_date": "2026-08-01",
            "status": "paid",
            "is_direct_invoice": True,
        },
    ]

    mock_env.payments_store = [
        {
            "_id": ObjectId(),
            "invoice_ids": [str(inv_paid)],
            "amount": 50000.0,
            "payment_date": "2026-08-01",
        }
    ]

    mock_env.clients_store = [
        {
            "company_name": "Campus Shoes",
            "name": "Campus Shoes",
            "email": "accounts@campusshoes.com",
            "contact_person": "Alok Gupta",
        }
    ]

    mock_env.settings_store["email_config"] = {
        "gmail_user": "billing@sskfootcare.com",
        "gmail_app_password": "abcdefghijklmnop",
        "from_name": "SSK Accounts",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
    }

    # 1. Test summary aggregation endpoint
    summary_res = test_client.get("/api/invoices/overdue-reminders-summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["ok"] is True
    assert summary_data["total_overdue_invoices"] == 2
    assert summary_data["total_overdue_amount"] == 100000.0
    assert len(summary_data["clients"]) == 1

    client_item = summary_data["clients"][0]
    assert client_item["client_name"] == "Campus Shoes"
    assert client_item["client_email"] == "accounts@campusshoes.com"
    assert client_item["total_outstanding"] == 100000.0
    assert len(client_item["invoices"]) == 2

    # 2. Test batch reminders dispatch endpoint
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        batch_payload = {
            "batches": [
                {
                    "client_name": "Campus Shoes",
                    "to_email": "accounts@campusshoes.com",
                    "invoice_ids": [str(inv_a), str(inv_b)],
                    "cc_emails": "billing-audit@sskfootcare.com",
                }
            ]
        }

        batch_res = test_client.post("/api/invoices/send-batch-overdue-reminders", json=batch_payload)
        assert batch_res.status_code == 200
        bdata = batch_res.json()
        assert bdata["ok"] is True
        assert bdata["sent_count"] == 1
        assert bdata["failed_count"] == 0
        assert mock_instance.sendmail.called


def test_safe_float_and_template_robustness():
    """Verify templates do not crash on empty strings or corrupt float values."""
    from services.email_service import _safe_float

    assert _safe_float("") == 0.0
    assert _safe_float("   ") == 0.0
    assert _safe_float(None) == 0.0
    assert _safe_float("invalid-123") == 0.0
    assert _safe_float("12500.50") == 12500.5
    assert _safe_float(45000) == 45000.0

    invoice = {
        "invoice_no": "SSK-EMPTY-01",
        "net_amount": "",
        "received_amount": None,
        "outstanding": "",
        "due_date": "2026-07-01",
    }
    client = {"company_name": "Test Client"}
    company = {"name": "SSK Footcare"}

    subj, txt, html = build_payment_reminder_template(invoice, client, company)
    assert "SSK-EMPTY-01" in subj
    assert "₹0.00" in txt
    assert "₹0.00" in html

    multi_subj, multi_txt, multi_html = build_multi_invoice_reminder_template([invoice], client, company)
    assert "SSK-EMPTY-01" in multi_txt
    assert "₹0.00" in multi_html


@pytest.mark.anyio
async def test_async_send_email_and_date_header():
    """Verify async_send_email runs non-blockingly and formats Date header properly."""
    from services.email_service import async_send_email
    import smtplib

    with patch("smtplib.SMTP_SSL") as mock_ssl:
        mock_instance = MagicMock()
        mock_ssl.return_value.__enter__.return_value = mock_instance

        ok, msg = await async_send_email(
            to_emails="customer@example.com",
            subject="Test Date and Async",
            text_body="Hello world",
            config={
                "gmail_user": "billing@sskfootcare.com",
                "gmail_app_password": "apppassword1234",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 465,
            },
        )

        assert ok is True
        assert mock_instance.sendmail.called
        call_args = mock_instance.sendmail.call_args[0]
        raw_email = call_args[2]
        assert "Date:" in raw_email


def test_smtp_timeout_diagnostic_message():
    """Verify timeout diagnostics point out cloud hosting port blocking and Resend API solution."""
    from services.email_service import verify_smtp_credentials
    import socket

    with patch("services.email_service.create_smtp_connection", side_effect=socket.timeout("Timed out")):
        ok, msg = verify_smtp_credentials("smtp.gmail.com", 587, "test@gmail.com", "pass1234", timeout=1)
        assert ok is False
        assert "timed out after" in msg
        assert "Resend API" in msg
        assert "Port 443" in msg
