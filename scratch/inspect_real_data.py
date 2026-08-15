import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect_real_data():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    
    pos = await db.pos.find({}).to_list(100)
    print(f"=== ALL POs ({len(pos)}) ===")
    for p in pos:
        print(f"PO #{p.get('po_number')} | Client: {p.get('client_name')} | Created: {p.get('created_at')} | Status: {p.get('status')} | Line items: {len(p.get('line_items', []))}")

    jobs = await db.production_jobs.find({}).to_list(500)
    print(f"\n=== ALL JOBS ({len(jobs)}) ===")
    real_jobs = [j for j in jobs if not str(j.get("po_number", "")).startswith(("TEST", "DISP-TEST", "WRKTEST", "CARDTEST", "RFPTEST"))]
    print(f"Real business jobs: {len(real_jobs)} / {len(jobs)}")
    for j in real_jobs[:10]:
        print(f"  Job #{j.get('job_number')} | PO: {j.get('po_number')} | Style: {j.get('style_code')} | Stage: {j.get('stage')} | Qty: {j.get('quantity')} | Comp: {j.get('completed_qty')}")

if __name__ == "__main__":
    asyncio.run(inspect_real_data())
