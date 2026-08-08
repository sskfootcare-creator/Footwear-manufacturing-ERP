import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def list_all():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    print("Databases:", dbs)
    for db_name in dbs:
        if db_name in ["admin", "config", "local"]: continue
        db = client[db_name]
        cols = await db.list_collection_names()
        print(f"\nDatabase '{db_name}' collections:", cols)
        if "production_jobs" in cols:
            jobs = await db.production_jobs.find({}).to_list(1000)
            print(f"Total jobs in {db_name}.production_jobs: {len(jobs)}")
            for j in jobs:
                if j.get("inventory_consume_error"):
                    print(f"  -> Job {j['_id']} error: {j.get('inventory_consume_error')}")

if __name__ == "__main__":
    asyncio.run(list_all())
