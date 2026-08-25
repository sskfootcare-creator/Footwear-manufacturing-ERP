"""Unit and integration tests for authoritative fees_total in settlement imports.

Verifies:
1. Preview endpoint returns authoritative fees_total (including GST on fees and fixed fees)
   preventing the previous frontend-only display variance (comm + ship + rto).
2. On commit, fees_total and reconciled_fees_total are accurately persisted to online_settlements
   and online_order_items.
3. Settlement summary aggregates fees_total consistently.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_settlement_row_fees_total_includes_gst_and_fixed_fee():
    """Verify _parse_and_resolve_settlement_row includes GST on fees and fixed fees in fees_total."""
    async def run():
        mock_db = MagicMock()
        mock_db.online_order_items.find_one = AsyncMock(return_value=None)
        mock_db.online_orders.find_one = AsyncMock(return_value=None)

        cfg = {
            "platform": "myntra",
            "column_map": {
                "order_ref": "OrderRef",
                "leaf_sku": "SKU",
                "gross_amount": "Gross",
                "commission": "Commission",
                "shipping_fee": "Shipping",
                "rto_charge": "RTO",
                "gst_on_fees": "GST_Fees",
                "fixed_fee": "FixedFee",
                "net_payout": "NetPayout",
            }
        }

        # Row with commission (100) + shipping (50) + rto (20) + gst_on_fees (27) + fixed_fee (10) = 207.0
        # Legacy frontend formula (comm + ship + rto) would have yielded 170.0 (37.0 variance)
        raw_row = {
            "OrderRef": "ORD-FEES-101",
            "SKU": "SKU_TEST_001_8",
            "Gross": "1000",
            "Commission": "100",
            "Shipping": "50",
            "RTO": "20",
            "GST_Fees": "27",
            "FixedFee": "10",
            "NetPayout": "793",
        }

        with patch.object(server, "db", mock_db):
            res = await server._parse_and_resolve_settlement_row(raw_row, cfg, "myntra", 1)

            assert res["gross_amount"] == 1000.0
            assert res["commission"] == 100.0
            assert res["shipping_fee"] == 50.0
            assert res["rto_charge"] == 20.0
            assert res["gst_on_fees"] == 27.0
            assert res["fixed_fee"] == 10.0
            assert res["fees_total"] == 207.0, "Authoritative fees_total must include all fee components (207.0)"
            assert res["net_payout"] == 793.0

    asyncio.run(run())


def test_settlement_import_preview_and_commit_persists_fees_total():
    """Verify settlement preview returns fees_total and commit persists reconciled_fees_total."""
    async def run():
        mock_db = MagicMock()
        mock_user = {"email": "admin@sskfootcare.com", "role": "admin"}

        fake_item_id = ObjectId()
        mock_matched_item = {
            "_id": fake_item_id,
            "order_id": "ORD-SETTLE-777",
            "leaf_sku": "SKU_777_8",
            "selling_price": 1000.0,
            "stage": "dispatched",
        }

        mock_db.online_order_items.find_one = AsyncMock(return_value=mock_matched_item)
        mock_db.online_orders.find_one = AsyncMock(return_value=None)
        mock_db.online_settlements.update_one = AsyncMock()
        mock_db.online_order_items.update_one = AsyncMock()

        cfg_doc = {
            "platform": "flipkart",
            "role": "settlement",
            "active": True,
            "column_map": {
                "order_ref": "Order ID",
                "leaf_sku": "FSN",
                "gross_amount": "Sale Amount",
                "commission": "Marketplace Fee",
                "shipping_fee": "Shipping Fee",
                "rto_charge": "Reverse Fee",
                "gst_on_fees": "Taxes on Fees",
                "net_payout": "Bank Payout",
            },
            "sheet_locator": {"type": "first"},
            "header_locator": {"type": "row", "row_1_based": 1},
            "skip_rows_after_header": 0,
        }
        mock_db.order_import_format_configs.find_one = AsyncMock(return_value=cfg_doc)

        csv_content = (
            b"Order ID,FSN,Sale Amount,Marketplace Fee,Shipping Fee,Reverse Fee,Taxes on Fees,Bank Payout\n"
            b"ORD-SETTLE-777,SKU_777_8,1000,120,60,0,32.40,787.60\n"
        )
        mock_file = MagicMock()
        mock_file.filename = "settlement.csv"
        mock_file.read = AsyncMock(return_value=csv_content)

        with patch.object(server, "get_current_user", AsyncMock(return_value=mock_user)), \
             patch.object(server, "log_activity", AsyncMock()), \
             patch.object(server, "db", mock_db):

            # 1. Preview Test
            preview = await server.import_settlement_report(
                request=None,
                file=mock_file,
                platform="flipkart",
                dry_run=True,
            )
            assert preview["stats"]["total_fees_total"] == 212.40
            preview_row = preview["rows"][0]
            assert preview_row["fees_total"] == 212.40
            assert preview_row["net_payout"] == 787.60

            # 2. Commit Test
            mock_file.read = AsyncMock(return_value=csv_content)
            commit_res = await server.import_settlement_report(
                request=None,
                file=mock_file,
                platform="flipkart",
                dry_run=False,
            )
            assert commit_res["committed"] is True

            # Verify online_settlements was saved with fees_total = 212.40
            settle_save_calls = mock_db.online_settlements.update_one.call_args_list
            assert len(settle_save_calls) == 1
            saved_doc = settle_save_calls[0][0][1]["$set"]
            assert saved_doc["fees_total"] == 212.40
            assert saved_doc["net_payout"] == 787.60

            # Verify online_order_items was reconciled with reconciled_fees_total = 212.40
            item_update_calls = mock_db.online_order_items.update_one.call_args_list
            assert len(item_update_calls) == 1
            reconciled_set = item_update_calls[0][0][1]["$set"]
            assert reconciled_set["reconciled_fees_total"] == 212.40
            assert reconciled_set["reconciled_net_payout"] == 787.60
            assert reconciled_set["is_reconciled"] is True

    asyncio.run(run())
