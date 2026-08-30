"""Tests for Bank Accounts, Bank Statement Lines, and Payment/Expense/Settlement model integration."""

import pytest
from io import BytesIO
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException

from models.banking import (
    BankAccountIn,
    BankAccountUpdate,
    BankStatementLineIn,
    BankStatementLineUpdate,
    MatchedTo,
)
from models.vendors import PaymentIn
from models.expenses import ExpenseIn, ExpenseUpdate, RecurringExpenseIn
from models.online_reconciliation import SettlementImportIn, DailyPaymentRow, NonOrderDeductionRow
from routes.banking import (
    list_bank_accounts,
    create_bank_account,
    get_bank_account,
    update_bank_account,
    delete_bank_account,
    list_statement_lines,
    create_statement_lines,
    match_statement_line,
)


def test_bank_account_models_validation():
    """Verify BankAccountIn validation for online_channel and b2b_client accounts."""
    hdfc = BankAccountIn(
        name="HDFC - Online",
        bank_name="HDFC",
        account_number_last4="4321",
        account_type="online_channel",
        opening_balance=150000.50,
        opening_balance_date="2026-04-01",
        active=True,
    )
    assert hdfc.name == "HDFC - Online"
    assert hdfc.bank_name == "HDFC"
    assert hdfc.account_type == "online_channel"
    assert hdfc.opening_balance == 150000.50

    uco = BankAccountIn(
        name="UCO Bank - Offline",
        bank_name="UCO Bank",
        account_number_last4="8765",
        account_type="b2b_client",
        opening_balance=50000.0,
        opening_balance_date="2026-04-01",
        active=True,
    )
    assert uco.name == "UCO Bank - Offline"
    assert uco.account_type == "b2b_client"


def test_bank_statement_line_models_validation():
    """Verify BankStatementLineIn and MatchedTo structure validation."""
    line = BankStatementLineIn(
        bank_account_id=str(ObjectId()),
        date="2026-08-15",
        narration="NEFT-MYNTRA DESIGNS-SETTLEMENT-AUG15",
        reference_no="UTR987654321",
        debit_amount=0.0,
        credit_amount=45230.75,
        running_balance=195231.25,
        match_status="matched",
        matched_to=MatchedTo(type="settlement", ref_id="settle_123"),
    )
    assert line.credit_amount == 45230.75
    assert line.match_status == "matched"
    assert line.matched_to.type == "settlement"
    assert line.matched_to.ref_id == "settle_123"


def test_payment_and_expense_models_backward_compatibility():
    """Verify PaymentIn and ExpenseIn accept bank_account_id alongside legacy fields."""
    # Payment without bank_account_id (legacy)
    p1 = PaymentIn(
        amount=10000.0,
        payment_date="2026-08-20",
        mode="NEFT",
        bank="HDFC Bank",
    )
    assert p1.bank == "HDFC Bank"
    assert p1.bank_account_id is None

    # Payment with bank_account_id
    acc_id = str(ObjectId())
    p2 = PaymentIn(
        amount=25000.0,
        payment_date="2026-08-20",
        mode="RTGS",
        bank="HDFC Bank",
        bank_account_id=acc_id,
    )
    assert p2.bank_account_id == acc_id
    assert p2.bank == "HDFC Bank"

    # ExpenseIn with bank_account_id
    e1 = ExpenseIn(
        category="Rent & Utilities",
        amount=45000.0,
        date="2026-08-01",
        payee="Landlord Realty",
        bank_account_id=acc_id,
    )
    assert e1.bank_account_id == acc_id

    # Online reconciliation records
    s1 = SettlementImportIn(
        seller_order_id="ORD123",
        settled_amount_postpaid=1200.0,
        bank_account_id=acc_id,
    )
    assert s1.bank_account_id == acc_id


@pytest.mark.anyio
async def test_bank_accounts_crud_routes(monkeypatch):
    """Test full CRUD lifecycle of bank accounts via API route handlers."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    # 1. Create HDFC - Online
    acc_oid_1 = ObjectId()
    created_doc_1 = {
        "_id": acc_oid_1,
        "name": "HDFC - Online",
        "bank_name": "HDFC",
        "account_number_last4": "4321",
        "account_type": "online_channel",
        "opening_balance": 100000.0,
        "opening_balance_date": "2026-04-01",
        "active": True,
        "created_at": "2026-08-30T10:00:00Z",
        "created_by": "admin@sskfootcare.com",
    }
    mock_db.bank_accounts.insert_one = AsyncMock(return_value=MagicMock(inserted_id=acc_oid_1))
    mock_db.bank_accounts.find_one = AsyncMock(return_value=created_doc_1)

    req = MagicMock()
    payload = BankAccountIn(
        name="HDFC - Online",
        bank_name="HDFC",
        account_number_last4="4321",
        account_type="online_channel",
        opening_balance=100000.0,
        opening_balance_date="2026-04-01",
        active=True,
    )
    res = await create_bank_account(payload, req)
    assert res["id"] == str(acc_oid_1)
    assert res["name"] == "HDFC - Online"
    assert res["account_type"] == "online_channel"

    # 2. List accounts
    acc_oid_2 = ObjectId()
    created_doc_2 = {
        "_id": acc_oid_2,
        "name": "UCO Bank - Offline",
        "bank_name": "UCO Bank",
        "account_number_last4": "8765",
        "account_type": "b2b_client",
        "opening_balance": 50000.0,
        "opening_balance_date": "2026-04-01",
        "active": True,
    }
    
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[created_doc_1, created_doc_2])
    mock_db.bank_accounts.find = MagicMock(return_value=mock_cursor)

    accs = await list_bank_accounts(req, active=True)
    assert len(accs) == 2
    assert accs[0]["name"] == "HDFC - Online"
    assert accs[1]["name"] == "UCO Bank - Offline"

    # 3. Get single account
    mock_db.bank_accounts.find_one = AsyncMock(return_value=created_doc_1)
    single = await get_bank_account(str(acc_oid_1), req)
    assert single["id"] == str(acc_oid_1)
    assert single["bank_name"] == "HDFC"

    # 4. Update account
    updated_doc = dict(created_doc_1, opening_balance=125000.0)
    mock_db.bank_accounts.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db.bank_accounts.find_one = AsyncMock(return_value=updated_doc)

    patch_res = await update_bank_account(str(acc_oid_1), BankAccountUpdate(opening_balance=125000.0), req)
    assert patch_res["opening_balance"] == 125000.0

    # 5. Delete account (no statement lines -> hard delete)
    mock_db.bank_statement_lines.count_documents = AsyncMock(return_value=0)
    mock_db.bank_accounts.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    del_res = await delete_bank_account(str(acc_oid_1), req)
    assert del_res["ok"] is True
    assert "deleted" in del_res["message"]


@pytest.mark.anyio
async def test_bank_statement_lines_routes(monkeypatch):
    """Test importing and matching bank statement lines."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    req = MagicMock()
    acc_id = str(ObjectId())
    line_id = ObjectId()

    # 1. Insert statement line
    lines_in = [
        BankStatementLineIn(
            bank_account_id=acc_id,
            date="2026-08-25",
            narration="ACH CR-MYNTRA DESIGNS-AUG25",
            reference_no="ACH123456",
            credit_amount=78500.0,
            debit_amount=0.0,
            running_balance=250000.0,
            match_status="unmatched",
        )
    ]
    mock_db.bank_statement_lines.insert_many = AsyncMock(return_value=MagicMock(inserted_ids=[line_id]))
    create_res = await create_statement_lines(lines_in, req)
    assert create_res["ok"] is True
    assert create_res["inserted_count"] == 1

    # 2. Match statement line
    matched_doc = {
        "_id": line_id,
        "bank_account_id": acc_id,
        "date": "2026-08-25",
        "narration": "ACH CR-MYNTRA DESIGNS-AUG25",
        "reference_no": "ACH123456",
        "credit_amount": 78500.0,
        "debit_amount": 0.0,
        "running_balance": 250000.0,
        "match_status": "matched",
        "matched_to": {"type": "settlement", "ref_id": "settle_myntra_aug25"},
    }
    mock_db.bank_statement_lines.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db.bank_statement_lines.find_one = AsyncMock(return_value=matched_doc)

    match_payload = BankStatementLineUpdate(
        match_status="matched",
        matched_to=MatchedTo(type="settlement", ref_id="settle_myntra_aug25"),
    )
    match_res = await match_statement_line(str(line_id), match_payload, req)
    assert match_res["match_status"] == "matched"
    assert match_res["matched_to"]["type"] == "settlement"
    assert match_res["matched_to"]["ref_id"] == "settle_myntra_aug25"


@pytest.mark.anyio
async def test_hdfc_statement_import_csv(monkeypatch):
    """Test importing HDFC bank statement CSV with custom column map layout."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    hdfc_acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "HDFC - Online",
        "bank_name": "HDFC",
        "statement_format": {
            "sheet_locator": {"type": "first_sheet"},
            "header_locator": {"type": "fixed_row", "row": 0},
            "skip_rows_after_header": 0,
            "column_map": {
                "date": "Date",
                "narration": "Narration",
                "reference": "Chq./Ref.No.",
                "debit_amount": "Withdrawal Amt.",
                "credit_amount": "Deposit Amt.",
                "balance": "Closing Balance",
            },
            "date_format": "%d/%m/%Y",
        }
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=hdfc_acc_doc)

    inserted_docs = []
    async def mock_insert_many(docs):
        inserted_docs.extend(docs)
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])
    mock_db.bank_statement_lines.insert_many = AsyncMock(side_effect=mock_insert_many)

    hdfc_csv_content = (
        "Date,Narration,Chq./Ref.No.,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "15/08/2026,ACH CR-MYNTRA DESIGNS-SETTLEMENT,ACH001,,45250.50,145250.50\n"
        "16/08/2026,UPI-SWIGGY-EXPENSE,UPI999,350.00,,144900.50\n"
        "17/08/2026,NEFT DR-LEATHER SUPPLIER VENDOR,NEFT777,25000.00,,119900.50\n"
    ).encode("utf-8")

    from fastapi import UploadFile
    from io import BytesIO
    file = UploadFile(filename="hdfc_aug_statement.csv", file=BytesIO(hdfc_csv_content))

    req = MagicMock()
    res = await routes.banking.import_bank_statement(acc_id, req, file=file, dry_run=False)

    assert res["ok"] is True
    assert res["inserted_count"] == 3
    assert len(inserted_docs) == 3

    # Row 1 check
    assert inserted_docs[0]["date"] == "2026-08-15"
    assert inserted_docs[0]["narration"] == "ACH CR-MYNTRA DESIGNS-SETTLEMENT"
    assert inserted_docs[0]["reference_no"] == "ACH001"
    assert inserted_docs[0]["credit_amount"] == 45250.50
    assert inserted_docs[0]["debit_amount"] == 0.0
    assert inserted_docs[0]["running_balance"] == 145250.50
    assert inserted_docs[0]["match_status"] == "unmatched"

    # Row 2 check
    assert inserted_docs[1]["date"] == "2026-08-16"
    assert inserted_docs[1]["debit_amount"] == 350.00
    assert inserted_docs[1]["running_balance"] == 144900.50


@pytest.mark.anyio
async def test_uco_statement_import_csv(monkeypatch):
    """Test importing UCO bank statement CSV with different column names and date formats."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    uco_acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "UCO Bank - Offline",
        "bank_name": "UCO Bank",
        "statement_format": {
            "sheet_locator": {"type": "first_sheet"},
            "header_locator": {"type": "fixed_row", "row": 0},
            "skip_rows_after_header": 0,
            "column_map": {
                "date": "Txn Date",
                "narration": "Description",
                "reference": "Ref No",
                "debit_amount": "Debit",
                "credit_amount": "Credit",
                "balance": "Balance",
            },
            "date_format": "%d-%m-%Y",
        }
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=uco_acc_doc)

    inserted_docs = []
    async def mock_insert_many(docs):
        inserted_docs.extend(docs)
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])
    mock_db.bank_statement_lines.insert_many = AsyncMock(side_effect=mock_insert_many)

    uco_csv_content = (
        "Txn Date,Description,Ref No,Debit,Credit,Balance\n"
        "20-08-2026,CHQ DEP - BAXTER RETAIL CLIENT,CHQ54321,,120000.00,520000.00\n"
        "21-08-2026,RTGS - RAW MATERIAL AGRA,RTGS1234,80000.00,,440000.00\n"
    ).encode("utf-8")

    from fastapi import UploadFile
    from io import BytesIO
    file = UploadFile(filename="uco_statement.csv", file=BytesIO(uco_csv_content))

    req = MagicMock()
    res = await routes.banking.import_bank_statement(acc_id, req, file=file, dry_run=False)

    assert res["ok"] is True
    assert res["inserted_count"] == 2
    assert len(inserted_docs) == 2

    # Row 1 check
    assert inserted_docs[0]["date"] == "2026-08-20"
    assert inserted_docs[0]["narration"] == "CHQ DEP - BAXTER RETAIL CLIENT"
    assert inserted_docs[0]["reference_no"] == "CHQ54321"
    assert inserted_docs[0]["credit_amount"] == 120000.00
    assert inserted_docs[0]["debit_amount"] == 0.0
    assert inserted_docs[0]["running_balance"] == 520000.00
    assert inserted_docs[0]["match_status"] == "unmatched"

    # Row 2 check
    assert inserted_docs[1]["date"] == "2026-08-21"
    assert inserted_docs[1]["debit_amount"] == 80000.00
    assert inserted_docs[1]["running_balance"] == 440000.00


@pytest.mark.anyio
async def test_hdfc_statement_import_xlsx(monkeypatch):
    """Test importing HDFC bank statement Excel workbook (.xlsx)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    
    # Headers
    ws.append(["Date", "Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"])
    # Data rows
    ws.append(["15/08/2026", "ACH CR-MYNTRA DESIGNS-SETTLEMENT", "ACH001", "", 45250.50, 145250.50])
    ws.append(["16/08/2026", "UPI-SWIGGY-EXPENSE", "UPI999", 350.00, "", 144900.50])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    hdfc_acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "HDFC - Online",
        "bank_name": "HDFC",
        "statement_format": {
            "sheet_locator": {"type": "fixed_name", "name": "Statement"},
            "header_locator": {"type": "fixed_row", "row": 0},
            "skip_rows_after_header": 0,
            "column_map": {
                "date": "Date",
                "narration": "Narration",
                "reference": "Chq./Ref.No.",
                "debit_amount": "Withdrawal Amt.",
                "credit_amount": "Deposit Amt.",
                "balance": "Closing Balance",
            },
            "date_format": "%d/%m/%Y",
        }
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=hdfc_acc_doc)

    inserted_docs = []
    async def mock_insert_many(docs):
        inserted_docs.extend(docs)
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])
    mock_db.bank_statement_lines.insert_many = AsyncMock(side_effect=mock_insert_many)

    from fastapi import UploadFile
    file = UploadFile(filename="hdfc_statement.xlsx", file=bio)

    req = MagicMock()
    res = await routes.banking.import_bank_statement(acc_id, req, file=file, dry_run=False)

    assert res["ok"] is True
    assert res["inserted_count"] == 2
    assert len(inserted_docs) == 2
    assert inserted_docs[0]["credit_amount"] == 45250.50
    assert inserted_docs[0]["running_balance"] == 145250.50


@pytest.mark.anyio
async def test_auto_reconcile_online_account_credits(monkeypatch):
    """Test auto-reconciliation on online account: confident match, ambiguous match, and no match."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "HDFC - Online",
        "account_type": "online_channel",
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=acc_doc)

    line1_id = ObjectId()
    line2_id = ObjectId()
    line3_id = ObjectId()

    unmatched_lines = [
        # Confident match candidate: amount 45250.0 on 2026-08-15 (matches 45250.5 on 2026-08-14)
        {
            "_id": line1_id,
            "bank_account_id": acc_id,
            "date": "2026-08-15",
            "credit_amount": 45250.0,
            "debit_amount": 0.0,
            "match_status": "unmatched",
            "narration": "ACH CR-MYNTRA DESIGNS",
        },
        # Ambiguous candidate: amount 10000.0 on 2026-08-16 (two settlements of 10000.0)
        {
            "_id": line2_id,
            "bank_account_id": acc_id,
            "date": "2026-08-16",
            "credit_amount": 10000.0,
            "debit_amount": 0.0,
            "match_status": "unmatched",
            "narration": "ACH CR-FLIPKART",
        },
        # No match candidate: amount 99999.0
        {
            "_id": line3_id,
            "bank_account_id": acc_id,
            "date": "2026-08-17",
            "credit_amount": 99999.0,
            "debit_amount": 0.0,
            "match_status": "unmatched",
            "narration": "UNKNOWN CREDIT",
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=unmatched_lines)
    mock_db.bank_statement_lines.find = MagicMock(return_value=mock_cursor)

    settle1_id = ObjectId()
    settle2_id = ObjectId()
    settle3_id = ObjectId()

    settlement_docs = [
        # Exactly 1 match for Line 1
        {
            "_id": settle1_id,
            "order_release_id": "ORD001",
            "net_payout": 45250.50,
            "settlement_date": "2026-08-14",
            "bank_account_id": None,
        },
        # 2 settlements matching Line 2 (ambiguous!)
        {
            "_id": settle2_id,
            "order_release_id": "ORD002",
            "net_payout": 10000.0,
            "settlement_date": "2026-08-16",
            "bank_account_id": None,
        },
        {
            "_id": settle3_id,
            "order_release_id": "ORD003",
            "net_payout": 10000.0,
            "settlement_date": "2026-08-16",
            "bank_account_id": None,
        },
    ]

    mock_db.online_settlements.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=settlement_docs)))
    mock_db.payments.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_db.expenses.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    updated_statement_lines = {}
    async def mock_update_stmt(q, u):
        updated_statement_lines[str(q["_id"])] = u["$set"]
        return MagicMock(matched_count=1)
    mock_db.bank_statement_lines.update_one = AsyncMock(side_effect=mock_update_stmt)

    updated_settlements = {}
    async def mock_update_settle(q, u):
        updated_settlements[str(q["_id"])] = u["$set"]
        return MagicMock(matched_count=1)
    mock_db.online_settlements.update_one = AsyncMock(side_effect=mock_update_settle)

    req = MagicMock()
    res = await routes.banking.reconcile_bank_account(
        id=acc_id,
        request=req,
        date_window_days=3,
        amount_tolerance=1.0,
        dry_run=False,
    )

    assert res["ok"] is True
    assert res["total_unmatched_evaluated"] == 3
    assert res["auto_matched_count"] == 1
    assert res["ambiguous_count"] == 1
    assert res["no_match_count"] == 1

    # Confirmed match verification
    assert str(line1_id) in updated_statement_lines
    assert updated_statement_lines[str(line1_id)]["match_status"] == "matched"
    assert updated_statement_lines[str(line1_id)]["matched_to"]["type"] == "settlement"
    assert updated_statement_lines[str(line1_id)]["matched_to"]["ref_id"] == str(settle1_id)

    # Confirmed settlement bank_account_id set
    assert str(settle1_id) in updated_settlements
    assert updated_settlements[str(settle1_id)]["bank_account_id"] == acc_id

    # Line 2 and Line 3 must NOT have been updated (remained unmatched)
    assert str(line2_id) not in updated_statement_lines
    assert str(line3_id) not in updated_statement_lines


@pytest.mark.anyio
async def test_auto_reconcile_b2b_account_credits_and_debits(monkeypatch):
    """Test auto-reconciliation on offline account with client payment credit & expense/vendor debits."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "UCO Bank - Offline",
        "account_type": "b2b_client",
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=acc_doc)

    credit_line_id = ObjectId()
    debit_vendor_line_id = ObjectId()
    debit_expense_line_id = ObjectId()

    unmatched_lines = [
        # Credit line: client payment 120,000 on 2026-08-20
        {
            "_id": credit_line_id,
            "bank_account_id": acc_id,
            "date": "2026-08-20",
            "credit_amount": 120000.0,
            "debit_amount": 0.0,
            "match_status": "unmatched",
            "narration": "CHQ DEP - BAXTER RETAIL",
        },
        # Debit line 1: vendor payment 25,000 on 2026-08-22
        {
            "_id": debit_vendor_line_id,
            "bank_account_id": acc_id,
            "date": "2026-08-22",
            "credit_amount": 0.0,
            "debit_amount": 25000.0,
            "match_status": "unmatched",
            "narration": "NEFT - AGRA SOLE SUPPLIER",
        },
        # Debit line 2: office rent expense 45,000 on 2026-08-01
        {
            "_id": debit_expense_line_id,
            "bank_account_id": acc_id,
            "date": "2026-08-01",
            "credit_amount": 0.0,
            "debit_amount": 45000.0,
            "match_status": "unmatched",
            "narration": "NEFT - FACTORY RENT",
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=unmatched_lines)
    mock_db.bank_statement_lines.find = MagicMock(return_value=mock_cursor)

    client_pay_id = ObjectId()
    vendor_pay_id = ObjectId()
    expense_id = ObjectId()

    # Client payment
    client_pay_doc = {
        "_id": client_pay_id,
        "payment_date": "2026-08-19",
        "amount": 120000.0,
        "client_name": "Baxter Retail",
        "type": "client_payment",
        "vendor_id": None,
        "bank_account_id": None,
    }

    # Vendor payment
    vendor_pay_doc = {
        "_id": vendor_pay_id,
        "payment_date": "2026-08-22",
        "amount": 25000.0,
        "type": "vendor_payment",
        "vendor_id": "v_agra_1",
        "bank_account_id": None,
    }

    # Expense
    expense_doc = {
        "_id": expense_id,
        "date": "2026-08-01",
        "amount": 45000.0,
        "category": "Rent & Utilities",
        "payee": "Factory Landlord",
        "bank_account_id": None,
    }

    mock_db.online_settlements.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    
    # Setup payments and expenses find responses
    def mock_payments_find(q):
        if q.get("type") == {"$ne": "vendor_payment"}:
            return [client_pay_doc]
        return [vendor_pay_doc]
    mock_db.payments.find = MagicMock(side_effect=lambda q: MagicMock(to_list=AsyncMock(return_value=mock_payments_find(q))))
    mock_db.expenses.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[expense_doc])))

    updated_stmt = {}
    mock_db.bank_statement_lines.update_one = AsyncMock(side_effect=lambda q, u: updated_stmt.update({str(q["_id"]): u["$set"]}))
    mock_db.payments.update_one = AsyncMock()
    mock_db.expenses.update_one = AsyncMock()

    req = MagicMock()
    res = await routes.banking.reconcile_bank_account(
        id=acc_id,
        request=req,
        date_window_days=3,
        amount_tolerance=1.0,
        dry_run=False,
    )

    assert res["ok"] is True
    assert res["total_unmatched_evaluated"] == 3
    assert res["auto_matched_count"] == 3
    assert res["ambiguous_count"] == 0
    assert res["no_match_count"] == 0

    # Verify all 3 matched
    assert updated_stmt[str(credit_line_id)]["matched_to"]["type"] == "payment"
    assert updated_stmt[str(credit_line_id)]["matched_to"]["ref_id"] == str(client_pay_id)

    assert updated_stmt[str(debit_vendor_line_id)]["matched_to"]["type"] == "vendor_payment"
    assert updated_stmt[str(debit_vendor_line_id)]["matched_to"]["ref_id"] == str(vendor_pay_id)

    assert updated_stmt[str(debit_expense_line_id)]["matched_to"]["type"] == "expense"
    assert updated_stmt[str(debit_expense_line_id)]["matched_to"]["ref_id"] == str(expense_id)


@pytest.mark.anyio
async def test_suggest_and_confirm_transfers_and_reconciliation_summary(monkeypatch):
    """
    Test scenario:
    1. Debit in HDFC (₹50,000 on Aug 15) and Credit in UCO (₹50,000 on Aug 16) surfaced as suggested transfer pair.
    2. Explicit confirmation marks both lines match_status='transfer' pointing to each other.
    3. Reconciliation summary strictly excludes the transfer pair from income/expenses.
    """
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    hdfc_acc_id = str(ObjectId())
    uco_acc_id = str(ObjectId())

    acc_docs = [
        {"_id": ObjectId(hdfc_acc_id), "name": "HDFC - Online", "bank_name": "HDFC", "account_type": "online_channel"},
        {"_id": ObjectId(uco_acc_id), "name": "UCO Bank - Offline", "bank_name": "UCO Bank", "account_type": "b2b_client"},
    ]
    mock_db.bank_accounts.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=acc_docs)))

    hdfc_debit_trf_id = ObjectId()
    uco_credit_trf_id = ObjectId()
    uco_income_line_id = ObjectId()
    hdfc_expense_line_id = ObjectId()

    # In-memory statement lines store
    statement_store = {
        str(hdfc_debit_trf_id): {
            "_id": hdfc_debit_trf_id,
            "bank_account_id": hdfc_acc_id,
            "date": "2026-08-15",
            "debit_amount": 50000.0,
            "credit_amount": 0.0,
            "match_status": "unmatched",
            "narration": "NEFT OUT - TRF TO UCO BANK",
        },
        str(uco_credit_trf_id): {
            "_id": uco_credit_trf_id,
            "bank_account_id": uco_acc_id,
            "date": "2026-08-16",
            "debit_amount": 0.0,
            "credit_amount": 50000.0,
            "match_status": "unmatched",
            "narration": "NEFT IN - TRF FROM HDFC ONLINE",
        },
        str(uco_income_line_id): {
            "_id": uco_income_line_id,
            "bank_account_id": uco_acc_id,
            "date": "2026-08-18",
            "debit_amount": 0.0,
            "credit_amount": 100000.0,
            "match_status": "matched",
            "narration": "CHQ DEP - CLIENT PAYMENT",
        },
        str(hdfc_expense_line_id): {
            "_id": hdfc_expense_line_id,
            "bank_account_id": hdfc_acc_id,
            "date": "2026-08-19",
            "debit_amount": 20000.0,
            "credit_amount": 0.0,
            "match_status": "matched",
            "narration": "RAW MATERIAL PAYMENT",
        },
    }

    def mock_stmt_find(q):
        status_filter = q.get("match_status")
        res = list(statement_store.values())
        if status_filter:
            res = [r for r in res if r.get("match_status") == status_filter]
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=res)
        return mock_cursor

    mock_db.bank_statement_lines.find = MagicMock(side_effect=mock_stmt_find)

    async def mock_stmt_find_one(q):
        oid_key = str(q.get("_id"))
        return statement_store.get(oid_key)
    mock_db.bank_statement_lines.find_one = AsyncMock(side_effect=mock_stmt_find_one)

    async def mock_stmt_update_one(q, u):
        oid_key = str(q.get("_id"))
        if oid_key in statement_store:
            statement_store[oid_key].update(u.get("$set", {}))
        return MagicMock(matched_count=1)
    mock_db.bank_statement_lines.update_one = AsyncMock(side_effect=mock_stmt_update_one)

    req = MagicMock()

    # Step 1: Scan for suggested transfer pairs
    suggestions = await routes.banking.get_suggested_transfers(
        request=req,
        date_window_days=3,
        amount_tolerance=1.0,
    )
    assert suggestions["ok"] is True
    assert suggestions["total_suggestions"] == 1
    pair = suggestions["pairs"][0]
    assert pair["from_line"]["id"] == str(hdfc_debit_trf_id)
    assert pair["to_line"]["id"] == str(uco_credit_trf_id)
    assert pair["amount_diff"] == 0.0
    assert pair["day_diff"] == 1

    # Both lines must still be unmatched before confirmation
    assert statement_store[str(hdfc_debit_trf_id)]["match_status"] == "unmatched"
    assert statement_store[str(uco_credit_trf_id)]["match_status"] == "unmatched"

    # Step 2: Explicitly confirm the transfer pair
    from models.banking import TransferConfirmIn
    confirm_res = await routes.banking.confirm_transfer_pair(
        payload=TransferConfirmIn(
            from_line_id=str(hdfc_debit_trf_id),
            to_line_id=str(uco_credit_trf_id),
            notes="Liquidity rebalance to UCO account",
        ),
        request=req,
    )
    assert confirm_res["ok"] is True
    assert statement_store[str(hdfc_debit_trf_id)]["match_status"] == "transfer"
    assert statement_store[str(hdfc_debit_trf_id)]["matched_to"]["ref_id"] == str(uco_credit_trf_id)
    assert statement_store[str(uco_credit_trf_id)]["match_status"] == "transfer"
    assert statement_store[str(uco_credit_trf_id)]["matched_to"]["ref_id"] == str(hdfc_debit_trf_id)

    # Step 3: Verify reconciliation summary excludes transfer pair from income/expenses
    summary_res = await routes.banking.get_reconciliation_summary(request=req)
    assert summary_res["ok"] is True
    s = summary_res["summary"]

    # Total income is ONLY the ₹100,000 client payment (the ₹50,000 transfer credit is excluded!)
    assert s["total_income"] == 100000.0
    assert s["matched_income"] == 100000.0
    assert s["unmatched_income"] == 0.0

    # Total expenses is ONLY the ₹20,000 raw material expense (the ₹50,000 transfer debit is excluded!)
    assert s["total_expenses"] == 20000.0
    assert s["matched_expenses"] == 20000.0
    assert s["unmatched_expenses"] == 0.0

    # Net operating cashflow is 100,000 - 20,000 = 80,000
    assert s["net_operating_cashflow"] == 80000.0

    # Transfers tracked separately
    assert s["total_transfers_volume"] == 50000.0
    assert s["transfer_lines_count"] == 2


@pytest.mark.anyio
async def test_unmatched_erp_candidates_listing(monkeypatch):
    """Test get_unmatched_erp_candidates returns settlements, payments, and expenses."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}
    
    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    acc_id = str(ObjectId())
    acc_doc = {
        "_id": ObjectId(acc_id),
        "name": "HDFC - Online",
        "account_type": "online_channel",
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=acc_doc)

    settlements = [
        {"_id": ObjectId(), "platform": "myntra", "seller_order_id": "ORD999", "net_payout": 3450.0, "settlement_date": "2026-08-20", "bank_account_id": None}
    ]
    expenses = [
        {"_id": ObjectId(), "category": "Office", "payee": "Broadband Provider", "amount": 1500.0, "date": "2026-08-21", "bank_account_id": None}
    ]
    vendor_payments = [
        {"_id": ObjectId(), "type": "vendor_payment", "vendor_name": "Sole Corp", "amount": 12000.0, "payment_date": "2026-08-22", "bank_account_id": None}
    ]

    mock_db.online_settlements.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=settlements)))))))
    mock_db.expenses.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=expenses)))))))
    mock_db.payments.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=vendor_payments)))))))

    req = MagicMock()
    res = await routes.banking.get_unmatched_erp_candidates(
        request=req,
        bank_account_id=acc_id,
        side="all",
    )

    assert res["ok"] is True
    assert res["total"] == 3
    types = [c["type"] for c in res["candidates"]]
    assert "settlement" in types
    assert "expense" in types
    assert "vendor_payment" in types


@pytest.mark.anyio
async def test_auto_reconcile_expense_with_pre_set_bank_account(monkeypatch):
    """Ensure auto-reconcile on Account A does NOT match an expense pre-assigned to Account B."""
    mock_db = MagicMock()
    mock_user = {"role": "admin", "email": "admin@sskfootcare.com", "name": "Admin"}

    import routes.banking
    monkeypatch.setattr(routes.banking, "_get_user", AsyncMock(return_value=mock_user))
    monkeypatch.setattr(routes.banking, "_get_db", lambda r: mock_db)

    account_a_id = str(ObjectId())
    account_b_id = str(ObjectId())

    acc_a_doc = {
        "_id": ObjectId(account_a_id),
        "name": "Account A - UCO Bank",
        "account_type": "b2b_client",
    }
    mock_db.bank_accounts.find_one = AsyncMock(return_value=acc_a_doc)

    # Statement line on Account A (debit of 15000.0 on 2026-08-10)
    line_id = ObjectId()
    unmatched_lines = [
        {
            "_id": line_id,
            "bank_account_id": account_a_id,
            "date": "2026-08-10",
            "credit_amount": 0.0,
            "debit_amount": 15000.0,
            "match_status": "unmatched",
            "narration": "OFFICE EXPENSE PAYMENT",
        }
    ]

    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=unmatched_lines)
    mock_db.bank_statement_lines.find = MagicMock(return_value=mock_cursor)

    # Expense is pre-assigned to Account B
    expense_doc = {
        "_id": ObjectId(),
        "date": "2026-08-10",
        "amount": 15000.0,
        "category": "Office & Administrative",
        "payee": "Stationery Mart",
        "bank_account_id": account_b_id,
    }

    # When querying expenses, simulate MongoDB filtering on bank_account_id
    def mock_expenses_find(query):
        acc_filter = query.get("bank_account_id", {})
        allowed_accounts = acc_filter.get("$in", []) if isinstance(acc_filter, dict) else [acc_filter]
        matching = [expense_doc] if expense_doc.get("bank_account_id") in allowed_accounts else []
        return MagicMock(to_list=AsyncMock(return_value=matching))

    mock_db.expenses.find = MagicMock(side_effect=mock_expenses_find)
    mock_db.online_settlements.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_db.payments.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    updated_stmt = {}
    mock_db.bank_statement_lines.update_one = AsyncMock(side_effect=lambda q, u: updated_stmt.update({str(q["_id"]): u["$set"]}))
    mock_db.expenses.update_one = AsyncMock()

    req = MagicMock()
    # Run auto-reconcile on Account A
    res = await routes.banking.reconcile_bank_account(
        id=account_a_id,
        request=req,
        date_window_days=3,
        amount_tolerance=1.0,
        dry_run=False,
    )

    assert res["ok"] is True
    assert res["total_unmatched_evaluated"] == 1
    assert res["auto_matched_count"] == 0
    assert res["no_match_count"] == 1
    assert str(line_id) not in updated_stmt
    mock_db.expenses.update_one.assert_not_called()





