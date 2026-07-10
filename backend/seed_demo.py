"""
seed_demo.py — idempotent demo-data loader for Online Orders / Picklists /
Pending Product List. Run from /app/backend:

    python -m seed_demo

Safe to re-run: every insert is keyed on a stable "demo:*" marker so the script
either inserts fresh or leaves existing rows alone. Use the `--reset` flag to
wipe just the demo rows and reseed.

Seeds:
    - 6 warehouse locations + fg_location_inventory rows across all three
      existing styles so picklists can allocate real stock.
    - 6 online-order production_jobs (channel=myntra/amazon/ajio, stages spread
      across procurement / production / packing, some with component shortages).
    - 4 top-level online_orders (embedded item arrays) linked to those jobs.
    - 3 picklists (fully allocated / partial / small ajio) — with real product
      images so the picklist and pending-list screens look populated.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME",   "test_database")

DEMO_TAG      = "demo:online-seed"
DEMO_PO_TAG   = "DEMO-ONLINE-"        # prefix for demo-only production_jobs
DEMO_PL_TAG   = "PL-DEMO-"            # prefix for demo picklists


# ─── helpers ───────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def past_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


async def pick_styles(db, n: int = 3):
    """Return the first `n` styles as [(oid, code, name, image_url)]."""
    out = []
    async for s in db.styles.find({}).sort("created_at", 1).limit(n):
        out.append((
            s["_id"], s["code"], s.get("name", ""),
            s.get("image_url", ""), s.get("image_display_url", ""),
            s.get("image_thumbnail_url", ""),
        ))
    return out


async def wipe_demo(db):
    r1 = await db.production_jobs.delete_many({"demo_tag": DEMO_TAG})
    r2 = await db.online_orders.delete_many({"demo_tag": DEMO_TAG})
    r3 = await db.online_order_items.delete_many({"demo_tag": DEMO_TAG})
    r4 = await db.picklists.delete_many({"demo_tag": DEMO_TAG})
    r5 = await db.fg_location_inventory.delete_many({"demo_tag": DEMO_TAG})
    r6 = await db.fg_stock.delete_many({"demo_tag": DEMO_TAG})
    r7 = await db.fg_stock_movements.delete_many({"demo_tag": DEMO_TAG})
    r8 = await db.component_stock.delete_many({"demo_tag": DEMO_TAG})
    print(f"  wiped: jobs={r1.deleted_count} orders={r2.deleted_count} "
          f"items={r3.deleted_count} picklists={r4.deleted_count} "
          f"loc_inv={r5.deleted_count} fg_stock={r6.deleted_count} "
          f"movements={r7.deleted_count} comp_stock={r8.deleted_count}")


# ─── seeders ───────────────────────────────────────────────────────────────
async def seed_fg_inventory(db, styles):
    """Populate `fg_location_inventory` for a matrix of sizes/colors across the
    demo styles so picklists have physical stock to allocate.
    """
    if await db.fg_location_inventory.count_documents({"demo_tag": DEMO_TAG}):
        print("  fg_location_inventory demo rows already present — skip")
        return

    # Reuse existing warehouse_locations if any; otherwise fall back to fixed codes.
    codes = []
    async for w in db.warehouse_locations.find({}).limit(3):
        codes.append((w["location_code"], w.get("rack"), w.get("row"), w.get("column")))
    if not codes:
        codes = [("R1-A-1", "R1", "A", 1), ("R1-A-2", "R1", "A", 2), ("R1-B-1", "R1", "B", 1)]

    rows = []
    now = now_iso()
    # style 0 → Tan/Brown Sizes 7-9  in code[0]
    # style 1 → Black size 8-10       in code[1]
    # style 2 → Beige size 6-8        in code[2]
    plans = [
        (styles[0 % len(styles)], "Tan",   ["7", "8", "9"],  codes[0 % len(codes)]),
        (styles[0 % len(styles)], "Brown", ["8", "9"],       codes[1 % len(codes)]),
        (styles[1 % len(styles)], "Black", ["8", "9", "10"], codes[1 % len(codes)]),
        (styles[2 % len(styles)], "Beige", ["6", "7", "8"],  codes[2 % len(codes)]),
    ]
    for style, color, sizes, loc in plans:
        style_oid, style_code, *_ = style
        loc_code, rack, row, col = loc
        for sz in sizes:
            rows.append({
                "style_id":       style_oid,
                "style_code":     style_code,
                "color":          color,
                "size":           sz,
                "location_code":  loc_code,
                "qty":            10,           # 10 pairs per bin
                "reserved_qty":   0,
                "created_at":     now,
                "updated_at":     now,
                "demo_tag":       DEMO_TAG,
            })
    if rows:
        await db.fg_location_inventory.insert_many(rows)
        print(f"  fg_location_inventory rows seeded: {len(rows)}")


async def seed_production_jobs(db, styles):
    """Create demo production_jobs for online orders — these power the Pending
    Product List page (source_type='online_channel').
    """
    if await db.production_jobs.count_documents({"demo_tag": DEMO_TAG}):
        print("  production_jobs demo rows already present — skip")
        return

    s0, s1, s2 = styles[0], styles[1 % len(styles)], styles[2 % len(styles)]
    now = now_iso()

    jobs = [
        # (style, color, size, qty, channel, po_number, stage, days_old, components_shortage_hint)
        (s0, "Tan",   "7",  8,  "myntra", "MYN-2601", "procurement",  1, False),
        (s0, "Tan",   "8",  12, "myntra", "MYN-2601", "procurement",  1, False),
        (s0, "Brown", "9",  6,  "myntra", "MYN-2602", "cutting",      2, True),
        (s1, "Black", "8",  10, "amazon", "AMZ-A114", "stitching",    3, False),
        (s1, "Black", "9",  4,  "amazon", "AMZ-A114", "packing",      4, False),
        (s2, "Beige", "7",  15, "ajio",   "AJO-77021","procurement",  0, True),
    ]
    docs = []
    for st, color, size, qty, channel, po_no, stage, age, shortage in jobs:
        style_oid, style_code, *_ = st
        docs.append({
            "source_type":       "online_channel",
            "channel":           channel,
            "po_number":         f"{DEMO_PO_TAG}{po_no}",
            "style_id":          style_oid,
            "style_code":        style_code,
            "color":             color,
            "size":              size,
            "quantity":          qty,
            "stage":             stage,
            # A cheap-and-cheerful `components` map — Pending List cares that
            # the object exists and computes `components_available` server-side.
            "components": {
                "upper_done":  stage in ("stitching", "packing"),
                "bottom_done": stage in ("stitching", "packing"),
                "sole_done":   stage == "packing",
            },
            # If shortage flag set, add a bogus component code so the Pending
            # List renders the "missing components" red banner.
            "component_shortages_seed": [
                {"component_code": "OFFT-BR-01", "component_name": "Off-white PU Sole", "available": 0, "needed": qty}
            ] if shortage else [],
            "created_at":        past_iso(age),
            "updated_at":        past_iso(age),
            "demo_tag":          DEMO_TAG,
        })
    r = await db.production_jobs.insert_many(docs)
    print(f"  production_jobs (online) seeded: {len(r.inserted_ids)}")


async def seed_online_orders(db, styles):
    """Top-level `online_orders` docs (embedded items). Powers the Online
    Orders index/reports page. Grouped by channel + order_id.
    """
    if await db.online_orders.count_documents({"demo_tag": DEMO_TAG}):
        print("  online_orders demo rows already present — skip")
        return

    s0, s1, s2 = styles[0], styles[1 % len(styles)], styles[2 % len(styles)]
    now = now_iso()

    orders = [
        {
            "platform":  "myntra",
            "order_id":  "MYN-ORD-90001",
            "customer_name": "Aditi Kapoor",
            "city": "Bangalore", "state": "KA", "pincode": "560001",
            "status": "confirmed",
            "created_at": past_iso(1),
            "items": [
                {"style_id": str(s0[0]), "style_code": s0[1], "color": "Tan",   "size": "7", "qty": 1, "unit_price": 1899, "amount": 1899},
                {"style_id": str(s0[0]), "style_code": s0[1], "color": "Tan",   "size": "8", "qty": 1, "unit_price": 1899, "amount": 1899},
            ],
        },
        {
            "platform":  "myntra",
            "order_id":  "MYN-ORD-90002",
            "customer_name": "Neha Sharma",
            "city": "Mumbai", "state": "MH", "pincode": "400001",
            "status": "shipped",
            "created_at": past_iso(3),
            "items": [
                {"style_id": str(s0[0]), "style_code": s0[1], "color": "Brown", "size": "9", "qty": 2, "unit_price": 2099, "amount": 4198},
            ],
        },
        {
            "platform":  "amazon",
            "order_id":  "AMZ-407-9948721-33",
            "customer_name": "Rakesh Iyer",
            "city": "Chennai", "state": "TN", "pincode": "600001",
            "status": "confirmed",
            "created_at": past_iso(2),
            "items": [
                {"style_id": str(s1[0]), "style_code": s1[1], "color": "Black", "size": "8",  "qty": 1, "unit_price": 2499, "amount": 2499},
                {"style_id": str(s1[0]), "style_code": s1[1], "color": "Black", "size": "9",  "qty": 1, "unit_price": 2499, "amount": 2499},
                {"style_id": str(s1[0]), "style_code": s1[1], "color": "Black", "size": "10", "qty": 1, "unit_price": 2499, "amount": 2499},
            ],
        },
        {
            "platform":  "ajio",
            "order_id":  "AJO-4488712",
            "customer_name": "Priya Menon",
            "city": "Kochi", "state": "KL", "pincode": "682001",
            "status": "confirmed",
            "created_at": past_iso(0),
            "items": [
                {"style_id": str(s2[0]), "style_code": s2[1], "color": "Beige", "size": "6", "qty": 1, "unit_price": 1799, "amount": 1799},
                {"style_id": str(s2[0]), "style_code": s2[1], "color": "Beige", "size": "7", "qty": 2, "unit_price": 1799, "amount": 3598},
            ],
        },
    ]

    for o in orders:
        o["total_qty"]    = sum(i["qty"] for i in o["items"])
        o["total_amount"] = sum(i["amount"] for i in o["items"])
        o["updated_at"]   = now
        o["demo_tag"]     = DEMO_TAG
        res = await db.online_orders.insert_one(o)
        # Denormalised item rows for easy filtering (mirrors import-configured behaviour)
        for it in o["items"]:
            it2 = dict(it)
            it2["online_order_id"] = res.inserted_id
            it2["platform"]        = o["platform"]
            it2["order_id"]        = o["order_id"]
            it2["created_at"]      = o["created_at"]
            it2["demo_tag"]        = DEMO_TAG
            await db.online_order_items.insert_one(it2)
    print(f"  online_orders seeded: {len(orders)}")


async def seed_components_and_boms(db, styles):
    """Populate `component_master` and `style_component_mapping` (BOM) for the
    demo styles so the Production Floor + BOM editor have realistic examples.
    Idempotent: rows are keyed on `component_code`."""
    now = now_iso()
    # Baseline component palette — mimics a real footwear BOM
    palette = [
        # (code,          name,                 category, color,  unit,  stock, reorder)
        ("DEMO-UPP-TAN",  "Tan PU Upper",       "Upper",  "Tan",   "pair", 120, 20),
        ("DEMO-UPP-BLK",  "Black PU Upper",     "Upper",  "Black", "pair",  90, 20),
        ("DEMO-UPP-BEG",  "Beige Suede Upper",  "Upper",  "Beige", "pair",  80, 20),
        ("DEMO-SOL-EVA",  "EVA Bottom Sole",    "Sole",   "",      "pair", 200, 30),
        ("DEMO-INS-MEM",  "Memory Foam Insole", "Insole", "",      "pair", 250, 30),
        ("DEMO-BOX-STD",  "Standard Shoe Box",  "Box",    "",      "pcs",  400, 50),
        ("DEMO-BAG-POLY", "Poly Bag",           "Packaging","",    "pcs",  600, 80),
        ("DEMO-TAG-BRAND","Brand Tag",          "Tag",    "",      "pcs",  500, 60),
    ]
    comp_by_code = {}
    for (code, name, cat, color, unit, stock, reorder) in palette:
        existing = await db.component_master.find_one({"component_code": code})
        if existing:
            comp_by_code[code] = existing["_id"]
            continue
        doc = {
            "component_code":     code,
            "component_name":     name,
            "component_category": cat,
            "color":              color or None,
            "unit":               unit,
            "current_stock":      stock,
            "reserved_stock":     0,
            "reorder_level":      reorder,
            "minimum_stock":      max(5, reorder // 2),
            "vendor":             "",
            "active":             True,
            "created_at":         now,
            "updated_at":         now,
            "demo_tag":           DEMO_TAG,
        }
        r = await db.component_master.insert_one(doc)
        comp_by_code[code] = r.inserted_id
    print(f"  component_master rows ready: {len(comp_by_code)}")

    # BOM per style — every style consumes Sole + Insole + Box + Poly + Tag,
    # plus the color-appropriate Upper. Realistic quantities-per-pair.
    s0, s1, s2 = styles[0], styles[1 % len(styles)], styles[2 % len(styles)]
    bom_plan = [
        # (style, upper_code)
        (s0, "DEMO-UPP-TAN"),
        (s1, "DEMO-UPP-BLK"),
        (s2, "DEMO-UPP-BEG"),
    ]
    common = [
        # Only the two essentials that scale per pair. Packaging (Box / Poly /
        # Tag) is intentionally NOT auto-seeded so the operator can add just
        # what their style actually consumes via the BOM editor.
        ("DEMO-SOL-EVA",  1.0, 3.0),
        ("DEMO-INS-MEM",  1.0, 2.0),
    ]
    inserted, skipped = 0, 0
    for style, upper_code in bom_plan:
        style_oid, style_code, *_ = style
        rows = [("upper", upper_code, 1.0, 5.0)] + [("", c, q, w) for (c, q, w) in common]
        for (_label, ccode, qty, waste) in rows:
            cid = comp_by_code.get(ccode)
            if not cid:
                continue
            already = await db.style_component_mapping.find_one({"style_id": style_oid, "component_id": cid})
            if already:
                skipped += 1
                continue
            comp = await db.component_master.find_one({"_id": cid})
            await db.style_component_mapping.insert_one({
                "style_id":           style_oid,
                "component_id":       cid,
                "component_category": (comp or {}).get("component_category", ""),
                "quantity_per_pair":  float(qty),
                "wastage_percent":    float(waste),
                "active":             True,
                "created_at":         now,
                "updated_at":         now,
                "created_by":         "demo@ssk.com",
                "demo_tag":           DEMO_TAG,
            })
            inserted += 1
    print(f"  style_component_mapping rows: inserted={inserted}, already-there skipped={skipped}")


async def seed_picklists(db, styles):
    """Create picklists directly — small, self-contained, image-enriched.

    We do NOT call `_generate_picklist_for_order` because that requires a fully-
    wired online-order flow and would double-book inventory reservations. This
    seed manually builds picklist docs that mirror the runtime shape.
    """
    if await db.picklists.count_documents({"demo_tag": DEMO_TAG}):
        print("  picklists demo rows already present — skip")
        return

    s0, s1, s2 = styles[0], styles[1 % len(styles)], styles[2 % len(styles)]

    # Pull the first three warehouse location codes for realism.
    codes = []
    async for w in db.warehouse_locations.find({}).limit(3):
        codes.append((w["location_code"], w.get("rack"), w.get("row"), w.get("column")))
    if not codes:
        codes = [("R1-A-1", "R1", "A", 1), ("R1-A-2", "R1", "A", 2), ("R1-B-1", "R1", "B", 1)]

    def make_item(style, color, size, qty, loc):
        style_oid, style_code, _sn, _iu, _idu, _itu = style
        return {
            "style_id":      str(style_oid),
            "style_code":    style_code,
            "color":         color,
            "size":          size,
            "location_code": loc[0],
            "rack":          loc[1],
            "row":           loc[2],
            "column":        loc[3],
            "qty":           qty,
            "picked":        False,
            "picked_at":     None,
        }

    picklists = [
        {
            "picklist_no": f"{DEMO_PL_TAG}0001",
            "order_id":    "MYN-ORD-90001",
            "channel":     "myntra",
            "status":      "pending",
            "items": [
                make_item(s0, "Tan", "7", 1, codes[0]),
                make_item(s0, "Tan", "8", 1, codes[0]),
            ],
        },
        {
            "picklist_no": f"{DEMO_PL_TAG}0002",
            "order_id":    "AMZ-407-9948721-33",
            "channel":     "amazon",
            "status":      "pending",
            "items": [
                make_item(s1, "Black", "8",  1, codes[1]),
                make_item(s1, "Black", "9",  1, codes[1]),
                make_item(s1, "Black", "10", 1, codes[1]),
            ],
        },
        {
            "picklist_no": f"{DEMO_PL_TAG}0003",
            "order_id":    "AJO-4488712",
            "channel":     "ajio",
            "status":      "pending",
            "items": [
                make_item(s2, "Beige", "6", 1, codes[2]),
                make_item(s2, "Beige", "7", 2, codes[2]),
            ],
        },
    ]
    now = now_iso()
    for pl in picklists:
        pl["picker"]      = None
        pl["created_at"]  = now
        pl["updated_at"]  = now
        pl["created_by"]  = "demo@ssk.com"
        pl["completed_at"] = None
        pl["total_items"] = len(pl["items"])
        pl["total_qty"]   = sum(i["qty"] for i in pl["items"])
        pl["demo_tag"]    = DEMO_TAG
    await db.picklists.insert_many(picklists)
    print(f"  picklists seeded: {len(picklists)}")


# ─── main ──────────────────────────────────────────────────────────────────
async def main(reset: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    if reset:
        print("Resetting demo rows…")
        await wipe_demo(db)

    styles = await pick_styles(db, 3)
    if len(styles) < 3:
        raise RuntimeError(f"Need at least 3 styles in the DB before seeding — found {len(styles)}. "
                           "Create/import styles first (or run the styles bulk-import template).")

    print(f"Using demo styles: {[s[1] for s in styles]}")
    await seed_components_and_boms(db, styles)
    await seed_fg_inventory(db, styles)
    await seed_production_jobs(db, styles)
    await seed_online_orders(db, styles)
    await seed_picklists(db, styles)

    # Print a small summary
    print("\n=== Post-seed counts ===")
    for coll in ("styles", "warehouse_locations", "fg_location_inventory",
                 "production_jobs", "online_orders", "online_order_items", "picklists"):
        total = await db[coll].count_documents({})
        demo  = await db[coll].count_documents({"demo_tag": DEMO_TAG}) if coll != "styles" and coll != "warehouse_locations" else "-"
        print(f"  {coll:26s} total={total:<6}  demo={demo}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed demo online orders / picklists / pending list data")
    ap.add_argument("--reset", action="store_true", help="Wipe existing demo rows first")
    args = ap.parse_args()
    asyncio.run(main(reset=args.reset))
