"""Unit & Integration tests for Direct Invoice (No PO), Client Master & Partial Payments."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone

from models.clients import DirectInvoiceIn, DirectInvoiceLineItem, ClientIn


def test_direct_invoice_in_model():
    """Verify DirectInvoiceIn model validation and defaults."""
    item = DirectInvoiceLineItem(
        style_code="OXFORD-01",
        color="Black",
        size="8",
        qty=10,
        unit_price=500.0,
    )
    inv = DirectInvoiceIn(
        client_name="Test Footwear Emporium",
        client_gstin="09AABCT1332L1Z1",
        billing_address="Civil Lines, Kanpur, UP",
        place_of_supply="09-Uttar Pradesh",
        line_items=[item],
    )
    assert inv.client_name == "Test Footwear Emporium"
    assert inv.gst_rate == 5.0
    assert inv.payment_terms_days == 30
    assert len(inv.line_items) == 1
    assert inv.line_items[0].qty == 10
    assert inv.line_items[0].unit_price == 500.0


def _build_mock_db():
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.invoices.find.return_value = mock_cursor
    mock_db.dispatch_records.find.return_value = mock_cursor
    mock_db.counters.find_one = AsyncMock(return_value=None)
    mock_db.counters.update_one = AsyncMock()
    mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 42})
    mock_db.invoices.find_one = AsyncMock(return_value=None)
    mock_db.invoices.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.clients.find_one = AsyncMock(return_value=None)
    mock_db.clients.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    return mock_db


@pytest.mark.anyio
async def test_direct_invoice_tax_intra_state():
    """Verify intra-state (UP) gets 2.5% CGST + 2.5% SGST by default."""
    from routes.invoice_packing import create_direct_invoice
    
    mock_db = _build_mock_db()
    mock_req = MagicMock()
    mock_req.app.mongodb = mock_db

    with patch("routes.invoice_packing._get_db", return_value=mock_db), \
         patch("routes.invoice_packing._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin"})), \
         patch("services.supabase_invoice_service.sync_direct_invoice_to_supabase", return_value=None):

        payload = DirectInvoiceIn(
            client_name="UP Retailer",
            client_gstin="09ABCDE1234F1Z5",
            place_of_supply="09-Uttar Pradesh",
            client_state_code="09",
            payment_terms_days=30,
            line_items=[
                DirectInvoiceLineItem(style_code="DERBY-10", qty=20, unit_price=1000.0)
            ]
        )
        resp = await create_direct_invoice(payload, mock_req)
        assert resp.status_code == 200
        
        # Verify inserted document
        insert_args = mock_db.invoices.insert_one.call_args[0][0]
        assert insert_args["subtotal"] == 20000.0
        assert insert_args["cgst_rate"] == 2.5
        assert insert_args["sgst_rate"] == 2.5
        assert insert_args["igst_rate"] == 0.0
        assert insert_args["cgst_amount"] == 500.0
        assert insert_args["sgst_amount"] == 500.0
        assert insert_args["igst_amount"] == 0.0
        assert insert_args["grand_total"] == 21000.0
        assert insert_args["is_direct_invoice"] is True
        assert insert_args["po_number"] == "DIRECT"


@pytest.mark.anyio
async def test_direct_invoice_tax_inter_state():
    """Verify out-of-state gets 5.0% IGST by default."""
    from routes.invoice_packing import create_direct_invoice
    
    mock_db = _build_mock_db()
    mock_req = MagicMock()
    mock_req.app.mongodb = mock_db

    with patch("routes.invoice_packing._get_db", return_value=mock_db), \
         patch("routes.invoice_packing._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin"})), \
         patch("services.supabase_invoice_service.sync_direct_invoice_to_supabase", return_value=None):

        payload = DirectInvoiceIn(
            client_name="Delhi Shoes Wholesale",
            client_gstin="07ABCDE1234F1Z9",
            place_of_supply="07-Delhi",
            client_state_code="07",
            payment_terms_days=45,
            line_items=[
                DirectInvoiceLineItem(style_code="SNEAKER-02", qty=10, unit_price=800.0)
            ]
        )
        resp = await create_direct_invoice(payload, mock_req)
        assert resp.status_code == 200
        
        insert_args = mock_db.invoices.insert_one.call_args[0][0]
        assert insert_args["subtotal"] == 8000.0
        assert insert_args["cgst_rate"] == 0.0
        assert insert_args["sgst_rate"] == 0.0
        assert insert_args["igst_rate"] == 5.0
        assert insert_args["igst_amount"] == 400.0
        assert insert_args["grand_total"] == 8400.0


@pytest.mark.anyio
async def test_direct_invoice_custom_gst_rate():
    """Verify custom GST rate selection (e.g. 12% intra-state -> 6% + 6%)."""
    from routes.invoice_packing import create_direct_invoice
    
    mock_db = _build_mock_db()
    mock_req = MagicMock()
    mock_req.app.mongodb = mock_db

    with patch("routes.invoice_packing._get_db", return_value=mock_db), \
         patch("routes.invoice_packing._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin"})), \
         patch("services.supabase_invoice_service.sync_direct_invoice_to_supabase", return_value=None):

        payload = DirectInvoiceIn(
            client_name="UP Premium Boutique",
            place_of_supply="09-Uttar Pradesh",
            gst_rate=12.0,
            line_items=[
                DirectInvoiceLineItem(style_code="BOOT-PREMIUM", qty=5, unit_price=2000.0)
            ]
        )
        resp = await create_direct_invoice(payload, mock_req)
        assert resp.status_code == 200
        
        insert_args = mock_db.invoices.insert_one.call_args[0][0]
        assert insert_args["subtotal"] == 10000.0
        assert insert_args["cgst_rate"] == 6.0
        assert insert_args["sgst_rate"] == 6.0
        assert insert_args["cgst_amount"] == 600.0
        assert insert_args["sgst_amount"] == 600.0
        assert insert_args["grand_total"] == 11200.0


def test_direct_invoice_decoration_and_partial_payment():
    """Verify _decorate_invoice sets due_date and tracks partial payments correctly."""
    from routes.invoice_packing import _decorate_invoice
    
    inv_id = str(ObjectId())
    doc = {
        "_id": ObjectId(inv_id),
        "invoice_no": "SSK26-27-042",
        "invoice_date": "01/09/2026",
        "invoice_iso_date": "2026-09-01",
        "due_date": "2026-10-01",
        "payment_terms_days": 30,
        "is_direct_invoice": True,
        "grand_total": 50000.0,
        "grn_date": None,
    }
    
    # 1. Zero payments: status = pending, outstanding = 50000
    dec1 = _decorate_invoice(doc, payments_map={}, grns_map={})
    assert dec1["due_date"] == "2026-10-01"
    assert dec1["outstanding"] == 50000.0
    assert dec1["status"] in ("pending", "overdue")

    # 2. Partial payment of ₹20,000: status = partial, outstanding = 30000
    dec2 = _decorate_invoice(doc, payments_map={inv_id: 20000.0}, grns_map={})
    assert dec2["received_amount"] == 20000.0
    assert dec2["outstanding"] == 30000.0
    assert dec2["status"] == "partial"

    # 3. Full payment of ₹50,000: status = paid, outstanding = 0
    dec3 = _decorate_invoice(doc, payments_map={inv_id: 50000.0}, grns_map={})
    assert dec3["received_amount"] == 50000.0
    assert dec3["outstanding"] == 0.0
    assert dec3["status"] == "paid"


@pytest.mark.anyio
async def test_client_master_create_and_list():
    """Verify Client Master creation and list endpoint."""
    from routes.pos import create_or_update_client_master, list_clients_master

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {"_id": ObjectId(), "company_name": "Bata India", "gstin": "09BATA1234A1Z1", "payment_terms_days": 45}
    ])
    mock_db.clients.find.return_value = mock_cursor
    mock_db.clients.find_one = AsyncMock(return_value=None)
    mock_db.clients.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    mock_req = MagicMock()
    mock_req.json = AsyncMock(return_value={
        "company_name": "Liberty Shoes",
        "gstin": "09LIB1234F1Z0",
        "billing_address": "Karnal, Haryana",
        "payment_terms_days": 60,
    })

    with patch("routes.pos.get_db", return_value=mock_db), \
         patch("routes.pos._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin"})), \
         patch("services.supabase_invoice_service.ensure_client_entity", return_value=None):

        res = await create_or_update_client_master(mock_req)
        assert mock_db.clients.insert_one.called
        insert_doc = mock_db.clients.insert_one.call_args[0][0]
        assert insert_doc["company_name"] == "Liberty Shoes"
        assert insert_doc["payment_terms_days"] == 60

        listed = await list_clients_master(mock_req)
        assert len(listed) == 1
        assert listed[0]["company_name"] == "Bata India"

