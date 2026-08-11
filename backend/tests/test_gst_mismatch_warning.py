"""Tests for GST rate mismatch warning on styles and order import lines."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_order_import_gst_mismatch_warning():
    """Verify _parse_and_resolve_order_row flags GST mismatch warning when line price suggests different GST."""
    async def run():
        fake_style_id = str(ObjectId())
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "SSK_00001",
            "gst_pct": 5.0,  # Style set to 5% GST
        }
        mock_db = MagicMock()
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        with patch.object(server, "db", mock_db):
            with patch.object(server, "resolve_style", AsyncMock(return_value={
                "matched": True,
                "matched_exact": True,
                "style_id": fake_style_id,
                "style_code": "SSK_00001",
                "match_via": "code",
            })):
                raw_row = {
                    "Leaf SKU": "SSK_00001",
                    "Selling Price": "3000.0",  # ₹3,000 > ₹2,500 threshold -> suggests 18% GST
                }
                cfg = {"column_map": {"leaf_sku": "Leaf SKU", "selling_price": "Selling Price"}}
                parsed = await server._parse_and_resolve_order_row(
                    raw_row=raw_row,
                    cfg=cfg,
                    platform="flipkart",
                    picklist_batch_id="PB_1",
                )

                assert parsed["matched"] is True
                assert parsed["gst_mismatch_warning"] is not None
                assert "suggests 18% GST" in parsed["gst_mismatch_warning"]
                assert "currently set to 5%" in parsed["gst_mismatch_warning"]

    asyncio.run(run())


def test_order_import_no_gst_mismatch_when_matching():
    """Verify _parse_and_resolve_order_row leaves gst_mismatch_warning None when GST matches."""
    async def run():
        fake_style_id = str(ObjectId())
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "SSK_00001",
            "gst_pct": 18.0,  # Style set to 18% GST
        }
        mock_db = MagicMock()
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        with patch.object(server, "db", mock_db):
            with patch.object(server, "resolve_style", AsyncMock(return_value={
                "matched": True,
                "matched_exact": True,
                "style_id": fake_style_id,
                "style_code": "SSK_00001",
                "match_via": "code",
            })):
                raw_row = {
                    "Leaf SKU": "SSK_00001",
                    "Selling Price": "3000.0",  # ₹3,000 > ₹2,500 threshold -> suggests 18% GST
                }
                cfg = {"column_map": {"leaf_sku": "Leaf SKU", "selling_price": "Selling Price"}}
                parsed = await server._parse_and_resolve_order_row(
                    raw_row=raw_row,
                    cfg=cfg,
                    platform="flipkart",
                    picklist_batch_id="PB_1",
                )

                assert parsed["matched"] is True
                assert parsed["gst_mismatch_warning"] is None

    asyncio.run(run())
