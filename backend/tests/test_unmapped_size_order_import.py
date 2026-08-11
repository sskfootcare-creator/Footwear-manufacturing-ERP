"""Unit and integration tests for unmapped size / color handling during order import.

Verifies:
1. When importing an order CSV containing a line with an unmapped size (e.g. size_map={"8":"8"} and size="9"):
   - Line with unmapped size (size="9") lands in the unresolved/exceptions queue with matched=False.
   - Line with unmapped size does NOT get included in picklist generation.
   - Correctly-mapped lines (e.g. size="8") in the same import process normally into matched items/picklists.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_order_row_resolution_unmapped_size():
    """Verify _parse_and_resolve_order_row marks matched=False when size is not in size_map."""
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {"8": "8"}, # Only size 8 mapped
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "INT-STYLE-1",
        }

        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        cfg = {
            "platform": "flipkart",
            "column_map": {
                "leaf_sku": "SKU",
                "size": "Size",
                "qty": "Quantity",
                "order_id": "OrderID",
            },
            "known_sku_prefixes_to_strip": [],
            "known_sku_prefix_replacements": {},
        }

        with patch.object(server, "db", mock_db):
            # Test Line 1: Mapped size "8"
            raw_row_mapped = {"SKU": "EXT-SKU-1", "Size": "8", "Quantity": "1", "OrderID": "ORD-1"}
            canon_mapped = await server._parse_and_resolve_order_row(raw_row_mapped, cfg, "flipkart", None)

            assert canon_mapped["matched"] is True, f"Expected matched=True, got {canon_mapped}"
            assert canon_mapped["style_code"] == "INT-STYLE-1"
            assert canon_mapped["size"] == "8"

            # Test Line 2: Unmapped size "9"
            raw_row_unmapped = {"SKU": "EXT-SKU-1", "Size": "9", "Quantity": "1", "OrderID": "ORD-2"}
            canon_unmapped = await server._parse_and_resolve_order_row(raw_row_unmapped, cfg, "flipkart", None)

            assert canon_unmapped["matched"] is False
            assert canon_unmapped["size"] == "9"
            assert "Unmapped color/size" in canon_unmapped["exception_reason"]

    asyncio.run(run())


def test_configured_import_unmapped_size_routes_to_exceptions():
    """Verify import_online_orders_configured places unmapped size rows into exceptions and not picklist."""
    async def run():
        fake_style_id = str(ObjectId())
        fake_mapping_id = str(ObjectId())
        mock_mapping = {
            "_id": ObjectId(fake_mapping_id),
            "source_type": "online_channel",
            "source_name": "flipkart",
            "external_sku": "EXT-SKU-1",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {"8": "8"}, # Only size 8 is mapped
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "INT-STYLE-1",
        }

        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)

        cfg_doc = {
            "platform": "flipkart",
            "role": "order",
            "active": True,
            "column_map": {
                "leaf_sku": "SKU",
                "size": "Size",
                "qty": "Quantity",
                "order_id": "OrderID",
            },
            "sheet_locator": {"type": "first"},
            "header_locator": {"type": "row", "row_1_based": 1},
            "skip_rows_after_header": 0,
            "is_picklist": False,
        }

        # Mock user with correct role field
        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}

        # CSV Content with one mapped (8) and one unmapped (9) size
        csv_content = b"OrderID,SKU,Size,Quantity\nORD-101,EXT-SKU-1,8,1\nORD-102,EXT-SKU-1,9,1\n"

        mock_file = MagicMock()
        mock_file.filename = "orders.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        mock_db.order_import_format_configs.find_one = AsyncMock(return_value=cfg_doc)
        mock_db.online_orders.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        mock_db.online_order_items.insert_one = AsyncMock()
        mock_db.online_order_exceptions.insert_many = AsyncMock()
        mock_db.activity_logs.insert_one = AsyncMock()

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            res = await server.import_online_orders_configured(
                file=mock_file,
                platform="flipkart",
                dry_run=False,
                request=None,
            )

            assert res["stats"]["total_rows_read"] == 2
            assert res["stats"]["matched"] == 1
            assert res["stats"]["unmatched"] == 1

            # Verify exceptions queued
            assert res["committed"]["exceptions_queued"] == 1
            mock_db.online_order_exceptions.insert_many.assert_called_once()
            exceptions_arg = mock_db.online_order_exceptions.insert_many.call_args[0][0]
            assert len(exceptions_arg) == 1
            assert exceptions_arg[0]["order_id"] == "ORD-102"
            assert "Unmapped color/size" in exceptions_arg[0]["reason"]

    asyncio.run(run())
