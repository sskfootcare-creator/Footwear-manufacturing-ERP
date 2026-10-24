"""Investor entity, funding calculations, advances and repayments service."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from bson import ObjectId
from fastapi import HTTPException

log = logging.getLogger(__name__)


def oid(val: Any) -> ObjectId:
    if isinstance(val, ObjectId):
        return val
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(400, f"Invalid ObjectId: {val}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def compute_investor_funding_required(
    po_id: Any,
    include_opex: bool,
    db: Any
) -> Dict[str, Any]:
    """
    Computes required funding for a given Purchase Order.
    Pulls bom_cost + labor_cost from compute_po_profitability * PO quantity (reuse, don't recompute).
    Opex is NOT auto-apportioned:
      - If include_opex is True, sum the recurring_expenses templates flagged is_investor_opex=True and add once.
      - If False, opex_cost is 0.0.
    Caller decides include_opex per cycle — this function never guesses it.
    """
    # 1. Fetch PO from db.pos
    po_doc = None
    try:
        po_doc = await db.pos.find_one({"_id": oid(po_id)})
    except Exception:
        pass

    if not po_doc:
        po_doc = await db.pos.find_one({"_id": str(po_id)})
    if not po_doc:
        po_doc = await db.pos.find_one({"id": str(po_id)})
    if not po_doc:
        po_doc = await db.pos.find_one({"po_number": str(po_id)})

    if not po_doc:
        raise HTTPException(404, f"Purchase order '{po_id}' not found")

    from routes.pos import _attach_po_profitability

    # Attach official PO profitability & production budget rollup (exact same calculation as PO tab)
    po_copy = dict(po_doc)
    if not po_copy.get("line_items"):
        if po_copy.get("items"):
            po_copy["line_items"] = po_copy["items"]
        elif po_copy.get("style_code") or po_copy.get("style_id"):
            po_copy["line_items"] = [{
                "style_code": po_copy.get("style_code"),
                "style_id": po_copy.get("style_id"),
                "color": po_copy.get("color"),
                "unit_price": po_copy.get("unit_price") or po_copy.get("pair_price") or 0,
                "quantity": po_copy.get("total_quantity") or po_copy.get("quantity") or 0,
            }]
    await _attach_po_profitability([po_copy], db)
    prod_budget = po_copy.get("production_budget") or po_copy.get("profitability") or {}

    total_bom_cost = float(prod_budget.get("total_bom_cost") or 0.0)
    total_labor_cost = float(prod_budget.get("total_labor_cost") or 0.0)
    total_packing_cost = float(prod_budget.get("total_packing_cost") or 0.0)
    total_outside_cost = float(prod_budget.get("total_outside_cost") or 0.0)
    total_pairs = int(prod_budget.get("total_quantity") or po_doc.get("total_quantity") or po_doc.get("quantity") or 0)

    # 2. Opex calculation
    opex_cost = 0.0
    if include_opex:
        # Sum active recurring_expenses templates flagged is_investor_opex=True
        opex_templates = await db.recurring_expenses.find({
            "is_investor_opex": True,
            "active": {"$ne": False}
        }).to_list(1000)
        opex_cost = round(sum(float(t.get("amount") or 0.0) for t in opex_templates), 2)

    total_bom_cost = round(total_bom_cost, 2)
    total_labor_cost = round(total_labor_cost, 2)
    total_packing_cost = round(total_packing_cost, 2)
    total_outside_cost = round(total_outside_cost, 2)

    # Base production budget matches the PO Tab exactly: BOM + Labour + Packing + Outside Labour
    base_po_budget = round(total_bom_cost + total_labor_cost + total_packing_cost + total_outside_cost, 2)
    total_funding_required = round(base_po_budget + opex_cost, 2)

    return {
        "po_id": str(po_doc["_id"]),
        "po_number": po_doc.get("po_number", ""),
        "pairs": total_pairs,
        "bom_cost": total_bom_cost,
        "labor_cost": total_labor_cost,
        "labour_cost": total_labor_cost,
        "packing_cost": total_packing_cost,
        "outside_cost": total_outside_cost,
        "base_po_budget": base_po_budget,
        "opex_cost": opex_cost,
        "opex_included": bool(include_opex),
        "total_funding_required": total_funding_required,
        "amount": total_funding_required,
        "breakdown": {
            "bom_cost": total_bom_cost,
            "labour_cost": total_labor_cost,
            "labor_cost": total_labor_cost,
            "packing_cost": total_packing_cost,
            "outside_cost": total_outside_cost,
            "base_po_budget": base_po_budget,
            "opex_cost": opex_cost,
            "opex_included": bool(include_opex),
        }
    }
