import asyncio
from datetime import datetime, timezone, timedelta
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

BASE_URL = "http://localhost:8000/api"

async def setup_demo_data():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]

    # Fetch PO 2220011455 if it exists
    po = await db.pos.find_one({"po_number": "2220011455"})
    po_id = str(po["_id"]) if po else "demo_po_1"
    po_num = po.get("po_number", "2220011455") if po else "2220011455"
    client_name_1 = po.get("client_name", "SIYARAM SILK MILLS LTD.") if po else "SIYARAM SILK MILLS LTD."

    # Bank account
    bank_acc = await db.bank_accounts.find_one({"name": "B2B AC"})
    if not bank_acc:
        bank_acc = await db.bank_accounts.find_one({})
    bank_id = str(bank_acc["_id"]) if bank_acc else None
    bank_name = (bank_acc.get("bank_name") or bank_acc.get("name")) if bank_acc else "HDFC Bank"

    # Clean previous demo invoices
    demo_inv_nos = ["SSK26-27-016", "SSK26-27-017", "SSK26-27-018"]
    await db.payments.delete_many({"reference": {"$regex": "^DEMO-"}})
    await db.invoices.delete_many({"invoice_no": {"$in": demo_inv_nos}})

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    due_str_1 = (now.date() + timedelta(days=30)).isoformat()
    due_str_2 = (now.date() + timedelta(days=45)).isoformat()
    due_str_3 = (now.date() - timedelta(days=5)).isoformat() # Overdue demo

    demo_invoices = [
        {
            "invoice_no": "SSK26-27-016",
            "po_id": po_id,
            "po_ids": [po_id],
            "po_number": po_num,
            "po_numbers": [po_num],
            "client_name": client_name_1,
            "invoice_date": today_str,
            "grn_date": today_str,
            "grn_no": "GRN-2026-088",
            "due_date": due_str_1,
            "payment_terms_days": 30,
            "subtotal": 50000.0,
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "cgst_amount": 3000.0,
            "sgst_amount": 3000.0,
            "igst_rate": 0.0,
            "igst_amount": 0.0,
            "grand_total": 56000.0,
            "net_amount": 56000.0,
            "grn_adjustment": 0.0,
            "total_pairs": 120,
            "line_items_snapshot": [
                {
                    "style_code": "SSK-FORMAL-01",
                    "color": "Black",
                    "size": "8",
                    "quantity": 60,
                    "unit_price": 416.67,
                    "amount": 25000.0,
                },
                {
                    "style_code": "SSK-FORMAL-01",
                    "color": "Brown",
                    "size": "9",
                    "quantity": 60,
                    "unit_price": 416.67,
                    "amount": 25000.0,
                },
            ],
            "created_at": now.isoformat(),
        },
        {
            "invoice_no": "SSK26-27-017",
            "po_id": "",
            "po_ids": [],
            "po_number": "PO-BATA-2026-90",
            "po_numbers": ["PO-BATA-2026-90"],
            "client_name": "Bata India Ltd.",
            "invoice_date": today_str,
            "grn_date": today_str,
            "grn_no": "GRN-2026-092",
            "due_date": due_str_2,
            "payment_terms_days": 45,
            "subtotal": 75000.0,
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "cgst_amount": 4500.0,
            "sgst_amount": 4500.0,
            "igst_rate": 0.0,
            "igst_amount": 0.0,
            "grand_total": 84000.0,
            "net_amount": 84000.0,
            "grn_adjustment": 0.0,
            "total_pairs": 200,
            "created_at": now.isoformat(),
        },
        {
            "invoice_no": "SSK26-27-018",
            "po_id": "",
            "po_ids": [],
            "po_number": "PO-METRO-401",
            "po_numbers": ["PO-METRO-401"],
            "client_name": "Metro Brands Ltd.",
            "invoice_date": (now.date() - timedelta(days=40)).isoformat(),
            "grn_date": (now.date() - timedelta(days=40)).isoformat(),
            "grn_no": "GRN-2026-060",
            "due_date": due_str_3,
            "payment_terms_days": 30,
            "subtotal": 35000.0,
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "cgst_amount": 2100.0,
            "sgst_amount": 2100.0,
            "igst_rate": 0.0,
            "igst_amount": 0.0,
            "grand_total": 39200.0,
            "net_amount": 39200.0,
            "grn_adjustment": 0.0,
            "total_pairs": 80,
            "created_at": now.isoformat(),
        },
    ]

    inserted_ids = []
    for inv in demo_invoices:
        res = await db.invoices.insert_one(inv)
        inserted_ids.append((str(res.inserted_id), inv["invoice_no"], inv["client_name"], inv["grand_total"]))

    # Also make sure clients exist in db.clients for client ledger
    for c_name in [client_name_1, "Bata India Ltd.", "Metro Brands Ltd."]:
        c_exist = await db.clients.find_one({"name": c_name})
        if not c_exist:
            await db.clients.insert_one({
                "name": c_name,
                "created_at": now.isoformat(),
            })

    return inserted_ids, bank_id, bank_name, client_name_1

def run_test():
    inserted_ids, bank_id, bank_name, client_name_1 = asyncio.run(setup_demo_data())
    print("================================================================================")
    print("STEP 1: CREATED DEMO INVOICES IN ERP")
    print("================================================================================")
    for iid, inv_no, cl, total in inserted_ids:
        print(f" - ID: {iid} | Invoice: {inv_no} | Client: {cl} | Grand Total: INR {total:,.2f}")
    
    session = requests.Session()
    # Login
    login_resp = session.post(f"{BASE_URL}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json().get("token") or login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # STEP 2: Verify in Invoices section via API (GET /api/invoices)
    print("\n================================================================================")
    print("STEP 2: VERIFY INVOICES SECTION (/api/invoices)")
    print("================================================================================")
    r_invoices = session.get(f"{BASE_URL}/invoices", headers=headers)
    assert r_invoices.status_code == 200, f"Failed to list invoices: {r_invoices.text}"
    invoices = r_invoices.json()
    demo_in_erp = [inv for inv in invoices if inv.get("invoice_no") in ["SSK26-27-016", "SSK26-27-017", "SSK26-27-018"]]
    print(f"Found {len(demo_in_erp)} demo invoices in Invoices section:")
    for inv in demo_in_erp:
        print(f" -> {inv.get('invoice_no')}: Client='{inv.get('client_name')}', Net=INR {inv.get('net_amount'):,.2f}, Received=INR {inv.get('received_amount'):,.2f}, Outstanding=INR {inv.get('outstanding'):,.2f}, Status='{inv.get('status')}'")

    inv1_id = inserted_ids[0][0]
    inv1_no = inserted_ids[0][1]

    # STEP 3: Record Payment 1 against Demo Invoice 1 (Partial payment: INR 30,000)
    print("\n================================================================================")
    print(f"STEP 3: RECORD PAYMENT 1 (PARTIAL) AGAINST INVOICE {inv1_no}")
    print("================================================================================")
    pay_payload_1 = {
        "invoice_ids": [inv1_id],
        "amount": 30000.0,
        "payment_date": datetime.now().date().isoformat(),
        "mode": "NEFT",
        "reference": "DEMO-UTR-9911001",
        "bank": bank_name,
        "bank_account_id": bank_id,
        "notes": "Partial installment payment from Siyaram",
    }
    r_pay1 = session.post(f"{BASE_URL}/payments", json=pay_payload_1, headers=headers)
    print("POST /api/payments Status:", r_pay1.status_code)
    assert r_pay1.status_code in [200, 201], f"Payment failed: {r_pay1.text}"
    pay1_data = r_pay1.json()
    print(f"Payment Created: {pay1_data.get('payment_no')}")
    print(f" - Amount: INR {pay1_data.get('amount'):,.2f}")
    print(f" - Allocations: {pay1_data.get('allocations')}")
    print(f" - Reference: {pay1_data.get('reference')}")
    print(f" - Bank Account: {pay1_data.get('bank')} (ID: {pay1_data.get('bank_account_id')})")

    # STEP 4: Verify Invoice State after Payment 1
    print("\n================================================================================")
    print(f"STEP 4: VERIFY INVOICE {inv1_no} STATE AFTER PAYMENT 1")
    print("================================================================================")
    r_inv1_after_p1 = session.get(f"{BASE_URL}/invoices/{inv1_id}", headers=headers)
    inv1_data_p1 = r_inv1_after_p1.json()
    print(f"Invoice {inv1_no}:")
    print(f" - Net Amount: INR {inv1_data_p1.get('net_amount'):,.2f}")
    print(f" - Received: INR {inv1_data_p1.get('received_amount'):,.2f}")
    print(f" - Outstanding: INR {inv1_data_p1.get('outstanding'):,.2f}")
    print(f" - Status: '{inv1_data_p1.get('status')}'")
    print(f" - Attached Payments ({len(inv1_data_p1.get('payments', []))}):")
    for p in inv1_data_p1.get("payments", []):
        print(f"    * {p.get('payment_no')} | {p.get('payment_date')} | INR {p.get('amount'):,.2f} | Mode: {p.get('mode')} | Ref: {p.get('reference')}")

    assert inv1_data_p1.get("status") == "partial", f"Expected status 'partial', got {inv1_data_p1.get('status')}"
    assert inv1_data_p1.get("received_amount") == 30000.0, f"Expected received 30000, got {inv1_data_p1.get('received_amount')}"
    assert inv1_data_p1.get("outstanding") == 26000.0, f"Expected outstanding 26000, got {inv1_data_p1.get('outstanding')}"

    # STEP 5: Record Payment 2 (Settling remaining INR 26,000)
    print("\n================================================================================")
    print(f"STEP 5: RECORD PAYMENT 2 (FINAL SETTLEMENT) AGAINST INVOICE {inv1_no}")
    print("================================================================================")
    pay_payload_2 = {
        "invoice_ids": [inv1_id],
        "amount": 26000.0,
        "payment_date": datetime.now().date().isoformat(),
        "mode": "RTGS",
        "reference": "DEMO-UTR-9911002",
        "bank": bank_name,
        "bank_account_id": bank_id,
        "notes": "Full balance clearance payment",
    }
    r_pay2 = session.post(f"{BASE_URL}/payments", json=pay_payload_2, headers=headers)
    print("POST /api/payments Status:", r_pay2.status_code)
    assert r_pay2.status_code in [200, 201], f"Payment 2 failed: {r_pay2.text}"
    pay2_data = r_pay2.json()
    print(f"Payment Created: {pay2_data.get('payment_no')}")
    print(f" - Amount: INR {pay2_data.get('amount'):,.2f}")
    print(f" - Allocations: {pay2_data.get('allocations')}")

    # STEP 6: Verify Invoice State after Payment 2 (Fully Settled)
    print("\n================================================================================")
    print(f"STEP 6: VERIFY INVOICE {inv1_no} STATE AFTER PAYMENT 2 (FULLY PAID)")
    print("================================================================================")
    r_inv1_after_p2 = session.get(f"{BASE_URL}/invoices/{inv1_id}", headers=headers)
    inv1_data_p2 = r_inv1_after_p2.json()
    print(f"Invoice {inv1_no}:")
    print(f" - Net Amount: INR {inv1_data_p2.get('net_amount'):,.2f}")
    print(f" - Received: INR {inv1_data_p2.get('received_amount'):,.2f}")
    print(f" - Outstanding: INR {inv1_data_p2.get('outstanding'):,.2f}")
    print(f" - Status: '{inv1_data_p2.get('status')}'")
    assert inv1_data_p2.get("status") == "paid", f"Expected status 'paid', got {inv1_data_p2.get('status')}"
    assert inv1_data_p2.get("outstanding") == 0.0, f"Expected outstanding 0, got {inv1_data_p2.get('outstanding')}"
    assert inv1_data_p2.get("received_amount") == 56000.0, f"Expected received 56000, got {inv1_data_p2.get('received_amount')}"

    # STEP 7: Verify Payments Ledger (/api/payments)
    print("\n================================================================================")
    print("STEP 7: VERIFY PAYMENTS LIST IN ERP (/api/payments)")
    print("================================================================================")
    r_pays = session.get(f"{BASE_URL}/payments?invoice_id={inv1_id}", headers=headers)
    pays_for_inv = r_pays.json()
    print(f"Payments recorded for Invoice {inv1_no} ({len(pays_for_inv)}):")
    for p in pays_for_inv:
        print(f" -> {p.get('payment_no')}: INR {p.get('amount'):,.2f} via {p.get('mode')} (Ref: {p.get('reference')})")

    # STEP 8: Verify Client Ledger reflects Invoice Debit and Payment Credits
    print("\n================================================================================")
    print(f"STEP 8: VERIFY CLIENT LEDGER FOR '{client_name_1}' (/api/clients/{client_name_1}/ledger)")
    print("================================================================================")
    r_ledger = session.get(f"{BASE_URL}/clients/{client_name_1}/ledger", headers=headers)
    print("Client Ledger Status:", r_ledger.status_code)
    if r_ledger.status_code == 200:
        ledger_data = r_ledger.json()
        entries = ledger_data.get("ledger") or ledger_data.get("transactions", [])
        print(f"Ledger entries for {client_name_1}: {len(entries)}")
        for e in entries:
            print(f" -> {e.get('date')} | Type: {e.get('vch_type')} | Vch No: {e.get('vch_no')} | Debit: INR {e.get('debit', 0):,.2f} | Credit: INR {e.get('credit', 0):,.2f} | Particulars: {e.get('particulars')}")
        print(f"Summary: Total Invoiced=INR {ledger_data.get('total_invoiced', 0):,.2f} | Total Paid=INR {ledger_data.get('total_received', 0):,.2f} | Closing Balance=INR {ledger_data.get('closing_balance', 0):,.2f} ({ledger_data.get('balance_type', '')})")

    print("\n>>> ALL ERP INVOICE & PAYMENT FLOW CHECKS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_test()
