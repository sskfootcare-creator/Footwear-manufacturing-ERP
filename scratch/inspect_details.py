import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect_details():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    
    print("=== POS ===")
    pos = await db.pos.find({}).to_list(100)
    for p in pos:
        print(f"PO: id={p.get('_id')} | po_number={p.get('po_number')} | client={p.get('client_name')} | status={p.get('status')} | invoice_no={p.get('invoice_no')}")
        
    print("\n=== INVOICES ===")
    invoices = await db.invoices.find({}).to_list(100)
    for inv in invoices:
        print(f"INV: id={inv.get('_id')} | no={inv.get('invoice_no')} | date={inv.get('invoice_date')} | po={inv.get('po_number')} | client={inv.get('client_name')} | by={inv.get('by')} | created_at={inv.get('created_at')}")

    print("\n=== DISPATCH RECORDS ===")
    dispatches = await db.dispatch_records.find({}).to_list(100)
    for d in dispatches:
        print(f"DR: id={d.get('_id')} | inv={d.get('invoice_no')} | po={d.get('po_numbers')} | client={d.get('client_name')} | by={d.get('dispatched_by') or d.get('by')} | created={d.get('created_at') or d.get('dispatched_at')}")

if __name__ == "__main__":
    asyncio.run(inspect_details())
