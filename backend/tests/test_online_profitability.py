"""
Tests for _compute_online_profitability:
- Labor cost / source / cost_is_estimated resolution (actual vs estimated)
- Platform fees handling:
  - When revenue is fallback/unreconciled (item_final_amount): platform fees ARE subtracted from profit/gross_profit
  - When revenue is settlement-reconciled (net_payout / settlement_forward): platform fees are ALREADY netted, so profit is revenue - COGS (no double-counting)
"""

import asyncio
import os
import sys
from bson import ObjectId
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    _compute_online_profitability,
    compute_style_costing_async,
    compute_po_profitability,
)
import server


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, limit=None):
        return self._docs


class _Collection:
    def __init__(self, docs=None, agg_result=None):
        self._docs = docs or []
        self._agg_result = agg_result if agg_result is not None else []

    def find(self, query=None):
        if query and "$in" in query.get("_id", {}):
            in_ids = set(query["_id"]["$in"])
            filtered = [
                d for d in self._docs
                if d.get("_id") in in_ids or str(d.get("_id")) in [str(x) for x in in_ids]
            ]
            return _Cursor(filtered)
        if query and "$or" in query:
            conditions = query["$or"]
            res = []
            for d in self._docs:
                for cond in conditions:
                    match = True
                    for k, v in cond.items():
                        if isinstance(v, dict) and "$in" in v:
                            doc_val = d.get(k)
                            in_list = [str(x) for x in v["$in"]]
                            if str(doc_val) not in in_list and doc_val not in v["$in"]:
                                match = False
                                break
                        elif str(d.get(k, "")) != str(v):
                            match = False
                            break
                    if match and d not in res:
                        res.append(d)
            return _Cursor(res)
        return _Cursor(self._docs)

    def aggregate(self, pipeline):
        if callable(self._agg_result):
            return _Cursor(self._agg_result(pipeline))
        return _Cursor(self._agg_result)


class _MockDB:
    def __init__(
        self,
        styles=None,
        jobs=None,
        order_items_sold=None,
        order_items_ret=None,
        online_settlements=None,
        existing_collections=None,
    ):
        self._styles = styles or []
        self._jobs = jobs or []
        self._order_items_sold = order_items_sold or []
        self._order_items_ret = order_items_ret or []
        self._online_settlements = online_settlements or []
        self._existing_collections = existing_collections or []
        self.styles = _Collection(self._styles)
        self.production_jobs = _Collection(self._jobs)

    def __getitem__(self, item):
        return _Collection([])

    async def list_collection_names(self):
        return self._existing_collections

    @property
    def online_order_items(self):
        class _OrderItemsCollection:
            def __init__(self, sold, ret):
                self.sold = sold
                self.ret = ret

            def aggregate(self, pipeline):
                is_ret = False
                for stage in pipeline:
                    if "$match" in stage and stage["$match"].get("was_returned_to_stock") is True:
                        is_ret = True
                        break
                return _Cursor(self.ret if is_ret else self.sold)
        return _OrderItemsCollection(self._order_items_sold, self._order_items_ret)

    @property
    def online_settlements(self):
        def _agg_handler(pipeline):
            return [
                {
                    "_id": s.get("matched_style_id"),
                    "net_payout": s.get("net_payout", 0),
                    "count": 1,
                }
                for s in self._online_settlements
            ]
        return _Collection(self._online_settlements, agg_result=_agg_handler)


def test_online_profitability_actual_vs_estimated_labor(monkeypatch):
    actual_style_id = ObjectId("60d5ec49f1b2c80015f8a001")
    est_style_id = ObjectId("60d5ec49f1b2c80015f8a002")

    styles = [
        {
            "_id": actual_style_id,
            "code": "STYLE_ACTUAL",
            "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Stitching", "rate": 20.0}],  # planned = 20
            "overhead_pct": 10.0,
            "packing_cost": 5.0,
        },
        {
            "_id": est_style_id,
            "code": "STYLE_ESTIMATED",
            "bom": [{"rate": 80.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Cutting", "rate": 15.0}],  # planned = 15
            "overhead_pct": 10.0,
            "packing_cost": 5.0,
        },
    ]

    jobs = [
        {
            "style_id": str(actual_style_id),
            "style_code": "STYLE_ACTUAL",
            "assignments": {
                "cutting": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 18.0},
                "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 22.0},
            },
        }
    ]

    sold_rows = [
        {
            "_id": actual_style_id,
            "style_code": "STYLE_ACTUAL",
            "color": "Black",
            "units_sold": 10,
            "item_final_amount": 2500.0,
            "order_release_ids": ["REL1"],
        },
        {
            "_id": est_style_id,
            "style_code": "STYLE_ESTIMATED",
            "color": "Tan",
            "units_sold": 5,
            "item_final_amount": 1000.0,
            "order_release_ids": ["REL2"],
        },
    ]

    mock_db = _MockDB(
        styles=styles,
        jobs=jobs,
        order_items_sold=sold_rows,
        order_items_ret=[],
    )

    monkeypatch.setattr(server, "db", mock_db)

    async def _run():
        return await _compute_online_profitability(
            platform=None, date_from=None, date_to=None, style_id=None
        )

    res = asyncio.run(_run())

    assert "by_style" in res
    assert len(res["by_style"]) == 2

    by_code = {r["style_code"]: r for r in res["by_style"]}

    # 1. Style with actual production jobs:
    actual_row = by_code["STYLE_ACTUAL"]
    assert actual_row["labor_source"] == "actual"
    assert actual_row["cost_is_estimated"] is False
    assert actual_row["labor_cost"] == 40.0
    assert actual_row["materials_cost"] == 100.0
    assert actual_row["unit_cogs"] == 159.0
    assert actual_row["cogs"] == 159.0 * 10

    # 2. Style with NO production jobs:
    est_row = by_code["STYLE_ESTIMATED"]
    assert est_row["labor_source"] == "estimated"
    assert est_row["cost_is_estimated"] is True
    assert est_row["labor_cost"] == 15.0
    assert est_row["materials_cost"] == 80.0
    assert est_row["unit_cogs"] == 109.5
    assert est_row["cogs"] == 109.5 * 5

    # 3. Total COGS calculation
    expected_total_cogs = (159.0 * 10) + (109.5 * 5)
    assert res["total_net_cogs"] == round(expected_total_cogs, 2)

    # 4. Top-level cost_is_estimated
    assert res["cost_is_estimated"] is True


def test_online_profitability_all_actual_labor(monkeypatch):
    """When all styles have confirmed production job history, cost_is_estimated is False at top level."""
    actual_style_id = ObjectId("60d5ec49f1b2c80015f8a003")

    styles = [
        {
            "_id": actual_style_id,
            "code": "STYLE_ALL_ACTUAL",
            "bom": [{"rate": 50.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Stitching", "rate": 20.0}],
            "overhead_pct": 0.0,
            "packing_cost": 0.0,
        },
    ]

    jobs = [
        {
            "style_id": str(actual_style_id),
            "style_code": "STYLE_ALL_ACTUAL",
            "assignments": {
                "stitching": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 25.0},
            },
        }
    ]

    sold_rows = [
        {
            "_id": actual_style_id,
            "style_code": "STYLE_ALL_ACTUAL",
            "color": "Black",
            "units_sold": 4,
            "item_final_amount": 400.0,
            "order_release_ids": ["REL1"],
        },
    ]

    mock_db = _MockDB(
        styles=styles,
        jobs=jobs,
        order_items_sold=sold_rows,
        order_items_ret=[],
    )

    monkeypatch.setattr(server, "db", mock_db)

    async def _run():
        return await _compute_online_profitability(
            platform=None, date_from=None, date_to=None, style_id=None
        )

    res = asyncio.run(_run())

    assert len(res["by_style"]) == 1
    row = res["by_style"][0]
    assert row["labor_source"] == "actual"
    assert row["cost_is_estimated"] is False
    assert res["cost_is_estimated"] is False


def test_online_profitability_fees_subtracted_on_fallback_revenue(monkeypatch):
    """When revenue is fallback item_final_amount, platform fees ARE subtracted from profit."""
    style_id = ObjectId("60d5ec49f1b2c80015f8a004")

    styles = [
        {
            "_id": style_id,
            "code": "STYLE_FALLBACK",
            "bom": [{"rate": 50.0, "quantity": 1}],
            "labor": [{"name": "Stitching", "rate": 20.0}],
            "overhead_pct": 0.0,
            "packing_cost": 0.0,
        },
    ]

    sold_rows = [
        {
            "_id": style_id,
            "style_code": "STYLE_FALLBACK",
            "color": "Brown",
            "units_sold": 2,
            "item_final_amount": 1000.0,
            "order_release_ids": ["REL_FB"],
        },
    ]

    settlements = [
        {
            "matched": True,
            "matched_style_id": str(style_id),
            "net_payout": 400.0,  # 1 unit reconciled at 400
        },
    ]

    mock_db = _MockDB(
        styles=styles,
        jobs=[],
        order_items_sold=sold_rows,
        order_items_ret=[],
        online_settlements=settlements,
        existing_collections=["online_settlements", "settlement_forward"],
    )

    monkeypatch.setattr(server, "db", mock_db)

    # Monkeypatch per-style fees split and top-level fees
    async def _mock_split(settle_match, sold_rows):
        return {}, {str(style_id): 100.0}

    monkeypatch.setattr(server, "_per_style_settlement_split", _mock_split)

    async def _mock_sum_settlement(coll, fields, match):
        return 100.0 if "settlement_forward" in coll else 0.0

    monkeypatch.setattr(server, "_sum_settlement_fields", _mock_sum_settlement)

    async def _run():
        return await _compute_online_profitability(
            platform=None, date_from=None, date_to=None, style_id=None
        )

    res = asyncio.run(_run())

    # Total units sold = 2, reconciled = 1.
    # Reconciled net payout = 400, fallback estimated portion = 1000 * (1/2) = 500. Total revenue = 900.
    # Total net COGS = (50+20) * 2 = 140.0
    # Total platform fees = 100.0
    # Revenue source used = "net_payout (reconciled) + final_amount (estimated fallback)"
    # Since revenue contains final_amount, gross profit subtracts platform fees:
    # Gross profit = 900 - 140 - 100 = 660.0
    assert "final_amount" in res["revenue_source_used"]
    assert res["total_net_cogs"] == 140.0
    assert res["total_platform_fees"] == 100.0
    assert res["gross_profit"] == 660.0

    row = res["by_style"][0]
    # Row has 1 reconciled unit and 1 estimated unit => row revenue source is partially estimated ("final_amount")
    assert "final_amount" in row["revenue_source"]
    assert row["platform_fees"] == 100.0
    assert row["profit"] == 660.0


def test_online_profitability_fees_not_double_subtracted_on_settlement(monkeypatch):
    """When revenue is settlement-reconciled (net_payout), platform fees are ALREADY netted, so profit = revenue - COGS."""
    style_id = ObjectId("60d5ec49f1b2c80015f8a005")

    styles = [
        {
            "_id": style_id,
            "code": "STYLE_SETTLED",
            "bom": [{"rate": 50.0, "quantity": 1}],
            "labor": [{"name": "Stitching", "rate": 20.0}],
            "overhead_pct": 0.0,
            "packing_cost": 0.0,
        },
    ]

    sold_rows = [
        {
            "_id": style_id,
            "style_code": "STYLE_SETTLED",
            "color": "Black",
            "units_sold": 2,
            "item_final_amount": 1000.0,
            "order_release_ids": ["REL_SETTLE"],
        },
    ]

    settlements = [
        {
            "matched": True,
            "matched_style_id": str(style_id),
            "net_payout": 425.0,  # unit 1
        },
        {
            "matched": True,
            "matched_style_id": str(style_id),
            "net_payout": 425.0,  # unit 2
        },
    ]

    mock_db = _MockDB(
        styles=styles,
        jobs=[],
        order_items_sold=sold_rows,
        order_items_ret=[],
        online_settlements=settlements,
        existing_collections=["online_settlements"],
    )

    monkeypatch.setattr(server, "db", mock_db)

    async def _run():
        return await _compute_online_profitability(
            platform=None, date_from=None, date_to=None, style_id=None
        )

    res = asyncio.run(_run())

    # COGS = 70 * 2 = 140.0
    # Reconciled Net Payout = 425 + 425 = 850.0 (already net of fees)
    # Profit must NOT subtract fees again!
    # Expected gross_profit = 850.0 - 140.0 = 710.0
    assert res["revenue_source_used"] == "net_payout (reconciled)"
    assert res["total_net_cogs"] == 140.0
    assert res["gross_profit"] == 710.0

    row = res["by_style"][0]
    assert row["revenue_source"] == "net_payout (reconciled)"
    assert row["profit"] == 710.0


def test_online_profitability_all_four_combinations(monkeypatch):
    """Verify full flow with real data showing all 4 combinations:
    1. Revenue Confirmed + Cost Actual (is_estimated=False, cost_is_estimated=False)
    2. Revenue Confirmed + Cost Estimated (is_estimated=False, cost_is_estimated=True)
    3. Revenue Estimated + Cost Actual (is_estimated=True, cost_is_estimated=False)
    4. Revenue Estimated + Cost Estimated (is_estimated=True, cost_is_estimated=True)
    """
    id_conf_act = ObjectId("60d5ec49f1b2c80015f8a011")
    id_conf_est = ObjectId("60d5ec49f1b2c80015f8a012")
    id_est_act  = ObjectId("60d5ec49f1b2c80015f8a013")
    id_est_est  = ObjectId("60d5ec49f1b2c80015f8a014")

    styles = [
        {"_id": id_conf_act, "code": "REV_CONF_COST_ACT", "bom": [{"rate": 50.0, "quantity": 1}], "labor": [{"name": "L", "rate": 20.0}]},
        {"_id": id_conf_est, "code": "REV_CONF_COST_EST", "bom": [{"rate": 60.0, "quantity": 1}], "labor": [{"name": "L", "rate": 25.0}]},
        {"_id": id_est_act,  "code": "REV_EST_COST_ACT",  "bom": [{"rate": 70.0, "quantity": 1}], "labor": [{"name": "L", "rate": 30.0}]},
        {"_id": id_est_est,  "code": "REV_EST_COST_EST",  "bom": [{"rate": 80.0, "quantity": 1}], "labor": [{"name": "L", "rate": 35.0}]},
    ]

    jobs = [
        {
            "style_id": str(id_conf_act),
            "style_code": "REV_CONF_COST_ACT",
            "assignments": {"stitching": {"worker_id": "w1", "rate_per_pair": 22.0}},
        },
        {
            "style_id": str(id_est_act),
            "style_code": "REV_EST_COST_ACT",
            "assignments": {"stitching": {"worker_id": "w2", "rate_per_pair": 32.0}},
        },
    ]

    sold_rows = [
        {"_id": id_conf_act, "style_code": "REV_CONF_COST_ACT", "color": "Black", "units_sold": 1, "item_final_amount": 500.0, "order_release_ids": ["R1"]},
        {"_id": id_conf_est, "style_code": "REV_CONF_COST_EST", "color": "Brown", "units_sold": 1, "item_final_amount": 600.0, "order_release_ids": ["R2"]},
        {"_id": id_est_act,  "style_code": "REV_EST_COST_ACT",  "color": "Tan",   "units_sold": 1, "item_final_amount": 700.0, "order_release_ids": ["R3"]},
        {"_id": id_est_est,  "style_code": "REV_EST_COST_EST",  "color": "White", "units_sold": 1, "item_final_amount": 800.0, "order_release_ids": ["R4"]},
    ]

    # Only styles 1 and 2 have reconciled settlement rows
    settlements = [
        {"matched": True, "matched_style_id": str(id_conf_act), "net_payout": 450.0},
        {"matched": True, "matched_style_id": str(id_conf_est), "net_payout": 520.0},
    ]

    mock_db = _MockDB(
        styles=styles,
        jobs=jobs,
        order_items_sold=sold_rows,
        order_items_ret=[],
        online_settlements=settlements,
        existing_collections=["online_settlements"],
    )

    monkeypatch.setattr(server, "db", mock_db)

    async def _run():
        return await _compute_online_profitability(
            platform=None, date_from=None, date_to=None, style_id=None
        )

    res = asyncio.run(_run())

    # Top-level: at least one estimated revenue, at least one estimated cost
    assert res["is_estimated"] is True
    assert res["cost_is_estimated"] is True
    assert len(res["by_style"]) == 4

    by_code = {r["style_code"]: r for r in res["by_style"]}

    # Combination 1: Revenue Confirmed + Cost Actual
    row1 = by_code["REV_CONF_COST_ACT"]
    assert row1["is_estimated"] is False
    assert row1["cost_is_estimated"] is False
    assert row1["labor_source"] == "actual"
    assert row1["labor_cost"] == 22.0
    assert row1["unit_cogs"] == 72.0

    # Combination 2: Revenue Confirmed + Cost Estimated
    row2 = by_code["REV_CONF_COST_EST"]
    assert row2["is_estimated"] is False
    assert row2["cost_is_estimated"] is True
    assert row2["labor_source"] == "estimated"
    assert row2["labor_cost"] == 25.0
    assert row2["unit_cogs"] == 85.0

    # Combination 3: Revenue Estimated + Cost Actual
    row3 = by_code["REV_EST_COST_ACT"]
    assert row3["is_estimated"] is True
    assert row3["cost_is_estimated"] is False
    assert row3["labor_source"] == "actual"
    assert row3["labor_cost"] == 32.0
    assert row3["unit_cogs"] == 102.0

    # Combination 4: Revenue Estimated + Cost Estimated
    row4 = by_code["REV_EST_COST_EST"]
    assert row4["is_estimated"] is True
    assert row4["cost_is_estimated"] is True
    assert row4["labor_source"] == "estimated"
    assert row4["labor_cost"] == 35.0
    assert row4["unit_cogs"] == 115.0

