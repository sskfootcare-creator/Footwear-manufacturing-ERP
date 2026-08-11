"""Tests for unmapped occurrences logging on sku_map documents."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_resolve_style_increments_unmapped_encountered():
    """Verify resolve_style increments unmapped_encountered fields when matched_exact==False."""
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {"Red": "RED"},
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
            # Call resolve_style with size="9" (not in size_map)
            res = await server.resolve_style(
                source_type="online_channel",
                source_name="flipkart",
                external_sku="EXT-SKU-1",
                external_color="Red",
                external_size="9",
            )

            assert res["matched"] is True
            assert res["matched_exact"] is False
            assert res["size_matched_exact"] is False

            # Verify update_one was called to increment unmapped_encountered.size.9
            mock_db.sku_map.update_one.assert_called_once()
            call_args = mock_db.sku_map.update_one.call_args[0]
            assert call_args[0] == {"_id": ObjectId(fake_mapping_id)}
            assert call_args[1]["$inc"] == {"unmapped_encountered.size.9": 1}
            assert "last_unmapped_at" in call_args[1]["$set"]

    asyncio.run(run())
