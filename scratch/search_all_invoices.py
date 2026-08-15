import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def search_all():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    
    colls = await db.list_collection_names()
    print("Collections:", colls)
    
    for coll_name in colls:
        coll = db[coll_name]
        # Search for any doc containing SSK26-27
        docs = await coll.find({"$or": [
            {"invoice_no": {"$regex": "SSK26-27"}},
            {"invoice_id": {"$exists": True}}
        ]}).to_list(100)
        if docs:
            print(f"\nIn collection '{coll_name}' ({len(docs)} matching):")
            for d in docs:
                print(f"  _id: {d.get('_id')} | invoice_no: {d.get('invoice_no')} | invoice_id: {d.get('invoice_id')}")

if __name__ == "__main__":
    asyncio.run(search_all())
