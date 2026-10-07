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

    from routes.pos import compute_po_profitability

    line_items = po_doc.get("line_items") or po_doc.get("items") or []
    if not line_items and (po_doc.get("style_code") or po_doc.get("style_id")):
        line_items = [{
            "style_code": po_doc.get("style_code"),
            "style_id": po_doc.get("style_id"),
            "color": po_doc.get("color"),
            "unit_price": po_doc.get("unit_price", 0),
            "quantity": po_doc.get("total_quantity") or po_doc.get("quantity") or 0,
        }]

    total_bom_cost = 0.0
    total_labor_cost = 0.0
    total_pairs = 0

    for item in line_items:
        qty = float(item.get("quantity") or 0.0)
        total_pairs += int(qty)

        # Retrieve style object
        style_doc = None
        style_code = (item.get("style_code") or "").strip()
        style_id_val = item.get("style_id")

        q_or = []
        if style_code:
            q_or.append({"code": style_code})
        if style_id_val:
            try:
                q_or.append({"_id": oid(style_id_val)})
            except Exception:
                q_or.append({"_id": str(style_id_val)})

        if q_or:
            query = {"$or": q_or} if len(q_or) > 1 else q_or[0]
            style_doc = await db.styles.find_one(query)

        # Call compute_po_profitability to reuse exact BOM and Labor costing
        prof = await compute_po_profitability(item, style_doc or {}, db=db)
        bom_unit = float(prof.get("bom_cost") or 0.0)
        labor_unit = float(prof.get("labor_cost") or 0.0)

        total_bom_cost += (bom_unit * qty)
        total_labor_cost += (labor_unit * qty)

    if total_pairs == 0:
        total_pairs = int(po_doc.get("total_quantity") or po_doc.get("quantity") or 0)

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
    total_funding_required = round(total_bom_cost + total_labor_cost + opex_cost, 2)

    return {
        "po_id": str(po_doc["_id"]),
        "po_number": po_doc.get("po_number", ""),
        "pairs": total_pairs,
        "bom_cost": total_bom_cost,
        "labor_cost": total_labor_cost,
        "opex_cost": opex_cost,
        "opex_included": bool(include_opex),
        "total_funding_required": total_funding_required,
        "amount": total_funding_required,
        "breakdown": {
            "bom_cost": total_bom_cost,
            "labour_cost": total_labor_cost,
            "labor_cost": total_labor_cost,
            "opex_cost": opex_cost,
            "opex_included": bool(include_opex),
        }
    }
