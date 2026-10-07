import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import httpx
from bson import ObjectId
import motor.motor_asyncio
from auth import create_access_token
import server

async def main():
    db = server.db
    u = await db.users.find_one({"role": "admin"})
    uid = str(u["_id"]) if u else str(ObjectId())
    token = create_access_token(uid, "admin@sskfootcare.com", "admin")
    transport = httpx.ASGITransport(app=server.app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Consolidated Ledger
        res = await client.get("/api/investors/ledger", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        print("================================================================================")
        print("                      CONSOLIDATED INVESTOR LEDGER                              ")
        print("================================================================================")
        print(f"Title:                           {data.get('statement_title')}")
        print(f"Account:                         {data.get('account_holder')}")
        print(f"Statement Date:                  {data.get('statement_date')}")
        print(f"Total Capital Invested (Credits): Rs {data.get('total_credit_inflow'):,.2f}")
        print(f"Total Principal Repaid (Debits):  Rs {data.get('total_principal_repaid'):,.2f}")
        print(f"Total Margin Yields Disbursed:    Rs {data.get('total_margin_paid'):,.2f}")
        print(f"Total Cash Disbursed from Bank:   Rs {data.get('total_cash_outflow'):,.2f}")
        print(f"Net Outstanding Balance:          Rs {data.get('closing_balance'):,.2f}")
        print(f"Total Ledger Entries:             {data.get('transactions_count')}")

        # Check Active Advances in DB
        valid_inv_ids = {str(i["_id"]) for i in await db.investors.find().to_list(100)}
        active_advs = await db.investor_advances.find({"status": "active", "investor_id": {"$in": list(valid_inv_ids)}}).to_list(100)
        active_bal = sum(float(a["amount"]) for a in active_advs)
        print(f"Active Advances in DB:            {len(active_advs)} advances (Total: Rs {active_bal:,.2f})")
        print(f">> RECONCILIATION MATCH:          {'PERFECT MATCH (100%)' if round(data.get('closing_balance'), 2) == round(active_bal, 2) else 'MISMATCH'}")

        # 2. Individual Investor Ledgers
        investors = await db.investors.find({"name": {"$regex": "Batch Capital"}}).to_list(10)
        for inv in investors:
            iid = str(inv["_id"])
            res_inv = await client.get(f"/api/investors/ledger?investor_id={iid}", headers={"Authorization": f"Bearer {token}"})
            d = res_inv.json()
            print("\n--------------------------------------------------------------------------------")
            print(f"INVESTOR: {inv.get('name')} (ID: {iid[-8:]})")
            print("--------------------------------------------------------------------------------")
            print(f"  * Total Capital Invested:  Rs {d.get('total_credit_inflow'):,.2f}")
            print(f"  * Principal Repaid:        Rs {d.get('total_principal_repaid'):,.2f}")
            print(f"  * Margin Disbursed:        Rs {d.get('total_margin_paid'):,.2f}")
            print(f"  * Net Outstanding Balance: Rs {d.get('closing_balance'):,.2f}")
            print(f"  * Entries Count:           {d.get('transactions_count')}")
            print("\n  Date       | Voucher      | Particulars & Purpose                     | Debit (Rs)   | Margin (Rs)| Credit (Rs)  | Balance (Rs) | Status")
            print("  " + "-" * 115)
            for t in reversed(d.get("transactions", [])): # Show chronological
                v = t.get("voucher_no")
                dt = t.get("date")
                narr = (t.get("narration") or "")[:42]
                deb = t.get("debit", 0)
                marg = t.get("margin_paid", 0)
                cred = t.get("credit", 0)
                bal = t.get("running_balance", 0)
                st = t.get("status")
                print(f"  {dt} | {v:<12} | {narr:<42} | Rs {deb:>9,.2f} | Rs {marg:>7,.2f} | Rs {cred:>9,.2f} | Rs {bal:>9,.2f} | {st}")

if __name__ == "__main__":
    asyncio.run(main())
