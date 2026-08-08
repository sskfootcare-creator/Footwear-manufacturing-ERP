import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from server import get_b2b_profitability
from tests.test_b2b_profitability import _DB, _Request

styles = [
    {
        "_id": "style_actual_id",
        "code": "STYLE_ACTUAL",
        "name": "Actual Production Style",
        "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 30.0}],
        "packing_cost": 10.0,
        "overhead_pct": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    },
    {
        "_id": "style_est_id",
        "code": "STYLE_ESTIMATED",
        "name": "Brand New Style",
        "bom": [{"rate": 80.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Cutting", "rate": 20.0}],
        "packing_cost": 5.0,
        "overhead_pct": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    },
]

jobs = [
    {
        "style_id": "style_actual_id",
        "style_code": "STYLE_ACTUAL",
        "assignments": {
            "cutting": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 15.0},
            "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 25.0},
        },
    }
]

invoices = [
    {
        "_id": "inv_1",
        "invoice_no": "INV-2026-001",
        "invoice_date": "2026-08-01",
        "po_number": "PO-101",
        "client_name": "Client Alpha",
        "line_items_snapshot": [
            {
                "style_code": "STYLE_ACTUAL",
                "quantity": 100,
                "unit_price": 200.0,
            }
        ],
    },
    {
        "_id": "inv_2",
        "invoice_no": "INV-2026-002",
        "invoice_date": "2026-08-05",
        "po_number": "PO-102",
        "client_name": "Client Beta",
        "line_items_snapshot": [
            {
                "style_code": "STYLE_ESTIMATED",
                "quantity": 50,
                "unit_price": 150.0,
            }
        ],
    },
]

db = _DB(invoices=invoices, styles=styles, jobs=jobs)
req = _Request()

async def debug():
    res = await get_b2b_profitability(req, date_from="2026-08-01", date_to="2026-08-31")
    print("LINES COUNT:", len(res["lines"]))
    for l in res["lines"]:
        print("LINE:", l)
    print("SUMMARY:", res["summary"])

asyncio.run(debug())
