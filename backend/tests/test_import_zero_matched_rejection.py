"""Unit tests verifying server-side rejection of imports when matched count is 0 on commit.

Verifies:
1. POST /api/online-orders/import-configured with dry_run=False and 0 matched rows raises HTTPException(400, "Nothing to commit — no rows matched.")
2. POST /api/online-orders/dispatch-import with dry_run=False and 0 matched rows raises HTTPException(400, "Nothing to commit — no rows matched.")
3. POST /api/online-orders/settlement-import with dry_run=False and 0 matched rows raises HTTPException(400, "Nothing to commit — no rows matched.")
4. Dry run with 0 matched rows succeeds and returns preview stats without throwing.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi import HTTPException
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_import_online_orders_configured_zero_matched_rejected_on_commit():
    """Verify import_online_orders_configured rejects commit when 0 rows match."""
    async def run():
        mock_db = MagicMock()
        # No SKU mappings found -> 0 rows matched
        mock_db.sku_map.find_one = AsyncMock(return_value=None)
        mock_db.styles.find_one = AsyncMock(return_value=None)

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

        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}
        csv_content = b"OrderID,SKU,Size,Quantity\nORD-101,UNMAPPED_SKU_1,8,1\nORD-102,UNMAPPED_SKU_2,9,1\n"

        mock_file = MagicMock()
        mock_file.filename = "orders.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        mock_db.order_import_format_configs.find_one = AsyncMock(return_value=cfg_doc)

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            # Dry run should succeed and return preview
            preview = await server.import_online_orders_configured(
                file=mock_file,
                platform="flipkart",
                dry_run=True,
                request=None,
            )
            assert preview["stats"]["matched"] == 0
            assert preview["stats"]["unmatched"] == 2

            # Direct commit (dry_run=False) with 0 matched rows MUST raise 400
            with pytest.raises(HTTPException) as exc_info:
                await server.import_online_orders_configured(
                    file=mock_file,
                    platform="flipkart",
                    dry_run=False,
                    request=None,
                )
            assert exc_info.value.status_code == 400
            assert "Nothing to commit — no rows matched" in exc_info.value.detail

    asyncio.run(run())


def test_dispatch_import_zero_matched_rejected_on_commit():
    """Verify dispatch_import rejects commit when 0 rows match."""
    async def run():
        mock_db = MagicMock()
        mock_db.sku_map.find_one = AsyncMock(return_value=None)
        mock_db.styles.find_one = AsyncMock(return_value=None)

        cfg_doc = {
            "platform": "flipkart",
            "role": "dispatch",
            "active": True,
            "column_map": {
                "leaf_sku": "SKU",
                "order_id": "OrderID",
                "order_release_id": "ReleaseID",
            },
            "sheet_locator": {"type": "first"},
            "header_locator": {"type": "row", "row_1_based": 1},
            "skip_rows_after_header": 0,
        }

        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}
        csv_content = b"OrderID,ReleaseID,SKU\nORD-101,REL-1,UNMAPPED_DISPATCH_SKU\n"

        mock_file = MagicMock()
        mock_file.filename = "dispatch.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        mock_db.order_import_format_configs.find_one = AsyncMock(return_value=cfg_doc)

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            # Direct commit (dry_run=False) with 0 matched rows MUST raise 400
            with pytest.raises(HTTPException) as exc_info:
                await server.import_dispatch_configured(
                    file=mock_file,
                    platform="flipkart",
                    dry_run=False,
                    request=None,
                )
            assert exc_info.value.status_code == 400
            assert "Nothing to commit — no rows matched" in exc_info.value.detail

    asyncio.run(run())


def test_settlement_import_zero_matched_rejected_on_commit():
    """Verify import_settlement_report rejects commit when 0 rows match."""
    async def run():
        mock_db = MagicMock()
        mock_db.order_import_format_configs.find_one = AsyncMock(return_value={
            "platform": "myntra",
            "role": "settlement",
            "active": True,
            "column_map": {
                "order_ref": "OrderRef",
                "leaf_sku": "SKU",
                "gross_amount": "Gross",
                "net_payout": "Net",
            },
            "header_locator": {"type": "row", "row_1_based": 1},
        })
        mock_db.online_order_items.find_one = AsyncMock(return_value=None)
        mock_db.online_orders.find_one = AsyncMock(return_value=None)

        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}
        csv_content = b"OrderRef,SKU,Gross,Net\nREF-999,UNMAPPED_SETTLE_SKU,1000,800\n"

        mock_file = MagicMock()
        mock_file.filename = "settlement.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            # Direct commit with 0 matched items MUST raise 400
            with pytest.raises(HTTPException) as exc_info:
                await server.import_settlement_report(
                    file=mock_file,
                    platform="myntra",
                    dry_run=False,
                    request=None,
                )
            assert exc_info.value.status_code == 400
            assert "Nothing to commit — no rows matched" in exc_info.value.detail


    asyncio.run(run())
