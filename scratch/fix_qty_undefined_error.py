import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add backend directory to sys.path to import server helpers if needed
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

async def fix():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footcare"]
    
    # Find all jobs with inventory_consume_error containing 'qty'
    jobs = await db.production_jobs.find({
        "inventory_consume_error": {"$regex": "qty", "$options": "i"}
    }).to_list(1000)
    
    print(f"Found {len(jobs)} jobs with 'qty' undefined error in inventory_consume_error.")
    
    for job in jobs:
        print(f"Clearing error for job ID: {job['_id']} (PO: {job.get('po_number')}, Style: {job.get('style_code')})")
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$unset": {"inventory_consume_error": ""}}
        )
    
    # Also check if any job in a stage past procurement needs auto consume re-run
    from server import _auto_consume_inventory
    jobs_to_retry = await db.production_jobs.find({
        "stage": {"$ne": "procurement"},
        "inventory_consumed": {"$ne": True}
    }).to_list(1000)
    
    print(f"Retrying auto-consume for {len(jobs_to_retry)} jobs past procurement...")
    for j in jobs_to_retry:
        try:
            res = await _auto_consume_inventory(j, "system_fix@sskfootwear.com")
            print(f"Job {j['_id']} auto-consume result: {res}")
        except Exception as e:
            print(f"Error retrying job {j['_id']}: {e}")

if __name__ == "__main__":
    asyncio.run(fix())
