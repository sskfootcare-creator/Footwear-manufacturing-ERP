"""Direct unit tests for resolve_style() in server.py.

Verifies:
1. size_map={"8": "8"}, size="9": returns size="9" (passed through) and matched_exact=False.
2. size_map={"8": "8"}, size="8": returns size="8" and matched_exact=True.
3. size_map={} (empty/no size_map): returns size="9" and matched_exact=True (reflects "no translation needed").
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_resolve_style_with_size_map_unmatched_value():
    """Call with size_map={"8":"8"} and size="9".
    Confirm returned size=="9" (passed through, not silently replaced) and matched_exact==False.
    """
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "Flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {"8": "8"},
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "INT-STYLE-1",
        }

        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)
        mock_db.sku_map.update_one = AsyncMock()

        with patch.object(server, "db", mock_db):
            res = await server.resolve_style(
                source_type="online_channel",
                source_name="Flipkart",
                external_sku="EXT-SKU-1",
                external_size="9",
            )

            assert res["matched"] is True
            assert res["size"] == "9"
            assert res["matched_exact"] is False
            assert res["size_matched_exact"] is False
            assert res["unmapped_size"] == "9"

    asyncio.run(run())


def test_resolve_style_with_size_map_matched_value():
    """Call with size_map={"8":"8"} and size="8".
    Confirm returned size=="8" and matched_exact==True.
    """
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "Flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {"8": "8"},
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "INT-STYLE-1",
        }

        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        with patch.object(server, "db", mock_db):
            res = await server.resolve_style(
                source_type="online_channel",
                source_name="Flipkart",
                external_sku="EXT-SKU-1",
                external_size="8",
            )

            assert res["matched"] is True
            assert res["size"] == "8"
            assert res["matched_exact"] is True
            assert res["size_matched_exact"] is True
            assert res["unmapped_size"] is None

    asyncio.run(run())


def test_resolve_style_with_empty_size_map():
    """Call with an empty/no size_map.
    Confirm matched_exact reflects "no translation needed" (True).
    """
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "Flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {},
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "INT-STYLE-1",
        }

        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        with patch.object(server, "db", mock_db):
            res = await server.resolve_style(
                source_type="online_channel",
                source_name="Flipkart",
                external_sku="EXT-SKU-1",
                external_size="9",
            )

            assert res["matched"] is True
            assert res["size"] == "9"
            assert res["matched_exact"] is True
            assert res["size_matched_exact"] is True
            assert res["unmapped_size"] is None

    asyncio.run(run())
