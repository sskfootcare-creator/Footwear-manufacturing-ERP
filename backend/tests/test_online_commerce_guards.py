"""Regression tests for audited online commerce duplicate and WMS guards."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import asyncio
from bson import ObjectId
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_erp")
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import server  # noqa: E402


class UpdateResult:
    def __init__(self, modified_count=1, matched_count=1):
        self.modified_count = modified_count
        self.matched_count = matched_count


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


def test_normalized_marketplace_keys_collapse_case_space_hyphen_exactly():
    assert server._norm_marketplace(" FlipKart ") == server._norm_marketplace("flipkart")
    assert server._norm_key(" SKU_001 ") == server._norm_key("sku_001")
    # Similar but distinct business SKUs must not be collapsed by punctuation stripping.
    assert server._norm_key("ST-01_BLACK_8") != server._norm_key("ST01_BLACK_8")
