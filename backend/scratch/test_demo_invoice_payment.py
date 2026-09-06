import asyncio
import json
from datetime import datetime, timezone
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = "http://localhost:8000/api"

async def setup_demo_invoice():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]

    # Clean up any existing demo invoice & its payments
    existing = await db.invoices.find_one({"invoice_no": "SSK26-27-DEMO-001"})
    if existing:
        await db.payments.delete_many({"invoice_ids": str(existing["_id"])})
        await db.invoices.delete_one({"_id": existing["_id"]})

    bank_acc = await db.bank_accounts.find_one({})
    bank_acc_id = str(bank_acc["_id"]) if bank_acc else None

    doc = {
        "invoice_no": "SSK26-27-DEMO-001",
        "client_name": "Metro Footwear Brands",
        "invoice_date": "2026-09-06",
        "due_date": "2026-10-21",
        "payment_terms_days": 45,
        "subtotal": 38135.59,
        "total_quantity": 100,
        "cgst_rate": 9.0,
        "sgst_rate": 9.0,
        "cgst_amount": 3432.20,
        "sgst_amount": 3432.20,
        "igst_rate": 0.0,
        "igst_amount": 0.0,
        "grand_total": 45000.0,
        "net_amount": 45000.0,
        "grn_adjustment": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.invoices.insert_one(doc)
    print(f"Created demo invoice {doc['invoice_no']} (ID: {res.inserted_id}) for INR {doc['grand_total']:.2f}")
    return str(res.inserted_id), bank_acc_id


def main():
    inv_id, bank_id = asyncio.run(setup_demo_invoice())

    # 1. Login to ERP
    session = requests.Session()
    login_res = session.post(
        f"{BASE_URL}/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    print("Admin Login Status:", login_res.status_code)
    login_data = login_res.json()
    token = login_data.get("token") or login_data.get("access_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # 2. Check invoice before any payment
    r_before = session.get(f"{BASE_URL}/invoices/{inv_id}", headers=headers)
    print("\n--- 1. Invoice State BEFORE Payment ---")
    inv_data = r_before.json()
    print("Invoice No:", inv_data.get("invoice_no"))
    print("Client:", inv_data.get("client_name"))
    print("Net Amount: INR", inv_data.get("net_amount"))
    print("Received Amount: INR", inv_data.get("received_amount"))
    print("Outstanding: INR", inv_data.get("outstanding"))
    print("Status:", inv_data.get("status"))
    print("Payments Attached:", len(inv_data.get("payments", [])))

    # 3. Record Payment 1 (Partial Payment of INR 25,000)
    pay_payload_1 = {
        "invoice_ids": [inv_id],
        "amount": 25000.0,
        "payment_date": "2026-09-06",
        "mode": "NEFT",
        "reference": "UTR-DEMO-998877",
        "bank_account_id": bank_id,
        "notes": "First partial client installment via NEFT",
    }
    r_pay1 = session.post(f"{BASE_URL}/payments", json=pay_payload_1, headers=headers)
    print("\n--- 2. Recording Payment 1 (INR 25,000.00) ---")
    print("Response Status Code:", r_pay1.status_code)
    pay1_data = r_pay1.json()
    print("Recorded Payment No:", pay1_data.get("payment_no"))
    print("Payment Amount: INR", pay1_data.get("amount"))
    print("Allocations:", pay1_data.get("allocations"))
    print("Bank Account ID:", pay1_data.get("bank_account_id"))
    print("Reference:", pay1_data.get("reference"))

    # 4. Verify invoice state after Payment 1
    r_after1 = session.get(f"{BASE_URL}/invoices/{inv_id}", headers=headers)
    print("\n--- 3. Invoice State AFTER Payment 1 ---")
    inv_data1 = r_after1.json()
    print("Received Amount: INR", inv_data1.get("received_amount"))
    print("Outstanding: INR", inv_data1.get("outstanding"))
    print("Status:", inv_data1.get("status"))
    print("Payments Attached:", len(inv_data1.get("payments", [])))
    for p in inv_data1.get("payments", []):
        print(f"  -> Payment {p.get('payment_no')}: INR {p.get('amount')} ({p.get('mode')}) Ref: {p.get('reference')}")

    # 5. Record Payment 2 (Settlement Payment of remaining INR 20,000)
    pay_payload_2 = {
        "invoice_ids": [inv_id],
        "amount": 20000.0,
        "payment_date": "2026-09-06",
        "mode": "RTGS",
        "reference": "UTR-DEMO-998878",
        "bank_account_id": bank_id,
        "notes": "Final settlement payment",
    }
    r_pay2 = session.post(f"{BASE_URL}/payments", json=pay_payload_2, headers=headers)
    print("\n--- 4. Recording Payment 2 (INR 20,000.00) ---")
    print("Response Status Code:", r_pay2.status_code)
    pay2_data = r_pay2.json()
    print("Recorded Payment No:", pay2_data.get("payment_no"))
    print("Payment Amount: INR", pay2_data.get("amount"))
    print("Allocations:", pay2_data.get("allocations"))

    # 6. Verify invoice state after Payment 2
    r_after2 = session.get(f"{BASE_URL}/invoices/{inv_id}", headers=headers)
    print("\n--- 5. Invoice State AFTER Payment 2 (Fully Settled) ---")
    inv_data2 = r_after2.json()
    print("Received Amount: INR", inv_data2.get("received_amount"))
    print("Outstanding: INR", inv_data2.get("outstanding"))
    print("Status:", inv_data2.get("status"))
    print("Payments Attached:", len(inv_data2.get("payments", [])))
    for p in inv_data2.get("payments", []):
        print(f"  -> Payment {p.get('payment_no')}: INR {p.get('amount')} ({p.get('mode')}) Ref: {p.get('reference')}")

    # 7. Verify in payments ledger list (/api/payments)
    r_pay_list = session.get(f"{BASE_URL}/payments?invoice_id={inv_id}", headers=headers)
    print("\n--- 6. Verification in Payments Ledger (/api/payments) ---")
    print("Payments in list:", len(r_pay_list.json()))
    for p in r_pay_list.json():
        print(f"  -> {p.get('payment_no')}: INR {p.get('amount')} by {p.get('by')}, Ref: {p.get('reference')}")

    # 8. Verify in invoices list (/api/invoices)
    r_inv_list = session.get(f"{BASE_URL}/invoices", headers=headers)
    matching = [inv for inv in r_inv_list.json() if inv.get("id") == inv_id]
    print("\n--- 7. Verification in Invoices List (/api/invoices) ---")
    if matching:
        m = matching[0]
        print(f"Invoice {m.get('invoice_no')}: Status='{m.get('status')}', Received=INR {m.get('received_amount')}, Outstanding=INR {m.get('outstanding')}")

if __name__ == "__main__":
    main()
