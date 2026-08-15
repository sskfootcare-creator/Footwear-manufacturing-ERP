"""
Resequence Invoices & Clean Test Artifacts
==========================================
1. Backs up existing collections.
2. Removes leftover test suite artifacts (test clients, test POs, test invoices, test dispatch records).
3. Re-sequences real customer invoices sequentially starting from SSK26-27-016.
4. Regenerates PDF invoices with new serial numbers.
5. Updates live counter in db.counters.
"""

import asyncio
import base64
import os
import sys
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# Add backend to path for pdf_docs import
sys.path.insert(0, os.path.dirname(__file__))
from pdf_docs import build_invoice

TEST_CLIENT_PATTERNS = [
    "DispatchTestClient",
    "Card Client",
    "Client Ledger Test",
    "Test Client",
    "RFP Client",
    "Test Gate Client",
    "Test Retail Client",
    "Test Bulk Client",
]

TEST_PO_PREFIXES = (
    "PO-PACK-TEST-",
    "PO-BULK-CONFIRM-",
    "DISP-TEST-",
    "WRKTEST-",
    "RFPTEST-",
    "CARDTEST-",
    "PO-GATE-TEST-",
    "TEST-",
)

def is_test_record(doc: dict) -> bool:
    client_name = str(doc.get("client_name") or "")
    for pat in TEST_CLIENT_PATTERNS:
        if pat.lower() in client_name.lower():
            return True
    
    po_number = str(doc.get("po_number") or "")
    if po_number.startswith(TEST_PO_PREFIXES):
        return True
    
    po_numbers = doc.get("po_numbers") or []
    for p in po_numbers:
        if str(p).startswith(TEST_PO_PREFIXES):
            return True
            
    invoice_no = str(doc.get("invoice_no") or "")
    if invoice_no.startswith("INV-"):
        return True
        
    return False

async def run_resequence():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]

    print("=== STEP 1: Creating backup collections ===")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for coll_name in ["invoices", "dispatch_records", "counters", "pos", "packing_cartons", "grns", "payments"]:
        docs = await db[coll_name].find({}).to_list(100000)
        if docs:
            backup_name = f"_backup_{coll_name}_{timestamp}"
            await db[backup_name].insert_many(docs)
            print(f"  Backed up {len(docs)} documents from '{coll_name}' to '{backup_name}'")

    print("\n=== STEP 2: Cleaning test artifacts ===")
    
    # 1. Clean test invoices
    all_invoices = await db.invoices.find({}).to_list(1000)
    test_inv_ids = []
    real_invoices = []
    for inv in all_invoices:
        if is_test_record(inv):
            test_inv_ids.append(inv["_id"])
        else:
            real_invoices.append(inv)
            
    if test_inv_ids:
        del_res = await db.invoices.delete_many({"_id": {"$in": test_inv_ids}})
        print(f"  Deleted {del_res.deleted_count} test invoices")
    print(f"  Found {len(real_invoices)} real invoices to resequence")

    # 2. Clean test dispatch records
    all_drs = await db.dispatch_records.find({}).to_list(1000)
    test_dr_ids = [d["_id"] for d in all_drs if is_test_record(d)]
    if test_dr_ids:
        del_dr = await db.dispatch_records.delete_many({"_id": {"$in": test_dr_ids}})
        print(f"  Deleted {del_dr.deleted_count} test dispatch records")

    # 3. Clean test POs
    all_pos = await db.pos.find({}).to_list(1000)
    test_po_ids = [p["_id"] for p in all_pos if is_test_record(p)]
    if test_po_ids:
        del_po = await db.pos.delete_many({"_id": {"$in": test_po_ids}})
        print(f"  Deleted {del_po.deleted_count} test POs")

    # 4. Clean test GRNs and payments
    all_grns = await db.grns.find({}).to_list(1000)
    test_grn_ids = [g["_id"] for g in all_grns if is_test_record(g) or g.get("invoice_id") in [str(i) for i in test_inv_ids]]
    if test_grn_ids:
        del_grn = await db.grns.delete_many({"_id": {"$in": test_grn_ids}})
        print(f"  Deleted {del_grn.deleted_count} test GRNs")

    all_payments = await db.payments.find({}).to_list(1000)
    test_pay_ids = [p["_id"] for p in all_payments if is_test_record(p) or any(iid in [str(i) for i in test_inv_ids] for iid in (p.get("invoice_ids") or []))]
    if test_pay_ids:
        del_pay = await db.payments.delete_many({"_id": {"$in": test_pay_ids}})
        print(f"  Deleted {del_pay.deleted_count} test payments")

    print("\n=== STEP 3: Resequencing real invoices ===")
    # Sort real invoices chronologically by created_at or invoice_date
    real_invoices.sort(key=lambda x: x.get("created_at") or "")

    start_seq = 16  # Pre-ERP bills 001..015 were paper bills; ERP starts at 016
    current_seq = start_seq

    for inv in real_invoices:
        old_no = inv.get("invoice_no")
        new_no = f"SSK26-27-{current_seq:03d}"
        inv_id = inv["_id"]
        
        print(f"  Resequencing Invoice {inv_id}: {old_no} -> {new_no}")
        
        # Load PO for generating PDF
        po_doc = None
        if inv.get("po_id"):
            try:
                po_doc = await db.pos.find_one({"_id": ObjectId(inv["po_id"])})
            except Exception:
                po_doc = None
        if not po_doc and inv.get("po_number"):
            po_doc = await db.pos.find_one({"po_number": inv.get("po_number")})
            
        po_dict = po_doc or {
            "po_number": inv.get("po_number", ""),
            "client_name": inv.get("client_name", ""),
            "cgst_rate": inv.get("cgst_rate", 0),
            "sgst_rate": inv.get("sgst_rate", 0),
            "igst_rate": inv.get("igst_rate", 0),
        }
        
        line_items = inv.get("line_items_snapshot") or inv.get("line_items") or po_dict.get("line_items", [])
        
        # Regenerate PDF with new invoice number
        pdf_bytes = build_invoice(
            po=po_dict,
            invoice_no=new_no,
            invoice_date=inv.get("invoice_date", ""),
            transport_mode=inv.get("transport_mode", ""),
            vehicle_no=inv.get("vehicle_no", ""),
            supply_date=inv.get("supply_date", ""),
            line_items=line_items,
        )
        file_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        
        # Update invoice in db.invoices
        await db.invoices.update_one(
            {"_id": inv_id},
            {"$set": {
                "invoice_no": new_no,
                "file_b64": file_b64,
            }}
        )
        
        # Update any linked dispatch records
        await db.dispatch_records.update_many(
            {"$or": [{"invoice_id": str(inv_id)}, {"invoice_no": old_no}]},
            {"$set": {
                "invoice_no": new_no,
                "invoice_file_b64": file_b64,
            }}
        )
        
        # Update any linked GRNs
        await db.grns.update_many(
            {"$or": [{"invoice_id": str(inv_id)}, {"invoice_no": old_no}]},
            {"$set": {"invoice_no": new_no}}
        )
        
        # Update any packing cartons
        await db.packing_cartons.update_many(
            {"invoice_id": str(inv_id)},
            {"$set": {"invoice_no": new_no}}
        )

        current_seq += 1

    last_assigned_seq = current_seq - 1
    print(f"\n=== STEP 4: Updating counter invoice_26-27 ===")
    print(f"  Setting counter invoice_26-27 seq to {last_assigned_seq}")
    await db.counters.update_one(
        {"_id": "invoice_26-27"},
        {"$set": {"seq": last_assigned_seq}},
        upsert=True
    )

    print("\n=== RESEQUENCING COMPLETED SUCCESSFULLY ===")
    print(f"Total real invoices re-sequenced: {len(real_invoices)}")
    print(f"Next invoice generated will be: SSK26-27-{last_assigned_seq + 1:03d}")

if __name__ == "__main__":
    asyncio.run(run_resequence())
