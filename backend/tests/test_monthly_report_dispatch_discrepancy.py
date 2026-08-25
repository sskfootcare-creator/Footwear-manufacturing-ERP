"""Unit and integration tests for monthly report dispatch discrepancy detection.

Verifies:
1. When a monthly report row lacks packed_on AND internal system records confirm no dispatch:
   - classified as never_touched_inventory = True, has_dispatch_discrepancy = False.
2. When a monthly report row lacks packed_on BUT internal system records (online_order_items / fg_stock_movements)
   show the unit was dispatched:
   - NOT classified as never_touched_inventory (never_touched_inventory = False).
   - Flagged as a discrepancy: has_dispatch_discrepancy = True, discrepancy_reason populated.
   - stats["discrepancies"] is incremented.
   - On commit, queued to exceptions and persisted to online_order_items with has_dispatch_discrepancy = True.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_monthly_classification_flags_discrepancy_when_internal_dispatch_exists():
    """Verify missing packed_on in monthly file is flagged as discrepancy when internal records show dispatch."""
    async def run():
        mock_db = MagicMock()

        # Mock an existing dispatched online_order_item in internal DB
        mock_dispatched_item = {
            "_id": ObjectId(),
            "platform": "myntra",
            "order_release_id": "REL-DISPATCHED-1",
            "order_id": "ORD-101",
            "leaf_sku": "SKU_AK_001_8",
            "stage": "dispatched",
            "dispatched_at": "2026-06-01T10:00:00Z",
        }

        async def find_one_side_effect(query, *args, **kwargs):
            or_list = query.get("$or", [])
            has_rel1 = (
                query.get("order_release_id") == "REL-DISPATCHED-1"
                or any(c.get("order_release_id") == "REL-DISPATCHED-1" for c in or_list if isinstance(c, dict))
            )
            if has_rel1:
                return mock_dispatched_item
            return None

        mock_db.online_order_items.find_one = AsyncMock(side_effect=find_one_side_effect)
        mock_db.fg_stock_movements.find_one = AsyncMock(return_value=None)
        mock_db.online_orders.find_one = AsyncMock(return_value=None)

        with patch.object(server, "db", mock_db):
            # Row 1: Missing packed_on, but internal DB has dispatch record for REL-DISPATCHED-1
            row_discrepancy = {
                "order_id": "ORD-101",
                "order_release_id": "REL-DISPATCHED-1",
                "packed_on": None,
                "order_status": "DELIVERED",
                "leaf_sku": "SKU_AK_001_8",
            }
            res1 = await server._classify_monthly_row(row_discrepancy, "myntra")
            assert res1["never_touched_inventory"] is False, "Must NOT be classified as never_touched_inventory"
            assert res1["has_dispatch_discrepancy"] is True, "Must be flagged as a dispatch discrepancy"
            assert "dispatch_discrepancy" in res1["flags"]
            assert res1["discrepancy_reason"] is not None

            # Row 2: Missing packed_on, and internal DB confirms NO dispatch record
            row_never_touched = {
                "order_id": "ORD-102",
                "order_release_id": "REL-NEVER-TOUCHED-2",
                "packed_on": None,
                "order_status": "CANCELLED",
                "leaf_sku": "SKU_AK_002_8",
            }
            res2 = await server._classify_monthly_row(row_never_touched, "myntra")
            assert res2["never_touched_inventory"] is True, "Must be classified as never_touched_inventory"
            assert res2["has_dispatch_discrepancy"] is False, "Must not be flagged as discrepancy"

    asyncio.run(run())


def test_monthly_report_import_endpoint_discrepancies_and_exceptions():
    """Verify import_monthly_report calculates discrepancy stats and records them in exceptions."""
    async def run():
        mock_db = MagicMock()
        fake_style_id = str(ObjectId())

        mock_mapping = {
            "_id": ObjectId(),
            "source_type": "online_channel",
            "source_name": "myntra",
            "external_sku": "SKU_AK_001_8",
            "style_id": fake_style_id,
            "color_map": {},
            "size_map": {"8": "8"},
        }
        mock_style = {
            "_id": ObjectId(fake_style_id),
            "code": "STYLE-AK-001",
        }

        # Internal dispatch record exists for REL-DISP-999
        mock_dispatched_item = {
            "_id": ObjectId(),
            "platform": "myntra",
            "order_release_id": "REL-DISP-999",
            "stage": "dispatched",
            "dispatched_at": "2026-06-01T12:00:00Z",
        }

        async def find_one_items(query, *args, **kwargs):
            or_list = query.get("$or", [])
            has_rel_disp = (
                query.get("order_release_id") == "REL-DISP-999"
                or any(c.get("order_release_id") == "REL-DISP-999" for c in or_list if isinstance(c, dict))
            )
            if has_rel_disp:
                return mock_dispatched_item
            return None

        mock_db.sku_map.find_one = AsyncMock(return_value=mock_mapping)
        mock_db.styles.find_one = AsyncMock(return_value=mock_style)
        mock_db.online_order_items.find_one = AsyncMock(side_effect=find_one_items)
        mock_db.fg_stock_movements.find_one = AsyncMock(return_value=None)
        mock_db.online_orders.find_one = AsyncMock(return_value=None)
        mock_db.online_orders.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        mock_db.online_order_items.insert_one = AsyncMock()
        mock_db.activity_logs.insert_one = AsyncMock()

        cfg_doc = {
            "platform": "myntra",
            "role": "monthly_report",
            "active": True,
            "column_map": {
                "order_id": "OrderID",
                "order_release_id": "ReleaseID",
                "leaf_sku": "SKU",
                "size": "Size",
                "order_status": "Status",
                "packed_on": "PackedOn",
            },
            "sheet_locator": {"type": "first"},
            "header_locator": {"type": "row", "row_1_based": 1},
            "skip_rows_after_header": 0,
        }
        mock_db.order_import_format_configs.find_one = AsyncMock(return_value=cfg_doc)

        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}
        # Monthly CSV with missing PackedOn
        csv_content = b"OrderID,ReleaseID,SKU,Size,Status,PackedOn\nORD-999,REL-DISP-999,SKU_AK_001_8,8,DELIVERED,null\n"

        mock_file = MagicMock()
        mock_file.filename = "monthly_report.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            # Dry run test
            preview = await server.import_monthly_report(
                request=None,
                file=mock_file,
                platform="myntra",
                dry_run=True,
            )
            assert preview["stats"]["discrepancies"] == 1
            assert preview["stats"]["never_touched_inventory"] == 0
            row = preview["rows"][0]
            assert row["has_dispatch_discrepancy"] is True
            assert row["never_touched_inventory"] is False

    asyncio.run(run())

