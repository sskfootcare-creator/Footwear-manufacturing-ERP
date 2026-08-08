import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
db_name = os.environ.get("DB_NAME", "ssk_footwear_dev")

async def inspect():
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    invs = await db.invoices.find({}, {"file_b64": 0}).to_list(10)
    print("INVOICES COUNT:", await db.invoices.count_documents({}))
    if invs:
        print("SAMPLE INVOICE:", list(invs[0].keys()))
        print("SAMPLE INVOICE LINE ITEMS:", invs[0].get("line_items_snapshot") or invs[0].get("line_items"))

    pos = await db.pos.find({}).to_list(10)
    print("POS COUNT:", await db.pos.count_documents({}))
    if pos:
        print("SAMPLE PO:", list(pos[0].keys()))
        print("SAMPLE PO LINES:", pos[0].get("line_items"))

    styles = await db.styles.find({}).to_list(10)
    print("STYLES COUNT:", await db.styles.count_documents({}))

asyncio.run(inspect())
