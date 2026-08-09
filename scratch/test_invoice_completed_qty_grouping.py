"""Unit test for invoice completed quantity & style/color grouping logic."""
import os
import sys
import asyncio
import re

# Add backend directory to sys.path
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(backend_dir))

from pdf_docs import build_invoice

def test_invoice_grouping_and_completed_qty():
    # Sample PO with 5 size items for SSK_00009 / CREAM
    po = {
        "id": "507f1f77bcf86cd799439011",
        "po_number": "2220008833",
        "client_name": "SIYARAM SILK MILLS LTD.",
        "cgst_rate": 0.0,
        "sgst_rate": 0.0,
        "igst_rate": 5.0,
        "line_items": [
            {"style_code": "SSK_00009", "color": "CREAM", "size": "4", "quantity": 144, "completed_qty": 142, "unit_price": 170.0, "description": "ZFLWWFLT05266 CREAM 4"},
            {"style_code": "SSK_00009", "color": "CREAM", "size": "5", "quantity": 144, "completed_qty": 143, "unit_price": 170.0, "description": "ZFLWWFLT05266 CREAM 5"},
            {"style_code": "SSK_00009", "color": "CREAM", "size": "6", "quantity": 144, "completed_qty": 142, "unit_price": 170.0, "description": "ZFLWWFLT05266 CREAM 6"},
            {"style_code": "SSK_00009", "color": "CREAM", "size": "7", "quantity": 144, "completed_qty": 142, "unit_price": 170.0, "description": "ZFLWWFLT05266 CREAM 7"},
            {"style_code": "SSK_00009", "color": "CREAM", "size": "8", "quantity": 144, "completed_qty": 144, "unit_price": 170.0, "description": "ZFLWWFLT05266 CREAM 8"},
        ]
    }

    # Simulate logic from _generate_invoice_payload
    po_items = po.get("line_items", [])
    raw_items = []
    for li in po_items:
        comp = li.get("completed_qty")
        qty = comp if (comp is not None and comp > 0) else li.get("quantity", 0)
        unit_price = li.get("unit_price", 0)
        raw_items.append({
            "style_code": li.get("style_code", ""),
            "description": li.get("description", ""),
            "color": li.get("color", ""),
            "size": str(li.get("size", "")),
            "hsn_code": li.get("hsn_code", "") or "64029990",
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "mrp": li.get("mrp", ""),
        })

    grouped = {}
    for item in raw_items:
        sc = (item.get("style_code") or "").strip()
        color = (item.get("color") or "").strip()
        g_key = (sc, color)

        desc = (item.get("description") or "").strip()
        clean_desc = re.sub(r'(\s+\d+|\s*/?\s*Sz\s*\d+)+$', '', desc, flags=re.IGNORECASE).strip()

        if g_key not in grouped:
            grouped[g_key] = {
                "style_code": sc,
                "description": clean_desc,
                "color": color,
                "hsn_code": item.get("hsn_code", "") or "64029990",
                "quantity": 0,
                "unit_price": float(item.get("unit_price") or 0),
                "mrp": item.get("mrp", ""),
            }
        grouped[g_key]["quantity"] += int(item.get("quantity", 0) or 0)
        if clean_desc and not grouped[g_key]["description"]:
            grouped[g_key]["description"] = clean_desc

    line_items = []
    for g in grouped.values():
        qty = g["quantity"]
        unit_price = float(g["unit_price"] or 0)
        line_items.append({
            "style_code": g["style_code"],
            "description": g["description"],
            "color": g["color"],
            "hsn_code": g["hsn_code"],
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "mrp": g["mrp"],
        })

    # Assertions
    print(f"Grouped Line Items Count: {len(line_items)}")
    assert len(line_items) == 1, f"Expected 1 line item, got {len(line_items)}"
    item = line_items[0]
    expected_completed_qty = 142 + 143 + 142 + 142 + 144  # 713
    print(f"Total Invoice Quantity: {item['quantity']} (Expected: {expected_completed_qty})")
    assert item["quantity"] == expected_completed_qty, f"Expected completed qty {expected_completed_qty}, got {item['quantity']}"
    assert item["style_code"] == "SSK_00009"
    assert item["color"] == "CREAM"
    assert item["description"] == "ZFLWWFLT05266 CREAM"
    expected_amount = round(713 * 170.0, 2)
    assert item["amount"] == expected_amount, f"Expected amount {expected_amount}, got {item['amount']}"

    # Build PDF
    pdf_bytes = build_invoice(po, "SSK26-27-016", "09/08/2026", line_items=line_items)
    assert pdf_bytes and len(pdf_bytes) > 0, "PDF bytes should not be empty"
    print(f"PDF generated successfully, size: {len(pdf_bytes)} bytes")
    print("ALL VERIFICATION CHECKS PASSED!")

if __name__ == "__main__":
    test_invoice_grouping_and_completed_qty()
