"""SQLAlchemy 2.0 Relational Financial Models for SSK Footwear ERP."""

import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Numeric,
    Date,
    DateTime,
    ForeignKey,
    Text,
    Integer,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
try:
    from db.postgres import Base
except ImportError:
    from backend.db.postgres import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# 1. FISCAL CALENDAR & PERIOD LOCKS
# ============================================================================
class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(50), nullable=False, unique=True)  # e.g. "FY 2026-2027"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, nullable=False, default=False)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String(100), nullable=True)


class AccountingPeriodLock(Base):
    __tablename__ = "accounting_period_locks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    bank_account_id = Column(String(36), nullable=True)  # None = Global lock across all accounts
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    locked_at = Column(DateTime, nullable=False, default=now_utc)
    locked_by = Column(String(100), nullable=False)
    lock_reason = Column(String(255), default="Monthly reconciliation finalized")
    unlocked_at = Column(DateTime, nullable=True)
    unlocked_by = Column(String(100), nullable=True)
    unlock_reason = Column(String(255), nullable=True)


# ============================================================================
# 2. CHART OF ACCOUNTS
# ============================================================================
class Account(Base):
    __tablename__ = "chart_of_accounts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    code = Column(String(30), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False)
    account_type = Column(String(30), nullable=False)  # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    sub_type = Column(String(50), nullable=False)      # BANK_ACCOUNT, CASH_IN_HAND, ACCOUNTS_RECEIVABLE, etc.
    currency = Column(String(3), nullable=False, default="INR")
    parent_account_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_reconcilable = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    # Self-referential relationship
    parent = relationship("Account", remote_side=[id], backref="children")
    journal_lines = relationship("JournalLine", back_populates="account")


# ============================================================================
# 3. FINANCIAL ENTITIES (Sub-ledger Partners: Clients, Vendors, Workers, Banks)
# ============================================================================
class FinancialEntity(Base):
    __tablename__ = "financial_entities"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    entity_type = Column(String(30), nullable=False)  # CLIENT, VENDOR, WORKER, BANK, CASH_REGISTER, MARKETPLACE
    external_ref_id = Column(String(64), nullable=True, index=True)  # MongoDB _id
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    gstin = Column(String(15), nullable=True)
    pan = Column(String(10), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    billing_address = Column(Text, nullable=True)
    payment_terms_days = Column(Integer, nullable=False, default=30)
    gl_account_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    gl_account = relationship("Account")
    bank_accounts = relationship("BankAccount", back_populates="entity")


# ============================================================================
# 4. BANK ACCOUNTS & CASH REGISTERS
# ============================================================================
class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    entity_id = Column(String(36), ForeignKey("financial_entities.id"), nullable=True)
    gl_account_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=False)
    account_name = Column(String(100), nullable=False)
    bank_name = Column(String(100), nullable=False)
    account_number = Column(String(40), nullable=False, unique=True)
    account_number_last4 = Column(String(10), nullable=False)
    ifsc = Column(String(15), nullable=False)
    branch = Column(String(100), nullable=True)
    category = Column(String(30), nullable=False, default="b2b_client")  # online_channel, b2b_client
    opening_balance = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    opening_balance_date = Column(Date, nullable=False, default=date.today)
    current_cleared_balance = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    entity = relationship("FinancialEntity", back_populates="bank_accounts")
    gl_account = relationship("Account")
    statement_lines = relationship("BankStatementLine", back_populates="bank_account")


class CashRegister(Base):
    __tablename__ = "cash_registers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False, unique=True)
    gl_account_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=False)
    custodian_user_email = Column(String(100), nullable=True)
    opening_balance = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    current_balance = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    gl_account = relationship("Account")


# ============================================================================
# 5. JOURNAL ENTRIES & BALANCED LINES (Double-Entry Core)
# ============================================================================
class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    entry_number = Column(String(50), nullable=False, unique=True, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    entry_type = Column(String(40), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="POSTED")  # DRAFT, POSTED, VOIDED
    narration = Column(Text, nullable=False)
    source_document_ref = Column(String(100), nullable=True, index=True)
    fiscal_year_id = Column(String(36), ForeignKey("fiscal_years.id"), nullable=True)
    total_debit = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_credit = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    posted_by = Column(String(100), nullable=False)
    posted_at = Column(DateTime, nullable=False, default=now_utc)
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(String(100), nullable=True)
    void_reason = Column(String(255), nullable=True)

    lines = relationship("JournalLine", back_populates="journal_entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=False, index=True)
    entity_id = Column(String(36), ForeignKey("financial_entities.id"), nullable=True, index=True)
    line_number = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    debit = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    credit = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    reconciliation_status = Column(String(20), nullable=False, default="UNRECONCILED")  # UNRECONCILED, RECONCILED
    reconciled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")
    entity = relationship("FinancialEntity")

    __table_args__ = (
        UniqueConstraint("journal_entry_id", "line_number", name="uq_journal_entry_line"),
    )


# ============================================================================
# 6. SALES INVOICES & RECEIVABLES (AR)
# ============================================================================
class SalesInvoice(Base):
    __tablename__ = "sales_invoices"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    invoice_no = Column(String(50), nullable=False, unique=True, index=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    client_id = Column(String(36), ForeignKey("financial_entities.id"), nullable=False, index=True)
    po_number = Column(String(100), nullable=True)
    customer_gstin = Column(String(15), nullable=True)
    place_of_supply = Column(String(50), nullable=True)
    subtotal = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    cgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    sgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    igst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tcs_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    grand_total = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    grn_adjustment = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_receivable = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    paid_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    status = Column(String(25), nullable=False, default="POSTED")  # DRAFT, POSTED, PARTIALLY_PAID, PAID, CANCELLED
    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    client = relationship("FinancialEntity")
    journal_entry = relationship("JournalEntry")


# ============================================================================
# 7. VENDOR BILLS & ACCOUNTS PAYABLE (AP)
# ============================================================================
class VendorBill(Base):
    __tablename__ = "vendor_bills"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    bill_no = Column(String(50), nullable=False)
    vendor_id = Column(String(36), ForeignKey("financial_entities.id"), nullable=False, index=True)
    vendor_po_ref = Column(String(50), nullable=True)
    bill_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    subtotal = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    paid_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    status = Column(String(25), nullable=False, default="POSTED")
    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    vendor = relationship("FinancialEntity")
    journal_entry = relationship("JournalEntry")

    __table_args__ = (
        UniqueConstraint("vendor_id", "bill_no", name="uq_vendor_bill_no"),
    )


# ============================================================================
# 8. PAYMENT & RECEIPT VOUCHERS + ALLOCATIONS
# ============================================================================
class PaymentVoucher(Base):
    __tablename__ = "payment_vouchers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    voucher_no = Column(String(50), nullable=False, unique=True, index=True)
    voucher_type = Column(String(20), nullable=False)  # RECEIPT, PAYMENT
    voucher_date = Column(Date, nullable=False)
    entity_id = Column(String(36), ForeignKey("financial_entities.id"), nullable=False, index=True)
    payment_mode = Column(String(20), nullable=False)  # BANK_TRANSFER, RTGS, NEFT, UPI, CHEQUE, CASH, ADJUSTMENT
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=True)
    cash_register_id = Column(String(36), ForeignKey("cash_registers.id"), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    reference_number = Column(String(100), nullable=True)
    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    entity = relationship("FinancialEntity")
    bank_account = relationship("BankAccount")
    cash_register = relationship("CashRegister")
    journal_entry = relationship("JournalEntry")
    allocations = relationship("VoucherAllocation", back_populates="voucher", cascade="all, delete-orphan")


class VoucherAllocation(Base):
    __tablename__ = "voucher_allocations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    voucher_id = Column(String(36), ForeignKey("payment_vouchers.id", ondelete="CASCADE"), nullable=False, index=True)
    sales_invoice_id = Column(String(36), ForeignKey("sales_invoices.id"), nullable=True, index=True)
    vendor_bill_id = Column(String(36), ForeignKey("vendor_bills.id"), nullable=True, index=True)
    allocated_amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    voucher = relationship("PaymentVoucher", back_populates="allocations")
    sales_invoice = relationship("SalesInvoice")
    vendor_bill = relationship("VendorBill")


# ============================================================================
# 9. BANK STATEMENTS & RECONCILIATION
# ============================================================================
class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    value_date = Column(Date, nullable=True)
    narration = Column(Text, nullable=False)
    cheque_reference_no = Column(String(100), nullable=True, index=True)
    debit_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    credit_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    running_balance = Column(Numeric(14, 2), nullable=True)
    match_status = Column(String(20), nullable=False, default="UNMATCHED", index=True)  # UNMATCHED, MATCHED, TRANSFERRED, IGNORED
    matched_journal_line_id = Column(String(36), ForeignKey("journal_lines.id"), nullable=True)
    matched_voucher_id = Column(String(36), ForeignKey("payment_vouchers.id"), nullable=True)
    imported_batch_id = Column(String(64), nullable=True)
    imported_by = Column(String(100), nullable=True)
    imported_at = Column(DateTime, nullable=False, default=now_utc)
    reconciled_by = Column(String(100), nullable=True)
    reconciled_at = Column(DateTime, nullable=True)
    remarks = Column(String(255), nullable=True)

    bank_account = relationship("BankAccount", back_populates="statement_lines")
    matched_journal_line = relationship("JournalLine")
    matched_voucher = relationship("PaymentVoucher")


class BankReconciliationStatement(Base):
    __tablename__ = "bank_reconciliation_statements"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False)
    bank_statement_balance = Column(Numeric(14, 2), nullable=False)
    book_balance = Column(Numeric(14, 2), nullable=False)
    unpresented_cheques_total = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    uncredited_deposits_total = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    unreconciled_bank_debits = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    unreconciled_bank_credits = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    reconciled_difference = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    is_balanced = Column(Boolean, nullable=False, default=False)
    finalized_at = Column(DateTime, nullable=True)
    finalized_by = Column(String(100), nullable=True)

    bank_account = relationship("BankAccount")

    __table_args__ = (
        UniqueConstraint("bank_account_id", "as_of_date", name="uq_brs_account_date"),
    )


# ============================================================================
# 10. MARKETPLACE SETTLEMENTS
# ============================================================================
class MarketplaceSettlement(Base):
    __tablename__ = "marketplace_settlements"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    platform = Column(String(30), nullable=False)
    neft_utr = Column(String(100), nullable=False)
    settlement_date = Column(Date, nullable=False)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False)
    gross_order_value = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    marketplace_commission = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    logistics_forward = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    logistics_reverse = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tech_packaging_fees = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tcs_cgst = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tcs_sgst = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tcs_igst = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tds_194o = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    gst_on_services = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_settled_amount = Column(Numeric(14, 2), nullable=False)
    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=True)
    statement_line_id = Column(String(36), ForeignKey("bank_statement_lines.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)

    bank_account = relationship("BankAccount")
    journal_entry = relationship("JournalEntry")
    statement_line = relationship("BankStatementLine")

    __table_args__ = (
        UniqueConstraint("platform", "neft_utr", name="uq_mkt_utr"),
    )
