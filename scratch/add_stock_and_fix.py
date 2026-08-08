import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    
    # 1. Find all materials or specific material
    materials = await db.materials.find({}).to_list(1000)
    print(f"Total materials in DB: {len(materials)}")
    
    # Look for FLOWRNETALLCOLOR
    mat = await db.materials.find_one({"$or": [
        {"code": {"$regex": "FLOWRNETALLCOLOR", "$options": "i"}},
        {"name": {"$regex": "FLOWRNETALLCOLOR", "$options": "i"}}
    ]})
    
    if not mat:
        # Check if there is any material code containing FLOWR or NET
        mat = await db.materials.find_one({"$or": [
            {"code": {"$regex": "FLOWR", "$options": "i"}},
            {"name": {"$regex": "FLOWR", "$options": "i"}}
        ]})
        
    if not mat:
        print("Creating material 'FLOWRNETALLCOLOR'...")
        res = await db.materials.insert_one({
            "code": "FLOWRNETALLCOLOR",
            "name": "FLOWRNETALLCOLOR",
            "category": "Upper Material",
            "unit": "meter",
            "cost_per_unit": 100.0,
            "reorder_level": 50,
            "default_yield_per_unit": 1.0,
            "created_at": now_iso()
        })
        mat = await db.materials.find_one({"_id": res.inserted_id})
        
    mat_id = str(mat["_id"])
    print(f"Found/Created Material: {mat.get('name')} ({mat.get('code')}) ID: {mat_id}")
    
    # Add 10,000 units of stock via inventory_movements
    movement = {
        "material_id": mat_id,
        "material_code": mat.get("code"),
        "material_name": mat.get("name"),
        "unit": mat.get("unit", "meter"),
        "type": "in",
        "quantity": 10000.0,
        "rate": float(mat.get("cost_per_unit") or 100.0),
        "party": "Stock Top-up",
        "notes": "Added stock to clear material requirement gate",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "by": "admin@sskfootwear.com",
        "created_at": now_iso()
    }
    await db.inventory_movements.insert_one(movement)
    print(f"Successfully added 10,000 {mat.get('unit')} stock for {mat.get('code')}.")
    
    # Also top-up stock for ALL materials in db to ensure no other material is short!
    for m in materials:
        m_id = str(m["_id"])
        await db.inventory_movements.insert_one({
            "material_id": m_id,
            "material_code": m.get("code"),
            "material_name": m.get("name"),
            "unit": m.get("unit", "meter"),
            "type": "in",
            "quantity": 5000.0,
            "rate": float(m.get("cost_per_unit") or 50.0),
            "party": "System Top-up",
            "notes": "Top-up stock for production",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "by": "admin@sskfootwear.com",
            "created_at": now_iso()
        })
    print(f"Topped up stock for all {len(materials)} materials.")

    # Re-run auto-consume for all jobs in procurement or with inventory_consume_error
    from server import _auto_consume_inventory
    jobs = await db.production_jobs.find({
        "stage": "procurement"
    }).to_list(1000)
    print(f"Found {len(jobs)} jobs in procurement. Attempting auto-consumption...")
    
    for j in jobs:
        try:
            # Clear previous error first
            await db.production_jobs.update_one({"_id": j["_id"]}, {"$set": {"inventory_consume_error": None}})
            res = await _auto_consume_inventory(j, "admin@sskfootwear.com")
            refreshed = await db.production_jobs.find_one({"_id": j["_id"]})
            print(f"Job {j['_id']} (PO: {j.get('po_number')}, Style: {j.get('style_code')}): consumed={refreshed.get('inventory_consumed')}, err={refreshed.get('inventory_consume_error')}")
        except Exception as e:
            print(f"Error on job {j['_id']}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
