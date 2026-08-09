import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def init_counter():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]

    # Set counter seq to 15 so next atomic $inc generates SSK26-27-016
    res = await db.counters.update_one(
        {"_id": "invoice_26-27"},
        {"$set": {"seq": 15}},
        upsert=True
    )
    print("SUCCESS: Set invoice_26-27 counter seq to 15 in database.")
    
    counter = await db.counters.find_one({"_id": "invoice_26-27"})
    print("Verified database counter state:", counter)

if __name__ == "__main__":
    asyncio.run(init_counter())
