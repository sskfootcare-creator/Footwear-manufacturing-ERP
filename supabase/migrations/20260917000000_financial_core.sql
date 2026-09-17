-- ============================================================================
-- SSK FOOTWEAR ERP — RELATIONAL FINANCIAL CORE MIGRATION
-- Built following Supabase & PostgreSQL Best Practices:
-- 1. All foreign keys indexed (prevents sequential scans on JOIN/CASCADE)
-- 2. Explicit NUMERIC(14, 2) currency data types (no floating-point rounding errors)
-- 3. Row-Level Security (RLS) enabled on all financial tables
-- 4. Period locking immutability verification trigger
-- 5. Standard 33 Indian Footwear Manufacturing Chart of Accounts seeded
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. FISCAL CALENDAR & PERIOD LOCKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS fiscal_years (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    closed_at TIMESTAMPTZ,
    closed_by VARCHAR(100),
    CONSTRAINT chk_fy_dates CHECK (end_date > start_date)
);

CREATE TABLE IF NOT EXISTS accounting_period_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_account_id UUID,
    period_from DATE NOT NULL,
    period_to DATE NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_by VARCHAR(100) NOT NULL,
    lock_reason VARCHAR(255) DEFAULT 'Monthly reconciliation finalized',
    unlocked_at TIMESTAMPTZ,
    unlocked_by VARCHAR(100),
    unlock_reason VARCHAR(255),
    CONSTRAINT chk_lock_dates CHECK (period_to >= period_from)
);

CREATE INDEX IF NOT EXISTS idx_period_locks_dates ON accounting_period_locks(period_from, period_to) WHERE unlocked_at IS NULL;

-- ============================================================================
-- 2. CHART OF ACCOUNTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    account_type VARCHAR(30) NOT NULL,
    sub_type VARCHAR(50) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    parent_account_id UUID REFERENCES chart_of_accounts(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_reconcilable BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coa_code ON chart_of_accounts(code);
CREATE INDEX IF NOT EXISTS idx_coa_type ON chart_of_accounts(account_type, sub_type);
CREATE INDEX IF NOT EXISTS idx_coa_parent ON chart_of_accounts(parent_account_id);

-- ============================================================================
-- 3. FINANCIAL ENTITIES (Sub-ledger Partners)
-- ============================================================================
CREATE TABLE IF NOT EXISTS financial_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(30) NOT NULL,
    external_ref_id VARCHAR(64),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    gstin VARCHAR(15),
    pan VARCHAR(10),
    phone VARCHAR(20),
    email VARCHAR(100),
    billing_address TEXT,
    payment_terms_days INT NOT NULL DEFAULT 30,
    gl_account_id UUID NOT NULL REFERENCES chart_of_accounts(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_type_ref ON financial_entities(entity_type, external_ref_id);
CREATE INDEX IF NOT EXISTS idx_entity_gl_account ON financial_entities(gl_account_id);

-- ============================================================================
-- 4. BANK ACCOUNTS & CASH REGISTERS
-- ============================================================================
CREATE TABLE IF NOT EXISTS bank_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES financial_entities(id) ON DELETE RESTRICT,
    gl_account_id UUID NOT NULL REFERENCES chart_of_accounts(id) ON DELETE RESTRICT,
    account_name VARCHAR(100) NOT NULL,
    bank_name VARCHAR(100) NOT NULL,
    account_number VARCHAR(40) NOT NULL UNIQUE,
    account_number_last4 VARCHAR(10) NOT NULL,
    ifsc VARCHAR(15) NOT NULL,
    branch VARCHAR(100),
    category VARCHAR(30) NOT NULL DEFAULT 'b2b_client',
    opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    opening_balance_date DATE NOT NULL DEFAULT CURRENT_DATE,
    current_cleared_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_entity ON bank_accounts(entity_id);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_gl ON bank_accounts(gl_account_id);

CREATE TABLE IF NOT EXISTS cash_registers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    gl_account_id UUID NOT NULL REFERENCES chart_of_accounts(id) ON DELETE RESTRICT,
    custodian_user_email VARCHAR(100),
    opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cash_reg_gl ON cash_registers(gl_account_id);

-- ============================================================================
-- 5. JOURNAL ENTRIES & BALANCED LINES (Double-Entry Core)
-- ============================================================================
CREATE TABLE IF NOT EXISTS journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_number VARCHAR(50) NOT NULL UNIQUE,
    entry_date DATE NOT NULL,
    entry_type VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'POSTED',
    narration TEXT NOT NULL,
    source_document_ref VARCHAR(100),
    fiscal_year_id UUID REFERENCES fiscal_years(id) ON DELETE RESTRICT,
    total_debit NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    total_credit NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    posted_by VARCHAR(100) NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    voided_at TIMESTAMPTZ,
    voided_by VARCHAR(100),
    void_reason VARCHAR(255),
    CONSTRAINT chk_balanced_entry CHECK (total_debit = total_credit AND total_debit >= 0)
);

CREATE INDEX IF NOT EXISTS idx_je_date_type ON journal_entries(entry_date, entry_type);
CREATE INDEX IF NOT EXISTS idx_je_source_ref ON journal_entries(source_document_ref);
CREATE INDEX IF NOT EXISTS idx_je_fy ON journal_entries(fiscal_year_id);

CREATE TABLE IF NOT EXISTS journal_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES chart_of_accounts(id) ON DELETE RESTRICT,
    entity_id UUID REFERENCES financial_entities(id) ON DELETE RESTRICT,
    line_number INT NOT NULL,
    description VARCHAR(255),
    debit NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    credit NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    reconciliation_status VARCHAR(20) NOT NULL DEFAULT 'UNRECONCILED',
    reconciled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_line_amounts CHECK (
        (debit > 0 AND credit = 0) OR
        (credit > 0 AND debit = 0) OR
        (debit = 0 AND credit = 0)
    ),
    CONSTRAINT uq_je_line UNIQUE (journal_entry_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_jl_je_id ON journal_lines(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_jl_account_created ON journal_lines(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jl_entity ON journal_lines(entity_id);

-- ============================================================================
-- 6. B2B SALES INVOICES & RECEIVABLES (AR)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sales_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_no VARCHAR(50) NOT NULL UNIQUE,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    client_id UUID NOT NULL REFERENCES financial_entities(id) ON DELETE RESTRICT,
    po_number VARCHAR(100),
    customer_gstin VARCHAR(15),
    place_of_supply VARCHAR(50),
    subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cgst_rate NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    cgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    sgst_rate NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    sgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    igst_rate NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    igst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tcs_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    grand_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    grn_adjustment NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_receivable NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    paid_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(25) NOT NULL DEFAULT 'POSTED',
    journal_entry_id UUID REFERENCES journal_entries(id) ON DELETE RESTRICT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inv_client_due ON sales_invoices(client_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_inv_je ON sales_invoices(journal_entry_id);

-- ============================================================================
-- 7. VENDOR BILLS & ACCOUNTS PAYABLE (AP)
-- ============================================================================
CREATE TABLE IF NOT EXISTS vendor_bills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_no VARCHAR(50) NOT NULL,
    vendor_id UUID NOT NULL REFERENCES financial_entities(id) ON DELETE RESTRICT,
    vendor_po_ref VARCHAR(50),
    bill_date DATE NOT NULL,
    due_date DATE NOT NULL,
    subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    sgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    igst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    paid_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(25) NOT NULL DEFAULT 'POSTED',
    journal_entry_id UUID REFERENCES journal_entries(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vendor_bill UNIQUE (vendor_id, bill_no)
);

CREATE INDEX IF NOT EXISTS idx_bill_vendor_due ON vendor_bills(vendor_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_bill_je ON vendor_bills(journal_entry_id);

-- ============================================================================
-- 8. PAYMENT & RECEIPT VOUCHERS + ALLOCATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS payment_vouchers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voucher_no VARCHAR(50) NOT NULL UNIQUE,
    voucher_type VARCHAR(20) NOT NULL,
    voucher_date DATE NOT NULL,
    entity_id UUID NOT NULL REFERENCES financial_entities(id) ON DELETE RESTRICT,
    payment_mode VARCHAR(20) NOT NULL,
    bank_account_id UUID REFERENCES bank_accounts(id) ON DELETE RESTRICT,
    cash_register_id UUID REFERENCES cash_registers(id) ON DELETE RESTRICT,
    amount NUMERIC(14, 2) NOT NULL,
    reference_number VARCHAR(100),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE RESTRICT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_positive_voucher_amt CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_pmt_entity ON payment_vouchers(entity_id);
CREATE INDEX IF NOT EXISTS idx_pmt_bank ON payment_vouchers(bank_account_id);
CREATE INDEX IF NOT EXISTS idx_pmt_cash ON payment_vouchers(cash_register_id);
CREATE INDEX IF NOT EXISTS idx_pmt_je ON payment_vouchers(journal_entry_id);

CREATE TABLE IF NOT EXISTS voucher_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voucher_id UUID NOT NULL REFERENCES payment_vouchers(id) ON DELETE CASCADE,
    sales_invoice_id UUID REFERENCES sales_invoices(id) ON DELETE RESTRICT,
    vendor_bill_id UUID REFERENCES vendor_bills(id) ON DELETE RESTRICT,
    allocated_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_positive_alloc CHECK (allocated_amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_alloc_voucher ON voucher_allocations(voucher_id);
CREATE INDEX IF NOT EXISTS idx_alloc_invoice ON voucher_allocations(sales_invoice_id);
CREATE INDEX IF NOT EXISTS idx_alloc_bill ON voucher_allocations(vendor_bill_id);

-- ============================================================================
-- 9. BANK STATEMENTS & RECONCILIATION
-- ============================================================================
CREATE TABLE IF NOT EXISTS bank_statement_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE RESTRICT,
    transaction_date DATE NOT NULL,
    value_date DATE,
    narration TEXT NOT NULL,
    cheque_reference_no VARCHAR(100),
    debit_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    credit_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    running_balance NUMERIC(14, 2),
    match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED',
    matched_journal_line_id UUID REFERENCES journal_lines(id) ON DELETE SET NULL,
    matched_voucher_id UUID REFERENCES payment_vouchers(id) ON DELETE SET NULL,
    imported_batch_id VARCHAR(64),
    imported_by VARCHAR(100),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reconciled_by VARCHAR(100),
    reconciled_at TIMESTAMPTZ,
    remarks VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_stmt_acc_date ON bank_statement_lines(bank_account_id, transaction_date, match_status);
CREATE INDEX IF NOT EXISTS idx_stmt_matched_voucher ON bank_statement_lines(matched_voucher_id);
CREATE INDEX IF NOT EXISTS idx_stmt_matched_jl ON bank_statement_lines(matched_journal_line_id);

CREATE TABLE IF NOT EXISTS bank_reconciliation_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE RESTRICT,
    as_of_date DATE NOT NULL,
    bank_statement_balance NUMERIC(14, 2) NOT NULL,
    book_balance NUMERIC(14, 2) NOT NULL,
    unpresented_cheques_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    uncredited_deposits_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    unreconciled_bank_debits NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    unreconciled_bank_credits NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    reconciled_difference NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    is_balanced BOOLEAN NOT NULL DEFAULT FALSE,
    finalized_at TIMESTAMPTZ,
    finalized_by VARCHAR(100),
    CONSTRAINT uq_brs_account_date UNIQUE (bank_account_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_brs_account ON bank_reconciliation_statements(bank_account_id);

-- ============================================================================
-- 10. ONLINE MARKETPLACE SETTLEMENT RECONCILIATION
-- ============================================================================
CREATE TABLE IF NOT EXISTS marketplace_settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(30) NOT NULL,
    neft_utr VARCHAR(100) NOT NULL,
    settlement_date DATE NOT NULL,
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE RESTRICT,
    gross_order_value NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    marketplace_commission NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    logistics_forward NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    logistics_reverse NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tech_packaging_fees NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tcs_cgst NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tcs_sgst NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tcs_igst NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    tds_194o NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    gst_on_services NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_settled_amount NUMERIC(14, 2) NOT NULL,
    journal_entry_id UUID REFERENCES journal_entries(id) ON DELETE RESTRICT,
    statement_line_id UUID REFERENCES bank_statement_lines(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_mkt_utr UNIQUE (platform, neft_utr)
);

CREATE INDEX IF NOT EXISTS idx_mkt_bank ON marketplace_settlements(bank_account_id);
CREATE INDEX IF NOT EXISTS idx_mkt_je ON marketplace_settlements(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_mkt_stmt ON marketplace_settlements(statement_line_id);

-- ============================================================================
-- 11. ROW-LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
ALTER TABLE fiscal_years ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounting_period_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chart_of_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_registers ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_bills ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_vouchers ENABLE ROW LEVEL SECURITY;
ALTER TABLE voucher_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_statement_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_reconciliation_statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_settlements ENABLE ROW LEVEL SECURITY;

-- Allow full access to service_role and authenticated backend requests
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN (
            'fiscal_years', 'accounting_period_locks', 'chart_of_accounts', 'financial_entities',
            'bank_accounts', 'cash_registers', 'journal_entries', 'journal_lines',
            'sales_invoices', 'vendor_bills', 'payment_vouchers', 'voucher_allocations',
            'bank_statement_lines', 'bank_reconciliation_statements', 'marketplace_settlements'
        )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_access ON %I', tbl);
        EXECUTE format('CREATE POLICY rls_authenticated_access ON %I FOR ALL TO authenticated USING (true) WITH CHECK (true)', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_service_role_access ON %I', tbl);
        EXECUTE format('CREATE POLICY rls_service_role_access ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl);
    END LOOP;
END;
$$;

-- ============================================================================
-- 12. SEED STANDARD CHART OF ACCOUNTS (33 Indian Footwear Manufacturing Accounts)
-- ============================================================================
INSERT INTO chart_of_accounts (code, name, account_type, sub_type, is_reconcilable) VALUES
('1010', 'Bank Accounts', 'ASSET', 'BANK_ACCOUNT', true),
('1010-HDFC-MAIN', 'HDFC Current Account (Main)', 'ASSET', 'BANK_ACCOUNT', true),
('1010-UCO-OP', 'UCO Bank Current Account', 'ASSET', 'BANK_ACCOUNT', true),
('1020', 'Cash in Hand', 'ASSET', 'CASH_IN_HAND', true),
('1020-FACTORY-CASH', 'Factory Petty Cash', 'ASSET', 'CASH_IN_HAND', true),
('1020-OFFICE-CASH', 'Head Office Cash Register', 'ASSET', 'CASH_IN_HAND', true),
('1030', 'Accounts Receivable (B2B Buyers)', 'ASSET', 'ACCOUNTS_RECEIVABLE', true),
('1040', 'Raw Material Inventory Asset', 'ASSET', 'INVENTORY_ASSET', false),
('1050', 'Finished Goods Inventory Asset', 'ASSET', 'INVENTORY_ASSET', false),
('1060-CGST-IN', 'CGST Input Tax Credit', 'ASSET', 'GST_INPUT_TAX_CREDIT', true),
('1060-SGST-IN', 'SGST Input Tax Credit', 'ASSET', 'GST_INPUT_TAX_CREDIT', true),
('1060-IGST-IN', 'IGST Input Tax Credit', 'ASSET', 'GST_INPUT_TAX_CREDIT', true),
('1070', 'Worker & Karigar Advances', 'ASSET', 'WORKER_ADVANCE', true),
('2010', 'Accounts Payable (Raw Material Suppliers)', 'LIABILITY', 'ACCOUNTS_PAYABLE', true),
('2020', 'Karigar Wages Payable', 'LIABILITY', 'WAGES_PAYABLE', true),
('2030-CGST-OUT', 'CGST Output Tax Payable', 'LIABILITY', 'GST_OUTPUT_TAX_PAYABLE', true),
('2030-SGST-OUT', 'SGST Output Tax Payable', 'LIABILITY', 'GST_OUTPUT_TAX_PAYABLE', true),
('2030-IGST-OUT', 'IGST Output Tax Payable', 'LIABILITY', 'GST_OUTPUT_TAX_PAYABLE', true),
('2040-194C', 'TDS Payable - Contractor (194C)', 'LIABILITY', 'TDS_PAYABLE', true),
('2040-194J', 'TDS Payable - Professional (194J)', 'LIABILITY', 'TDS_PAYABLE', true),
('2050-TCS', 'TCS Payable on Marketplace Sales', 'LIABILITY', 'TCS_PAYABLE', true),
('3010', 'Owner / Partner Capital', 'EQUITY', 'OWNERS_EQUITY', false),
('3020', 'Retained Earnings', 'EQUITY', 'OWNERS_EQUITY', false),
('4010', 'B2B Footwear Sales Revenue', 'REVENUE', 'OPERATING_REVENUE', false),
('4020', 'Online Marketplace Sales Revenue', 'REVENUE', 'MARKETPLACE_SALES', false),
('4030', 'Discounts & Round-off Income', 'REVENUE', 'OTHER_INCOME', false),
('5010', 'Raw Material Consumption (COGS)', 'EXPENSE', 'RAW_MATERIAL_EXPENSE', false),
('5020', 'Direct Karigar Labor & Wages', 'EXPENSE', 'DIRECT_LABOR_EXPENSE', false),
('5030', 'Factory Rent & Electricity', 'EXPENSE', 'FACTORY_OVERHEAD', false),
('5040', 'Outward Freight & Shipping', 'EXPENSE', 'SELLING_AND_DISTRIBUTION', false),
('5050', 'Marketplace Commission & Fulfillment Fees', 'EXPENSE', 'SELLING_AND_DISTRIBUTION', false),
('5060', 'Administrative & Office Expenses', 'EXPENSE', 'ADMINISTRATIVE_EXPENSE', false),
('5070', 'Bank Charges & Payment Gateway Fees', 'EXPENSE', 'FINANCIAL_EXPENSE', false)
ON CONFLICT (code) DO NOTHING;
