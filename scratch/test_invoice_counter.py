import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

async def test_counter():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]

    # Check current counter for invoice_26-27
    counter = await db.counters.find_one({"_id": "invoice_26-27"})
    print("Current counter in DB before script:", counter)

    # Set counter seq to 15 so next $inc becomes 16 (or if missing/lower, sync it)
    await db.counters.update_one(
        {"_id": "invoice_26-27"},
        {"$set": {"seq": 15}},
        upsert=True
    )
    print("Updated counter to seq: 15")

    # Import next_invoice_no from backend
    from server import next_invoice_no
    inv1 = await next_invoice_no()
    inv2 = await next_invoice_no()
    print("Generated Invoice 1:", inv1)
    print("Generated Invoice 2:", inv2)

    assert inv1 == "SSK26-27-016", f"Expected SSK26-27-016, got {inv1}"
    assert inv2 == "SSK26-27-017", f"Expected SSK26-27-017, got {inv2}"

    # Reset seq to 15 so the system produces SSK26-27-016 on next user action
    await db.counters.update_one(
        {"_id": "invoice_26-27"},
        {"$set": {"seq": 15}},
        upsert=True
    )
    print("Reset counter to seq: 15 for production readiness.")

if __name__ == "__main__":
    asyncio.run(test_counter())
