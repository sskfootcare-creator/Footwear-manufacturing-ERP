import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    
    jobs = await db.production_jobs.find({"inventory_consume_error": {"$ne": None}}).to_list(1000)
    print(f"Total jobs with non-null inventory_consume_error: {len(jobs)}")
    for j in jobs:
        print(f"Job {j['_id']} (PO: {j.get('po_number')}, Style: {j.get('style_code')}, Stage: {j.get('stage')}): '{j.get('inventory_consume_error')}'")

    # Clear 'qty' undefined errors
    qty_jobs = [j for j in jobs if "qty" in str(j.get("inventory_consume_error")).lower()]
    print(f"Jobs with 'qty' error: {len(qty_jobs)}")
    for j in qty_jobs:
        await db.production_jobs.update_one({"_id": j["_id"]}, {"$unset": {"inventory_consume_error": ""}})
        print(f"Cleared error for job {j['_id']}")

if __name__ == "__main__":
    asyncio.run(inspect())
