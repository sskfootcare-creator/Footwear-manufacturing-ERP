-- ============================================================================
-- SSK FOOTWEAR ERP — BASELINE SEED DATA FOR SUPABASE
-- Conforms to DB-003 acceptance criteria for clean provisioning
-- ============================================================================

-- 1. Initial Fiscal Year (FY 2026-27: 2026-04-01 to 2027-03-31)
INSERT INTO fiscal_years (name, start_date, end_date, is_closed)
VALUES ('FY 2026-27', '2026-04-01', '2027-03-31', false)
ON CONFLICT (name) DO NOTHING;

-- 2. Baseline Financial Entities
DO $$
DECLARE
    ar_id UUID;
    ap_id UUID;
BEGIN
    SELECT id INTO ar_id FROM chart_of_accounts WHERE code = '1030' LIMIT 1;
    SELECT id INTO ap_id FROM chart_of_accounts WHERE code = '2010' LIMIT 1;

    IF ar_id IS NOT NULL THEN
        INSERT INTO financial_entities (entity_type, code, name, payment_terms_days, gl_account_id)
        VALUES ('CUSTOMER', 'CUST-DEFAULT', 'Direct Cash / B2B Counter Buyer', 0, ar_id)
        ON CONFLICT (code) DO NOTHING;
    END IF;

    IF ap_id IS NOT NULL THEN
        INSERT INTO financial_entities (entity_type, code, name, payment_terms_days, gl_account_id)
        VALUES ('VENDOR', 'VEND-DEFAULT', 'Primary Leather & Raw Material Vendor', 30, ap_id)
        ON CONFLICT (code) DO NOTHING;
    END IF;
END $$;
