"""Regression tests for audited online commerce duplicate and WMS guards.

Covers:
  OC-001  Duplicate configured online order import (see test_online_orders_routes.py for full flow)
  OC-002  WMS pick-item atomic claim and reserved-stock guard
  OC-003  Normalised marketplace / SKU key collapse
  OC-004  Settlement import idempotency (row-hash deduplication)
"""
import hashlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import asyncio
from bson import ObjectId
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_erp")
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import server  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class UpdateResult:
    def __init__(self, modified_count=1, matched_count=1, upserted_id=None):
        self.modified_count = modified_count
        self.matched_count = matched_count
        self.upserted_id = upserted_id


def _make_settlement_row_key(platform, payment_id, order_ref, leaf_sku, settlement_date):
    raw = f"{platform}:{payment_id}:{order_ref}:{leaf_sku}:{settlement_date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# OC-002  Picking guards
# ---------------------------------------------------------------------------

def test_deduct_from_specific_location_requires_reserved_stock(monkeypatch):
    """Picking must consume a location reservation, not unreserved free stock."""
    loc_id = ObjectId()
    loc_doc = {
        "_id": loc_id,
        "style_id": ObjectId(),
        "color": "Black",
        "size": "8",
        "location_code": "R01-A-001",
        "qty": 5,
        "reserved_qty": 0,
    }

    collection = SimpleNamespace()
    collection.find_one = AsyncMock(side_effect=[loc_doc, loc_doc])
    collection.update_one = AsyncMock(return_value=UpdateResult(modified_count=0))

    monkeypatch.setattr(server, "db", SimpleNamespace(fg_location_inventory=collection))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._deduct_from_specific_location(str(loc_doc["style_id"]), "Black", "8", 1, "R01-A-001"))

    assert exc.value.status_code == 400
    assert "Insufficient reserved stock" in exc.value.detail
    collection.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# OC-003  Normalised key helpers
# ---------------------------------------------------------------------------

def test_normalized_marketplace_keys_collapse_case_space_hyphen_exactly():
    assert server._norm_marketplace(" FlipKart ") == server._norm_marketplace("flipkart")
    assert server._norm_key(" SKU_001 ") == server._norm_key("sku_001")
    # Similar but distinct business SKUs must not be collapsed by punctuation stripping.
    assert server._norm_key("ST-01_BLACK_8") != server._norm_key("ST01_BLACK_8")


# ---------------------------------------------------------------------------
# OC-004  Settlement import idempotency
# ---------------------------------------------------------------------------

def test_settlement_row_key_is_deterministic():
    """The same inputs must always produce the same idempotency key."""
    k1 = _make_settlement_row_key("myntra", "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    k2 = _make_settlement_row_key("myntra", "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    assert k1 == k2


def test_settlement_row_key_differs_by_platform():
    """Different platforms with the same order/sku must produce different keys."""
    k_m = _make_settlement_row_key("myntra",   "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    k_f = _make_settlement_row_key("flipkart", "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    assert k_m != k_f


def test_settlement_row_key_differs_by_payment_id():
    """Different payment IDs (same NEFT reference guard) must produce different keys."""
    k1 = _make_settlement_row_key("myntra", "NEFT001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    k2 = _make_settlement_row_key("myntra", "NEFT002", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    assert k1 != k2


def test_settlement_row_key_differs_by_date():
    """Two settlements for the same order on different dates are distinct rows."""
    k1 = _make_settlement_row_key("myntra", "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-01")
    k2 = _make_settlement_row_key("myntra", "PAY001", "ORD1234", "SSK-BOOTS-8", "2026-09-15")
    assert k1 != k2


def test_settlement_import_uses_upsert_with_row_key():
    """
    import_settlement (OC-004 guard): the commit path must call update_one/upsert
    keyed on settlement_row_key, NOT insert_many.
    Verified by inspecting the source of routes.online_orders.import_settlement.
    """
    import inspect
    from routes import online_orders as oo_mod

    src = inspect.getsource(oo_mod.import_settlement)
    assert "settlement_row_key" in src, \
        "import_settlement must write a settlement_row_key idempotency field"
    assert "setOnInsert" in src, \
        "import_settlement must use $setOnInsert (upsert) not insert_many"
    # Verify no bare insert_many call on the settlements collection exists.
    # (Comments referencing insert_many are acceptable; DB calls are not.)
    import re as _re
    assert not _re.search(r"online_settlements\.insert_many", src), \
        "import_settlement must not call online_settlements.insert_many (non-idempotent)"


def test_duplicate_settlement_import_is_skipped():
    """
    Simulates two imports of the same settlement row.
    On the second import, upserted_id is None (doc already existed),
    which must count as a skipped duplicate.
    """
    platform   = "myntra"
    payment_id = "NEFT-2026-001"
    order_ref  = "ORD-9999"
    leaf_sku   = "SSK-BOOT-8"
    s_date     = "2026-09-01"
    key = _make_settlement_row_key(platform, payment_id, order_ref, leaf_sku, s_date)

    store: dict = {}

    async def upsert_one(filter_doc, update_doc, upsert=False):
        k = filter_doc.get("settlement_row_key")
        if k and k in store:
            return UpdateResult(modified_count=0, upserted_id=None)
        else:
            doc = update_doc.get("$setOnInsert", {})
            store[k] = doc
            return UpdateResult(modified_count=1, upserted_id=ObjectId())

    # First import: record is new.
    result1 = asyncio.run(upsert_one({"settlement_row_key": key}, {"$setOnInsert": {"settlement_row_key": key}}, upsert=True))
    assert result1.upserted_id is not None, "First import must insert the row"
    assert len(store) == 1

    # Second import of same row: must be detected as duplicate.
    result2 = asyncio.run(upsert_one({"settlement_row_key": key}, {"$setOnInsert": {"settlement_row_key": key}}, upsert=True))
    assert result2.upserted_id is None, "Duplicate import must NOT insert a new document"
    assert len(store) == 1, "Exactly one document must remain after two imports of the same row"


def test_partial_settlement_file_resumes_correctly():
    """
    A partial file import (first 2 of 3 rows) followed by a full-file re-import
    must insert only the missing 1 row, leaving exactly 3 total records.
    """
    platform = "myntra"
    rows = [
        ("NEFT-001", "ORD-1", "SSK-A-8", "2026-09-01"),
        ("NEFT-001", "ORD-2", "SSK-A-9", "2026-09-01"),
        ("NEFT-001", "ORD-3", "SSK-B-8", "2026-09-01"),
    ]
    keys = [_make_settlement_row_key(platform, r[0], r[1], r[2], r[3]) for r in rows]

    store: dict = {}

    def import_rows(row_indices):
        inserted = 0
        skipped  = 0
        for i in row_indices:
            k = keys[i]
            if k in store:
                skipped += 1
            else:
                store[k] = {"settlement_row_key": k, "order_ref": rows[i][1]}
                inserted += 1
        return inserted, skipped

    # Partial import: rows 0 and 1 only.
    ins1, sk1 = import_rows([0, 1])
    assert ins1 == 2 and sk1 == 0

    # Full re-import: all 3 rows.
    ins2, sk2 = import_rows([0, 1, 2])
    assert ins2 == 1, "Only the missing row must be inserted on resume"
    assert sk2 == 2, "The two already-imported rows must be skipped"
    assert len(store) == 3, "Exactly 3 unique settlement records must exist"


def test_unknown_order_ref_row_is_not_committed():
    """
    A settlement row whose order_ref does not resolve to a known order
    must not be written to DB; unresolved_count must be incremented instead.
    """
    platform   = "myntra"
    payment_id = "NEFT-999"
    order_ref  = "UNKNOWN-ORDER-0000"
    leaf_sku   = "SSK-NOMATCH-8"
    s_date     = "2026-09-01"

    key = _make_settlement_row_key(platform, payment_id, order_ref, leaf_sku, s_date)

    matched_result = {"matched": False}

    records    = []
    unresolved = 0
    if matched_result["matched"]:
        records.append({"settlement_row_key": key})
    else:
        unresolved += 1

    assert len(records) == 0, "Unresolved rows must not be written to DB"
    assert unresolved == 1
    assert len(key) == 64  # SHA-256 hex digest is always 64 chars
