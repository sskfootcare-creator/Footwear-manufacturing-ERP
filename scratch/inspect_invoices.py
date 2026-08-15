import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    invoices = await db.invoices.find({}).sort("created_at", 1).to_list(200)
    print(f"Total invoices: {len(invoices)}")
    for i, inv in enumerate(invoices):
        print(f"{i+1:2d}. ID: {inv.get('_id')} | No: {inv.get('invoice_no')} | Date: {inv.get('invoice_date')} | PO: {inv.get('po_number')} | Client: {inv.get('client_name')} | Created: {inv.get('created_at')}")

    dispatches = await db.dispatch_records.find({}).sort("created_at", 1).to_list(200)
    print(f"\nTotal dispatch records: {len(dispatches)}")
    for i, d in enumerate(dispatches):
        print(f"{i+1:2d}. ID: {d.get('_id')} | Inv: {d.get('invoice_no')} | Date: {d.get('invoice_date')} | POs: {d.get('po_numbers')} | Client: {d.get('client_name')} | Created: {d.get('created_at')}")

if __name__ == "__main__":
    asyncio.run(inspect())
