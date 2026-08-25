"""Test invoice net_amount standardization, write-time persistence, and view consistency."""
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient
import server
from server import (
    oid,
    create_grn,
    delete_grn,
    list_invoices,
    get_invoice,
    list_clients,
    client_ledger,
    _compute_invoice_totals,
)
from models.vendors import GRNIn, GRNLineItem


class DummyRequest:
    """Mock Request for unit testing endpoints with auth state."""
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    monkeypatch.setattr(server, "client", c)
    monkeypatch.setattr(server, "db", d)
    yield d
    c.close()


@pytest.mark.anyio
async def test_invoice_net_amount_consistency(fresh_db, monkeypatch):
    """Verify: create an invoice, confirm net_amount equals grand_total (no GRN yet).
    Apply a GRN adjustment, confirm net_amount updates correctly and every view
    (list, detail, PDF/file, totals tile/clients ledger) shows the SAME number consistently.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    client_name = "Consistent Retailers Ltd"
    po_totals = _compute_invoice_totals(
        {"cgst_rate": 0, "sgst_rate": 0, "igst_rate": 0},
        [
            {
                "style_code": "SSK_CONSISTENT",
                "color": "Black",
                "size": "8",
                "quantity": 100,
                "amount": 10000.0,
                "unit_price": 100.0,
            }
        ]
    )

    # 1. Create an invoice
    inv_doc = {
        "invoice_no": "INV-CONSISTENT-001",
        "invoice_date": "25/08/2026",
        "invoice_iso_date": "2026-08-25",
        "due_date": None,
        "grn_date": None,
        "grn_recorded": False,
        "payment_terms_days": 45,
        "po_number": "PO-CONSISTENT-01",
        "po_numbers": ["PO-CONSISTENT-01"],
        "client_name": client_name,
        "line_items_snapshot": [
            {
                "style_code": "SSK_CONSISTENT",
                "color": "Black",
                "size": "8",
                "quantity": 100,
                "unit_price": 100.0,
                "amount": 10000.0,
            }
        ],
        **po_totals,
        "created_at": "2026-08-25T10:00:00Z",
    }
    res = await server.db.invoices.insert_one(inv_doc)
    inv_id = str(res.inserted_id)

    try:
        # Verify write-time persistence: net_amount equals grand_total when no GRN exists
        saved_inv = await server.db.invoices.find_one({"_id": oid(inv_id)})
        assert saved_inv["grand_total"] == 10000.0
        assert saved_inv["net_amount"] == 10000.0
        assert saved_inv["grn_adjustment"] == 0.0

        # Verify list view
        invoices_list = await list_invoices(dummy_req, client=client_name)
        assert len(invoices_list) == 1
        inv_item = invoices_list[0]
        assert inv_item["net_amount"] == 10000.0
        assert inv_item["grand_total"] == 10000.0
        assert inv_item["outstanding"] == 10000.0

        # Verify detail view
        inv_detail = await get_invoice(inv_id, dummy_req)
        assert inv_detail["net_amount"] == 10000.0
        assert inv_detail["grand_total"] == 10000.0
        assert inv_detail["grn_adjustment"] == 0.0

        # Verify clients summary & ledger
        clients_summary = await list_clients(dummy_req)
        c_item = next(c for c in clients_summary if c["client_name"] == client_name)
        assert c_item["total_invoiced"] == 10000.0
        assert c_item["outstanding"] == 10000.0

        ledger_data = await client_ledger(client_name, dummy_req)
        assert ledger_data["total_invoiced"] == 10000.0
        assert ledger_data["closing_balance"] == 10000.0

        # 2. Apply a GRN with short/rejected items (100 dispatched, 80 received -> 20 short @ 100 = 2000 adjustment)
        grn_payload = GRNIn(
            invoice_id=inv_id,
            grn_date="2026-08-25",
            client_reference="CLIENT-GRN-01",
            line_items=[
                GRNLineItem(
                    style_code="SSK_CONSISTENT",
                    color="Black",
                    size="8",
                    dispatched_qty=100,
                    received_qty=80,
                    rejected_qty=0,
                    accepted_qty=80,
                )
            ]
        )
        grn_res = await create_grn(grn_payload, dummy_req)
        grn_id = grn_res["id"]

        # Verify write-time update on invoice document
        updated_inv = await server.db.invoices.find_one({"_id": oid(inv_id)})
        assert updated_inv["grand_total"] == 10000.0
        assert updated_inv["grn_adjustment"] == 2000.0
        assert updated_inv["net_amount"] == 8000.0

        # Verify all views reflect the exact SAME net_amount of 8000.0
        # A) List view
        invoices_list_after_grn = await list_invoices(dummy_req, client=client_name)
        inv_item_after = invoices_list_after_grn[0]
        assert inv_item_after["net_amount"] == 8000.0
        assert inv_item_after["outstanding"] == 8000.0

        # B) Detail view
        inv_detail_after = await get_invoice(inv_id, dummy_req)
        assert inv_detail_after["net_amount"] == 8000.0
        assert inv_detail_after["grn_adjustment"] == 2000.0
        assert inv_detail_after["outstanding"] == 8000.0

        # C) Clients summary
        clients_summary_after = await list_clients(dummy_req)
        c_item_after = next(c for c in clients_summary_after if c["client_name"] == client_name)
        assert c_item_after["total_invoiced"] == 8000.0
        assert c_item_after["outstanding"] == 8000.0

        # D) Client ledger
        ledger_data_after = await client_ledger(client_name, dummy_req)
        assert ledger_data_after["total_invoiced"] == 8000.0
        assert ledger_data_after["closing_balance"] == 8000.0


        # 3. Delete the GRN and verify rollback
        await delete_grn(grn_id, dummy_req)
        inv_rolled_back = await server.db.invoices.find_one({"_id": oid(inv_id)})
        assert inv_rolled_back["net_amount"] == 10000.0
        assert inv_rolled_back["grn_adjustment"] == 0.0

    finally:
        await server.db.invoices.delete_one({"_id": oid(inv_id)})
        await server.db.grns.delete_many({"invoice_id": inv_id})
