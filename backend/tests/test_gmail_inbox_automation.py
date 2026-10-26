"""Tests for Gmail Inbox GRN and Payment Automation."""

import pytest
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.gmail_extractor_service import (
    classify_email,
    extract_grn_data,
    extract_payment_data,
    match_with_erp,
    parse_and_match_email,
    extract_domain_from_email,
    normalize_root_domain,
    categorize_sender_sync,
    categorize_sender,
)


def test_classify_grn_email():
    subject = "Goods Receipt Note - GRN#98712 for PO 2220012750"
    body = "Dear Team, please find attached the goods receipt confirmation for 480 pairs dispatched against Invoice INV-2026-004."
    res = classify_email(subject, body, "reliance.retail@example.com")
    assert res["category"] == "GRN"
    assert res["sub_type"] == "GOODS_RECEIPT"
    assert res["confidence"] >= 0.7


def test_classify_payment_credit_email():
    subject = "Bank Alert: Your A/C has been credited with INR 1,50,000.00 via NEFT"
    body = "Dear Customer, INR 1,50,000.00 has been credited to your account ending in 4321 on 25-10-2026. UTR: HDFCR52026102500129. Remittance from Metro Brands against Invoice INV-2026-001."
    res = classify_email(subject, body, "alerts@hdfcbank.net")
    assert res["category"] == "PAYMENT"
    assert res["sub_type"] == "CLIENT_PAYMENT"
    assert res["confidence"] >= 0.7


def test_extract_grn_entities():
    subject = "Goods Acceptance / GRN Advice: PO 2220012750"
    body = """
    Invoice No: INV-2026-004
    PO Number: 2220012750
    Delivery Challan: DC-8871
    GRN Date: 2026-10-24
    Total Dispatched: 500 pairs
    Total Received: 500 pairs
    Total Accepted: 492 pairs
    Total Rejected: 8 pairs
    Remarks: Minor scuffing on 8 pairs.
    """
    grn_data = extract_grn_data(subject, body, "buyer@bata.in")
    assert grn_data["invoice_no"] == "INV-2026-004"
    assert grn_data["po_number"] == "2220012750"
    assert grn_data["total_dispatched"] == 500
    assert grn_data["total_received"] == 500
    assert grn_data["total_accepted"] == 492
    assert grn_data["total_rejected"] == 8
    assert grn_data["received_date"] == "2026-10-24"


def test_extract_payment_entities():
    subject = "Payment Remittance Advice - Metro Brands Ltd"
    body = """
    We have processed electronic payment via RTGS:
    Amount: INR 2,40,000.50
    Value Date: 2026-10-25
    UTR No: ICICR520261025987654
    Bank: ICICI Bank
    Credited Account: A/C ending with 9812
    Against Invoices: INV-2026-010, INV-2026-011
    """
    pay_data = extract_payment_data(subject, body, "accounts@metrobrands.com")
    assert pay_data["amount"] == 240000.50
    assert pay_data["reference"] == "ICICR520261025987654"
    assert pay_data["mode"] == "RTGS"
    assert pay_data["payment_date"] == "2026-10-25"
    assert "INV-2026-010" in pay_data["invoice_numbers"]
    assert "INV-2026-011" in pay_data["invoice_numbers"]
    assert pay_data["bank_account_last4"] == "9812"


@pytest.mark.anyio
async def test_erp_matching_flow():
    """Verify ERP cross-matching logic for GRN and Payment."""
    import server
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    test_inv_id = ObjectId()
    inv_doc = {
        "_id": test_inv_id,
        "invoice_no": "INV-2026-099",
        "po_number": "PO-998811",
        "client_name": "Metro Brands Ltd",
        "grand_total": 75000.0,
        "net_amount": 75000.0,
        "total_pairs": 300,
        "status": "APPROVED",
        "invoice_date": "2026-10-20",
        "due_date": "2026-11-20",
        "line_items": [
            {"style_code": "ART-OXFORD", "color": "Tan", "size": "8", "dispatched_qty": 150, "quantity": 150},
            {"style_code": "ART-OXFORD", "color": "Tan", "size": "9", "dispatched_qty": 150, "quantity": 150},
        ]
    }

    test_bank_id = ObjectId()
    bank_doc = {
        "_id": test_bank_id,
        "name": "HDFC Current Account",
        "bank_name": "HDFC Bank",
        "account_number": "50200012344321",
        "current_balance": 500000.0,
    }

    await db.invoices.delete_many({"invoice_no": "INV-2026-099"})
    await db.invoices.insert_one(inv_doc)
    await db.bank_accounts.delete_many({"account_number": "50200012344321"})
    await db.bank_accounts.insert_one(bank_doc)

    # 1. Test GRN matching
    grn_extracted = {
        "invoice_no": "INV-2026-099",
        "po_number": "PO-998811",
        "total_received": 300,
        "total_accepted": 298,
        "total_rejected": 2,
        "received_date": "2026-10-25",
    }
    match_grn = await match_with_erp("GRN", grn_extracted, db)
    assert match_grn["is_matched"] is True
    assert match_grn["matched_invoice"]["invoice_no"] == "INV-2026-099"
    assert match_grn["match_confidence"] >= 0.9

    # 2. Test Payment matching
    pay_extracted = {
        "amount": 75000.0,
        "payment_date": "2026-10-25",
        "reference": "HDFCR520261025TEST1",
        "bank_account_last4": "4321",
        "invoice_numbers": ["INV-2026-099"],
        "client_name": "Metro Brands",
    }
    match_pay = await match_with_erp("PAYMENT", pay_extracted, db)
    assert match_pay["is_matched"] is True
    assert match_pay["matched_bank_account"]["account_number"] == "50200012344321"
    assert str(test_inv_id) in match_pay["suggested_allocations"]
    assert match_pay["suggested_allocations"][str(test_inv_id)] == 75000.0

    # Clean up test records
    await db.invoices.delete_many({"invoice_no": "INV-2026-099"})
    await db.bank_accounts.delete_many({"account_number": "50200012344321"})


@pytest.mark.anyio
async def test_gmail_inbox_recording_helpers():
    """Test router recording helpers for GRN and Payment."""
    from routes.email_inbox import _record_grn_internal, _record_payment_internal
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    inv_id = ObjectId()
    inv_doc = {
        "_id": inv_id,
        "invoice_no": "INV-TEST-SYNC-01",
        "client_name": "Test Client Pvt Ltd",
        "grand_total": 50000.0,
        "net_amount": 50000.0,
        "total_pairs": 200,
        "status": "APPROVED",
        "invoice_date": "2026-10-25",
        "line_items": [
            {"style_code": "SNK-01", "color": "White", "size": "8", "dispatched_qty": 100, "quantity": 100},
            {"style_code": "SNK-01", "color": "White", "size": "9", "dispatched_qty": 100, "quantity": 100},
        ]
    }
    await db.invoices.delete_many({"invoice_no": "INV-TEST-SYNC-01"})
    await db.invoices.insert_one(inv_doc)

    # 1. Test GRN Recording
    grn_extracted = {
        "invoice_no": "INV-TEST-SYNC-01",
        "total_dispatched": 200,
        "total_received": 200,
        "total_accepted": 196,
        "total_rejected": 4,
        "grn_date": "2026-10-25",
        "client_reference": "DC-9011",
        "line_items": [
            {"style_code": "SNK-01", "color": "White", "size": "8", "dispatched_qty": 100, "received_qty": 100, "accepted_qty": 98, "rejected_qty": 2},
            {"style_code": "SNK-01", "color": "White", "size": "9", "dispatched_qty": 100, "received_qty": 100, "accepted_qty": 98, "rejected_qty": 2},
        ]
    }
    rec_grn = await _record_grn_internal(db, grn_extracted, str(inv_id), by="unit_test")
    assert rec_grn["type"] == "grn"
    assert rec_grn["invoice_no"] == "INV-TEST-SYNC-01"
    assert rec_grn["total_accepted"] == 196

    # Check DB GRN
    saved_grn = await db.grns.find_one({"invoice_id": str(inv_id)})
    assert saved_grn is not None
    assert saved_grn["total_rejected"] == 4

    # Check invoice flag
    updated_inv = await db.invoices.find_one({"_id": inv_id})
    assert updated_inv.get("grn_recorded") is True

    # 2. Test Client Payment Recording
    pay_extracted = {
        "amount": 50000.0,
        "payment_date": "2026-10-25",
        "mode": "NEFT",
        "reference": "HDFCR52026TESTPAY",
        "bank": "HDFC Bank",
        "notes": "Full settlement from client",
    }
    allocations = {str(inv_id): 50000.0}
    rec_pay = await _record_payment_internal(db, pay_extracted, allocations, by="unit_test")
    assert rec_pay["type"] == "payment"
    assert rec_pay["amount"] == 50000.0
    assert rec_pay["reference"] == "HDFCR52026TESTPAY"

    # Check DB payment
    saved_pay = await db.payments.find_one({"reference": "HDFCR52026TESTPAY"})
    assert saved_pay is not None
    assert saved_pay["amount"] == 50000.0

    # Check invoice marked PAID
    final_inv = await db.invoices.find_one({"_id": inv_id})
    assert final_inv.get("status") == "PAID"

    # Clean up
    await db.invoices.delete_many({"invoice_no": "INV-TEST-SYNC-01"})
    await db.grns.delete_many({"invoice_id": str(inv_id)})
    await db.payments.delete_many({"reference": "HDFCR52026TESTPAY"})


@pytest.mark.anyio
async def test_gmail_inbox_api_routes():
    """Verify HTTP API endpoints for Gmail Inbox Automation."""
    from httpx import AsyncClient, ASGITransport
    from server import app
    from auth import create_access_token, hash_password
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Find or create admin user
    admin_user = await db.users.find_one({"role": "admin"})
    if not admin_user:
        admin_doc = {
            "email": "admin@test-gmail.local",
            "password_hash": hash_password("Admin@123"),
            "role": "admin",
            "name": "Admin Tester",
            "active": True,
        }
        res = await db.users.insert_one(admin_doc)
        admin_doc["_id"] = res.inserted_id
        admin_user = admin_doc

    admin_id = str(admin_user["_id"])
    admin_email = admin_user.get("email", "admin@example.com")
    admin_token = create_access_token(admin_id, admin_email, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Seed test invoice and bank account
    test_inv_id = ObjectId()
    inv_doc = {
        "_id": test_inv_id,
        "invoice_no": "INV-API-TEST-99",
        "po_number": "PO-991100",
        "client_name": "Test Client Corp",
        "grand_total": 45000.0,
        "net_amount": 45000.0,
        "total_pairs": 150,
        "status": "APPROVED",
        "invoice_date": "2026-10-25",
        "line_items": [
            {"style_code": "SNK-02", "color": "Black", "size": "8", "dispatched_qty": 75, "quantity": 75},
            {"style_code": "SNK-02", "color": "Black", "size": "9", "dispatched_qty": 75, "quantity": 75},
        ]
    }
    await db.invoices.delete_many({"invoice_no": "INV-API-TEST-99"})
    await db.invoices.insert_one(inv_doc)

    test_bank_id = ObjectId()
    bank_doc = {
        "_id": test_bank_id,
        "name": "Kotak Operating A/c",
        "bank_name": "Kotak Mahindra Bank",
        "account_number": "100200300400",
        "current_balance": 200000.0,
        "active": True,
    }
    await db.bank_accounts.delete_many({"account_number": "100200300400"})
    await db.bank_accounts.insert_one(bank_doc)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. GET /api/gmail-inbox/status
        status_res = await ac.get("/api/gmail-inbox/status", headers=headers)
        assert status_res.status_code == 200
        status_json = status_res.json()
        assert "connected" in status_json
        assert "pending_grn_count" in status_json
        assert "pending_payment_count" in status_json

        # 2. GET & PUT /api/gmail-inbox/rules
        rules_get = await ac.get("/api/gmail-inbox/rules", headers=headers)
        assert rules_get.status_code == 200

        rules_put = await ac.put(
            "/api/gmail-inbox/rules",
            headers=headers,
            json={
                "auto_record_grn": True,
                "auto_record_payments": True,
                "min_confidence": 0.85,
                "auto_sync_interval_mins": 20,
                "require_exact_invoice_match": True,
            }
        )
        assert rules_put.status_code == 200
        assert rules_put.json()["rules"]["min_confidence"] == 0.85
        assert rules_put.json()["rules"]["auto_sync_interval_mins"] == 20

        # 3. POST /api/gmail-inbox/test-parse
        parse_grn = await ac.post(
            "/api/gmail-inbox/test-parse",
            headers=headers,
            json={
                "subject": "Delivery Acceptance: PO-991100 / INV-API-TEST-99",
                "sender": "stores@testclient.com",
                "body_text": "We have accepted 148 pairs out of 150 pairs for invoice INV-API-TEST-99. 2 pairs rejected.",
            }
        )
        assert parse_grn.status_code == 200
        p_json = parse_grn.json()
        assert p_json["category"] == "GRN"
        assert p_json["matched_invoice_no"] == "INV-API-TEST-99"

        parse_pay = await ac.post(
            "/api/gmail-inbox/test-parse",
            headers=headers,
            json={
                "subject": "Payment Advice: INR 45,000 Credited via RTGS",
                "sender": "accounts@testclient.com",
                "body_text": "UTR: KOTAKR202610259901 for settlement of invoice INV-API-TEST-99 into account ending in 0400.",
            }
        )
        assert parse_pay.status_code == 200
        pay_json = parse_pay.json()
        assert pay_json["category"] == "PAYMENT"

        # 4. Create and test Inbox Items: List, Get, Approve GRN
        grn_item_id = ObjectId()
        await db.gmail_inbox_items.insert_one({
            "_id": grn_item_id,
            "message_id": "test_msg_grn_01",
            "subject": "GRN Delivery Receipt for INV-API-TEST-99",
            "sender_name": "Warehouse Store",
            "from_email": "stores@testclient.com",
            "category": "GRN",
            "status": "pending_review",
            "confidence": 0.95,
            "extracted_data": {
                "invoice_no": "INV-API-TEST-99",
                "total_dispatched": 150,
                "total_received": 150,
                "total_accepted": 148,
                "total_rejected": 2,
            },
            "erp_match": {
                "is_matched": True,
                "matched_invoice": {"id": str(test_inv_id), "invoice_no": "INV-API-TEST-99"},
            },
            "created_at": "2026-10-25T16:00:00Z",
        })

        # List items
        items_res = await ac.get("/api/gmail-inbox/items?category=GRN&status=pending", headers=headers)
        assert items_res.status_code == 200
        items_list = items_res.json()["items"]
        assert any(i["id"] == str(grn_item_id) for i in items_list)

        # Get item
        single_res = await ac.get(f"/api/gmail-inbox/items/{grn_item_id}", headers=headers)
        assert single_res.status_code == 200
        assert single_res.json()["matched_invoice_no"] == "INV-API-TEST-99"

        # Approve GRN
        appr_grn_res = await ac.post(
            f"/api/gmail-inbox/items/{grn_item_id}/approve",
            headers=headers,
            json={"invoice_id": str(test_inv_id)}
        )
        assert appr_grn_res.status_code == 200
        assert appr_grn_res.json()["status"] == "success"

        # Verify item status is processed
        updated_item = await db.gmail_inbox_items.find_one({"_id": grn_item_id})
        assert updated_item["status"] == "processed"

        # 5. Create and Approve Payment Item
        pay_item_id = ObjectId()
        await db.gmail_inbox_items.insert_one({
            "_id": pay_item_id,
            "message_id": "test_msg_pay_01",
            "subject": "RTGS Remittance Credit INR 45,000",
            "sender_name": "Test Client Accounts",
            "from_email": "accounts@testclient.com",
            "category": "PAYMENT",
            "status": "pending_review",
            "confidence": 0.95,
            "extracted_data": {
                "amount": 45000.0,
                "reference": "UTR-API-TEST-1234",
                "mode": "RTGS",
                "payment_date": "2026-10-25",
            },
            "erp_match": {
                "is_matched": True,
                "matched_invoice": {"id": str(test_inv_id), "invoice_no": "INV-API-TEST-99"},
                "matched_bank_account": {"id": str(test_bank_id), "account_number": "100200300400"},
                "suggested_allocations": {str(test_inv_id): 45000.0},
            },
            "created_at": "2026-10-25T16:05:00Z",
        })

        appr_pay_res = await ac.post(
            f"/api/gmail-inbox/items/{pay_item_id}/approve",
            headers=headers,
            json={"override_invoice_id": str(test_inv_id), "override_bank_account_id": str(test_bank_id)}
        )
        assert appr_pay_res.status_code == 200
        assert appr_pay_res.json()["status"] == "success"

        # 6. Test Dismiss Item
        dis_item_id = ObjectId()
        await db.gmail_inbox_items.insert_one({
            "_id": dis_item_id,
            "message_id": "test_msg_dismiss_01",
            "subject": "Spam Newsletter",
            "category": "OTHER",
            "status": "pending_review",
            "created_at": "2026-10-25T16:10:00Z",
        })
        dis_res = await ac.post(f"/api/gmail-inbox/items/{dis_item_id}/dismiss", headers=headers)
        assert dis_res.status_code == 200
        dis_doc = await db.gmail_inbox_items.find_one({"_id": dis_item_id})
        assert dis_doc["status"] == "dismissed"

    # Clean up test artifacts
    await db.invoices.delete_many({"invoice_no": "INV-API-TEST-99"})
    await db.bank_accounts.delete_many({"account_number": "100200300400"})
    await db.gmail_inbox_items.delete_many({"_id": {"$in": [grn_item_id, pay_item_id, dis_item_id]}})
    await db.grns.delete_many({"invoice_id": str(test_inv_id)})
    await db.payments.delete_many({"reference": "UTR-API-TEST-1234"})


def test_sender_domain_extraction_and_normalization():
    """Verify clean domain extraction from headers and root domain normalization."""
    assert extract_domain_from_email("alerts@hdfcbank.net") == "hdfcbank.net"
    assert normalize_root_domain("hdfcbank.net") == "hdfcbank.net"

    assert extract_domain_from_email('"HDFC Bank Alerts" <alerts@mail.hdfcbank.net>') == "mail.hdfcbank.net"
    assert normalize_root_domain("mail.hdfcbank.net") == "hdfcbank.net"

    assert extract_domain_from_email("orders@siyaram.com") == "siyaram.com"
    assert normalize_root_domain("siyaram.com") == "siyaram.com"

    assert extract_domain_from_email("buyer@bata.in") == "bata.in"
    assert normalize_root_domain("bata.in") == "bata.in"

    assert extract_domain_from_email("notifications@mail.sbi.co.in") == "mail.sbi.co.in"
    assert normalize_root_domain("mail.sbi.co.in") == "sbi.co.in"

    assert extract_domain_from_email("<dispatch@metrobrands.com>") == "metrobrands.com"
    assert normalize_root_domain("metrobrands.com") == "metrobrands.com"


def test_categorize_sender_known_registries():
    """Verify categorization into Bank, Client, Marketplace, and Internal with formatted labels."""
    # 1. HDFC Bank -> HDFC Bank (Bank)
    res_hdfc = categorize_sender_sync("alerts@hdfcbank.net", sender_name="HDFC Bank Alerts")
    assert res_hdfc["sender_entity_type"] == "Bank"
    assert res_hdfc["sender_organization"] == "HDFC Bank"
    assert res_hdfc["sender_category_label"] == "HDFC Bank (Bank)"

    # 2. Siyaram.com -> Siyaram.com (Client)
    res_siyaram = categorize_sender_sync("order-desk@siyaram.com", sender_name="Siyaram Silk Mills")
    assert res_siyaram["sender_entity_type"] == "Client"
    assert res_siyaram["sender_organization"] == "Siyaram.com"
    assert res_siyaram["sender_category_label"] == "Siyaram.com (Client)"

    # 3. Bata India -> Bata India (Client)
    res_bata = categorize_sender_sync("buyer@bata.in")
    assert res_bata["sender_entity_type"] == "Client"
    assert res_bata["sender_category_label"] == "Bata India (Client)"

    # 4. Myntra -> Myntra (Marketplace)
    res_myntra = categorize_sender_sync("seller-ops@myntra.com")
    assert res_myntra["sender_entity_type"] == "Marketplace"
    assert res_myntra["sender_category_label"] == "Myntra (Marketplace)"

    # 5. SSK Footcare -> SSK Footcare (Internal)
    res_internal = categorize_sender_sync("admin@sskfootcare.com")
    assert res_internal["sender_entity_type"] == "Internal"
    assert res_internal["sender_category_label"] == "SSK Footcare (Internal)"


@pytest.mark.anyio
async def test_parse_and_match_email_sender_categorization():
    """Verify top-level pipeline enriches output with domain categorization."""
    # Test Bank email
    email_bank = {
        "message_id": "test_bank_email_101",
        "subject": "A/C Credited: INR 1,25,000 via NEFT from Metro Brands",
        "body_text": "INR 1,25,000 has been credited to your account ending 9999. UTR: HDFCR520261025881",
        "from_header": '"HDFC Bank Alerts" <alerts@hdfcbank.net>',
        "from_email": "alerts@hdfcbank.net",
        "sender_name": "HDFC Bank Alerts",
        "received_iso": datetime.now(timezone.utc).isoformat(),
        "attachments": [],
    }
    parsed_bank = await parse_and_match_email(email_bank)
    assert parsed_bank["sender_domain"] == "hdfcbank.net"
    assert parsed_bank["sender_entity_type"] == "Bank"
    assert parsed_bank["sender_organization"] == "HDFC Bank"
    assert parsed_bank["sender_category_label"] == "HDFC Bank (Bank)"

    # Test Client email
    email_client = {
        "message_id": "test_client_email_102",
        "subject": "Delivery Acceptance / GRN Advice for PO 2220012750",
        "body_text": "Dear SSK Team, 500 pairs received and 495 pairs accepted against invoice INV-2026-099.",
        "from_header": '"Siyaram Procurement" <procurement@siyaram.com>',
        "from_email": "procurement@siyaram.com",
        "sender_name": "Siyaram Procurement",
        "received_iso": datetime.now(timezone.utc).isoformat(),
        "attachments": [],
    }
    parsed_client = await parse_and_match_email(email_client)
    assert parsed_client["sender_domain"] == "siyaram.com"
    assert parsed_client["sender_entity_type"] == "Client"
    assert parsed_client["sender_organization"] == "Siyaram.com"
    assert parsed_client["sender_category_label"] == "Siyaram.com (Client)"


@pytest.mark.anyio
async def test_sender_domains_api_endpoints():
    """Verify GET, POST, and DELETE /api/gmail-inbox/sender-domains and items filtering."""
    import server
    from httpx import AsyncClient, ASGITransport
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    from auth import create_access_token
    admin_user = await db.users.find_one({"role": "admin"})
    if not admin_user:
        admin_doc = {
            "email": "admin@example.com",
            "name": "Admin Tester",
            "role": "admin",
            "roles": ["admin"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await db.users.insert_one(admin_doc)
        admin_doc["_id"] = res.inserted_id
        admin_user = admin_doc

    admin_id = str(admin_user["_id"])
    admin_email = admin_user.get("email", "admin@example.com")
    admin_token = create_access_token(admin_id, admin_email, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. GET sender-domains
        res_get = await ac.get("/api/gmail-inbox/sender-domains", headers=headers)
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert "custom_mappings" in data_get
        assert "registries_summary" in data_get
        assert data_get["registries_summary"]["known_banks_count"] > 0

        # 2. POST custom sender-domain mapping
        post_payload = {
            "domain": "customfootwearclient.com",
            "entity_type": "Client",
            "organization": "Custom Footwear Client",
        }
        res_post = await ac.post("/api/gmail-inbox/sender-domains", headers=headers, json=post_payload)
        assert res_post.status_code == 200
        assert res_post.json()["status"] == "success"
        assert res_post.json()["rule"]["category_label"] == "Custom Footwear Client (Client)"

        # Verify DB updated
        rules_doc = await db.settings.find_one({"_id": "gmail_automation_rules"})
        saved_rule = next((m for m in rules_doc.get("sender_domain_mappings", []) if m.get("domain") == "customfootwearclient.com"), None)
        assert saved_rule is not None
        assert saved_rule["entity_type"] == "Client"

        # 3. Insert mock items and test sender_type filtering
        mock_bank_item = ObjectId()
        mock_client_item = ObjectId()
        await db.gmail_inbox_items.insert_many([
            {
                "_id": mock_bank_item,
                "message_id": "mock_bank_1",
                "subject": "Bank Credit Alert",
                "sender_domain": "hdfcbank.net",
                "sender_entity_type": "Bank",
                "sender_category_label": "HDFC Bank (Bank)",
                "category": "PAYMENT",
                "status": "pending_review",
                "created_at": "2026-10-25T18:00:00Z",
            },
            {
                "_id": mock_client_item,
                "message_id": "mock_client_1",
                "subject": "GRN Acceptance",
                "sender_domain": "siyaram.com",
                "sender_entity_type": "Client",
                "sender_category_label": "Siyaram.com (Client)",
                "category": "GRN",
                "status": "pending_review",
                "created_at": "2026-10-25T18:05:00Z",
            }
        ])

        # Filter by sender_type=Bank
        res_filter_bank = await ac.get("/api/gmail-inbox/items?sender_type=Bank", headers=headers)
        assert res_filter_bank.status_code == 200
        bank_items = res_filter_bank.json()["items"]
        assert any(it["id"] == str(mock_bank_item) for it in bank_items)
        assert not any(it["id"] == str(mock_client_item) for it in bank_items)

        # Filter by sender_type=Client
        res_filter_client = await ac.get("/api/gmail-inbox/items?sender_type=Client", headers=headers)
        assert res_filter_client.status_code == 200
        client_items = res_filter_client.json()["items"]
        assert any(it["id"] == str(mock_client_item) for it in client_items)
        assert not any(it["id"] == str(mock_bank_item) for it in client_items)

        # 4. DELETE custom sender-domain mapping
        res_del = await ac.delete("/api/gmail-inbox/sender-domains/customfootwearclient.com", headers=headers)
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "success"

        # Clean up
        await db.gmail_inbox_items.delete_many({"_id": {"$in": [mock_bank_item, mock_client_item]}})






