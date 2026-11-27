-- ============================================================================
-- FINANCIAL INTEGRITY TRIGGERS, TRANSACTIONAL RPCs, AND RESTRICTED RLS
-- ============================================================================

-- 1. Enforce that journal_lines sums match journal_entries header totals
CREATE OR REPLACE FUNCTION public.enforce_journal_entry_line_balance()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    target_je_id UUID;
    hdr RECORD;
    line_debit NUMERIC(14, 2);
    line_credit NUMERIC(14, 2);
    line_count INT;
BEGIN
    IF TG_TABLE_NAME = 'journal_entries' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        target_je_id := NEW.id;
    ELSE
        target_je_id := COALESCE(NEW.journal_entry_id, OLD.journal_entry_id);
    END IF;

    SELECT id, total_debit, total_credit, status
    INTO hdr
    FROM public.journal_entries
    WHERE id = target_je_id;

    -- If header was deleted (cascade), nothing left to validate
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT
        COALESCE(SUM(debit), 0.00),
        COALESCE(SUM(credit), 0.00),
        COUNT(*)
    INTO line_debit, line_credit, line_count
    FROM public.journal_lines
    WHERE journal_entry_id = target_je_id;

    IF line_count = 0 THEN
        RAISE EXCEPTION 'Journal entry % must have at least one journal line', target_je_id;
    END IF;

    IF ABS(line_debit - line_credit) > 0.01 THEN
        RAISE EXCEPTION 'Journal entry % lines are unbalanced: debit (%) != credit (%)',
            target_je_id, line_debit, line_credit;
    END IF;

    IF ABS(line_debit - hdr.total_debit) > 0.01 OR ABS(line_credit - hdr.total_credit) > 0.01 THEN
        RAISE EXCEPTION 'Journal entry % header totals (%/%) do not match line sums (%/%)',
            target_je_id, hdr.total_debit, hdr.total_credit, line_debit, line_credit;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_je_balance_on_entry ON public.journal_entries;
CREATE CONSTRAINT TRIGGER trg_je_balance_on_entry
AFTER INSERT OR UPDATE ON public.journal_entries
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.enforce_journal_entry_line_balance();

DROP TRIGGER IF EXISTS trg_je_balance_on_lines ON public.journal_lines;
CREATE CONSTRAINT TRIGGER trg_je_balance_on_lines
AFTER INSERT OR UPDATE OR DELETE ON public.journal_lines
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.enforce_journal_entry_line_balance();

-- 2. Transactional RPC: Atomic Sales Invoice Sync (JE + JE Lines + Invoice + Invoice Lines)
CREATE OR REPLACE FUNCTION public.sync_sales_invoice_tx(
    p_je JSONB,
    p_je_lines JSONB,
    p_invoice JSONB,
    p_invoice_lines JSONB DEFAULT '[]'::JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_inv_id UUID;
    v_result JSONB;
BEGIN
    INSERT INTO public.journal_entries (
        id, entry_number, entry_date, entry_type, status, narration,
        source_document_ref, total_debit, total_credit, posted_by, posted_at
    )
    VALUES (
        (p_je->>'id')::UUID,
        p_je->>'entry_number',
        (p_je->>'entry_date')::DATE,
        COALESCE(p_je->>'entry_type', 'SALES_INVOICE'),
        COALESCE(p_je->>'status', 'POSTED'),
        COALESCE(p_je->>'narration', ''),
        p_je->>'source_document_ref',
        COALESCE((p_je->>'total_debit')::NUMERIC(14, 2), 0.00),
        COALESCE((p_je->>'total_credit')::NUMERIC(14, 2), 0.00),
        COALESCE(p_je->>'posted_by', 'system'),
        COALESCE((p_je->>'posted_at')::TIMESTAMPTZ, NOW())
    )
    ON CONFLICT (id) DO UPDATE SET
        entry_number = EXCLUDED.entry_number,
        entry_date = EXCLUDED.entry_date,
        entry_type = EXCLUDED.entry_type,
        status = EXCLUDED.status,
        narration = EXCLUDED.narration,
        source_document_ref = EXCLUDED.source_document_ref,
        total_debit = EXCLUDED.total_debit,
        total_credit = EXCLUDED.total_credit,
        posted_by = EXCLUDED.posted_by,
        posted_at = EXCLUDED.posted_at;

    INSERT INTO public.journal_lines (
        id, journal_entry_id, account_id, entity_id, line_number,
        description, debit, credit, reconciliation_status
    )
    SELECT
        (l->>'id')::UUID,
        (l->>'journal_entry_id')::UUID,
        (l->>'account_id')::UUID,
        NULLIF(l->>'entity_id', '')::UUID,
        (l->>'line_number')::INT,
        l->>'description',
        COALESCE((l->>'debit')::NUMERIC(14, 2), 0.00),
        COALESCE((l->>'credit')::NUMERIC(14, 2), 0.00),
        COALESCE(l->>'reconciliation_status', 'RECONCILED')
    FROM jsonb_array_elements(p_je_lines) AS l
    ON CONFLICT (id) DO UPDATE SET
        account_id = EXCLUDED.account_id,
        entity_id = EXCLUDED.entity_id,
        line_number = EXCLUDED.line_number,
        description = EXCLUDED.description,
        debit = EXCLUDED.debit,
        credit = EXCLUDED.credit,
        reconciliation_status = EXCLUDED.reconciliation_status;

    v_inv_id := (p_invoice->>'id')::UUID;

    INSERT INTO public.sales_invoices (
        id, invoice_no, invoice_date, due_date, client_id, po_number,
        customer_gstin, place_of_supply, subtotal, cgst_rate, cgst_amount,
        sgst_rate, sgst_amount, igst_rate, igst_amount, grand_total,
        paid_amount, net_receivable, status, journal_entry_id, notes, line_items
    )
    VALUES (
        v_inv_id,
        p_invoice->>'invoice_no',
        (p_invoice->>'invoice_date')::DATE,
        (p_invoice->>'due_date')::DATE,
        (p_invoice->>'client_id')::UUID,
        COALESCE(p_invoice->>'po_number', 'DIRECT'),
        COALESCE(p_invoice->>'customer_gstin', ''),
        COALESCE(p_invoice->>'place_of_supply', '09-Uttar Pradesh'),
        COALESCE((p_invoice->>'subtotal')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'cgst_rate')::NUMERIC(5, 2), 0.00),
        COALESCE((p_invoice->>'cgst_amount')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'sgst_rate')::NUMERIC(5, 2), 0.00),
        COALESCE((p_invoice->>'sgst_amount')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'igst_rate')::NUMERIC(5, 2), 0.00),
        COALESCE((p_invoice->>'igst_amount')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'grand_total')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'paid_amount')::NUMERIC(14, 2), 0.00),
        COALESCE((p_invoice->>'net_receivable')::NUMERIC(14, 2), 0.00),
        COALESCE(p_invoice->>'status', 'POSTED'),
        (p_invoice->>'journal_entry_id')::UUID,
        COALESCE(p_invoice->>'notes', ''),
        COALESCE(p_invoice->'line_items', '[]'::JSONB)
    )
    ON CONFLICT (id) DO UPDATE SET
        invoice_no = EXCLUDED.invoice_no,
        invoice_date = EXCLUDED.invoice_date,
        due_date = EXCLUDED.due_date,
        client_id = EXCLUDED.client_id,
        po_number = EXCLUDED.po_number,
        customer_gstin = EXCLUDED.customer_gstin,
        place_of_supply = EXCLUDED.place_of_supply,
        subtotal = EXCLUDED.subtotal,
        cgst_rate = EXCLUDED.cgst_rate,
        cgst_amount = EXCLUDED.cgst_amount,
        sgst_rate = EXCLUDED.sgst_rate,
        sgst_amount = EXCLUDED.sgst_amount,
        igst_rate = EXCLUDED.igst_rate,
        igst_amount = EXCLUDED.igst_amount,
        grand_total = EXCLUDED.grand_total,
        journal_entry_id = EXCLUDED.journal_entry_id,
        notes = EXCLUDED.notes,
        line_items = EXCLUDED.line_items;

    IF jsonb_array_length(COALESCE(p_invoice_lines, '[]'::JSONB)) > 0 THEN
        INSERT INTO public.sales_invoice_lines (
            id, invoice_id, invoice_no, line_number, po_number, customer_gstin,
            style_code, color, size, hsn_code, quantity, unit_price, amount
        )
        SELECT
            (il->>'id')::UUID,
            (il->>'invoice_id')::UUID,
            il->>'invoice_no',
            (il->>'line_number')::INT,
            COALESCE(il->>'po_number', 'DIRECT'),
            COALESCE(il->>'customer_gstin', ''),
            COALESCE(il->>'style_code', ''),
            COALESCE(il->>'color', ''),
            COALESCE(il->>'size', ''),
            COALESCE(il->>'hsn_code', '6403'),
            COALESCE((il->>'quantity')::NUMERIC(14, 2), 0.00),
            COALESCE((il->>'unit_price')::NUMERIC(14, 2), 0.00),
            COALESCE((il->>'amount')::NUMERIC(14, 2), 0.00)
        FROM jsonb_array_elements(p_invoice_lines) AS il
        ON CONFLICT (id) DO UPDATE SET
            invoice_no = EXCLUDED.invoice_no,
            line_number = EXCLUDED.line_number,
            po_number = EXCLUDED.po_number,
            customer_gstin = EXCLUDED.customer_gstin,
            style_code = EXCLUDED.style_code,
            color = EXCLUDED.color,
            size = EXCLUDED.size,
            hsn_code = EXCLUDED.hsn_code,
            quantity = EXCLUDED.quantity,
            unit_price = EXCLUDED.unit_price,
            amount = EXCLUDED.amount;
    END IF;

    SELECT to_jsonb(si) INTO v_result FROM public.sales_invoices si WHERE si.id = v_inv_id;
    RETURN v_result;
END;
$$;

-- 3. Transactional RPC: Idempotent Payment Sync (derives paid_amount from allocations)
CREATE OR REPLACE FUNCTION public.sync_invoice_payment_tx(
    p_je JSONB,
    p_je_lines JSONB,
    p_voucher JSONB,
    p_allocations JSONB DEFAULT '[]'::JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_voucher_id UUID;
    v_inv_id UUID;
    v_total_paid NUMERIC(14, 2);
    v_gt NUMERIC(14, 2);
    v_net NUMERIC(14, 2);
    v_result JSONB;
BEGIN
    INSERT INTO public.journal_entries (
        id, entry_number, entry_date, entry_type, status, narration,
        source_document_ref, total_debit, total_credit, posted_by, posted_at
    )
    VALUES (
        (p_je->>'id')::UUID,
        p_je->>'entry_number',
        (p_je->>'entry_date')::DATE,
        COALESCE(p_je->>'entry_type', 'RECEIPT'),
        COALESCE(p_je->>'status', 'POSTED'),
        COALESCE(p_je->>'narration', ''),
        p_je->>'source_document_ref',
        COALESCE((p_je->>'total_debit')::NUMERIC(14, 2), 0.00),
        COALESCE((p_je->>'total_credit')::NUMERIC(14, 2), 0.00),
        COALESCE(p_je->>'posted_by', 'system'),
        COALESCE((p_je->>'posted_at')::TIMESTAMPTZ, NOW())
    )
    ON CONFLICT (id) DO UPDATE SET
        entry_number = EXCLUDED.entry_number,
        entry_date = EXCLUDED.entry_date,
        entry_type = EXCLUDED.entry_type,
        status = EXCLUDED.status,
        narration = EXCLUDED.narration,
        source_document_ref = EXCLUDED.source_document_ref,
        total_debit = EXCLUDED.total_debit,
        total_credit = EXCLUDED.total_credit,
        posted_by = EXCLUDED.posted_by,
        posted_at = EXCLUDED.posted_at;

    INSERT INTO public.journal_lines (
        id, journal_entry_id, account_id, entity_id, line_number,
        description, debit, credit, reconciliation_status
    )
    SELECT
        (l->>'id')::UUID,
        (l->>'journal_entry_id')::UUID,
        (l->>'account_id')::UUID,
        NULLIF(l->>'entity_id', '')::UUID,
        (l->>'line_number')::INT,
        l->>'description',
        COALESCE((l->>'debit')::NUMERIC(14, 2), 0.00),
        COALESCE((l->>'credit')::NUMERIC(14, 2), 0.00),
        COALESCE(l->>'reconciliation_status', 'UNRECONCILED')
    FROM jsonb_array_elements(p_je_lines) AS l
    ON CONFLICT (id) DO UPDATE SET
        account_id = EXCLUDED.account_id,
        entity_id = EXCLUDED.entity_id,
        line_number = EXCLUDED.line_number,
        description = EXCLUDED.description,
        debit = EXCLUDED.debit,
        credit = EXCLUDED.credit,
        reconciliation_status = EXCLUDED.reconciliation_status;

    v_voucher_id := (p_voucher->>'id')::UUID;

    INSERT INTO public.payment_vouchers (
        id, voucher_no, voucher_type, voucher_date, entity_id,
        payment_mode, bank_account_id, amount, reference_number,
        journal_entry_id, notes
    )
    VALUES (
        v_voucher_id,
        p_voucher->>'voucher_no',
        COALESCE(p_voucher->>'voucher_type', 'RECEIPT'),
        (p_voucher->>'voucher_date')::DATE,
        (p_voucher->>'entity_id')::UUID,
        COALESCE(p_voucher->>'payment_mode', 'BANK_TRANSFER'),
        NULLIF(p_voucher->>'bank_account_id', '')::UUID,
        (p_voucher->>'amount')::NUMERIC(14, 2),
        COALESCE(p_voucher->>'reference_number', ''),
        (p_voucher->>'journal_entry_id')::UUID,
        COALESCE(p_voucher->>'notes', '')
    )
    ON CONFLICT (id) DO UPDATE SET
        voucher_no = EXCLUDED.voucher_no,
        voucher_date = EXCLUDED.voucher_date,
        entity_id = EXCLUDED.entity_id,
        payment_mode = EXCLUDED.payment_mode,
        bank_account_id = EXCLUDED.bank_account_id,
        amount = EXCLUDED.amount,
        reference_number = EXCLUDED.reference_number,
        journal_entry_id = EXCLUDED.journal_entry_id,
        notes = EXCLUDED.notes;

    IF jsonb_array_length(COALESCE(p_allocations, '[]'::JSONB)) > 0 THEN
        INSERT INTO public.voucher_allocations (
            id, voucher_id, sales_invoice_id, allocated_amount
        )
        SELECT
            (a->>'id')::UUID,
            (a->>'voucher_id')::UUID,
            (a->>'sales_invoice_id')::UUID,
            (a->>'allocated_amount')::NUMERIC(14, 2)
        FROM jsonb_array_elements(p_allocations) AS a
        ON CONFLICT (id) DO UPDATE SET
            allocated_amount = EXCLUDED.allocated_amount;

        -- Recompute paid_amount & net_receivable idempotently from voucher_allocations
        FOR v_inv_id IN
            SELECT DISTINCT (a->>'sales_invoice_id')::UUID
            FROM jsonb_array_elements(p_allocations) AS a
            WHERE NULLIF(a->>'sales_invoice_id', '') IS NOT NULL
        LOOP
            SELECT grand_total INTO v_gt FROM public.sales_invoices WHERE id = v_inv_id;
            IF FOUND THEN
                SELECT COALESCE(SUM(va.allocated_amount), 0.00)
                INTO v_total_paid
                FROM public.voucher_allocations va
                WHERE va.sales_invoice_id = v_inv_id;

                v_net := GREATEST(0.00, ROUND(v_gt - v_total_paid, 2));
                UPDATE public.sales_invoices
                SET
                    paid_amount = ROUND(v_total_paid, 2),
                    net_receivable = v_net,
                    status = CASE
                        WHEN v_net <= 0.01 THEN 'PAID'
                        WHEN v_total_paid > 0 THEN 'PARTIALLY_PAID'
                        ELSE 'POSTED'
                    END
                WHERE id = v_inv_id;
            END IF;
        END LOOP;
    END IF;

    SELECT to_jsonb(pv) INTO v_result FROM public.payment_vouchers pv WHERE pv.id = v_voucher_id;
    RETURN v_result;
END;
$$;

-- 4. Restrict RLS policies: remove unconditional authenticated FOR ALL USING(true)
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN (
            'fiscal_years', 'accounting_period_locks', 'chart_of_accounts', 'financial_entities',
            'bank_accounts', 'cash_registers', 'journal_entries', 'journal_lines',
            'sales_invoices', 'sales_invoice_lines', 'vendor_bills', 'payment_vouchers',
            'voucher_allocations', 'bank_statement_lines', 'bank_reconciliation_statements',
            'marketplace_settlements', 'staff_employees', 'staff_holidays',
            'staff_attendance', 'staff_salary_payments'
        )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_access ON %I', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_read ON %I', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_authenticated_write ON %I', tbl);
        EXECUTE format('DROP POLICY IF EXISTS rls_service_role_access ON %I', tbl);

        -- Service role (backend server) retains full access
        EXECUTE format('CREATE POLICY rls_service_role_access ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl);

        -- Authenticated users: read-only if assigned an ERP role; writes restricted to admin/accountant
        EXECUTE format(
            'CREATE POLICY rls_authenticated_read ON %I FOR SELECT TO authenticated USING (((select auth.jwt()) -> ''app_metadata'' ->> ''role'') IN (''admin'', ''accountant'', ''manager'', ''staff''))',
            tbl
        );
        EXECUTE format(
            'CREATE POLICY rls_authenticated_write ON %I FOR ALL TO authenticated USING (((select auth.jwt()) -> ''app_metadata'' ->> ''role'') IN (''admin'', ''accountant'')) WITH CHECK (((select auth.jwt()) -> ''app_metadata'' ->> ''role'') IN (''admin'', ''accountant''))',
            tbl
        );
    END LOOP;
END;
$$;
