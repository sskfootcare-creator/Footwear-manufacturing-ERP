import os
import sys
import pytest
import asyncio
from typing import Dict, Any

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from routes.online_orders import (
    _parse_myntra_pnl_workbook,
    _build_pnl_reconciliation_overview,
    UpdateStyleCostPayload,
    UpdateOperationalCostPayload,
)

SAMPLE_PNL_PATH = r"C:\Users\Dell\Downloads\PnLReport_37353.xlsx"


class MockCol:
    def __init__(self):
        self.docs = {}
    async def find_one(self, *args, **kwargs):
        return None
    def find(self, *args, **kwargs):
        class Cursor:
            async def to_list(self, *a, **kw):
                return []
        return Cursor()


class MockDB:
    def __init__(self):
        self.styles = MockCol()
        self.sku_map = MockCol()
        self.style_cost_snapshots = MockCol()
        self.online_monthly_reconciliation_overviews = MockCol()
        self.expenses = MockCol()
        self.recurring_expenses = MockCol()


def test_myntra_pnl_parsing_and_actual_profit():
    asyncio.run(_async_test_myntra_pnl_parsing_and_actual_profit())


async def _async_test_myntra_pnl_parsing_and_actual_profit():
    if not os.path.exists(SAMPLE_PNL_PATH):
        pytest.skip(f"Sample PnL workbook not found at {SAMPLE_PNL_PATH}")

    with open(SAMPLE_PNL_PATH, "rb") as f:
        content = f.read()

    month, seller_id, pnl_sum, sku_rows = _parse_myntra_pnl_workbook(content)

    # 1. Verify Header & Platform Summary
    assert month == "2026-08"
    assert seller_id == "37353"
    assert pnl_sum["gross_units"] == 1895
    assert pnl_sum["returns_units"] == -929
    assert pnl_sum["net_units"] == 966
    assert pnl_sum["gross_sales"] == 975454.0
    assert pnl_sum["returns_amount"] == -477302.0
    assert pnl_sum["net_sales"] == 498152.0
    assert round(pnl_sum["earnings_on_platform"], 2) == 245450.35

    # 2. Verify SKU rows count (352 SKUs)
    assert len(sku_rows) == 352

    # 3. Build Reconciliation Overview
    db = MockDB()
    overview = await _build_pnl_reconciliation_overview(
        month=month,
        seller_id=seller_id,
        pnl_summary=pnl_sum,
        sku_rows=sku_rows,
        platform="myntra",
        filename="PnLReport_37353.xlsx",
        db=db,
    )

    assert overview["styles_count"] == 85
    assert overview["total_skus"] == 352
    assert overview["total_net_sold"] == 966
    assert len(overview["sku_bifurcation"]) == 352
    assert len(overview["styles"]) == 85

    # 4. Verify 50% Operational Overhead and Actual Net Profit
    op = overview["operational_expenses"]
    assert op["allocation_pct"] == 50.0
    assert op["total_monthly_operational_cost"] == 137500.0  # 85k + 12.5k + 30k + 10k
    assert op["allocated_operational_cost"] == 68750.0

    # Total COGS = 966 net units * default ₹210 = 202,860.0
    assert overview["total_cost_of_production"] == 202860.0
    # Actual Net Profit = Platform Earnings (245,450.35) - COGS (202,860.0) - 50% Op (68,750.0)
    expected_profit = round(245450.35 - 202860.0 - 68750.0, 2)
    assert overview["actual_net_profit"] == expected_profit
    # 5. Test updating a style cost (e.g. CC-013 from 210 to 180)
    from routes.online_orders import update_monthly_style_cost, update_monthly_operational_cost

    class MockRequest:
        state = None
        headers = {}

    db.online_monthly_reconciliation_overviews = MockCol()
    overview["_id"] = "mock_overview_id"
    saved_doc = dict(overview)

    async def mock_find_one(q, *a, **kw):
        return saved_doc

    async def mock_update_one(q, update, *a, **kw):
        if "$set" in update:
            saved_doc.update(update["$set"])
        return True

    db.online_monthly_reconciliation_overviews.find_one = mock_find_one
    db.online_monthly_reconciliation_overviews.update_one = mock_update_one

    import routes.online_orders as roo
    original_find_one = roo._safe_find_one
    original_update_one = roo._safe_update_one
    original_get_user = roo._get_user
    original_get_db = roo.get_db

    roo._safe_find_one = mock_find_one
    roo._safe_update_one = mock_update_one
    async def mock_get_user(req):
        return {"email": "admin@sskfootcare.com", "role": "admin"}
    roo._get_user = mock_get_user
    roo.get_db = lambda: db

    try:
        cost_payload = UpdateStyleCostPayload(
            platform="myntra",
            month="2026-08",
            style_code="CC-013",
            unit_production_cost=180.0,
        )
        updated_res = await update_monthly_style_cost(cost_payload, MockRequest())
        assert updated_res["styles"][0]["unit_production_cost"] == 180.0 or any(
            s["style_code"] == "CC-013" and s["unit_production_cost"] == 180.0 for s in updated_res["styles"]
        )
        # Verify SKU bifurcation was also updated for CC-013
        cc013_skus = [sk for sk in updated_res["sku_bifurcation"] if sk["style_root"] == "CC-013"]
        assert all(sk["unit_production_cost"] == 180.0 for sk in cc013_skus)

        # 6. Test updating monthly operational cost
        op_payload = UpdateOperationalCostPayload(
            platform="myntra",
            month="2026-08",
            rent=80000.0,
            electricity=10000.0,
            salaries=25000.0,
            other_basic=5000.0,
            allocation_pct=50.0,
        )
        updated_op_res = await update_monthly_operational_cost(op_payload, MockRequest())
        new_op = updated_op_res["operational_expenses"]
        assert new_op["total_monthly_operational_cost"] == 120000.0
        assert new_op["allocated_operational_cost"] == 60000.0
        assert updated_op_res["allocated_operational_cost"] == 60000.0
    finally:
        roo._safe_find_one = original_find_one
        roo._safe_update_one = original_update_one
        roo._get_user = original_get_user
        roo.get_db = original_get_db


if __name__ == "__main__":
    asyncio.run(_async_test_myntra_pnl_parsing_and_actual_profit())
    print("All PnL integration assertions passed!")

