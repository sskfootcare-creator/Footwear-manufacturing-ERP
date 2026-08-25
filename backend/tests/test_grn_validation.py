"""Unit & integration tests for GRN received_qty <= dispatched_qty validation."""
import pytest
import os
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
import server
from server import (
    oid,
    create_grn,
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
async def test_grn_rejects_received_greater_than_dispatched(fresh_db, monkeypatch):
    """Verify: attempt to submit a GRN with received_qty exceeding dispatched_qty, confirm
    backend rejects it with a clear error; confirm a valid GRN still submits normally.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    # 1. Setup a test invoice
    inv_res = await server.db.invoices.insert_one({
        "invoice_no": "TEST-INV-GRN-VAL",
        "client_name": "Test Client Retail",
        "payment_terms_days": 45,
        "line_items_snapshot": [
            {
                "style_code": "SSK_OXFORD",
                "color": "Tan",
                "size": "7",
                "quantity": 50,
            }
        ]
    })
    inv_id = str(inv_res.inserted_id)

    try:
        # Case A: Invalid GRN with received_qty (60) > dispatched_qty (50)
        invalid_grn_payload = GRNIn(
            invoice_id=inv_id,
            grn_date="2026-08-25",
            client_reference="CLIENT-REF-001",
            line_items=[
                GRNLineItem(
                    style_code="SSK_OXFORD",
                    color="Tan",
                    size="7",
                    dispatched_qty=50,
                    received_qty=60, # EXCEEDS 50
                    rejected_qty=0,
                )
            ]
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_grn(invalid_grn_payload, dummy_req)

        assert exc_info.value.status_code == 400
        assert "Received quantity (60) cannot exceed dispatched quantity (50)" in exc_info.value.detail
        assert "SSK_OXFORD" in exc_info.value.detail

        # Case B: Invalid GRN with rejected_qty (15) > received_qty (10)
        invalid_grn_payload_rej = GRNIn(
            invoice_id=inv_id,
            grn_date="2026-08-25",
            client_reference="CLIENT-REF-002",
            line_items=[
                GRNLineItem(
                    style_code="SSK_OXFORD",
                    color="Tan",
                    size="7",
                    dispatched_qty=50,
                    received_qty=10,
                    rejected_qty=15, # EXCEEDS 10
                )
            ]
        )

        with pytest.raises(HTTPException) as exc_info_rej:
            await create_grn(invalid_grn_payload_rej, dummy_req)

        assert exc_info_rej.value.status_code == 400
        assert "Rejected quantity (15) cannot exceed received quantity (10)" in exc_info_rej.value.detail

        # Case C: Valid GRN with received_qty (48) <= dispatched_qty (50), rejected (3), accepted (45)
        valid_grn_payload = GRNIn(
            invoice_id=inv_id,
            grn_date="2026-08-25",
            client_reference="CLIENT-REF-VALID",
            line_items=[
                GRNLineItem(
                    style_code="SSK_OXFORD",
                    description="Oxford Formal",
                    color="Tan",
                    size="7",
                    dispatched_qty=50,
                    received_qty=48,
                    rejected_qty=3,
                    accepted_qty=45,
                    rejection_reason="Minor scuff",
                )
            ]
        )

        res = await create_grn(valid_grn_payload, dummy_req)
        assert res is not None
        assert res["total_dispatched"] == 50
        assert res["total_received"] == 48
        assert res["total_accepted"] == 45
        assert res["total_rejected"] == 3

        # Confirm GRN recorded in DB
        grn_doc = await server.db.grns.find_one({"invoice_id": inv_id})
        assert grn_doc is not None
        assert grn_doc["total_accepted"] == 45

    finally:
        await server.db.invoices.delete_one({"_id": oid(inv_id)})
        await server.db.grns.delete_many({"invoice_id": inv_id})
