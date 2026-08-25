"""Test SKU-map creation is transactional with PO save in the backend."""
import pytest
import os
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException
import server
from server import (
    create_po,
    _norm_marketplace,
    _norm_key,
)
from models.orders import POIn, POLineItem


class DummyRequest:
    """Mock Request for testing endpoints with admin role."""
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
async def test_po_save_failure_creates_no_orphaned_sku_mappings(fresh_db, monkeypatch):
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    dummy_req = DummyRequest()

    # 1. Create a style in DB
    style_code = f"SSK_TEST_{uuid.uuid4().hex[:6].upper()}"
    res_style = await server.db.styles.insert_one({
        "code": style_code,
        "name": "Test SKU Oxford",
        "category": "Formal",
        "season": "AW26",
    })

    po_number = f"PO_DUPL_{uuid.uuid4().hex[:6].upper()}"
    client_name = f"B2B Client {uuid.uuid4().hex[:4]}"
    ext_sku = f"EXT_{uuid.uuid4().hex[:6].upper()}"

    # 2. First create a PO successfully with po_number
    po1 = POIn(
        po_number=po_number,
        po_date="2026-08-25",
        client_name=client_name,
        line_items=[
            POLineItem(
                style_code=style_code,
                external_sku=style_code,
                quantity=50,
                unit_price=400.0,
                amount=20000.0,
            )
        ],
    )
    res_first = await create_po(po1, dummy_req)
    assert res_first["po_number"] == po_number

    # 3. Attempt to create a SECOND PO with the duplicate PO number and a new unmapped external_sku
    po_duplicate = POIn(
        po_number=po_number, # duplicate!
        po_date="2026-08-25",
        client_name=client_name,
        line_items=[
            POLineItem(
                style_code=style_code,
                external_sku=ext_sku,
                quantity=10,
                unit_price=500.0,
                amount=5000.0,
            )
        ],
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await create_po(po_duplicate, dummy_req)
    assert exc_info.value.status_code == 409

    # 4. Verify NO orphaned sku_map entry was created for ext_sku
    mapping = await server.db.sku_map.find_one({
        "source_name_key": _norm_marketplace(client_name),
        "external_sku_key": _norm_key(ext_sku),
    })
    assert mapping is None, "Failed PO save must not leave orphaned SKU mappings in db.sku_map!"

    # 5. Now create a PO successfully with ext_sku
    new_po_number = f"PO_OK_{uuid.uuid4().hex[:6].upper()}"
    po_valid = POIn(
        po_number=new_po_number,
        po_date="2026-08-25",
        client_name=client_name,
        line_items=[
            POLineItem(
                style_code=style_code,
                external_sku=ext_sku,
                description="Oxford Test Shoe",
                quantity=10,
                unit_price=500.0,
                amount=5000.0,
            )
        ],
    )
    res_ok = await create_po(po_valid, dummy_req)
    assert res_ok["po_number"] == new_po_number

    # 6. Verify sku_map entry was created on successful PO save and points to style_code
    mapping_created = await server.db.sku_map.find_one({
        "source_name_key": _norm_marketplace(client_name),
        "external_sku_key": _norm_key(ext_sku),
    })
    assert mapping_created is not None
    assert mapping_created["style_code"] == style_code
    assert mapping_created["external_sku"] == ext_sku
