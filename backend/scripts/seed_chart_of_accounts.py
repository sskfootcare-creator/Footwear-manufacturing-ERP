import os
import sys
import asyncio
import logging
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from db.postgres import get_session_factory, init_postgres_db
    from models.sql_financials import Account
except ImportError:
    from backend.db.postgres import get_session_factory, init_postgres_db
    from backend.models.sql_financials import Account

log = logging.getLogger(__name__)

STANDARD_CHART_OF_ACCOUNTS = [
    # Assets (1000 - 1999)
    {"code": "1010", "name": "Bank Accounts", "account_type": "ASSET", "sub_type": "BANK_ACCOUNT", "is_reconcilable": True},
    {"code": "1010-HDFC-MAIN", "name": "HDFC Current Account (Main)", "account_type": "ASSET", "sub_type": "BANK_ACCOUNT", "is_reconcilable": True},
    {"code": "1010-UCO-OP", "name": "UCO Bank Current Account", "account_type": "ASSET", "sub_type": "BANK_ACCOUNT", "is_reconcilable": True},
    {"code": "1020", "name": "Cash in Hand", "account_type": "ASSET", "sub_type": "CASH_IN_HAND", "is_reconcilable": True},
    {"code": "1020-FACTORY-CASH", "name": "Factory Petty Cash", "account_type": "ASSET", "sub_type": "CASH_IN_HAND", "is_reconcilable": True},
    {"code": "1020-OFFICE-CASH", "name": "Head Office Cash Register", "account_type": "ASSET", "sub_type": "CASH_IN_HAND", "is_reconcilable": True},
    {"code": "1030", "name": "Accounts Receivable (B2B Buyers)", "account_type": "ASSET", "sub_type": "ACCOUNTS_RECEIVABLE", "is_reconcilable": True},
    {"code": "1040", "name": "Raw Material Inventory Asset", "account_type": "ASSET", "sub_type": "INVENTORY_ASSET", "is_reconcilable": False},
    {"code": "1050", "name": "Finished Goods Inventory Asset", "account_type": "ASSET", "sub_type": "INVENTORY_ASSET", "is_reconcilable": False},
    {"code": "1060-CGST-IN", "name": "CGST Input Tax Credit", "account_type": "ASSET", "sub_type": "GST_INPUT_TAX_CREDIT", "is_reconcilable": True},
    {"code": "1060-SGST-IN", "name": "SGST Input Tax Credit", "account_type": "ASSET", "sub_type": "GST_INPUT_TAX_CREDIT", "is_reconcilable": True},
    {"code": "1060-IGST-IN", "name": "IGST Input Tax Credit", "account_type": "ASSET", "sub_type": "GST_INPUT_TAX_CREDIT", "is_reconcilable": True},
    {"code": "1070", "name": "Worker & Karigar Advances", "account_type": "ASSET", "sub_type": "WORKER_ADVANCE", "is_reconcilable": True},

    # Liabilities (2000 - 2999)
    {"code": "2010", "name": "Accounts Payable (Raw Material Suppliers)", "account_type": "LIABILITY", "sub_type": "ACCOUNTS_PAYABLE", "is_reconcilable": True},
    {"code": "2020", "name": "Karigar Wages Payable", "account_type": "LIABILITY", "sub_type": "WAGES_PAYABLE", "is_reconcilable": True},
    {"code": "2030-CGST-OUT", "name": "CGST Output Tax Payable", "account_type": "LIABILITY", "sub_type": "GST_OUTPUT_TAX_PAYABLE", "is_reconcilable": True},
    {"code": "2030-SGST-OUT", "name": "SGST Output Tax Payable", "account_type": "LIABILITY", "sub_type": "GST_OUTPUT_TAX_PAYABLE", "is_reconcilable": True},
    {"code": "2030-IGST-OUT", "name": "IGST Output Tax Payable", "account_type": "LIABILITY", "sub_type": "GST_OUTPUT_TAX_PAYABLE", "is_reconcilable": True},
    {"code": "2040-194C", "name": "TDS Payable - Contractor (194C)", "account_type": "LIABILITY", "sub_type": "TDS_PAYABLE", "is_reconcilable": True},
    {"code": "2040-194J", "name": "TDS Payable - Professional (194J)", "account_type": "LIABILITY", "sub_type": "TDS_PAYABLE", "is_reconcilable": True},
    {"code": "2050-TCS", "name": "TCS Payable on Marketplace Sales", "account_type": "LIABILITY", "sub_type": "TCS_PAYABLE", "is_reconcilable": True},

    # Equity (3000 - 3999)
    {"code": "3010", "name": "Owner / Partner Capital", "account_type": "EQUITY", "sub_type": "OWNERS_EQUITY", "is_reconcilable": False},
    {"code": "3020", "name": "Retained Earnings", "account_type": "EQUITY", "sub_type": "OWNERS_EQUITY", "is_reconcilable": False},

    # Revenue (4000 - 4999)
    {"code": "4010", "name": "B2B Footwear Sales Revenue", "account_type": "REVENUE", "sub_type": "OPERATING_REVENUE", "is_reconcilable": False},
    {"code": "4020", "name": "Online Marketplace Sales Revenue", "account_type": "REVENUE", "sub_type": "MARKETPLACE_SALES", "is_reconcilable": False},
    {"code": "4030", "name": "Discounts & Round-off Income", "account_type": "REVENUE", "sub_type": "OTHER_INCOME", "is_reconcilable": False},

    # Expenses (5000 - 5999)
    {"code": "5010", "name": "Raw Material Consumption (COGS)", "account_type": "EXPENSE", "sub_type": "RAW_MATERIAL_EXPENSE", "is_reconcilable": False},
    {"code": "5020", "name": "Direct Karigar Labor & Wages", "account_type": "EXPENSE", "sub_type": "DIRECT_LABOR_EXPENSE", "is_reconcilable": False},
    {"code": "5030", "name": "Factory Rent & Electricity", "account_type": "EXPENSE", "sub_type": "FACTORY_OVERHEAD", "is_reconcilable": False},
    {"code": "5040", "name": "Outward Freight & Shipping", "account_type": "EXPENSE", "sub_type": "SELLING_AND_DISTRIBUTION", "is_reconcilable": False},
    {"code": "5050", "name": "Marketplace Commission & Fulfillment Fees", "account_type": "EXPENSE", "sub_type": "SELLING_AND_DISTRIBUTION", "is_reconcilable": False},
    {"code": "5060", "name": "Administrative & Office Expenses", "account_type": "EXPENSE", "sub_type": "ADMINISTRATIVE_EXPENSE", "is_reconcilable": False},
    {"code": "5070", "name": "Bank Charges & Payment Gateway Fees", "account_type": "EXPENSE", "sub_type": "FINANCIAL_EXPENSE", "is_reconcilable": False},
]


async def seed_chart_of_accounts(session: AsyncSession) -> int:
    """Seed standard chart of accounts idempotently."""
    created_count = 0
    for acct_data in STANDARD_CHART_OF_ACCOUNTS:
        stmt = select(Account).where(Account.code == acct_data["code"])
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            account = Account(
                code=acct_data["code"],
                name=acct_data["name"],
                account_type=acct_data["account_type"],
                sub_type=acct_data["sub_type"],
                is_reconcilable=acct_data.get("is_reconcilable", False),
                currency="INR",
            )
            session.add(account)
            created_count += 1

    if created_count > 0:
        await session.commit()
        log.info(f"Seeded {created_count} standard chart of accounts.")
    return created_count


async def main():
    await init_postgres_db()
    session_factory = get_session_factory()
    async with session_factory() as session:
        count = await seed_chart_of_accounts(session)
        print(f"Chart of accounts seed finished. Inserted: {count}")


if __name__ == "__main__":
    asyncio.run(main())
