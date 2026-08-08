import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def print_jobs():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    jobs = await db.production_jobs.find({}).to_list(100)
    for i, j in enumerate(jobs):
        print(f"--- Job {i+1} ---")
        for k, v in j.items():
            if "error" in k.lower() or "qty" in k.lower() or "name" in str(v).lower():
                print(f"  {k}: {v}")
        print(f"  PO: {j.get('po_number')}, Style: {j.get('style_code')}, Color: {j.get('color')}, Stage: {j.get('stage')}")

if __name__ == "__main__":
    asyncio.run(print_jobs())
