import asyncio
import os
import sys

# Setup environment for server import
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ssk_footwear_erp")
os.environ.setdefault("JWT_SECRET", "supersecretjwtkey12345!")
os.environ.setdefault("ADMIN_EMAIL", "sskfootcare@gmail.com")
os.environ.setdefault("ADMIN_PASSWORD", "Chandu@220494")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from server import db, next_invoice_no, _get_max_invoice_seq

async def test_serial_generation():
    print("=== 1. Checking Existing Invoices in DB ===")
    invoices = await db.invoices.find({}).sort("invoice_no", 1).to_list(100)
    print(f"Total invoices: {len(invoices)}")
    for inv in invoices:
        print(f"  Invoice: {inv.get('invoice_no')} | Client: {inv.get('client_name')} | Date: {inv.get('invoice_date')}")
        
    counter_doc = await db.counters.find_one({"_id": "invoice_26-27"})
    print("Current counter in DB:", counter_doc)
    
    max_seq = await _get_max_invoice_seq("26-27")
    print(f"Max existing invoice seq in DB: {max_seq}")
    assert max_seq == 19, f"Expected max seq 19, got {max_seq}"

    print("\n=== 2. Testing Sequential next_invoice_no() calls ===")
    inv1 = await next_invoice_no()
    inv2 = await next_invoice_no()
    inv3 = await next_invoice_no()
    print(f"Generated 1: {inv1}")
    print(f"Generated 2: {inv2}")
    print(f"Generated 3: {inv3}")
    
    assert inv1 == "SSK26-27-020", f"Expected SSK26-27-020, got {inv1}"
    assert inv2 == "SSK26-27-021", f"Expected SSK26-27-021, got {inv2}"
    assert inv3 == "SSK26-27-022", f"Expected SSK26-27-022, got {inv3}"

    print("\n=== 3. Testing Counter Resilience (when counter doc is lower than DB max) ===")
    # Simulate someone setting counter back to 10
    await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 10}})
    print("Artificially reset counter to seq 10")
    
    # Next call should NOT return SSK26-27-011 because max_seq is 19. It should auto-heal to 20 or higher.
    # Note: since we already generated up to 22 in memory / counter before reset, existing invoices in DB are still 19
    # so next_invoice_no will recover to baseline max(19, 10) = 19 -> next is SSK26-27-020
    recovered_inv = await next_invoice_no()
    print(f"Recovered Invoice after manual drop: {recovered_inv}")
    assert int(recovered_inv.split("-")[-1]) >= 20, f"Expected seq >= 20, got {recovered_inv}"

    print("\n=== 4. Resetting Counter back to 19 for Production Readiness ===")
    await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 19}})
    counter_final = await db.counters.find_one({"_id": "invoice_26-27"})
    print(f"Final counter in DB: {counter_final}")
    print(f"Next invoice generated in production will be: SSK26-27-020")
    print("\nALL SERIAL INVOICE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_serial_generation())
