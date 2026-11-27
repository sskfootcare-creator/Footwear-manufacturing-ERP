-- Migration: Add invoice product lines & monthly salaried staff payroll tables
-- Date: 2026-11-27

-- 1. Add line_items JSONB column to sales_invoices for multi-line product tracking
ALTER TABLE IF EXISTS public.sales_invoices
    ADD COLUMN IF NOT EXISTS line_items JSONB DEFAULT '[]'::jsonb;

-- 2. Create normalized sales_invoice_lines table with GSTN & HSN per product line
CREATE TABLE IF NOT EXISTS public.sales_invoice_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES public.sales_invoices(id) ON DELETE CASCADE,
    invoice_no VARCHAR(50) NOT NULL,
    line_number INT NOT NULL DEFAULT 1,
    po_number VARCHAR(100),
    customer_gstin VARCHAR(15) DEFAULT '',
    style_code VARCHAR(100),
    color VARCHAR(80),
    size VARCHAR(40),
    hsn_code VARCHAR(20) DEFAULT '6403',
    quantity NUMERIC(12, 2) NOT NULL DEFAULT 0,
    unit_price NUMERIC(14, 2) NOT NULL DEFAULT 0,
    amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sales_inv_line UNIQUE (invoice_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_sil_invoice_id ON public.sales_invoice_lines(invoice_id);
CREATE INDEX IF NOT EXISTS idx_sil_invoice_no ON public.sales_invoice_lines(invoice_no);

-- 3. Monthly Salaried Staff Payroll Ledger tables
CREATE TABLE IF NOT EXISTS public.staff_employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mongo_id VARCHAR(50) UNIQUE,
    name VARCHAR(150) NOT NULL,
    role VARCHAR(100) NOT NULL,
    department VARCHAR(100) DEFAULT 'Operations',
    monthly_salary NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    phone VARCHAR(30),
    joining_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.staff_holidays (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    holiday_date DATE NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    holiday_type VARCHAR(50) DEFAULT 'Public Holiday',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.staff_attendance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id UUID NOT NULL REFERENCES public.staff_employees(id) ON DELETE CASCADE,
    attendance_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'present',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_staff_att_date UNIQUE (staff_id, attendance_date)
);

CREATE TABLE IF NOT EXISTS public.staff_salary_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id UUID NOT NULL REFERENCES public.staff_employees(id) ON DELETE CASCADE,
    month VARCHAR(7) NOT NULL,
    gross_salary NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    deductions NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    bonus NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_paid NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    payment_mode VARCHAR(30) DEFAULT 'bank',
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

-- Enable RLS with service_role & authenticated access
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN (
            'sales_invoice_lines', 'staff_employees', 'staff_holidays', 'staff_attendance', 'staff_salary_payments'
        )
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_access ON public.%I', tbl);
        EXECUTE format('CREATE POLICY rls_authenticated_access ON public.%I FOR ALL TO authenticated USING (true) WITH CHECK (true)', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_service_role_access ON public.%I', tbl);
        EXECUTE format('CREATE POLICY rls_service_role_access ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl);
    END LOOP;
END;
$$;
